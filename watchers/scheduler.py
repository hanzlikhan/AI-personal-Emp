"""
scheduler.py — Async Daemon Scheduler (Silver Tier)
=====================================================
Persistent asyncio loop that fires jobs on a cron-style schedule.

Features:
  - Declarative SCHEDULE table (add/remove jobs in one place)
  - Performance logging  → Logs/scheduler_perf.log
  - Auto-recovery        → 3 retries per job (1min → 2min → 4min back-off)
  - Alert injection      → creates /Needs_Action alert if all retries exhausted
  - CEO Daily Briefing   → injected at 08:55 each morning
  - --simulate           → run all jobs immediately (testing)
  - --daemon             → persistent loop  (Windows Task Scheduler)
  - --watchdog           → check daemon alive, restart if not
  - --once               → single-run (legacy support)

Windows Task Scheduler setup:  run setup_scheduler.bat (once, as Admin)
"""

import os
import sys
import asyncio
import subprocess
import argparse
import time
import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Awaitable

# ─── Windows UTF-8 ───────────────────────────────────────────────────────────
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR         = Path(__file__).resolve().parent
NEEDS_ACTION_DIR = BASE_DIR.parent / "Needs_Action"
DONE_DIR         = BASE_DIR.parent / "Done"
PLANS_DIR        = BASE_DIR.parent / "Plans"
PENDING_DIR      = BASE_DIR.parent / "Pending_Approval"
LOGS_DIR         = BASE_DIR.parent / "Logs"
PERF_LOG         = LOGS_DIR / "scheduler_perf.log"
DAEMON_PID_FILE  = BASE_DIR / ".scheduler.pid"

# ─── Config ───────────────────────────────────────────────────────────────────
MAX_JOB_RETRIES = 3    # attempts before alert
BASE_RETRY_MIN  = 1    # minutes; doubles each time (1 → 2 → 4)

# ─── Logging ─────────────────────────────────────────────────────────────────
def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg: str):
    try:
        print(f"[SCHED] [{ts()}] {msg}", flush=True)
    except UnicodeEncodeError:
        print(f"[SCHED] [{ts()}] {msg}".encode("ascii", errors="replace").decode(), flush=True)

def log_perf(job_name: str, elapsed: float, status: str, detail: str = ""):
    LOGS_DIR.mkdir(exist_ok=True)
    entry = json.dumps({
        "ts": datetime.now().isoformat(),
        "job": job_name,
        "elapsed_s": round(elapsed, 3),
        "status": status,
        "detail": detail,
    }, ensure_ascii=True)
    with open(PERF_LOG, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


# ─── Job Dataclass ─────────────────────────────────────────────────────────────
@dataclass
class Job:
    name:     str
    fn:       Callable[[], Awaitable[None]]
    every:    str           # "day" | "monday" | "tuesday" | ... | "friday" | "sunday"
    at:       str = "09:00" # "HH:MM" — 24-hour
    last_run: datetime = field(default=None, repr=False)

    def should_run(self, now: datetime) -> bool:
        """Return True if this job should fire right now (within 1-minute window)."""
        h, m = map(int, self.at.split(":"))
        if now.hour != h or now.minute != m:
            return False

        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
        }

        if self.every == "day":
            pass  # hour/minute already matched
        elif self.every in day_map:
            if now.weekday() != day_map[self.every]:
                return False
        else:
            return False

        # Deduplication: only fire once per scheduled slot
        if self.last_run and self.last_run.date() == now.date() and self.last_run.hour == h:
            return False

        return True


# ─── Task File Injection ──────────────────────────────────────────────────────
def inject_task(filename: str, content: str) -> Path:
    """Create a .md file in /Needs_Action (idempotent — skips if exists today)."""
    NEEDS_ACTION_DIR.mkdir(exist_ok=True)
    fp = NEEDS_ACTION_DIR / filename
    if fp.exists():
        log(f"  Task already exists today: {filename}  (skip)")
        return fp
    fp.write_text(content, encoding="utf-8")
    log(f"  [OK] Task injected: {filename}")
    return fp


def inject_alert(job_name: str, error: str):
    """Create an alert task if a job exhausts all retries."""
    ts_str   = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts_str}_ALERT_SCHEDULER_{job_name.replace(' ', '_')}.md"
    content  = (
        f"---\ntype: scheduler_alert\npriority: high\n"
        f"job: \"{job_name}\"\ncreated: \"{datetime.now().isoformat()}\"\n---\n\n"
        f"# ALERT: Scheduled Job Failed\n\n"
        f"**Job:** {job_name}\n"
        f"**Error:** {error}\n\n"
        f"Please investigate `Logs/scheduler_perf.log` for details.\n"
    )
    inject_task(filename, content)


# ─── Individual Job Functions ─────────────────────────────────────────────────

async def run_subprocess(script: str, args: list[str] = []) -> None:
    """Async subprocess runner — non-blocking."""
    cmd = [sys.executable, str(BASE_DIR / script)] + args
    log(f"  Running: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    if proc.returncode and proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace").strip()[-300:])
    if stdout:
        for line in stdout.decode(errors="replace").strip().splitlines()[-5:]:
            log(f"  > {line}")


async def job_gmail_check():
    """Run gmail_watcher.py --once."""
    await run_subprocess("gmail_watcher.py", ["--once"])


async def job_social_check():
    """Inject a daily social-check task (WhatsApp + Facebook) for orchestrator."""
    today = datetime.now().strftime("%Y%m%d")
    inject_task(
        f"{today}_Daily_Social_Check.md",
        f"---\ntype: general\npriority: normal\nstatus: pending\n"
        f"created: \"{datetime.now().isoformat()}\"\n---\n\n"
        "# Daily Social Check\n\n"
        "Please check WhatsApp and Facebook for new messages and notifications.\n"
        "Summarise any items requiring attention.\n"
    )


async def job_ceo_briefing():
    """Inject a CEO Daily Briefing task — summarises last 24h activity."""
    today     = datetime.now().strftime("%Y%m%d")
    date_str  = datetime.now().strftime("%A, %B %d %Y")
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()

    # Count recent files for context
    done_count    = len(list(DONE_DIR.glob("*.md")))    if DONE_DIR.exists()    else 0
    plans_count   = len(list(PLANS_DIR.glob("*.md")))   if PLANS_DIR.exists()   else 0
    pending_count = len(list(PENDING_DIR.glob("*.md"))) if PENDING_DIR.exists() else 0

    inject_task(
        f"{today}_CEO_Daily_Briefing.md",
        f"---\ntype: ceo_briefing\npriority: high\nstatus: pending\n"
        f"created: \"{datetime.now().isoformat()}\"\n---\n\n"
        f"# CEO Daily Briefing — {date_str}\n\n"
        f"## Context (auto-gathered at {ts()})\n"
        f"- Tasks completed (Done/): **{done_count}** files\n"
        f"- Plans generated (Plans/): **{plans_count}** files\n"
        f"- Pending approvals:        **{pending_count}** files\n\n"
        f"## Your Job\n"
        f"1. Summarise the most important actions taken since {yesterday[:10]}.\n"
        f"2. List any items in `/Pending_Approval` that need human review.\n"
        f"3. Suggest **3 priorities** for today.\n"
        f"4. Draft a brief status update suitable for a CEO morning email.\n"
    )


async def job_monday_briefing():
    """Inject Monday weekly briefing."""
    today = datetime.now().strftime("%Y%m%d")
    inject_task(
        f"{today}_Monday_Briefing.md",
        f"---\ntype: general\npriority: high\nstatus: pending\n"
        f"created: \"{datetime.now().isoformat()}\"\n---\n\n"
        "# Monday Weekly Briefing\n\n"
        "It is the start of the week. Please:\n"
        "1. Review any unresolved tasks from last week.\n"
        "2. Summarise pending emails and WhatsApp messages.\n"
        "3. Draft the week's action plan.\n"
        "4. Check /Pending_Approval for anything awaiting decision.\n"
    )


async def job_friday_facebook():
    """Inject a Friday Facebook post task."""
    today = datetime.now().strftime("%Y%m%d")
    inject_task(
        f"{today}_Friday_Facebook_Post.md",
        f"---\ntype: facebook_post\npriority: normal\nstatus: pending\n"
        f"context: \"End-of-Week Engagement\"\n"
        f"created: \"{datetime.now().isoformat()}\"\n---\n\n"
        "It is Friday! Draft an engaging Facebook post that:\n"
        "1. Wishes followers a great weekend.\n"
        "2. Highlights one achievement or tip from this week.\n"
        "3. Includes a question to drive engagement.\n"
        "Keep it warm and professional.\n"
    )


async def job_weekly_facebook_post():
    """Sunday — general weekly content post."""
    today = datetime.now().strftime("%Y%m%d")
    inject_task(
        f"{today}_Weekly_FB_Content.md",
        f"---\ntype: facebook_post\npriority: normal\nstatus: pending\n"
        f"context: \"Weekly Thought Leadership\"\n"
        f"created: \"{datetime.now().isoformat()}\"\n---\n\n"
        "Draft a Sunday thought-leadership Facebook post for a professional services brand.\n"
        "Topic: something insightful about productivity, AI, or business growth.\n"
        "Tone: inspiring, concise, 3-4 sentences + call to action.\n"
    )


# ─── Schedule Table ───────────────────────────────────────────────────────────
def build_schedule() -> list[Job]:
    return [
        Job("CEO Daily Briefing",    job_ceo_briefing,       every="day",      at="08:55"),
        Job("Daily Gmail Check",     job_gmail_check,        every="day",      at="09:00"),
        Job("Daily Social Check",    job_social_check,       every="day",      at="09:05"),
        Job("Monday Weekly Briefing",job_monday_briefing,    every="monday",   at="09:00"),
        Job("Friday Facebook Post",  job_friday_facebook,    every="friday",   at="09:00"),
        Job("Sunday FB Content",     job_weekly_facebook_post,every="sunday",  at="10:00"),
    ]


# ─── Job Runner with Retry ────────────────────────────────────────────────────
async def run_job_with_retry(job: Job) -> None:
    """Run a job with auto-recovery: up to MAX_JOB_RETRIES attempts."""
    last_error = None
    for attempt in range(1, MAX_JOB_RETRIES + 1):
        t_start = time.perf_counter()
        try:
            log(f">>> {job.name}  (attempt {attempt}/{MAX_JOB_RETRIES})")
            await job.fn()
            elapsed = time.perf_counter() - t_start
            log(f"<<< {job.name}  done in {elapsed:.2f}s [OK]")
            log_perf(job.name, elapsed, "ok")
            job.last_run = datetime.now()
            return
        except Exception as e:
            elapsed = time.perf_counter() - t_start
            last_error = str(e)
            log(f"    {job.name} attempt {attempt} FAILED ({elapsed:.1f}s): {e}")
            log_perf(job.name, elapsed, f"fail_attempt_{attempt}", last_error[:200])
            if attempt < MAX_JOB_RETRIES:
                wait_min = BASE_RETRY_MIN * (2 ** (attempt - 1))   # 1 → 2 → 4 min
                log(f"    Retrying in {wait_min} min...")
                await asyncio.sleep(wait_min * 60)
            else:
                log(f"    {job.name}: all {MAX_JOB_RETRIES} attempts exhausted.")
                log_perf(job.name, elapsed, "exhausted", last_error[:200])
                inject_alert(job.name, last_error)


# ─── Main Scheduler Loop ──────────────────────────────────────────────────────
async def scheduler_loop():
    """Persistent asyncio loop — checks every 60 seconds for jobs to fire."""
    schedule = build_schedule()
    log(f"Scheduler daemon started. {len(schedule)} jobs registered.")
    log(f"Jobs: {[j.name for j in schedule]}")

    # Write PID for watchdog
    DAEMON_PID_FILE.write_text(str(os.getpid()))

    while True:
        now = datetime.now()
        for job in schedule:
            if job.should_run(now):
                # Fire-and-forget — don't block the ticking loop
                asyncio.create_task(run_job_with_retry(job))
        await asyncio.sleep(60)  # tick every minute


# ─── Simulate Mode ────────────────────────────────────────────────────────────
async def simulate_all():
    """Run every job immediately — for testing."""
    log("SIMULATE MODE — running all jobs now...")
    schedule = build_schedule()
    for job in schedule:
        log(f"\n--- Simulating: {job.name} ---")
        await run_job_with_retry(job)
    log("\nSimulate complete. Check Needs_Action/ for injected tasks.")


# ─── Watchdog Mode ────────────────────────────────────────────────────────────
def watchdog_check():
    """Check if daemon is alive; restart if not."""
    if not DAEMON_PID_FILE.exists():
        log("Watchdog: PID file missing. Starting daemon...")
        _restart_daemon()
        return

    pid = int(DAEMON_PID_FILE.read_text().strip())
    alive = False
    try:
        os.kill(pid, 0)  # signal 0 = existence check
        alive = True
    except (OSError, ProcessLookupError):
        alive = False

    if alive:
        log(f"Watchdog: Daemon PID {pid} is alive. OK.")
    else:
        log(f"Watchdog: Daemon PID {pid} is dead. Restarting...")
        DAEMON_PID_FILE.unlink(missing_ok=True)
        _restart_daemon()


def _restart_daemon():
    """Spawn a new daemon process."""
    script = str(BASE_DIR / "scheduler.py")
    log(f"Watchdog: Launching: {sys.executable} {script} --daemon")
    subprocess.Popen(
        [sys.executable, script, "--daemon"],
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )
    log("Watchdog: Daemon restarted.")


# ─── Entry Point ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Silver Tier Async Scheduler")
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--daemon",   action="store_true", help="Run as persistent daemon (asyncio loop)")
    grp.add_argument("--simulate", action="store_true", help="Run all jobs immediately (test mode)")
    grp.add_argument("--watchdog", action="store_true", help="Check daemon alive; restart if not")
    grp.add_argument("--once",     action="store_true", help="Single-shot run (legacy)")
    args = parser.parse_args()

    if args.watchdog:
        watchdog_check()
        return

    if args.simulate:
        log("=== SIMULATE MODE ===")
        asyncio.run(simulate_all())
        return

    if args.daemon or args.once or len(sys.argv) == 1:
        # Default: daemon mode (or legacy --once treated as daemon for compat)
        log("=== DAEMON MODE ===")
        try:
            asyncio.run(scheduler_loop())
        except KeyboardInterrupt:
            log("Scheduler stopped (KeyboardInterrupt).")
            DAEMON_PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
