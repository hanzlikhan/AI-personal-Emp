---
name: Reasoning Loop
description: Async CoT brain — 4-step chain of thought, plan caching, model waterfall, time-tracking, Ralph Wiggum retry loop.
priority: 2
version: 3.0
updated: 2026-02-19
---

# Reasoning Loop Skill (v3 — Fully Optimized)

`watchers/reasoning_loop.py` is the AI brain. It processes `.md` task files from `/Needs_Action` using a 4-step async Chain-of-Thought (CoT) pipeline with plan caching, model waterfall, and full time tracking.

---

## Chain of Thought — 4 Steps

```
THINK    → Classify task type, extract sender/subject/urgency
ANALYZE  → Assess tone, relationship context, deadline sensitivity
DRAFT    → Generate specific content (email body / reply / decision / post)
VALIDATE → Review draft: quality, sensitivity flags, confidence scoring
```

Each step is a separate `async` AI call. Total cold-run time: **~15–25 s**.

### Model Waterfall (per CoT step)
```
1. Gemini 1.5 Flash  → fastest, default
2. Groq (llama3-70b) → fallback if Gemini fails
3. Claude Haiku      → fallback if Groq fails
4. Mock (template)   → always works, ~0.5 s — guarantees output
```

---

## Ralph Wiggum Loop (Self-Healing Retry)

```python
MAX_ITERATIONS = 10
RETRY_DELAYS   = [5, 10, 20, 40, 60]   # seconds (exp back-off, capped at 60)

for iteration in range(1, MAX_ITERATIONS + 1):
    t0 = time.monotonic()
    if task_in_done_folder(task_id): return   # idempotency guard

    try:
        plan = await run_cot_pipeline(task)    # THINK → ANALYZE → DRAFT → VALIDATE
        write_plan(plan)                        # /Plans/YYYYMMDD_task_plan.md
        write_approval(plan)                    # /Pending_Approval/YYYYMMDD_approval.md
        move_to_done(task)
        log_perf("reasoning_loop", time.monotonic()-t0, ok=True)
        return

    except Exception as e:
        delay = RETRY_DELAYS[min(iteration-1, len(RETRY_DELAYS)-1)]
        log_warning(f"Iteration {iteration} failed: {e} — retry in {delay}s")
        await asyncio.sleep(delay)

# All retries exhausted → archive with ERROR
move_to_done(task, note="ERROR: All 10 iterations failed")
log_perf("reasoning_loop", time.monotonic()-t0, ok=False)
```

---

## Plan Caching

Avoids re-processing already-planned tasks:

```python
async def check_cache(task_id: str) -> Path | None:
    t0 = time.monotonic()
    for plan_file in Path("Plans").glob(f"*{task_id}*"):
        log(f"[CACHE HIT] {plan_file} — skip CoT ({time.monotonic()-t0:.1f}ms)")
        return plan_file
    return None

# In main loop:
if cached := await check_cache(task_id):
    if not args.force:
        move_to_done(task)
        return   # ~5ms vs ~20s cold run
```

**Override:** `python reasoning_loop.py task.md --force`

---

## Per-Service CoT Focus

| Task Type | THINK | ANALYZE | DRAFT | VALIDATE |
|-----------|-------|---------|-------|----------|
| `email` | Sender intent, subject | Urgency (deadline?), tone | Full reply body + subject line | Length, disclosure check |
| `whatsapp_reply` | Preview sentiment | Brevity req., relationship | ≤ 3 sentences, casual | No sensitive info |
| `facebook_friend_request` | Mutual count, name | Authenticity signals | ACCEPT/REJECT + 1-line reason | Final confidence score |
| `facebook_message` | Sender context | Tone match | Messenger reply | Appropriate? |
| `ceo_briefing` | All folder counts | Priority items | Status summary + 3 priorities | Tone: executive |
| `manual` | Instruction intent | Scope, resources needed | Step-by-step plan | Flag if needs HITL |

---

## Output Files

### Plan → `/Plans/YYYYMMDD_HHMMSS_task_plan.md`
```yaml
---
status: planned
task_id: "20260219_email_from_john"
cot_model: "gemini"
cot_time_s: 18.4
created: "2026-02-19T09:00:18"
---
# Plan — Email from John Smith

## THINK
Sender: John Smith. Subject: Project deadline. Type: client email.

## ANALYZE
High urgency (Friday deadline mentioned). Professional tone required.

## DRAFT
Full reply body...

## VALIDATE
Confidence: HIGH. No sensitive data. Appropriate length.

## Execution Steps
1. Send reply to john@example.com via /send-email
```

### Approval → `/Pending_Approval/YYYYMMDD_HHMMSS_approval.md`
```yaml
---
type: email
status: pending_approval
confidence: high
cot_time_s: 18.4
suggested_mcp_endpoint: send-email
target: john@example.com
subject: "Re: Project Deadline"
created: "2026-02-19T09:00:18"
---

Hi John,

Thank you for your email. I'll have everything ready by Friday morning.

Best regards

---
> ✅ Move to /Approved/ to SEND  |  🗑 Delete to REJECT  |  ✏ Edit above to MODIFY
```

---

## Performance Metrics

Logged to `Logs/loop_perf.jsonl` after each run:
```json
{"ts":"2026-02-19T09:00:18","task":"email_john","model":"gemini","cot_s":18.4,"ok":true}
{"ts":"2026-02-19T09:01:05","task":"wa_sara","model":"groq","cot_s":6.1,"ok":true}
{"ts":"2026-02-19T09:01:08","task":"fb_ahmed","model":"mock","cot_s":0.5,"ok":true}
```

| Scenario | Time |
|----------|------|
| Plan cache hit (idempotency) | ~5 ms |
| Cold CoT — 4 calls (Gemini) | ~15–25 s |
| Fallback to Groq | ~6–10 s |
| Fallback to Mock | ~0.5 s (always succeeds) |

---

## CLI Commands

```bash
# Triggered by orchestrator (normal):
python watchers/reasoning_loop.py Needs_Action/task.md

# Force re-run (ignore plan cache):
python watchers/reasoning_loop.py Needs_Action/task.md --force

# Execute approved action immediately:
python watchers/reasoning_loop.py Approved/approval.md --execute

# Interactive chat mode:
python watchers/reasoning_loop.py --chat

# Run with specific model:
python watchers/reasoning_loop.py task.md --model groq
```

---

## Idempotency Guard

Before any processing:
```python
done_files = {f.stem for f in Path("Done").glob("*.md")}
if task_id in done_files:
    log(f"[SKIP] {task_id} already in Done/")
    return
```

Prevents double-processing if watcher fires twice for same file.
