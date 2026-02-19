"""
reasoning_loop.py — Async Optimized (Silver Tier)
==================================================
The AI "Brain" that processes task files from /Needs_Action.

Architecture:
  - Async throughout (asyncio.run, executor for LLM calls)
  - Chain of Thought (CoT): THINK → ANALYZE → DRAFT → VALIDATE
  - Ralph Wiggum Loop: up to MAX_ITERATIONS per task
  - Plan caching: skips re-processing if plan already exists
  - API retry: 3 attempts, exponential back-off (5s→10s→20s)
  - Per-service rich suggestions written to /Plans
  - Sensitive actions → /Pending_Approval (HITL)

Usage:
  python reasoning_loop.py <task_file>          # auto-triggered by orchestrator
  python reasoning_loop.py <task_file> --force  # re-run even if plan exists
  python reasoning_loop.py <task_file> --execute # execute approved action via MCP
  python reasoning_loop.py --chat               # manual instruction mode
"""

import os
import sys
import asyncio
import json
import re
import argparse
import traceback
import requests
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # fallback manual parser

# ─── Windows UTF-8 Console Fix ───────────────────────────────────────────────
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Directory Config ─────────────────────────────────────────────────────────
BASE_DIR            = Path(__file__).resolve().parent
PLANS_DIR           = BASE_DIR.parent / "Plans"
DONE_DIR            = BASE_DIR.parent / "Done"
PENDING_DIR         = BASE_DIR.parent / "Pending_Approval"
DASHBOARD_PATH      = BASE_DIR.parent / "Dashboard.md"
NEEDS_ACTION_DIR    = BASE_DIR.parent / "Needs_Action"
LOGS_DIR            = BASE_DIR.parent / "Logs"
LOG_PREFIX          = "[BRAIN]"

# ─── Loop Config ──────────────────────────────────────────────────────────────
MAX_ITERATIONS      = 10    # Ralph Wiggum loop cap
MAX_API_RETRIES     = 3     # API failure retries
RETRY_BASE_DELAY    = 5     # seconds, doubles each attempt

# ─── Logging ──────────────────────────────────────────────────────────────────
def ts() -> str:
    return f"{LOG_PREFIX} [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]"


def log(msg: str):
    try:
        print(f"{ts()} {msg}", flush=True)
    except UnicodeEncodeError:
        safe = f"{ts()} {msg}".encode("ascii", errors="replace").decode("ascii")
        print(safe, flush=True)


# ─── .env / API Keys ──────────────────────────────────────────────────────────
def get_env_key(key_name: str) -> str | None:
    val = os.environ.get(key_name)
    if not val:
        env_path = BASE_DIR.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith(f"{key_name}="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    break
    return val or None


# ─── AI Dispatcher ────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, system: str, api_key: str) -> str:
    models = [
        "gemini-2.0-flash-001",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-flash-latest",
    ]
    last_err = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1500},
        }
        try:
            r = requests.post(url, json=payload, timeout=45)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"All Gemini models failed: {last_err}")


def _call_groq(prompt: str, system: str, api_key: str) -> str:
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "llama3-70b-8192",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": 0.4,
        },
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_claude(prompt: str, system: str, api_key: str) -> str:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-3-5-sonnet-20240620",
            "max_tokens": 1500,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=45,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _ai_dispatch(prompt: str, system: str = "You are a smart, concise AI assistant.") -> str:
    """Try Gemini → Groq → Claude → Mock, synchronously."""
    key = get_env_key("GEMINI_API_KEY")
    if key:
        try:
            return _call_gemini(prompt, system, key)
        except Exception as e:
            log(f"⚠ Gemini failed: {e}")

    key = get_env_key("GROQ_API_KEY")
    if key:
        try:
            return _call_groq(prompt, system, key)
        except Exception as e:
            log(f"⚠ Groq failed: {e}")

    key = get_env_key("ANTHROPIC_API_KEY")
    if key:
        try:
            return _call_claude(prompt, system, key)
        except Exception as e:
            log(f"⚠ Claude failed: {e}")

    log("⚠ No valid API key found — using mock response.")
    return "MOCK: I analysed the task. Please add an API key to .env for real suggestions."


async def call_ai_async(prompt: str, system: str = "You are a smart, concise AI assistant.") -> str:
    """Async wrapper around the sync AI dispatcher with retry logic."""
    loop = asyncio.get_event_loop()
    last_err = None
    for attempt in range(1, MAX_API_RETRIES + 1):
        try:
            result = await loop.run_in_executor(None, _ai_dispatch, prompt, system)
            return result
        except Exception as e:
            last_err = e
            wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            log(f"⚠ AI attempt {attempt}/{MAX_API_RETRIES} failed: {e}. Retrying in {wait}s...")
            await asyncio.sleep(wait)
    raise RuntimeError(f"AI API failed after {MAX_API_RETRIES} attempts: {last_err}")


# ─── File Helpers ─────────────────────────────────────────────────────────────

async def read_task_file(filepath: Path) -> tuple[dict, str]:
    """Async file read + YAML frontmatter parse."""
    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(None, lambda: filepath.read_text(encoding="utf-8"))

    frontmatter: dict = {}
    body: str = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1].strip()
            body = parts[2].strip()
            try:
                if yaml:
                    frontmatter = yaml.safe_load(raw_yaml) or {}
                else:
                    # Manual fallback parser
                    for line in raw_yaml.splitlines():
                        if ":" in line:
                            k, _, v = line.partition(":")
                            frontmatter[k.strip()] = v.strip().strip("\"'")
            except Exception as e:
                log(f"⚠ YAML parse error: {e}")

    return frontmatter, body


def find_cached_plan(task_id: str) -> Path | None:
    """Look for an existing plan that matches this task ID."""
    if not PLANS_DIR.exists():
        return None
    for f in PLANS_DIR.glob(f"*{task_id}*.md"):
        return f
    return None


def is_in_done(filename: str) -> bool:
    """Check if this task file has already been moved to /Done."""
    return (DONE_DIR / filename).exists()


# ─── Plan File Writer ─────────────────────────────────────────────────────────

async def write_plan(task_id: str, cot_steps: dict, suggestion: str, task_type: str) -> Path:
    """Write a rich Plan.md with CoT sections and the final suggestion."""
    PLANS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{timestamp}_{task_id}_plan.md"
    filepath  = PLANS_DIR / filename
    now_iso   = datetime.now().isoformat()

    content = f"""---
task_id: "{task_id}"
type: "{task_type}"
created: "{now_iso}"
status: planned
---

# Plan: {task_id}

> *Generated by Async Reasoning Loop at {now_iso}*

---

## 🧠 Chain of Thought

### Step 1 — THINK
{cot_steps.get("think", "(not recorded)")}

### Step 2 — ANALYZE
{cot_steps.get("analyze", "(not recorded)")}

### Step 3 — DRAFT
{cot_steps.get("draft", "(not recorded)")}

### Step 4 — VALIDATE
{cot_steps.get("validate", "(not recorded)")}

---

## ✅ Final Suggestion

{suggestion}

---
*Plan auto-generated. Review in /Pending_Approval before execution.*
"""

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: filepath.write_text(content, encoding="utf-8"))
    log(f"✓ Plan saved: {filename}")
    return filepath


# ─── Pending Approval Writer ──────────────────────────────────────────────────

async def create_approval_request(
    action_type: str,
    content: str,
    metadata: dict,
    reasoning: str = "",
    mcp_endpoint: str = "",
    confidence: str = "medium",
) -> Path:
    """Create an enriched Pending_Approval .md file for HITL."""
    PENDING_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{timestamp}_{action_type}_approval.md"
    filepath  = PENDING_DIR / filename
    now_iso   = datetime.now().isoformat()

    meta_lines = "\n".join(f'{k}: "{v}"' for k, v in metadata.items())

    file_content = f"""---
type: {action_type}
status: pending_approval
confidence: {confidence}
suggested_mcp_endpoint: "{mcp_endpoint}"
created: "{now_iso}"
{meta_lines}
---

# 🔔 Approval Request — {action_type.upper()}

**Action**: {action_type.upper()}
**Confidence**: {confidence}
**MCP Endpoint**: `{mcp_endpoint}`

## 🤖 AI Reasoning

{reasoning}

## 📝 Proposed Content

{content}

---

> **Human Instructions:**
> - Move this file to `/Approved` to **execute**.
> - Delete this file to **reject**.
> - Edit content above before moving if you want to modify the suggestion.
"""

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: filepath.write_text(file_content, encoding="utf-8"))
    log(f"✓ Pending approval created: {filename}")
    return filepath


# ─── MCP Caller ───────────────────────────────────────────────────────────────

def call_mcp(endpoint: str, payload: dict) -> bool:
    url = f"http://localhost:3000/{endpoint}"
    try:
        log(f"→ MCP POST {url}")
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        result = r.json()
        log(f"← MCP response: {result}")
        return result.get("success", False)
    except Exception as e:
        log(f"✗ MCP error ({endpoint}): {e}")
        return False


# ─── Move to Done ─────────────────────────────────────────────────────────────

async def move_to_done(filepath: Path, note: str = ""):
    DONE_DIR.mkdir(exist_ok=True)
    dest = DONE_DIR / filepath.name
    loop = asyncio.get_event_loop()

    def _move():
        if dest.exists():
            dest.unlink()  # overwrite if duplicate run
        filepath.rename(dest)
        if note:
            with open(dest, "a", encoding="utf-8") as f:
                f.write(f"\n\n---\n*Completed at {datetime.now().isoformat()}. Note: {note}*\n")

    try:
        await loop.run_in_executor(None, _move)
        log(f"✓ Moved to Done: {filepath.name}")
    except Exception as e:
        log(f"⚠ Could not move to Done: {e}")


# ─── Dashboard Update ─────────────────────────────────────────────────────────

async def update_dashboard(entry: str):
    loop = asyncio.get_event_loop()
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _update():
        if not DASHBOARD_PATH.exists():
            return
        content = DASHBOARD_PATH.read_text(encoding="utf-8")
        log_section = f"\n- [{now}] {entry}"
        if "## Recent Activity" in content:
            content = content.replace(
                "## Recent Activity",
                f"## Recent Activity{log_section}",
                1,
            )
        else:
            content += f"\n\n## Recent Activity{log_section}\n"
        DASHBOARD_PATH.write_text(content, encoding="utf-8")

    await loop.run_in_executor(None, _update)


# ─── CoT Processing per Task Type ─────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a smart, professional AI assistant managing emails, WhatsApp, and Facebook "
    "for a busy professional. Be concise, actionable, and professional. "
    "Provide specific suggestions — not generic advice."
)


async def process_email(fm: dict, body: str) -> tuple[dict, str, dict]:
    """CoT for email tasks. Returns (cot_steps, suggestion, approval_meta)."""
    sender  = fm.get("from", "Unknown Sender")
    subject = fm.get("subject", "(No Subject)")
    priority = fm.get("priority", "normal")

    log(f"📧 Processing email from {sender} — '{subject}'")

    # THINK
    think = await call_ai_async(
        f"Email from: {sender}\nSubject: {subject}\nBody preview:\n{body}\n\n"
        "Step 1 — THINK: What is the core purpose of this email? Is it urgent? Spam? Business? Personal?",
        SYSTEM_PROMPT,
    )
    log(f"  THINK: {think[:80]}...")

    # ANALYZE
    analyze = await call_ai_async(
        f"Email analysis context:\n{think}\n\n"
        f"Step 2 — ANALYZE: What specific action is needed? Does it require a reply? "
        "What tone should the reply use? Who is likely the sender (client/colleague/stranger)?",
        SYSTEM_PROMPT,
    )
    log(f"  ANALYZE: {analyze[:80]}...")

    # DRAFT
    draft_raw = await call_ai_async(
        f"Context: Email from {sender} about '{subject}'.\nAnalysis: {analyze}\n\n"
        "Step 3 — DRAFT: Write a complete, professional email reply. "
        "Start with 'Dear [Name],' and end with a professional sign-off. "
        "If no reply is needed, write exactly: NO_REPLY",
        SYSTEM_PROMPT,
    )
    log(f"  DRAFT: {draft_raw[:80]}...")

    # VALIDATE
    validate = await call_ai_async(
        f"Draft reply:\n{draft_raw}\n\n"
        "Step 4 — VALIDATE: Is this reply appropriate, professional, and complete? "
        "Any concerns? Rate confidence: high/medium/low.",
        SYSTEM_PROMPT,
    )
    log(f"  VALIDATE: {validate[:80]}...")

    cot_steps = {"think": think, "analyze": analyze, "draft": draft_raw, "validate": validate}

    # Extract confidence
    confidence = "medium"
    if "high" in validate.lower():
        confidence = "high"
    elif "low" in validate.lower():
        confidence = "low"

    needs_reply = "NO_REPLY" not in draft_raw.upper()
    if needs_reply:
        suggestion = (
            f"**Suggested Reply to {sender}:**\n\n"
            f"**Subject:** Re: {subject}\n\n"
            f"{draft_raw}"
        )
        approval_meta = {
            "target": sender,
            "subject": f"Re: {subject}",
            "action": "send_email",
            "priority": priority,
        }
    else:
        suggestion = f"**No reply needed.** Reasoning:\n{analyze}"
        approval_meta = {}

    return cot_steps, suggestion, approval_meta, confidence, needs_reply


async def process_whatsapp(fm: dict, body: str) -> tuple[dict, str, dict]:
    """CoT for WhatsApp tasks."""
    sender = fm.get("sender", "Unknown")
    log(f"💬 Processing WhatsApp from {sender}")

    think = await call_ai_async(
        f"WhatsApp message from: {sender}\nContext:\n{body}\n\n"
        "Step 1 — THINK: What is this person trying to communicate? What's the context?",
        SYSTEM_PROMPT,
    )

    analyze = await call_ai_async(
        f"Context: {think}\n\n"
        "Step 2 — ANALYZE: What should my reply achieve? "
        "What tone (friendly/professional/brief)? Any sensitivity concerns?",
        SYSTEM_PROMPT,
    )

    draft_raw = await call_ai_async(
        f"WhatsApp from {sender}. Analysis: {analyze}\n\n"
        "Step 3 — DRAFT: Write a short, natural WhatsApp reply (max 3 sentences). "
        "WhatsApp tone — friendly but professional. No email format.",
        SYSTEM_PROMPT,
    )

    validate = await call_ai_async(
        f"Draft: {draft_raw}\n\n"
        "Step 4 — VALIDATE: Is this reply appropriate and natural for WhatsApp? "
        "Confidence: high/medium/low",
        SYSTEM_PROMPT,
    )

    cot_steps = {"think": think, "analyze": analyze, "draft": draft_raw, "validate": validate}
    confidence = "high" if "high" in validate.lower() else "medium"

    suggestion = (
        f"**Suggested WhatsApp Reply to {sender}:**\n\n"
        f"> {draft_raw}\n\n"
        f"*(Short, natural, WhatsApp-appropriate)*"
    )
    approval_meta = {"target": sender, "action": "send_whatsapp"}

    return cot_steps, suggestion, approval_meta, confidence


async def process_facebook_friend_request(fm: dict, body: str) -> tuple[dict, str, dict]:
    """CoT for Facebook friend request decisions."""
    person  = fm.get("person", fm.get("name", "Unknown"))
    mutuals = fm.get("mutual_friends", 0)
    log(f"👥 Processing friend request from {person} ({mutuals} mutuals)")

    think = await call_ai_async(
        f"Facebook friend request from: {person}\nMutual friends: {mutuals}\nContext:\n{body}\n\n"
        "Step 1 — THINK: Who might this person be? What does the mutual friend count suggest "
        "about the likelihood of it being a genuine connection?",
        SYSTEM_PROMPT,
    )

    analyze = await call_ai_async(
        f"Context: {think}\n\n"
        "Step 2 — ANALYZE: What are the risks and benefits of accepting? "
        "Consider: mutual friends ({mutuals}), profile authenticity, spam risk.",
        SYSTEM_PROMPT,
    )

    draft_raw = await call_ai_async(
        f"Friend request from {person}. Mutual friends: {mutuals}. Analysis: {analyze}\n\n"
        "Step 3 — DRAFT: Make a clear ACCEPT or REJECT recommendation. "
        "Format:\nDECISION: ACCEPT or REJECT\nREASON: [one sentence explanation]",
        SYSTEM_PROMPT,
    )

    validate = await call_ai_async(
        f"Decision: {draft_raw}\n\n"
        "Step 4 — VALIDATE: Is this decision sound? Any second thoughts? Confidence: high/medium/low",
        SYSTEM_PROMPT,
    )

    cot_steps = {"think": think, "analyze": analyze, "draft": draft_raw, "validate": validate}
    confidence = "high" if mutuals >= 3 else "medium" if mutuals >= 1 else "low"

    # Parse decision
    decision = "ACCEPT" if "ACCEPT" in draft_raw.upper() else "REJECT"
    reason_match = re.search(r"REASON:\s*(.+)", draft_raw, re.IGNORECASE)
    reason = reason_match.group(1).strip() if reason_match else analyze[:120]

    suggestion = (
        f"**Friend Request Decision: {decision}**\n\n"
        f"**Person:** {person}\n"
        f"**Mutual Friends:** {mutuals}\n\n"
        f"**Reason:** {reason}\n\n"
        f"**MCP Action if accepted:**\n"
        f"```\nPOST /accept-friend-facebook {{\"user_id\": \"{person}\"}}\n```"
    )
    approval_meta = {"person": person, "mutual_friends": str(mutuals), "decision": decision}

    return cot_steps, suggestion, approval_meta, confidence


async def process_facebook_message(fm: dict, body: str) -> tuple[dict, str, dict]:
    """CoT for Facebook message replies."""
    sender = fm.get("sender", "Unknown")
    log(f"💬 Processing Facebook message from {sender}")

    think = await call_ai_async(
        f"Facebook message from: {sender}\nContent:\n{body}\n\n"
        "Step 1 — THINK: What does this person want? Personal or business context?",
        SYSTEM_PROMPT,
    )

    analyze = await call_ai_async(
        f"Context: {think}\n\nStep 2 — ANALYZE: Appropriate tone? Reply length? Any concerns?",
        SYSTEM_PROMPT,
    )

    draft_raw = await call_ai_async(
        f"Facebook message from {sender}. Analysis: {analyze}\n\n"
        "Step 3 — DRAFT: Write a friendly, concise Facebook Messenger reply (2-4 sentences).",
        SYSTEM_PROMPT,
    )

    validate = await call_ai_async(
        f"Draft: {draft_raw}\n\nStep 4 — VALIDATE: Appropriate for Facebook? Confidence?",
        SYSTEM_PROMPT,
    )

    cot_steps = {"think": think, "analyze": analyze, "draft": draft_raw, "validate": validate}
    confidence = "high" if "high" in validate.lower() else "medium"

    suggestion = (
        f"**Suggested Facebook Reply to {sender}:**\n\n"
        f"> {draft_raw}"
    )
    approval_meta = {"sender": sender, "action": "facebook_message_reply"}
    # Fix: Use correct MCP endpoint
    mcp_endpoint = "send-facebook-message" 

    return cot_steps, suggestion, approval_meta, confidence

async def process_facebook_post(fm: dict, body: str) -> tuple[dict, str, dict]:
    """CoT for generating new Facebook posts."""
    topic = fm.get("topic", "General Update")
    log(f"📝 Processing Facebook Post Request: {topic}")

    think = await call_ai_async(
        f"Request: Create a Facebook post about '{topic}'\nContext:\n{body}\n\n"
        "Step 1 — THINK: What is the goal? Engagement? Announcement? Personal update?",
        SYSTEM_PROMPT,
    )

    analyze = await call_ai_async(
        f"Context: {think}\n\nStep 2 — ANALYZE: What tone works best for Facebook? "
        "Should it use emojis? Hashtags?",
        SYSTEM_PROMPT,
    )

    draft_raw = await call_ai_async(
        f"Topic: {topic}. Analysis: {analyze}\n\n"
        "Step 3 — DRAFT: Write a compelling Facebook post. Use emojis. Max 3-4 lines.",
        SYSTEM_PROMPT,
    )

    validate = await call_ai_async(
        f"Draft: {draft_raw}\n\nStep 4 — VALIDATE: Is this engaging? Confidence?",
        SYSTEM_PROMPT,
    )

    cot_steps = {"think": think, "analyze": analyze, "draft": draft_raw, "validate": validate}
    confidence = "medium"

    suggestion = (
        f"**Suggested Facebook Post:**\n\n"
        f"{draft_raw}"
    )
    approval_meta = {"topic": topic, "action": "facebook_post"}

    return cot_steps, suggestion, approval_meta, confidence


async def process_facebook_notification(fm: dict, body: str) -> tuple[dict, str, dict]:
    """CoT for general Facebook notifications."""
    event = fm.get("event", fm.get("type", "notification"))
    log(f"🔔 Processing Facebook notification: {event}")

    think = await call_ai_async(
        f"Facebook notification type: {event}\nDetails:\n{body}\n\n"
        "Step 1 — THINK: What happened on Facebook? Does it require a response?",
        SYSTEM_PROMPT,
    )

    analyze = await call_ai_async(
        f"Context: {think}\n\nStep 2 — ANALYZE: What is the best course of action? "
        "Is this time-sensitive?",
        SYSTEM_PROMPT,
    )

    draft_raw = await call_ai_async(
        f"Facebook event: {event}. Analysis: {analyze}\n\n"
        "Step 3 — DRAFT: What specific action should be taken? "
        "Be concrete (e.g., 'Like the post', 'Reply with X', 'No action needed').",
        SYSTEM_PROMPT,
    )

    validate = await call_ai_async(
        f"Recommendation: {draft_raw}\n\nStep 4 — VALIDATE: Sound? Confidence?",
        SYSTEM_PROMPT,
    )

    cot_steps = {"think": think, "analyze": analyze, "draft": draft_raw, "validate": validate}
    confidence = "medium"

    suggestion = (
        f"**Facebook Notification Action ({event}):**\n\n"
        f"{draft_raw}"
    )
    approval_meta = {"event": event, "action": "facebook_notification_response"}

    return cot_steps, suggestion, approval_meta, confidence


async def process_manual(instruction: str) -> tuple[dict, str, dict]:
    """CoT for manual chat instructions."""
    log(f"🗣 Processing manual instruction: {instruction[:60]}...")

    think = await call_ai_async(
        f"Manual instruction from user: {instruction}\n\n"
        "Step 1 — THINK: What is the user asking me to do? What context is needed?",
        SYSTEM_PROMPT,
    )

    analyze = await call_ai_async(
        f"Instruction: {instruction}\nContext: {think}\n\n"
        "Step 2 — ANALYZE: What are the steps to fulfill this? Any risks?",
        SYSTEM_PROMPT,
    )

    draft_raw = await call_ai_async(
        f"Instruction: {instruction}\nAnalysis: {analyze}\n\n"
        "Step 3 — DRAFT: Provide a concrete response or action plan.",
        SYSTEM_PROMPT,
    )

    validate = await call_ai_async(
        f"Plan: {draft_raw}\n\nStep 4 — VALIDATE: Complete and appropriate? Confidence?",
        SYSTEM_PROMPT,
    )

    cot_steps = {"think": think, "analyze": analyze, "draft": draft_raw, "validate": validate}
    suggestion = f"**Response to Manual Instruction:**\n\n{draft_raw}"
    approval_meta = {"action": "manual_instruction"}

    return cot_steps, suggestion, approval_meta, "medium"


# ─── Ralph Wiggum Loop ────────────────────────────────────────────────────────

async def ralph_wiggum_loop(filepath: Path, task_id: str, frontmatter: dict, body: str, force: bool = False):
    """
    Ralph Wiggum Loop — persists until task is complete.
    Named after the tenacious persistence of Ralph Wiggum.
    Runs up to MAX_ITERATIONS times, checking completion state each iteration.
    """
    task_type = frontmatter.get("type", "unknown")
    log(f"🔁 Ralph Wiggum Loop starting: {task_id} (type={task_type}, max={MAX_ITERATIONS} iterations)")

    for iteration in range(1, MAX_ITERATIONS + 1):
        log(f"  Iteration {iteration}/{MAX_ITERATIONS}")

        # ── Completion checks ─────────────────────────────────────────────
        if is_in_done(filepath.name):
            log(f"  ✓ Task already in /Done. Loop complete.")
            return

        # ── Plan caching ──────────────────────────────────────────────────
        if not force and iteration == 1:
            cached = find_cached_plan(task_id)
            if cached:
                log(f"  ✓ Plan already exists: {cached.name}. Skipping re-generation.")
                log(f"  Use --force to override.")
                await move_to_done(filepath, note="Cached plan reused")
                return

        # ── Run one CoT cycle ─────────────────────────────────────────────
        try:
            cot_steps   = {}
            suggestion  = ""
            approval_meta = {}
            confidence  = "medium"
            needs_reply = True
            action_type = task_type
            mcp_endpoint = ""

            if task_type == "email":
                cot_steps, suggestion, approval_meta, confidence, needs_reply = await process_email(frontmatter, body)
                action_type  = "email"
                mcp_endpoint = "send-email"

            elif task_type == "whatsapp_reply":
                cot_steps, suggestion, approval_meta, confidence = await process_whatsapp(frontmatter, body)
                action_type  = "whatsapp"
                mcp_endpoint = "send-whatsapp"
                needs_reply  = True

            elif task_type == "facebook_friend_request":
                cot_steps, suggestion, approval_meta, confidence = await process_facebook_friend_request(frontmatter, body)
                action_type  = "facebook_friend_request"
                mcp_endpoint = "accept-friend-facebook"
                needs_reply  = True

            elif task_type == "facebook_message":
                cot_steps, suggestion, approval_meta, confidence = await process_facebook_message(frontmatter, body)
                action_type  = "facebook_message"
                mcp_endpoint = "send-facebook-message"  # Fixed endpoint
                needs_reply  = True

            elif task_type == "facebook_post":
                cot_steps, suggestion, approval_meta, confidence = await process_facebook_post(frontmatter, body)
                action_type  = "facebook_post"
                mcp_endpoint = "post-facebook"
                needs_reply  = True

            elif task_type == "facebook_notification":
                cot_steps, suggestion, approval_meta, confidence = await process_facebook_notification(frontmatter, body)
                action_type  = "facebook_notification"
                mcp_endpoint = "post-facebook"
                needs_reply  = True

            elif task_type in ("manual", "unknown"):
                instruction = body or frontmatter.get("instruction", "No instruction provided.")
                
                # Intent Detection for Facebook Posting
                if "facebook" in instruction.lower() and ("post" in instruction.lower() or "status" in instruction.lower()):
                     log(f"  ↪ Redirecting manual instruction to Facebook Post logic")
                     task_type = "facebook_post" # switch type for next loop or just handle here (recursive call better or just inline?)
                     # Inline handling:
                     frontmatter["topic"] = instruction
                     cot_steps, suggestion, approval_meta, confidence = await process_facebook_post(frontmatter, instruction)
                     action_type = "facebook_post"
                     mcp_endpoint = "post-facebook"
                else:
                    cot_steps, suggestion, approval_meta, confidence = await process_manual(instruction)
                    action_type  = "manual"
                    mcp_endpoint = ""
                
                needs_reply  = True

            else:
                log(f"  ⚠ Unknown task type: {task_type}. Running generic CoT.")
                cot_steps, suggestion, approval_meta, confidence = await process_manual(body or str(frontmatter))
                action_type  = task_type
                mcp_endpoint = ""
                needs_reply  = True

            # ── Write Plan ────────────────────────────────────────────────
            plan_path = await write_plan(task_id, cot_steps, suggestion, task_type)

            # ── Write Pending Approval (for sensitive actions) ─────────────
            if needs_reply:
                reasoning = cot_steps.get("analyze", "") + "\n\n" + cot_steps.get("validate", "")
                content   = cot_steps.get("draft", suggestion)

                await create_approval_request(
                    action_type=action_type,
                    content=content,
                    metadata=approval_meta,
                    reasoning=reasoning,
                    mcp_endpoint=mcp_endpoint,
                    confidence=confidence,
                )

            # ── Update Dashboard ──────────────────────────────────────────
            await update_dashboard(
                f"Processed {task_type} task `{filepath.name}`. "
                f"Plan: `{plan_path.name}`. Confidence: {confidence}."
            )

            # ── Move to Done ──────────────────────────────────────────────
            await move_to_done(filepath, note=f"Processed in iteration {iteration}")
            log(f"✅ Task complete after {iteration} iteration(s).")
            return

        except Exception as e:
            log(f"  ✗ Iteration {iteration} error: {e}")
            if iteration == MAX_ITERATIONS:
                log(f"  ✗ Max iterations reached. Marking as error.")
                await move_to_done(filepath, note=f"ERROR after {MAX_ITERATIONS} iterations: {e}")
                return
            wait = RETRY_BASE_DELAY * (2 ** (iteration - 1))
            log(f"  Retrying in {wait}s...")
            await asyncio.sleep(wait)


# ─── Execution Mode (Approved Actions) ───────────────────────────────────────

async def execute_approved(filepath: Path):
    """Execute an approved action via MCP server."""
    frontmatter, body = await read_task_file(filepath)
    task_type    = frontmatter.get("type", "unknown")
    mcp_endpoint = frontmatter.get("suggested_mcp_endpoint", "")

    log(f"⚡ Executing approved action: {task_type} → {mcp_endpoint}")

    if task_type == "email":
        payload = {
            "to":      frontmatter.get("target", ""),
            "subject": frontmatter.get("subject", "Re: Your message"),
            "body":    body,
        }
        success = call_mcp("send-email", payload)

    elif task_type == "whatsapp":
        payload = {
            "contact": frontmatter.get("target", ""),
            "message": body,
        }
        success = call_mcp("send-whatsapp", payload)

    elif task_type == "facebook_friend_request":
        person = frontmatter.get("person", "next")
        decision = frontmatter.get("decision", "ACCEPT")
        if "ACCEPT" in decision.upper():
            success = call_mcp("accept-friend-facebook", {"user_id": person})
        else:
            log(f"Decision is REJECT — no MCP action taken.")
            success = True

    elif task_type == "facebook_message":
        payload = {"content": body}
        success = call_mcp("post-facebook", payload)

    else:
        log(f"⚠ No execution handler for type: {task_type}. Logged only.")
        success = True

    status = "SUCCESS" if success else "FAILED"
    log(f"⚡ Execution {status}")

    # Move to Done
    DONE_DIR.mkdir(exist_ok=True)
    dest = DONE_DIR / filepath.name
    if dest.exists():
        dest.unlink()
    filepath.rename(dest)
    log(f"✓ Moved executed file to Done: {filepath.name}")


# ─── Chat Mode ────────────────────────────────────────────────────────────────

async def chat_mode():
    """Interactive manual instruction mode."""
    log("🗣 CHAT MODE — Enter instructions manually.")
    log("Type 'exit' or 'quit' to stop.\n")

    NEEDS_ACTION_DIR.mkdir(exist_ok=True)

    while True:
        try:
            instruction = input("Your instruction: ").strip()
        except (EOFError, KeyboardInterrupt):
            log("\n👋 Chat mode stopped.")
            break

        if instruction.lower() in ("exit", "quit", ""):
            log("👋 Chat mode stopped.")
            break

        # Create a synthetic task file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_file = NEEDS_ACTION_DIR / f"{timestamp}_manual_chat.md"
        task_file.write_text(
            f"---\ntype: manual\ninstruction: \"{instruction}\"\nreceived: \"{datetime.now().isoformat()}\"\n---\n\n{instruction}\n",
            encoding="utf-8",
        )
        log(f"📝 Created task: {task_file.name}")

        # Process it
        frontmatter, body = await read_task_file(task_file)
        task_id = task_file.stem
        await ralph_wiggum_loop(task_file, task_id, frontmatter, body)

        log("\n─── Ready for next instruction ───\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def async_main(args):
    # Chat mode
    if getattr(args, "chat", False):
        await chat_mode()
        return

    filepath = Path(args.filepath).resolve()

    if not filepath.exists():
        log(f"✗ File not found: {filepath}")
        sys.exit(1)

    log(f"\n{'='*60}")
    log(f"🧠 Processing: {filepath.name}")
    log(f"{'='*60}\n")

    # Execution mode (triggered by approval_watcher for approved files)
    if getattr(args, "execute", False):
        await execute_approved(filepath)
        return

    # Planning mode (normal)
    frontmatter, body = await read_task_file(filepath)
    task_id = filepath.stem
    await ralph_wiggum_loop(
        filepath,
        task_id,
        frontmatter,
        body,
        force=getattr(args, "force", False),
    )


def main():
    parser = argparse.ArgumentParser(description="Reasoning Loop — Async Optimized (Silver Tier)")
    subgroup = parser.add_mutually_exclusive_group()
    subgroup.add_argument("filepath", nargs="?", help="Path to task file in /Needs_Action")
    subgroup.add_argument("--chat", action="store_true", help="Interactive manual instruction mode")
    parser.add_argument("--execute", action="store_true", help="Execute an approved action via MCP")
    parser.add_argument("--force",   action="store_true", help="Re-run even if plan already exists")
    args = parser.parse_args()

    if not args.chat and not args.filepath:
        parser.print_help()
        sys.exit(1)

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        log("\n💤 Reasoning loop stopped.")
    except Exception as e:
        log(f"✗ Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
