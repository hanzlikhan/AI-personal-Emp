"""
Gmail Watcher — Async Optimized (Silver Tier)
=============================================
Monitors Gmail for new unread emails using the Gmail API.
On detection: saves rich .md to /Needs_Action and spawns reasoning_loop.py.

Optimizations:
  - asyncio event loop (async-native where possible)
  - 30-second rate limit between checks
  - In-memory cache of seen message IDs (avoids reprocessing)
  - 3-attempt retry with exponential back-off for API errors
  - Timestamped logging throughout

Usage:
  python gmail_watcher.py            # continuous daemon (async loop)
  python gmail_watcher.py --once     # run once and exit
  python gmail_watcher.py --draft TO SUBJECT BODY
  python gmail_watcher.py --send  TO SUBJECT BODY
"""

import os
import sys
import asyncio
import subprocess
import pickle
import time
import argparse
import base64
import json
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ─── Configuration ────────────────────────────────────────────────────────────
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify'
]

BASE_DIR         = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / 'credentials.json'
TOKEN_FILE       = BASE_DIR / 'token.pickle'
NEEDS_ACTION_DIR = BASE_DIR.parent / 'Needs_Action'
REASONING_LOOP   = BASE_DIR / 'reasoning_loop.py'
LOG_PREFIX       = "[GMAIL]"

POLL_INTERVAL    = 30          # seconds between checks
MAX_RETRIES      = 3           # retry attempts for transient errors
RETRY_DELAY      = 5           # base delay (seconds) for back-off
MAX_EMAILS       = 10          # max emails fetched per check

# In-memory seen IDs (reset on restart — designed for daemon use)
_seen_ids: set = set()


def ts() -> str:
    """Return a timestamped log prefix."""
    return f"{LOG_PREFIX} [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"


# ─── Authentication ───────────────────────────────────────────────────────────

def authenticate_gmail():
    """Authenticate and return a Gmail API service object."""
    creds = None

    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print(f"{ts()} Refreshing expired token...")
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(f"credentials.json not found at {CREDENTIALS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)

    print(f"{ts()} Authenticated with Gmail API ✓")
    return build('gmail', 'v1', credentials=creds)


# ─── Retry Decorator ──────────────────────────────────────────────────────────

async def with_retry(coro_fn, *args, attempts=MAX_RETRIES, delay=RETRY_DELAY):
    """
    Retry an async coroutine up to `attempts` times with exponential back-off.
    coro_fn must be a callable that returns a coroutine.
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return await coro_fn(*args)
        except Exception as exc:
            last_exc = exc
            wait = delay * (2 ** (attempt - 1))   # 5s, 10s, 20s
            print(f"{ts()} ⚠ Attempt {attempt}/{attempts} failed: {exc}. Retrying in {wait}s...")
            await asyncio.sleep(wait)
    print(f"{ts()} ✗ All {attempts} attempts exhausted. Last error: {last_exc}")
    return None


# ─── Email Helpers ────────────────────────────────────────────────────────────

def _decode_body(part: dict) -> str:
    """Decode a single email body part from base64."""
    data = part.get('body', {}).get('data', '')
    if data:
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
    return ''


def _get_email_details(service, msg_id: str) -> dict | None:
    """Fetch full details for a single email (sync Gmail API call)."""
    try:
        msg = service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()

        headers = {h['name'].lower(): h['value'] for h in msg['payload']['headers']}

        # Extract body (plain text preferred)
        body = ''
        payload = msg.get('payload', {})
        parts = payload.get('parts', [])

        if parts:
            for part in parts:
                if part.get('mimeType') == 'text/plain':
                    body = _decode_body(part)
                    break
            if not body:
                for part in parts:
                    if part.get('mimeType') == 'text/html':
                        body = _decode_body(part)
                        break
        else:
            body = _decode_body(payload)

        return {
            'id':       msg_id,
            'threadId': msg.get('threadId', ''),
            'labels':   msg.get('labelIds', []),
            'from':     headers.get('from', ''),
            'to':       headers.get('to', ''),
            'subject':  headers.get('subject', '(No Subject)'),
            'date':     headers.get('date', ''),
            'body':     body[:600],
        }
    except Exception as exc:
        print(f"{ts()} ✗ Failed to get email {msg_id}: {exc}")
        return None


# ─── .md File Creation ────────────────────────────────────────────────────────

def _create_needs_action_md(email: dict) -> Path | None:
    """Write a rich Markdown task file to /Needs_Action."""
    try:
        NEEDS_ACTION_DIR.mkdir(exist_ok=True)
        priority   = 'high' if 'IMPORTANT' in email['labels'] else 'normal'
        timestamp  = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Safe filename
        safe_sub   = "".join(c if c.isalnum() or c in '-_' else '_' for c in email['subject'][:30])
        filename   = f"{timestamp}_gmail_{safe_sub}.md"
        filepath   = NEEDS_ACTION_DIR / filename
        now_iso    = datetime.now().isoformat()

        content = f"""---
type: email
from: "{email['from']}"
subject: "{email['subject']}"
thread_id: "{email['threadId']}"
labels: {json.dumps(email['labels'])}
received: "{now_iso}"
priority: {priority}
status: pending
---

## Email Details

| Field   | Value |
|---------|-------|
| **From**    | {email['from']} |
| **Subject** | {email['subject']} |
| **Date**    | {email['date']} |
| **Labels**  | {', '.join(email['labels'])} |

## Message Preview

{email['body']}

---

## 🤖 AI Instruction

Analyze this email and decide:
1. Is a reply needed? (Yes/No)
2. If yes, draft a professional reply addressing the sender's request.
3. If urgent (priority={priority}), flag it.

Suggested reply format:
> Dear [Name], ...

---
*Detected by Gmail Watcher at {now_iso}*
"""

        filepath.write_text(content, encoding='utf-8')
        print(f"{ts()} ✓ Created: {filename}")
        return filepath

    except Exception as exc:
        print(f"{ts()} ✗ Failed to create .md for '{email['subject']}': {exc}")
        return None


# ─── Trigger Reasoning Loop ───────────────────────────────────────────────────

async def _trigger_reasoning(filepath: Path):
    """Spawn reasoning_loop.py as a background subprocess (async)."""
    if not REASONING_LOOP.exists():
        print(f"{ts()} ⚠ reasoning_loop.py not found at {REASONING_LOOP}")
        return
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(REASONING_LOOP), str(filepath),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"{ts()} 🧠 Triggered reasoning_loop.py for {filepath.name} (PID {proc.pid})")
        # Let it run in background — don't await here
        asyncio.ensure_future(_wait_reasoning(proc, filepath.name))
    except Exception as exc:
        print(f"{ts()} ✗ Failed to spawn reasoning_loop.py: {exc}")


async def _wait_reasoning(proc, name: str):
    """Awaits a reasoning subprocess and logs its result."""
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        print(f"{ts()} ✓ reasoning_loop completed for {name}")
    else:
        print(f"{ts()} ✗ reasoning_loop error for {name}: {stderr.decode()[:200]}")


# ─── Core Async Check Logic ───────────────────────────────────────────────────

async def check_for_new_emails(service):
    """Async-wrapped email check: fetches unread emails, creates .md files."""

    async def _do_check():
        print(f"{ts()} Checking for new unread emails...")
        # Gmail API call (sync) run in executor to not block event loop
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: service.users().messages().list(
                userId='me', q='is:unread', maxResults=MAX_EMAILS
            ).execute()
        )

        messages = results.get('messages', [])
        new = [m for m in messages if m['id'] not in _seen_ids]

        if not new:
            print(f"{ts()} No new unread emails.")
            return

        print(f"{ts()} Found {len(new)} new email(s).")

        for msg in new:
            _seen_ids.add(msg['id'])

            # Fetch details in executor
            details = await loop.run_in_executor(
                None, _get_email_details, service, msg['id']
            )
            if not details:
                continue

            # Create the .md task file
            md_path = _create_needs_action_md(details)

            if md_path:
                # Mark email as read
                await loop.run_in_executor(
                    None,
                    lambda mid=msg['id']: service.users().messages().modify(
                        userId='me', id=mid,
                        body={'removeLabelIds': ['UNREAD']}
                    ).execute()
                )
                # Trigger AI reasoning
                await _trigger_reasoning(md_path)

    return await with_retry(_do_check)


# ─── Draft / Send Helpers (CLI Actions) ───────────────────────────────────────

def create_draft(service, to: str, subject: str, body: str):
    """Create a Gmail draft."""
    from email.mime.text import MIMEText
    msg = MIMEText(body)
    msg['to']      = to
    msg['subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        draft = service.users().drafts().create(
            userId='me', body={'message': {'raw': raw}}
        ).execute()
        print(f"{ts()} ✓ Draft created: {draft['id']}")
    except Exception as exc:
        print(f"{ts()} ✗ Draft failed: {exc}")


def send_email(service, to: str, subject: str, body: str):
    """Send a Gmail message immediately."""
    from email.mime.text import MIMEText
    msg = MIMEText(body)
    msg['to']      = to
    msg['subject'] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        sent = service.users().messages().send(
            userId='me', body={'raw': raw}
        ).execute()
        print(f"{ts()} ✓ Email sent: {sent['id']}")
    except Exception as exc:
        print(f"{ts()} ✗ Send failed: {exc}")


# ─── History & Status Helpers ─────────────────────────────────────────────────

HISTORY_FILE = BASE_DIR / "gmail_history.json"
HISTORY_FILE = BASE_DIR / "gmail_history.json"
STATUS_FILE  = BASE_DIR / "status_gmail.json"

def update_heartbeat():
    """Update status_gmail.json with current timestamp."""
    try:
        data = {
            "status": "online",
            "last_active": datetime.now().isoformat(),
            "pid": os.getpid()
        }
        STATUS_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        print(f"{ts()} ⚠ Failed to update heartbeat: {e}")

def sync_history(service):
    """Fetch last 15 emails (read or unread) for dashboard history."""
    try:
        results = service.users().messages().list(userId='me', maxResults=15).execute()
        messages = results.get('messages', [])
        
        history = []
        for msg in messages:
            details = _get_email_details(service, msg['id'])
            if details:
                # Simplify for frontend
                history.append({
                    "id": details['id'],
                    "from": details['from'],
                    "subject": details['subject'],
                    "snippet": details['body'][:100],
                    "date": details['date'],
                    "timestamp": datetime.now().isoformat() # Approx
                })
        
        HISTORY_FILE.write_text(json.dumps(history, indent=2))
        print(f"{ts()} ↻ Synced {len(history)} emails to history.")
    except Exception as e:
        print(f"{ts()} ⚠ History sync failed: {e}")

# ─── Main Async Loop ──────────────────────────────────────────────────────────

async def async_main(args):
    service = authenticate_gmail()

    if args.draft:
        to, subject, body = args.draft
        create_draft(service, to, subject, body)

    elif args.send:
        to, subject, body = args.send
        send_email(service, to, subject, body)

    elif args.once:
        print(f"{ts()} Running once...")
        await check_for_new_emails(service)
        sync_history(service)
        update_heartbeat()

    else:
        print(f"{ts()} 🚀 Starting continuous daemon (check every {POLL_INTERVAL}s)...")
        # Initial sync
        sync_history(service)
        
        while True:
            update_heartbeat()
            await check_for_new_emails(service)
            
            # Sync history every 5 loops (approx 2.5 mins) to save API quota
            # For now, just sync on start. Real-time new emails are handled by check_for_new_emails
            
            print(f"{ts()} ⏳ Waiting {POLL_INTERVAL}s before next check...")
            await asyncio.sleep(POLL_INTERVAL)


def main():
    parser = argparse.ArgumentParser(description='Gmail Watcher — Async Optimized')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--draft', nargs=3, metavar=('TO', 'SUBJECT', 'BODY'), help='Create a draft')
    group.add_argument('--send',  nargs=3, metavar=('TO', 'SUBJECT', 'BODY'), help='Send email immediately')
    group.add_argument('--once',  action='store_true', help='Check once and exit')
    args = parser.parse_args()

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print(f"\n{ts()} 💤 Gmail Watcher stopped.")


if __name__ == '__main__':
    main()