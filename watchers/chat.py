import asyncio
import sys
import json
import time
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

# Configuration
HISTORY_ file = Path("Logs/chat_history.jsonl")
NEEDS_ACTION_DIR = Path("Needs_Action")
PENDING_DIR = Path("Pending_Approval")
APPROVED_DIR = Path("Approved")
DONE_DIR = Path("Done")
REJECTED_DIR = Path("Rejected")
RATE_LIMIT = 10  # commands per minute
RATE_WINDOW = 60 # seconds

# State
_history = []
_command_timestamps = []

def load_history():
    """Load last 20 messages from history file."""
    global _history
    if not HISTORY_file.exists():
        return
    try:
        with open(HISTORY_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-20:]:
                _history.append(json.loads(line))
    except Exception as e:
        print(f"Error loading history: {e}")

def save_history(role: str, content: str):
    """Append message to history file and in-memory list."""
    entry = {
        "ts": datetime.now().isoformat(),
        "role": role,
        "content": content
    }
    _history.append(entry)
    if len(_history) > 20:
        _history.pop(0)

    try:
        HISTORY_file.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Error saving history: {e}")

def check_rate_limit() -> bool:
    """Token bucket rate limiter."""
    global _command_timestamps
    now = time.monotonic()
    # Filter out timestamps older than window
    _command_timestamps = [t for t in _command_timestamps if now - t < RATE_WINDOW]

    if len(_command_timestamps) >= RATE_LIMIT:
        return False

    _command_timestamps.append(now)
    return True

async def wait_for_approval(task_id: str):
    """Poll for approval file, show content, ask user."""
    print(f"\n[System] Waiting for reasoning loop to plan '{task_id}'...")
    
    # Watch for Pending_Approval file
    approval_file = None
    for _ in range(60): # Wait up to 60s for plan
        approval_file = next(PENDING_DIR.glob(f"*{task_id}*"), None)
        if approval_file:
            break
        await asyncio.sleep(1)

    if not approval_file:
        print(f"[Error] Timeout waiting for plan. Check reasoning loop.")
        return

    # Show Plan
    content = approval_file.read_text(encoding="utf-8")
    print("\n" + "="*40)
    print("🤖 AI SUGGESTION")
    print("="*40)
    # Extract body - everything after second ---
    parts = content.split("---", 2)
    if len(parts) > 2:
        print(parts[2].strip())
    else:
        print(content)
    print("="*40)
    
    # Ask User
    while True:
        choice = await aio_input("\n[A]pprove | [R]eject | [S]kip > ")
        choice = choice.strip().lower()

        if choice == 'a':
            # Move to Approved
            target = APPROVED_DIR / approval_file.name
            approval_file.rename(target)
            print(f"[System] Approved! Executing via approval_watcher...")
            save_history("system", f"Approved task {task_id}")
            return
        elif choice == 'r':
             # Delete (Reject)
             target = REJECTED_DIR / approval_file.name
             approval_file.rename(target)
             print("[System] Rejected.")
             save_history("system", f"Rejected task {task_id}")
             return
        elif choice == 's':
            print("[System] Skipped.")
            return

async def aio_input(prompt: str = "") -> str:
    """Async input."""
    print(prompt, end="", flush=True)
    return await asyncio.to_thread(sys.stdin.readline)

async def process_command(cmd: str):
    """Process a single user command."""
    cmd = cmd.strip()
    if not cmd: return

    save_history("user", cmd)

    # Special Commands
    if cmd.startswith("@status"):
         print(f"Needs Action: {len(list(NEEDS_ACTION_DIR.glob('*.md')))}")
         print(f"Pending: {len(list(PENDING_DIR.glob('*.md')))}")
         print(f"Approved: {len(list(APPROVED_DIR.glob('*.md')))}")
         print(f"Done: {len(list(DONE_DIR.glob('*.md')))}")
         return
    
    if cmd.startswith("@history"):
        for h in _history[-5:]:
            print(f"[{h['ts'][:16]}] {h['role']}: {h['content']}")
        return

    if cmd.startswith("@help"):
        print("Commands: @status, @history, @help, exit")
        print("Example: 'Send email to john@example.com hello'")
        return

    # User Instruction -> Task
    if not check_rate_limit():
        print(f"[Error] Rate limit exceeded ({RATE_LIMIT}/min). Wait a moment.")
        return

    # Generate Task File
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_cmd = re.sub(r'[^a-zA-Z0-9]', '_', cmd[:20])
    task_id = f"{ts}_manual_{clean_cmd}"
    filename = NEEDS_ACTION_DIR / f"{task_id}.md"

    content = f"""---
type: manual
status: pending
created: "{datetime.now().isoformat()}"
priority: high
---
# Manual Instruction

**User Input:**
{cmd}

## 🤖 AI Instruction
1. Analyze the user's request.
2. Determine the correct MCP tool (email, whatsapp, facebook, etc).
3. Draft the content.
4. Create an approval request.
"""
    
    filename.write_text(content, encoding="utf-8")
    print(f"[System] Task created: {filename.name}")

    # Wait for result
    await wait_for_approval(task_id)

async def main():
    print("🤖 Silver Tier Chat Interface (v3)")
    print("Type your instruction or @help. Ctrl+C to exit.")
    
    load_history()
    
    # Create dirs if missing
    for d in [NEEDS_ACTION_DIR, PENDING_DIR, APPROVED_DIR, REJECTED_DIR, HISTORY_file.parent]:
        d.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            cmd = await aio_input("\n> ")
            if cmd.strip().lower() in ["exit", "quit"]:
                print("Bye!")
                break
            await process_command(cmd)
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"\n[Error] {e}")

if __name__ == "__main__":
    asyncio.run(main())
