import os
import time
import sys
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

def start_orchestrator():
    """
    Starts the folder observer.
    """
    # Ensure directory exists
    if not os.path.exists(WATCH_FOLDER):
        os.makedirs(WATCH_FOLDER)
        print(f"[ORCHESTRATOR] Created missing directory: {WATCH_FOLDER}")

    event_handler = ActionHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    
    # Schedule Approval Watcher
    if ApprovalHandler:
        if not os.path.exists(APPROVED_DIR):
            os.makedirs(APPROVED_DIR)
        approval_handler = ApprovalHandler()
        observer.schedule(approval_handler, APPROVED_DIR, recursive=False)
        print(f"[ORCHESTRATOR] Watching {APPROVED_DIR} for approved tasks...")
    
    observer.start()
    
    print(f"[ORCHESTRATOR] 🧠 Agent Brain Active.")
    print(f"[ORCHESTRATOR] Watching {WATCH_FOLDER} for new tasks...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("[ORCHESTRATOR] 💤 Going to sleep.")
    
    observer.join()

if __name__ == "__main__":
    start_orchestrator()
