---
name: Scheduling
description: Async scheduler daemon — cron-style jobs, 3-retry auto-recovery, health check watchdog, Windows Task Scheduler, performance logging.
priority: 5
version: 3.0
updated: 2026-02-19
---

# Scheduling Skill (v3 — Fully Optimized)

`watchers/scheduler.py` is a persistent `asyncio` daemon. It fires jobs on a cron-style schedule, retries failures automatically (3×), emits performance logs, and is kept alive by a Windows Task Scheduler watchdog every 30 minutes.

---

## Job Schedule

| Job | Day | Time (local) | Action |
|-----|-----|-------------|--------|
| CEO Daily Briefing | Every day | 08:55 | Injects `ceo_briefing` task with live folder counts |
| Daily Gmail Check | Every day | 09:00 | Spawns `gmail_watcher.py --once` |
| Daily Social Check | Every day | 09:05 | Injects WA + FB check task into `/Needs_Action` |
| Monday Briefing | Monday | 09:00 | Injects weekly planning task |
| Friday Facebook Post | Friday | 09:00 | Injects FB engagement post task |
| Sunday FB Content | Sunday | 10:00 | Injects thought-leadership post task |

---

## Job Implementation Pattern

```python
async def run_job(job: Job):
    t0 = time.monotonic()
    last_run = _job_last_run.get(job.name)
    now = datetime.now()

    # Missed-run detection
    if last_run and (now - last_run).total_seconds() > job.expected_interval_s * 1.5:
        log_warning(f"[SCHEDULER] {job.name} — missed expected run, running now")

    for attempt in range(1, 4):   # 3 attempts
        try:
            await job.fn()
            _job_last_run[job.name] = now
            elapsed = time.monotonic() - t0
            log_perf(job.name, elapsed, ok=True)
            return

        except Exception as e:
            delay = attempt * 60   # 1 min → 2 min → 3 min
            log_warning(f"{job.name} attempt {attempt} failed: {e} — retry in {delay}s")
            if attempt < 3:
                await asyncio.sleep(delay)

    # All 3 attempts failed
    inject_alert(job.name)   # inject ALERT_SCHEDULER_*.md into /Needs_Action
    log_perf(job.name, time.monotonic()-t0, ok=False)
```

---

## Auto-Recovery (3 Retries per Job)

```
Attempt 1 → fail → wait 1 min  (transient issue — network/API)
Attempt 2 → fail → wait 2 min  (longer outage)
Attempt 3 → fail → wait 3 min  (last chance)
All 3 fail → inject ALERT_SCHEDULER_{JOB}.md → /Needs_Action/
```

Alert file format:
```yaml
---
type: scheduler_alert
job: "Daily Gmail Check"
status: failed
attempts: 3
failed_at: "2026-02-19T09:03:00"
priority: high
---
## Scheduler Alert
Job "Daily Gmail Check" failed all 3 attempts.
Please check network connectivity and Gmail API token.
```

The `reasoning_loop.py` surfaces this in the CEO Daily Briefing.

---

## CEO Daily Briefing (08:55) — Live Counts

```python
async def job_ceo_briefing():
    counts = {
        "done":     len(list(Path("Done").glob("*.md"))),
        "plans":    len(list(Path("Plans").glob("*.md"))),
        "pending":  len(list(Path("Pending_Approval").glob("*.md"))),
        "needs_action": len(list(Path("Needs_Action").glob("*.md"))),
    }
    inject_task("ceo_briefing", counts)
```

Injected task:
```markdown
---
type: ceo_briefing
priority: high
date: "Thursday, February 19 2026"
done_count: 21
plans_count: 29
pending_count: 9
needs_action_count: 3
---
# CEO Daily Briefing — Thursday, February 19 2026

- ✅ Tasks completed (Done/): 21
- 📋 Plans generated (Plans/): 29
- ⏳ Pending approvals: 9
- 🔔 In queue (Needs_Action/): 3

## Your Job
1. Summarise key actions since yesterday
2. List Pending_Approval items needing urgent review
3. Suggest 3 priorities for today
4. Flag any scheduler ALERT files from last 24h
5. Draft morning status email for CEO (optional)
```

---

## Performance Logging → `Logs/scheduler_perf.log`

```json
{"ts":"2026-02-19T08:55:01","job":"CEO Daily Briefing","elapsed_s":0.05,"ok":true,"attempt":1}
{"ts":"2026-02-19T09:00:12","job":"Daily Gmail Check","elapsed_s":14.3,"ok":true,"attempt":1}
{"ts":"2026-02-19T09:05:00","job":"Daily Social Check","elapsed_s":0.04,"ok":true,"attempt":1}
{"ts":"2026-02-19T09:00:00","job":"Friday Facebook Post","elapsed_s":0.03,"ok":true,"attempt":1}
```

Used by CEO Briefing to surface job health and performance trends.

---

## Watchdog (Windows Task Scheduler)

**Purpose:** Ensures `scheduler.py` daemon is always alive.

```
SilverTierWatchdog task runs every 30 minutes:
    1. Read watchers/.scheduler.pid
    2. os.kill(pid, 0)  → existence check (no signal sent)
    3. Alive  → log "OK" to Logs/watchdog.log
    4. Dead   → re-spawn: python watchers/scheduler.py --daemon
               → write new PID to .scheduler.pid
               → log "RESTARTED" to Logs/watchdog.log
```

Watchdog log:
```json
{"ts":"2026-02-19T09:30:00","watchdog":"scheduler","pid":1234,"status":"alive"}
{"ts":"2026-02-19T10:00:00","watchdog":"scheduler","pid":1234,"status":"dead","action":"restarted","new_pid":5678}
```

---

## Adding a New Job

```python
# 1. Define async function
async def job_weekly_report():
    inject_task("weekly_report", {
        "type": "weekly_briefing",
        "priority": "high"
    })

# 2. Register in build_schedule()
Job(name="Weekly Report", fn=job_weekly_report, every="monday", at="08:00"),

# 3. No other changes needed — scheduler auto-handles retry, logging, watchdog
```

---

## CLI Commands

```powershell
# Simulate all jobs immediately (test without waiting)
python watchers/scheduler.py --simulate

# Run as persistent daemon
python watchers/scheduler.py --daemon

# Run watchdog check (check/restart if dead)
python watchers/scheduler.py --watchdog

# Register watchdog in Windows Task Scheduler (Admin — run once)
watchers/setup_scheduler.bat
```

---

## Health Checks

```powershell
# Did jobs run today?
Get-Content Logs\scheduler_perf.log | Select-String "$(Get-Date -Format yyyy-MM-dd)"

# Is the daemon alive?
python watchers/scheduler.py --watchdog

# View last 20 perf entries:
Get-Content -Tail 20 Logs\scheduler_perf.log
```

---

## Performance Targets

| Metric | Target | Actual |
|--------|--------|--------|
| Job schedule accuracy | ± 60 s | ± 60 s |
| CEO Briefing inject | < 1 s | ~0.05 s |
| Gmail single-shot | < 30 s | ~14 s |
| Job retry decision | < 5 s | ~1 s |
| Watchdog detect + restart | < 2 min | ~1 min |
