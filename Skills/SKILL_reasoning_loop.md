---
name: Reasoning Loop (Async + CoT)
description: Autonomous async decision-making loop with Chain of Thought, Ralph Wiggum persistence, and HITL approval.
---

# Reasoning Loop Skill (Async Optimized)

The **Reasoning Loop** is the "brain" of the Silver Tier AI Employee. It processes task files from `/Needs_Action` using a structured **Chain of Thought** approach, then routes suggestions to `/Plans` and sensitive actions to `/Pending_Approval` for human approval.

---

## ⚙️ How It Works

### Chain of Thought (CoT) — 4 Steps per Task

```
Step 1 — THINK:    What is this task? Who sent it? What's the context?
Step 2 — ANALYZE:  What action is needed? What tone/approach? Any risks?
Step 3 — DRAFT:    Generate the actual content (reply/post/decision).
Step 4 — VALIDATE: Is the draft appropriate? Confidence level?
```

### Ralph Wiggum Loop

```python
MAX_ITERATIONS = 10
for iteration in range(MAX_ITERATIONS):
    run CoT cycle
    if success or already_in_done: break
    else: retry with exponential back-off
```
- If a task fails after 10 iterations, it is moved to `/Done` with an error note.
- Named for its tenacious persistence.

### Plan Caching

Before processing, the loop checks `/Plans/` for an existing plan with the same task ID:
```python
cached = find_cached_plan(task_id)
if cached: skip re-processing → use --force to override
```

### API Retry

```
Attempt 1 → wait 5s
Attempt 2 → wait 10s
Attempt 3 → wait 20s
```
Model priority: **Gemini** → **Groq** → **Claude** → Mock fallback.

---

## 📋 Per-Service Suggestions

| Task Type | Plan.md Contains | Pending_Approval Action |
|-----------|-----------------|------------------------|
| `email` | Full reply body + subject | `send-email` via MCP |
| `whatsapp_reply` | Short natural reply | `send-whatsapp` via MCP |
| `facebook_friend_request` | ACCEPT/REJECT + reason | `accept-friend-facebook` |
| `facebook_message` | Reply suggestion | Facebook Messenger |
| `facebook_notification` | Recommended action | `post-facebook` |

---

## 📁 Directory Flow

```
/Needs_Action/*.md  →  reasoning_loop.py
                              ↓
                  /Plans/[timestamp]_[task]_plan.md  (CoT + suggestion)
                              ↓
                  /Pending_Approval/[type]_approval.md  (HITL)
                              ↓
              Human moves to /Approved → approval_watcher executes
                              ↓
                  /Done/[original_task].md
```

---

## 🛠️ Usage

```bash
# Auto-triggered by orchestrator:
python watchers/reasoning_loop.py Needs_Action/task.md

# Force re-run (ignore cached plan):
python watchers/reasoning_loop.py Needs_Action/task.md --force

# Execute approved action (called by approval_watcher):
python watchers/reasoning_loop.py Approved/approval.md --execute

# Manual chat mode:
python watchers/reasoning_loop.py --chat
```

---

## Pending_Approval File Structure

```yaml
---
type: email
status: pending_approval
confidence: high
suggested_mcp_endpoint: "send-email"
target: "client@example.com"
subject: "Re: Project Update"
---
# Approval Request — EMAIL
**AI Reasoning**: [Analysis + Validation from CoT]
**Proposed Content**: [Full email body]
> Move to /Approved to execute. Delete to reject.
```
