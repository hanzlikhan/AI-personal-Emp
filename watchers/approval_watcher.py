import os
import time
import yaml
import subprocess
import sys
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPROVED_DIR = os.path.join(BASE_DIR, "..", "Approved")
DONE_DIR = os.path.join(BASE_DIR, "..", "Done")

class ApprovalHandler(FileSystemEventHandler):
    """
    Handles events in the /Approved folder.
    When a file is moved here, it executes the action.
    """
    def on_created(self, event):
        if event.is_directory:
            return
        
        filename = os.path.basename(event.src_path)
        if filename.endswith(".md"):
            self.process_approved_task(event.src_path)

    def process_approved_task(self, filepath):
        print(f"\n[APPROVAL] ✅ Approved Task Detected: {os.path.basename(filepath)}")
        
        try:
            # We no longer parse and switch here. We just pass the approved file back to the brain (reasoning_loop)
            # with the --execute flag. The brain knows what to do based on the file content.
            
            cmd = [
                sys.executable, os.path.join(BASE_DIR, "reasoning_loop.py"),
                filepath,
                "--execute"
            ]
            
            print(f"[APPROVAL] Triggering Execution via Brain: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

            # Move to Done
            if not os.path.exists(DONE_DIR):
                os.makedirs(DONE_DIR)
            
            final_path = os.path.join(DONE_DIR, os.path.basename(filepath))
            # Check if file still exists (reasoning_loop might NOT move it if we are just testing, 
            # but wait, reasoning_loop main block logic for --execute DOES NOT move file to done currently?
            # Let's check reasoning_loop again. 
            # My previous edit to reasoning_loop added execution logic but didn't explicitly move to done in that block.
            # However, approval_watcher previously moved it.
            # Let's keep the move here in approval_watcher for safety.
            
            if os.path.exists(filepath):
                 os.rename(filepath, final_path)
                 print(f"[APPROVAL] Task completed and moved to Done.")
            else:
                 print(f"[APPROVAL] File already moved or deleted.")

        except Exception as e:
            print(f"[APPROVAL] Error processing task: {e}")

def start_approval_watcher():
    if not os.path.exists(APPROVED_DIR):
        os.makedirs(APPROVED_DIR)
        
    event_handler = ApprovalHandler()
    observer = Observer()
    observer.schedule(event_handler, APPROVED_DIR, recursive=False)
    observer.start()
    
    print(f"[APPROVAL] Watching {APPROVED_DIR} for approved tasks...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_approval_watcher()
