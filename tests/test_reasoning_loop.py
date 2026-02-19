import os
import time
import shutil
import sys
import subprocess

# Setup paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(BASE_DIR, "..")
NEEDS_ACTION_DIR = os.path.join(PROJECT_ROOT, "Needs_Action")
PLANS_DIR = os.path.join(PROJECT_ROOT, "Plans")
PENDING_APPROVAL_DIR = os.path.join(PROJECT_ROOT, "Pending_Approval")
DONE_DIR = os.path.join(PROJECT_ROOT, "Done")
REASONING_LOOP_SCRIPT = os.path.join(PROJECT_ROOT, "watchers", "reasoning_loop.py")

def setup_dirs():
    for d in [NEEDS_ACTION_DIR, PLANS_DIR, PENDING_APPROVAL_DIR, DONE_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)

def create_test_task():
    filename = "test_email_task.md"
    filepath = os.path.join(NEEDS_ACTION_DIR, filename)
    content = """---
type: email
from: "test@example.com"
subject: "Urgent: System Down"
priority: high
received: "2024-01-01T12:00:00"
status: pending
---

## Email Details

System is down. Please fix immediately.
"""
    with open(filepath, "w") as f:
        f.write(content)
    return filepath

def run_reasoning_loop(filepath):
    print(f"Running reasoning loop on {filepath}...")
    cmd = [sys.executable, REASONING_LOOP_SCRIPT, filepath]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    return result.returncode == 0

def verify_results(task_filepath):
    task_filename = os.path.basename(task_filepath)
    
    # 1. Check if moved to Done
    done_path = os.path.join(DONE_DIR, task_filename)
    if not os.path.exists(done_path):
        print(f"❌ Task file not moved to Done: {done_path}")
        return False
    print(f"✅ Task moved to Done.")

    # 2. Check for Plan
    # Plans are named timestamp_taskname_plan.md, so we just check if *any* new plan was created recently
    plans = sorted([os.path.join(PLANS_DIR, f) for f in os.listdir(PLANS_DIR)], key=os.path.getmtime)
    if not plans:
        print("❌ No plans found.")
        return False
    latest_plan = plans[-1]
    print(f"✅ Plan created: {latest_plan}")

    # 3. Check for Approval Request
    approvals = sorted([os.path.join(PENDING_APPROVAL_DIR, f) for f in os.listdir(PENDING_APPROVAL_DIR)], key=os.path.getmtime)
    if not approvals:
        print("❌ No approval requests found.")
        return False
    latest_approval = approvals[-1]
    print(f"✅ Approval request created: {latest_approval}")
    
    return True

if __name__ == "__main__":
    setup_dirs()
    task_path = create_test_task()
    if run_reasoning_loop(task_path):
        if verify_results(task_path):
            print("\n🎉 Test Log: SUCCESS")
        else:
            print("\n❌ Test Log: FAILED Verification")
    else:
        print("\n❌ Test Log: FAILED Execution")
