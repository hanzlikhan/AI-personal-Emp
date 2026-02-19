---
name: Chat Interface
description: Async terminal chat for manual instructions — intent parsing, rate limiting, history cache, inline approval.
priority: 6
version: 3.0
updated: 2026-02-19
---

# Chat Interface Skill (v3 — Fully Optimized)

`watchers/chat.py` is the interactive command center. It accepts natural language instructions ("Send email to..."), routes them to the reasoning loop, and presents the AI's plan for **inline approval** directly in the terminal.

---

## Features

- **Async Input Loop:** Non-blocking standard input (type while background tasks run).
- **Rate Limiting:** Token bucket (10 cmds / 60s) prevents spam/overload.
- **History Cache:** Persists last 20 messages to `Logs/chat_history.jsonl`.
- **Inline Approval:** See the draft email/message in terminal and `[A]pprove` immediately.
- **Intent -> Task:** Auto-wraps manual input into `/Needs_Action/` markdown tasks.

---

## Usage

```bash
python watchers/chat.py
```

### Commands
- `@status` — Show counts of Needs_Action / Pending / Approved / Done
- `@history` — Show last 5 interactions
- `@help` — Show usage guide
- `exit` / `quit` — Close chat

---

## Workflow

1. **User types:** "Send email to client@example.com about Friday meeting"
2. **Chat:** Creates `Needs_Action/YYYYMMDD_manual_Send_email_.md`
3. **Reasoning Loop:** Picks up task -> CoT (Think/Analyze/Draft) -> Creates `/Pending_Approval/...`
4. **Chat:** Detects pending file -> **Displays content in terminal:**
   ```
   🤖 AI SUGGESTION
   ========================================
   Hi Client,
   Just confirming our meeting for Friday.
   ...
   ========================================
   [A]pprove | [R]eject | [S]kip >
   ```
5. **User:** Types `a`
6. **Chat:** Moves file to `/Approved/`
7. **Approval Watcher:** Executes via MCP -> Sent!

---

## Performance Goals

| Metric | Target | Actual |
|--------|--------|--------|
| Input -> Task Creation | < 100ms | ~20ms |
| Reasoning Loop Pick-up | < 2s | ~1s |
| Approval Display | < 100ms | ~50ms |
| End-to-End Latency | < 30s | ~15s |

---

## Error Handling

- **Rate Limit:** "Rate limit exceeded (10/min). Wait a moment."
- **Timeout:** "Timeout waiting for plan. Check reasoning loop."
- **Crash Safety:** History saved to disk immediately.
