---
name: Scheduling
description: Async scheduler daemon — runs cron-style jobs with auto-recovery and performance logging.
---

# Scheduling Skill (Async Optimized)

The **Scheduler** (`watchers/scheduler.py`) is a persistent asyncio daemon. It fires jobs on a cron-style schedule, retries on failure, and injects tasks into `/Needs_Action` for the orchestrator to pick up.

---

## Schedule Table

| Job | When | Time |
|-----|------|------|
| CEO Daily Briefing | Every day | 08:55 |
| Daily Gmail Check | Every day | 09:00 |
| Daily Social Check (WA + FB) | Every day | 09:05 |
| Monday Weekly Briefing | Monday | 09:00 |
| Friday Facebook Post | Friday | 09:00 |
| Sunday FB Content Post | Sunday | 10:00 |

---

## Architecture

```
asyncio.run(scheduler_loop())
    ↓  tick every 60 seconds
  for job in SCHEDULE:
    if job.should_run(now):
      asyncio.create_task(run_job_with_retry(job))
            ↓
        run job (async subprocess or task injection)
            ↓
        on failure: retry x3 (1min → 2min → 4min back-off)
        on exhaustion: inject ALERT into /Needs_Action
            ↓
        log timing → Logs/scheduler_perf.log
```

---

## Auto-Recovery

```
Attempt 1 → fail → wait 1 min
Attempt 2 → fail → wait 2 min
Attempt 3 → fail → inject ALERT task into /Needs_Action
```

Alert file format:
```
Needs_Action/20260219_085500_ALERT_Daily_Gmail_Check.md
type: scheduler_alert | priority: high
```

---

## Performance Logging

Every job run appended to `Logs/scheduler_perf.log`:
```json
{"ts":"2026-02-19T09:00:01","job":"Daily Gmail Check","elapsed_s":12.3,"status":"ok"}
{"ts":"2026-02-19T09:05:01","job":"Daily Social Check","elapsed_s":0.1,"status":"ok"}
```

---

## Watchdog (Auto-Restart)

```
setup_scheduler.bat registers:
  SilverTierWatchdog → runs every 30 min
    → reads .scheduler.pid
    → if PID dead → re-spawns scheduler.py --daemon
```

---

## Adding a New Job

1. Write an async function:
```python
async def job_my_task():
    inject_task("20260219_My_Task.md", "---\ntype: general\n---\nDo the thing.")
```

2. Add to `build_schedule()`:
```python
Job("My Task", job_my_task, every="wednesday", at="14:00"),
```

---

## Commands

```powershell
# Test all jobs immediately
.venv\Scripts\python watchers\scheduler.py --simulate

# Run as daemon (normally done by Task Scheduler)
.venv\Scripts\python watchers\scheduler.py --daemon

# Check + restart daemon
.venv\Scripts\python watchers\scheduler.py --watchdog

# Register Task Scheduler (run as Admin, once)
watchers\setup_scheduler.bat
```

---

## CEO Daily Briefing

Injected at 08:55 each morning into `/Needs_Action/YYYYMMDD_CEO_Daily_Briefing.md`:

- Counts files in `/Done`, `/Plans`, `/Pending_Approval`
- Asks agent to: summarise yesterday, list pending approvals, suggest 3 priorities, draft status email
- Processed by `orchestrator.py` → `reasoning_loop.py` → CoT → `/Plans/` + `/Pending_Approval/`
