"""
approval_watcher.py — Async Optimized (Silver Tier)
=====================================================
Watches /Approved for new .md files.
When detected: reads frontmatter, calls MCP directly via aiohttp with 3 retries.

Replaces slow subprocess → reasoning_loop.py --execute path.

Flow:
  File in /Approved
    → parse frontmatter (action_type, suggested_mcp_endpoint, payload fields)
    → call_mcp_with_retry(endpoint, payload)  [aiohttp, 3 attempts, exp back-off]
    → on success: move to /Done
    → on failure: move to /Done with ERROR note + log
"""

import os
import sys
import asyncio
import json
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

try:
    import aiohttp
    AIOHTTP_OK = True
except ImportError:
    AIOHTTP_OK = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_OK = True
except ImportError:
    WATCHDOG_OK = False

# ─── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent
APPROVED_DIR = BASE_DIR.parent / "Approved"
DONE_DIR     = BASE_DIR.parent / "Done"
LOGS_DIR     = BASE_DIR.parent / "Logs"
MCP_BASE_URL = "http://localhost:3001"

# ─── Retry config ──────────────────────────────────────────────────────────────
MAX_RETRIES  = 3
BASE_DELAY   = 5   # seconds; doubles each attempt: 5 → 10 → 20

# ─── Logging ───────────────────────────────────────────────────────────────────
def ts() -> str:
    return f"[APPROVAL] [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"

def log(msg: str):
    try:
        print(f"{ts()} {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"{ts()} {msg}".encode("ascii", errors="replace").decode("ascii"), flush=True)

# ─── Windows UTF-8 Fix ─────────────────────────────────────────────────────────
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Frontmatter Parser ────────────────────────────────────────────────────────
def parse_frontmatter(filepath: Path) -> tuple[dict, str]:
    """Manual YAML frontmatter parse (no PyYAML required)."""
    content = filepath.read_text(encoding="utf-8", errors="replace")
    frontmatter: dict = {}
    body = content

    if content.lstrip().startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw = parts[1].strip()
            body = parts[2].strip()
            for line in raw.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    frontmatter[k.strip()] = v.strip().strip("\"'")
    return frontmatter, body

# ─── Payload Builder ───────────────────────────────────────────────────────────
def build_payload(action_type: str, frontmatter: dict, body: str) -> dict:
    """
    Map frontmatter fields → MCP endpoint payload for each action type.
    """
    a = action_type.lower()

    if a == "email":
        return {
            "to":      frontmatter.get("target", frontmatter.get("to", "")),
            "subject": frontmatter.get("subject", "Re: Your message"),
            "body":    body,
        }
    elif a == "whatsapp":
        return {
            "contact": frontmatter.get("target", frontmatter.get("sender", "")),
            "message": body,
        }
    elif a in ("facebook_friend_request", "accept_friend"):
        return {
            "user_id": frontmatter.get("person", frontmatter.get("user_id", "next")),
        }
    elif a == "reject_friend":
        return {
            "user_id": frontmatter.get("person", frontmatter.get("user_id", "next")),
        }
    elif a in ("facebook_message", "facebook_notification"):
        return {
            "recipient": frontmatter.get("sender", frontmatter.get("target", "")),
            "message":   body,
        }
    elif a == "post_facebook":
        return {"content": body}
    else:
        # Generic fallback — send full body
        return {"content": body, "action": action_type}

# ─── MCP Caller (Async + Retry) ────────────────────────────────────────────────
async def call_mcp_with_retry(endpoint: str, payload: dict) -> dict:
    """
    POST to MCP server with 3 retry attempts and exponential back-off.
    Returns the JSON response dict on success.
    Raises on final failure.
    """
    if not AIOHTTP_OK:
        raise ImportError("aiohttp not installed — run: pip install aiohttp")

    url = f"{MCP_BASE_URL}/{endpoint.lstrip('/')}"
    last_err = None

    async with aiohttp.ClientSession() as session:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                log(f"  → MCP POST {url} (attempt {attempt}/{MAX_RETRIES})")
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as r:
                    data = await r.json()
                    if r.status == 429:
                        log(f"  ⚠ Rate limited by MCP server.")
                        raise aiohttp.ClientResponseError(r.request_info, r.history, status=429)
                    r.raise_for_status()
                    log(f"  ← MCP response ({r.status}): {json.dumps(data)[:120]}")
                    return data

            except Exception as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    wait = BASE_DELAY * (2 ** (attempt - 1))   # 5 → 10 → 20
                    log(f"  ✗ Attempt {attempt} failed: {e}. Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    log(f"  ✗ All {MAX_RETRIES} attempts failed: {e}")

    raise RuntimeError(f"MCP call to {endpoint} failed after {MAX_RETRIES} attempts: {last_err}")

# ─── Move to Done ──────────────────────────────────────────────────────────────
def move_to_done(filepath: Path, note: str = ""):
    DONE_DIR.mkdir(exist_ok=True)
    dest = DONE_DIR / filepath.name
    if dest.exists():
        dest.unlink()
    filepath.rename(dest)
    if note:
        with open(dest, "a", encoding="utf-8") as f:
            f.write(f"\n\n---\n*Processed at {datetime.now().isoformat()}. Note: {note}*\n")
    log(f"✓ Moved to Done: {filepath.name}")

# ─── Core: process one approved file ──────────────────────────────────────────
async def process_approved(filepath: Path):
    log(f"\n{'='*55}")
    log(f"✅ Approved: {filepath.name}")
    log(f"{'='*55}")

    # 1. Parse
    try:
        frontmatter, body = parse_frontmatter(filepath)
    except Exception as e:
        log(f"✗ Could not parse file: {e}")
        move_to_done(filepath, note=f"PARSE ERROR: {e}")
        return

    action_type  = frontmatter.get("type", "unknown")
    mcp_endpoint = frontmatter.get("suggested_mcp_endpoint", "")
    log(f"  Type: {action_type} | Endpoint: {mcp_endpoint}")

    # 2. Validate
    if not mcp_endpoint:
        log(f"  ⚠ No suggested_mcp_endpoint in frontmatter. Skipping MCP call.")
        move_to_done(filepath, note="No MCP endpoint — action logged only")
        return

    # 3. Build payload
    payload = build_payload(action_type, frontmatter, body)
    log(f"  Payload: {json.dumps(payload)[:120]}")

    # 4. Call MCP with retry
    try:
        result = await call_mcp_with_retry(mcp_endpoint, payload)
        success = result.get("success", True)  # default True if key missing
        if success:
            log(f"✓ MCP action succeeded: {json.dumps(result)[:80]}")
            move_to_done(filepath, note=f"SUCCESS: {json.dumps(result)[:80]}")
        else:
            log(f"⚠ MCP returned success=false: {result}")
            move_to_done(filepath, note=f"MCP FAILED: {result.get('error', 'unknown')}")
    except Exception as e:
        log(f"✗ MCP call failed: {e}")
        move_to_done(filepath, note=f"ERROR: {e}")

# ─── Watchdog Handler ─────────────────────────────────────────────────────────
if WATCHDOG_OK:
    class ApprovalHandler(FileSystemEventHandler):
        def __init__(self, loop: asyncio.AbstractEventLoop):
            self._loop = loop

        def on_created(self, event):
            if event.is_directory:
                return
            p = Path(event.src_path)
            if p.suffix == ".md":
                # Schedule coroutine on the async event loop from this sync thread
                asyncio.run_coroutine_threadsafe(process_approved(p), self._loop)

        def on_moved(self, event):
            """Also catch files moved INTO /Approved."""
            if event.is_directory:
                return
            p = Path(event.dest_path)
            if p.suffix == ".md" and str(APPROVED_DIR) in str(p):
                asyncio.run_coroutine_threadsafe(process_approved(p), self._loop)


# ─── Main ─────────────────────────────────────────────────────────────────────
async def async_main():
    APPROVED_DIR.mkdir(exist_ok=True)
    DONE_DIR.mkdir(exist_ok=True)

    log(f"👀 Watching {APPROVED_DIR} for approved actions...")
    log(f"   MCP server: {MCP_BASE_URL}")

    if not WATCHDOG_OK:
        log("⚠ watchdog not installed. Run: pip install watchdog")
        log("   Falling back to polling mode (5s interval)...")

        # Polling fallback
        seen: set[str] = set()
        while True:
            for md in APPROVED_DIR.glob("*.md"):
                if md.name not in seen:
                    seen.add(md.name)
                    await process_approved(md)
            await asyncio.sleep(5)
        return

    # Watchdog mode
    loop = asyncio.get_event_loop()
    handler  = ApprovalHandler(loop)
    observer = Observer()
    observer.schedule(handler, str(APPROVED_DIR), recursive=False)
    observer.start()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log("💤 Stopped.")
    finally:
        observer.stop()
        observer.join()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log("\n👋 Approval watcher stopped.")
    except Exception as e:
        log(f"✗ Fatal: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
