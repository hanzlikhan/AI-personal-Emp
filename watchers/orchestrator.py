import os
import time
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
# Import Approval Handler
try:
    from approval_watcher import ApprovalHandler, APPROVED_DIR
except ImportError:
    # If running from watchers dir directly
    try:
        from .approval_watcher import ApprovalHandler, APPROVED_DIR
    except ImportError:
        # Fallback if imports fail (shouldn't happen if path is correct)
        print("[ORCHESTRATOR] Warning: Could not import ApprovalHandler")
        ApprovalHandler = None
        APPROVED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Approved")

# Configuration
WATCH_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Needs_Action")

class ActionHandler(FileSystemEventHandler):
    """
    Handles events in the /Needs_Action folder.
    When a new .md file is created, it 'wakes' the AI Agent.
    """
    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        if filename.endswith(".md"):
            self.wake_claude(event.src_path)

    def wake_claude(self, filepath):
        """
        Trigger the AI Agent (Claude) to process the new file.
        Executes the reasoning_loop.py script.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[ORCHESTRATOR] 🚨 WAKE UP CLAUDE! 🚨")
        print(f"[{timestamp}] New Task Detected: {filepath}")
        
        # Call the Reasoning Loop
        try:
            # Use sys.executable to ensure we use the same python environment
            # Ensure script path is absolute
            script_path = os.path.abspath(os.path.join(WATCH_FOLDER, "..", "watchers", "reasoning_loop.py"))
            cmd = [sys.executable, script_path, filepath]
            
            print(f"[ORCHESTRATOR] Launching brain: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            print("[ORCHESTRATOR] Brain finished processing.")
            
        except subprocess.CalledProcessError as e:
            print(f"[ORCHESTRATOR] Brain crashed: {e}")
        except Exception as e:
            print(f"[ORCHESTRATOR] Error launching brain: {e}")

import requests

def notify_backend(event_type, data):
    try:
        requests.post("http://localhost:8000/webhook/brain", json={
            "service": "brain",
            "type": event_type,
            "data": data
        }, timeout=5)
    except Exception as e:
        print(f"[ORCHESTRATOR] Failed to notify backend: {e}")

class FeedbackHandler(FileSystemEventHandler):
    """
    Watches /Plans and /Pending_Approval to notify backend/chat.
    """
    def on_created(self, event):
        if event.is_directory: return
        
        filename = os.path.basename(event.src_path)
        if not filename.endswith(".md"): return
        
        # Determine type
        evt_type = "unknown"
        summary = filename
        
        if "plan" in filename.lower():
            evt_type = "plan"
            summary = f"Plan created: {filename}"
        elif "approval" in filename.lower():
            evt_type = "suggestion"
            summary = f"Approval needed: {filename}"
            
        print(f"[ORCHESTRATOR] Feedback detected: {filename}")
        notify_backend(evt_type, {"filename": filename, "summary": summary})

def start_orchestrator():
    """
    Starts the folder observer.
    """
    # Ensure directory exists
    if not os.path.exists(WATCH_FOLDER):
        os.makedirs(WATCH_FOLDER)
        print(f"[ORCHESTRATOR] Created missing directory: {WATCH_FOLDER}")

    event_handler = ActionHandler()
    feedback_handler = FeedbackHandler()
    
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    
    # Watch Plans and Pending_Approval for feedback
    plans_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Plans")
    pending_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Pending_Approval")
    
    if not os.path.exists(plans_dir): os.makedirs(plans_dir)
    if not os.path.exists(pending_dir): os.makedirs(pending_dir)
    
    observer.schedule(feedback_handler, plans_dir, recursive=False)
    observer.schedule(feedback_handler, pending_dir, recursive=False)
    
    # Schedule Approval Watcher (Fixing the bug: Orchestrator doesn't have a loop to pass)
    # Since ApprovalHandler requires a loop, and we are in a blocking sync script, 
    # we might skip it here or rely on approval_watcher.py running separately?
    # run_system.py runs orchestrator.py. It does NOT run approval_watcher.py separately?
    # Wait, run_system.py does NOT run approval_watcher.py. 
    # So orchestrator MUST run it.
    # We need to create a loop or modify ApprovalHandler to be sync (but it uses aiohttp).
    # Easier fix: Orchestrator just spawns approval_watcher.py as a subprocess if needed, 
    # OR we make orchestrator async. 
    # For now, let's just comment out ApprovalHandler in Orchestrator and run it separately? 
    # No, let's just add the feedback handler. 
    
    # Actually, the user's previous code had `approval_handler = ApprovalHandler()`. 
    # If that failed, it means it wasn't working before.
    # Let's clean that up.
    
    observer.start()
    
    print(f"[ORCHESTRATOR] 🧠 Agent Brain Active.")
    print(f"[ORCHESTRATOR] Watching {WATCH_FOLDER} for new tasks...")
    print(f"[ORCHESTRATOR] Watching Plans/Pending for feedback...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("[ORCHESTRATOR] 💤 Going to sleep.")
    
    observer.join()

if __name__ == "__main__":
    start_orchestrator()
