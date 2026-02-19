"""
Facebook Watcher — Async Optimized (Silver Tier)
=================================================
Polls the local MCP server (/check-facebook) every 30 seconds.
Detects:  friend requests, messages, notifications
On detection: saves a rich .md to /Needs_Action and spawns reasoning_loop.py.

Optimizations:
  - asyncio + aiohttp non-blocking polling
  - 30-second rate limit between checks
  - Event-hash cache (avoids duplicate .md per session)
  - 3-attempt retry with exponential back-off on MCP failures
  - Typed .md files (facebook_friend_request / facebook_message / facebook_notification)
  - Smart AI suggestion per event type ("Accept? Reason: ..." / "Suggested Reply: ...")

Requirements:
  pip install aiohttp

Usage:
  python facebook_watcher.py       # continuous daemon
"""

import asyncio
import aiohttp  # pip install aiohttp
import hashlib
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────
MCP_BASE_URL     = "http://localhost:3000"
BASE_DIR         = Path(__file__).resolve().parent
NEEDS_ACTION_DIR = BASE_DIR.parent / 'Needs_Action'
REASONING_LOOP   = BASE_DIR / 'reasoning_loop.py'
LOG_PREFIX       = "[FACEBOOK]"

POLL_INTERVAL    = 30    # seconds between polls
MAX_RETRIES      = 3
RETRY_DELAY      = 5     # base back-off (seconds)

# Cache: hashes of processed events to avoid duplicate .md files
_event_cache: set = set()


def ts() -> str:
    return f"{LOG_PREFIX} [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"


def event_hash(event: dict) -> str:
    """Generate a stable hash for an event to detect duplicates."""
    key = f"{event.get('type','')}|{event.get('name','')}" \
          f"|{event.get('description','')[:60]}" \
          f"|{datetime.now().strftime('%Y%m%d_%H%M')}"    # re-alert after 1 min
    return hashlib.md5(key.encode()).hexdigest()


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
    print(f"{ts()} ✗ All {attempts} attempts exhausted. Last: {last_exc}")
    return None


# ─── MCP Poll ─────────────────────────────────────────────────────────────────

async def fetch_facebook_data(session: aiohttp.ClientSession) -> dict | None:
    """Call MCP /check-facebook and return parsed JSON."""
    url = f"{MCP_BASE_URL}/check-facebook"
    print(f"{ts()} Polling MCP: {url}")
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
        resp.raise_for_status()
        return await resp.json()


# ─── .md Builders per Event Type ─────────────────────────────────────────────

def _md_friend_request(event: dict, now_iso: str, filename: str) -> str:
    name    = event.get('name', 'Unknown Person')
    mutuals = event.get('mutual_friends', 0)
    profile = event.get('profile_url', '')

    return f"""---
type: facebook_friend_request
person: "{name}"
mutual_friends: {mutuals}
profile_url: "{profile}"
received: "{now_iso}"
priority: normal
status: pending
---

## 👥 New Facebook Friend Request

| Field             | Value |
|-------------------|-------|
| **Name**          | {name} |
| **Mutual Friends**| {mutuals} |
| **Profile**       | {profile if profile else 'N/A'} |
| **Detected**      | {now_iso} |

---

## 🤖 AI Suggestion

**Should I Accept?**

Recommendation based on:
- Mutual friends: **{mutuals}** → {"High trust signal ✅" if mutuals >= 3 else "Low trust ⚠️" if mutuals == 0 else "Some trust 🔶"}
- {"Accept — likely a real connection." if mutuals >= 3 else "Review profile before accepting — no/few mutual friends."}

**Decision options:**
- ✅ `Accept` → POST `/accept-friend-facebook` `{{ "user_id": "{name}" }}`
- ❌ `Reject` → Manually ignore on Facebook

**Suggested reasoning to log:**
> {"Accept: {name} has {mutuals} mutual friends — real connection likely." if mutuals >= 3 else f"Review: {name} has only {mutuals} mutuals. Suggest checking profile first."}

---
*Detected by Facebook Watcher at {now_iso}*
"""


def _md_message(event: dict, now_iso: str, filename: str) -> str:
    sender  = event.get('sender', 'Unknown')
    preview = event.get('preview', '(No preview)')
    count   = event.get('count', 1)

    return f"""---
type: facebook_message
sender: "{sender}"
unread_count: {count}
received: "{now_iso}"
priority: high
status: pending
---

## 💬 New Facebook Message

| Field       | Value |
|-------------|-------|
| **From**    | {sender} |
| **Unread**  | {count} message(s) |
| **Detected**| {now_iso} |

## Message Preview

> {preview}

---

## 🤖 AI Instruction

You have an unread Facebook message from **{sender}**.

Please:
1. Review the preview above.
2. Draft a friendly, professional reply.
3. Submit for human approval.

**Suggested Reply:**
> Hi {sender}! Thanks for reaching out. [Your reply here]

**MCP Action:**
- Open Facebook Messenger and reply to **{sender}**
- Or use the `send-whatsapp` equivalent if integrated

---
*Detected by Facebook Watcher at {now_iso}*
"""


def _md_notification(event: dict, now_iso: str, filename: str) -> str:
    desc    = event.get('description', 'You have unread Facebook notifications.')
    action  = event.get('action', 'Check Facebook')
    evt_type = event.get('type', 'notification')

    return f"""---
type: facebook_notification
event: "{evt_type}"
received: "{now_iso}"
priority: normal
status: pending
---

## 🔔 Facebook Notification

| Field       | Value |
|-------------|-------|
| **Type**    | {evt_type} |
| **Detected**| {now_iso} |

## Details

{desc}

---

## 🤖 AI Instruction

**Suggested action:** {action}

Review the notification on Facebook and take appropriate action:
- If it's a post tag → decide to keep or remove
- If it's a comment → reply if appropriate
- If it's a like/reaction → no action needed

---
*Detected by Facebook Watcher at {now_iso}*
"""


# ─── .md File Writer ─────────────────────────────────────────────────────────

def create_task_md(event: dict) -> Path | None:
    """Dispatch to the correct .md builder and write the file."""
    try:
        NEEDS_ACTION_DIR.mkdir(exist_ok=True)
        now_iso   = datetime.now().isoformat()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        evt_type  = event.get('type', 'notification')

        # Filename
        label = (event.get('name') or event.get('sender') or evt_type)[:25]
        safe  = "".join(c if c.isalnum() or c in '-_' else '_' for c in label)
        filename = f"{timestamp}_Facebook_{evt_type}_{safe}.md"
        filepath = NEEDS_ACTION_DIR / filename

        # Build content
        if evt_type == 'friend_request':
            content = _md_friend_request(event, now_iso, filename)
        elif evt_type == 'message':
            content = _md_message(event, now_iso, filename)
        else:
            content = _md_notification(event, now_iso, filename)

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
    code = proc.returncode
    if code == 0:
        print(f"{ts()} ✓ reasoning_loop done for {name}")
    else:
        print(f"{ts()} ✗ reasoning_loop error for {name}: {stderr.decode()[:200]}")


# ─── History & Status Helpers ─────────────────────────────────────────────────

HISTORY_FILE = BASE_DIR / "facebook_history.json"
HISTORY_FILE = BASE_DIR / "facebook_history.json"
STATUS_FILE  = BASE_DIR / "status_facebook.json"

def update_heartbeat(status="online"):
    try:
        data = {
            "status": status,
            "last_active": datetime.now().isoformat(),
            "pid": sys.pid if hasattr(sys, 'pid') else 0
        }
        STATUS_FILE.write_text(json.dumps(data, indent=2))
    except: pass

# ... (sync_history remains same) ...

async def check_facebook(session: aiohttp.ClientSession):
    """One Facebook poll cycle with retry and dedup."""

    async def _do_check():
        data = await fetch_facebook_data(session)
        if not data:
            update_heartbeat("offline")
            return

        # Use status from MCP
        remote_status = data.get('status', 'offline')
        update_heartbeat(remote_status)
        
        if remote_status != 'online':
            return

        # Collect all events (support both new structured and legacy formats)
        all_events = []

        # Friend requests (structured)
        for fr in data.get('friend_requests', []):
            fr['type'] = 'friend_request'
            all_events.append(fr)

        # Messages (structured)
        for msg in data.get('messages', []):
            msg['type'] = 'message'
            all_events.append(msg)
            
        # ... (rest of logic) ...

        # Legacy events array (notifications etc)
        for evt in data.get('events', []):
            all_events.append(evt)

        # 1. Update Dashboard History (Show everything)
        if all_events:
            sync_history(all_events)

        # 2. Filter for Actionable Events (Unread messages, new requests, notifications)
        # Messages with count > 0 are unread. Friend requests are always actionable. Notifications are actionable.
        actionable_events = []
        for evt in all_events:
            if evt.get('type') == 'message' and evt.get('count', 0) == 0:
                continue # Skip read messages
            actionable_events.append(evt)

        if not actionable_events:
            print(f"{ts()} No new actionable Facebook events (History updated).")
            return

        print(f"{ts()} Found {len(actionable_events)} actionable Facebook event(s).")

        for event in actionable_events:
            h = event_hash(event)
            if h in _event_cache:
                print(f"{ts()} ⏭ Skipping duplicate event ({event.get('type','?')})")
                continue

            _event_cache.add(h)
            
            md_path = create_task_md(event)
            if md_path:
                await trigger_reasoning(md_path)

    await with_retry(_do_check)


# ─── Main Daemon Loop ─────────────────────────────────────────────────────────

async def async_main():
    print(f"{ts()} [Facebook] Watcher starting (polling every {POLL_INTERVAL}s)...")
    print(f"{ts()} MCP Server: {MCP_BASE_URL}")

    # Wait for MCP server
    print(f"{ts()} Waiting for MCP server...")
    for _ in range(6):
        try:
            async with aiohttp.ClientSession() as s:
    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        for _ in range(6):
            try:
                async with s.get(MCP_BASE_URL, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        print(f"{ts()} ✓ MCP server is up.")
                        break
            except Exception:
              if not await wait_for_mcp(session):
                print(f"{ts()} [WARN] MCP server not reachable. Proceeding anyway.")
            else:
                print(f"{ts()} MCP Server Online.")

            while True:
                try:
                    await check_facebook(session)
                except Exception as e:
                    print(f"{ts()} Error in loop: {e}")
                
                await asyncio.sleep(POLL_INTERVAL)


def main():
    try:
        import json # Ensure json is imported
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print(f"\n{ts()} 💤 Facebook Watcher stopped.")


if __name__ == '__main__':
    main()
