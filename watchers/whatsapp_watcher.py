"""
WhatsApp Watcher — Async Optimized (Silver Tier)
=================================================
Polls the local MCP server (/check-whatsapp) every 30 seconds.
On detection: saves a rich .md to /Needs_Action and spawns reasoning_loop.py.

Optimizations:
  - asyncio + aiohttp for non-blocking HTTP polling
  - 30-second rate limit between checks
  - In-memory sender-cache (avoids duplicate .md files per session)
  - 3-attempt retry with exponential back-off on MCP failures
  - Timestamped logging throughout

Requirements:
  pip install aiohttp

Usage:
  python whatsapp_watcher.py       # continuous daemon
"""

import asyncio
import aiohttp
import os
import json
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import subprocess
from asyncio import subprocess as aio_subprocess  # noqa: F401 — used via create_subprocess_exec
from datetime import datetime
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────
MCP_BASE_URL     = "http://localhost:3001"
BASE_DIR         = Path(__file__).resolve().parent
NEEDS_ACTION_DIR = BASE_DIR.parent / 'Needs_Action'
REASONING_LOOP   = BASE_DIR / 'reasoning_loop.py'
LOG_PREFIX       = "[WHATSAPP]"

POLL_INTERVAL    = 30    # seconds between polls
MAX_RETRIES      = 3     # retry attempts on MCP failure
RETRY_DELAY      = 5     # base back-off delay (seconds)

# Cache: set of (sender, timestamp_minute) tuples to avoid burst duplicates
_processed_cache: set = set()


def ts() -> str:
    return f"{LOG_PREFIX} [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"


# ─── Retry Helper ─────────────────────────────────────────────────────────────

async def with_retry(coro_fn, *args, attempts=MAX_RETRIES, delay=RETRY_DELAY):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_fn(*args)
        except Exception as exc:
            last_exc = exc
            wait = delay * (2 ** (attempt - 1))
            print(f"{ts()} ⚠ Attempt {attempt}/{attempts} failed: {exc}. Retry in {wait}s...")
            await asyncio.sleep(wait)
    print(f"{ts()} ✗ All {attempts} attempts failed. Last: {last_exc}")
    return None


# ─── MCP Poll ─────────────────────────────────────────────────────────────────

async def fetch_whatsapp_data(session: aiohttp.ClientSession) -> dict | None:
    """Call MCP /check-whatsapp and return parsed JSON."""
    url = f"{MCP_BASE_URL}/check-whatsapp"
    print(f"{ts()} Polling MCP: {url}")
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
        resp.raise_for_status()
        return await resp.json()


# ─── .md File Creation ────────────────────────────────────────────────────────

def create_task_md(msg: dict) -> Path | None:
    """Create a rich Markdown task file in /Needs_Action."""
    try:
        NEEDS_ACTION_DIR.mkdir(exist_ok=True)

        sender    = msg.get('sender', 'Unknown')
        count     = msg.get('count', 1)
        preview   = msg.get('preview', '(No preview available)')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        now_iso   = datetime.now().isoformat()

        safe_sender = "".join(c if c.isalnum() or c in '-_' else '_' for c in sender[:30])
        filename    = f"{timestamp}_WhatsApp_{safe_sender}.md"
        filepath    = NEEDS_ACTION_DIR / filename

        content = f"""---
type: whatsapp_reply
sender: "{sender}"
unread_count: {count}
received: "{now_iso}"
priority: high
status: pending
---

## 💬 New WhatsApp Message

| Field          | Value |
|----------------|-------|
| **Sender**     | {sender} |
| **Unread**     | {count} message(s) |
| **Detected**   | {now_iso} |

## Message Preview

> {preview}

---

## 🤖 AI Instruction

You have an unread WhatsApp message from **{sender}**.

Please:
1. Review the message context above.
2. Draft a short, friendly, professional reply.
3. Submit for approval.

**Suggested Reply Template:**
> Hi {sender}! Thanks for your message. [Your reply here]

**MCP Action:** To send, use:
```
POST /send-whatsapp  {{ "contact": "{sender}", "message": "..." }}
```

---
*Detected by WhatsApp Watcher at {now_iso}*
"""

        filepath.write_text(content, encoding='utf-8')
        print(f"{ts()} ✓ Created: {filename}")
        return filepath

    except Exception as exc:
        print(f"{ts()} ✗ Failed to create .md: {exc}")
        return None


# ─── Trigger Reasoning ────────────────────────────────────────────────────────

async def trigger_reasoning(filepath: Path):
    """Spawn reasoning_loop.py asynchronously."""
    if not REASONING_LOOP.exists():
        print(f"{ts()} ⚠ reasoning_loop.py not found at {REASONING_LOOP}")
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(REASONING_LOOP), str(filepath),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"{ts()} 🧠 Triggered reasoning_loop.py (PID {proc.pid}) for {filepath.name}")
        asyncio.ensure_future(_wait_proc(proc, filepath.name))
    except Exception as exc:
        print(f"{ts()} ✗ Failed to spawn reasoning_loop.py: {exc}")


async def _wait_proc(proc, name: str):
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        print(f"{ts()} ✓ reasoning_loop done for {name}")
    else:
        print(f"{ts()} ✗ reasoning_loop error for {name}: {stderr.decode()[:200]}")


# ─── History & Status Helpers ─────────────────────────────────────────────────

HISTORY_FILE = BASE_DIR / "whatsapp_history.json"
STATUS_FILE  = BASE_DIR / "status_whatsapp.json"

def update_heartbeat(status="online", extra: dict = None):
    try:
        data = {
            "status": status,
            "last_active": datetime.now().isoformat(),
            "pid": os.getpid()
        }
        if extra:
            data.update(extra)
        STATUS_FILE.write_text(json.dumps(data, indent=2))
    except: pass


def sync_history(chats: list) -> bool:
    """
    Save chats from MCP to whatsapp_history.json in dashboard-friendly format.
    Returns True if new items were added.
    """
    try:
        # Load current history
        current = []
        if HISTORY_FILE.exists():
            try:
                current = json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
            except: pass

        # Build a set of existing sender keys for dedup
        existing_senders = {e.get('sender', '') for e in current}

        now_iso = datetime.now().isoformat()
        new_entries = []
        for chat in chats:
            sender  = chat.get('sender', 'Unknown')
            preview = chat.get('preview', '')
            count   = chat.get('count', 0)

            entry = {
                "id":        f"wa_{sender}_{datetime.now().strftime('%Y%m%d%H%M')}",
                "service":   "whatsapp",
                "type":      "message",
                "sender":    sender,
                "preview":   preview,
                "text":      preview,
                "subject":   f"WhatsApp from {sender}",
                "unread":    count > 0,
                "count":     count,
                "timestamp": now_iso,
            }
            new_entries.append(entry)

        if not new_entries:
            return False

        # Merge: new data replaces old entries for same senders (keeps latest)
        sender_map = {e.get('sender', ''): e for e in current}
        for e in new_entries:
            sender_map[e['sender']] = e

        merged = list(sender_map.values())
        # Sort by unread first, then by timestamp
        merged.sort(key=lambda x: (not x.get('unread', False), x.get('timestamp', '')), reverse=False)
        merged = merged[:50]

        HISTORY_FILE.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
        print(f"{ts()} ✓ History synced: {len(merged)} chats ({sum(1 for c in merged if c.get('unread'))} unread)")
        return True

    except Exception as e:
        print(f"{ts()} ⚠ History sync failed: {e}")
        return False


async def check_whatsapp(session: aiohttp.ClientSession):
    """Run one WhatsApp poll cycle with retry."""

    async def _do_check():
        data = await fetch_whatsapp_data(session)

        if not data:
            update_heartbeat("offline")
            return

        remote_status = data.get('status', 'offline')
        chats = data.get('new_messages', [])

        # Always update heartbeat with chat count
        update_heartbeat(remote_status, {"chat_count": len(chats)})

        if remote_status != 'online':
            print(f"{ts()} WhatsApp status: {remote_status}")
            return

        print(f"{ts()} WhatsApp online — {len(chats)} chat(s) visible")

        # ── ALWAYS sync history (shows all chats on dashboard) ──
        history_updated = sync_history(chats)

        # ── Always notify backend to refresh dashboard ──
        await notify_backend("status_update", {
            "status": remote_status,
            "chat_count": len(chats),
            "history_updated": history_updated
        })

        # ── Filter unread for AI processing ──
        unread = [m for m in chats if m.get('count', 0) > 0]

        if not unread:
            print(f"{ts()} No unread messages.")
            return

        print(f"{ts()} 🔴 {len(unread)} UNREAD chat(s) — triggering AI...")

        for msg in unread:
            sender = msg.get('sender', 'Unknown')
            minute_key = datetime.now().strftime('%Y%m%d_%H%M')
            cache_key  = f"{sender}|{minute_key}"

            if cache_key in _processed_cache:
                print(f"{ts()} ⏭ Skipping duplicate: {sender}")
                continue

            _processed_cache.add(cache_key)
            md_path = create_task_md(msg)
            if md_path:
                await trigger_reasoning(md_path)
                # Notify backend specifically about new unread message
                await notify_backend("new_message", msg)

    result = await with_retry(_do_check)
    if result is None:
        print(f"{ts()} ⚠ Check skipped after all retries.")


# ─── Backend Notification ─────────────────────────────────────────────────────

async def notify_backend(event_type: str, data: dict):
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"service": "whatsapp", "type": event_type, "data": data}
            await session.post("http://localhost:8000/webhook/whatsapp", json=payload)
    except Exception as e:
        print(f"{ts()} ⚠ Failed to notify backend: {e}")



# ─── Main Daemon Loop ─────────────────────────────────────────────────────────

async def async_main():
    print(f"{ts()} [WhatsApp] Watcher starting (polling every {POLL_INTERVAL}s)...")
    print(f"{ts()} MCP Server: {MCP_BASE_URL}")

    # Wait for MCP server to be ready
    print(f"{ts()} Waiting for MCP server...")
    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        for _ in range(6):
            try:
                async with session.get(MCP_BASE_URL, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        print(f"{ts()} ✓ MCP server is up.")
                        break
            except Exception:
                print(f"{ts()} [WARN] MCP server not reachable. Retrying...")
                await asyncio.sleep(5)
        else:
             print(f"{ts()} [WARN] MCP Server could not be reached. Proceeding anyway.")

        while True:
            try:
                await check_whatsapp(session)
            except Exception as e:
                print(f"{ts()} Error in loop: {e}")
            
            await asyncio.sleep(POLL_INTERVAL)


def main():
    try:
        import json # Ensure json is imported
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print(f"\n{ts()} 💤 WhatsApp Watcher stopped.")


if __name__ == '__main__':
    main()
