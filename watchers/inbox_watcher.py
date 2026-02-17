import os
import shutil
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class InboxHandler(FileSystemEventHandler):
    """Handles file drop events in the Inbox folder."""
    
    def __init__(self, inbox_path, needs_action_path):
        self.inbox_path = inbox_path
        self.needs_action_path = needs_action_path
        
    def on_created(self, event):
        if event.is_directory:
            return
            
        # Handle new file creation in Inbox
        self.process_new_file(event.src_path)
        
    def on_moved(self, event):
        if event.is_directory:
            return
            
        # Handle file moves to the Inbox
        if self.is_in_inbox(event.dest_path):
            self.process_new_file(event.dest_path)
    
    def is_in_inbox(self, file_path):
        """Check if the file is in the inbox folder."""
        return os.path.dirname(file_path) == self.inbox_path
    
    def process_new_file(self, file_path):
        """Process a new file dropped in the inbox."""
        if not os.path.isfile(file_path):
            return
            
        # Extract file information
        original_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        timestamp = datetime.now().isoformat()
        
        # Copy the original file to Needs_Action with FILE_ prefix
        file_extension = os.path.splitext(original_name)[1]
        file_name_without_ext = os.path.splitext(original_name)[0]
        new_filename = f"FILE_{file_name_without_ext}{file_extension}"
        destination_path = os.path.join(self.needs_action_path, new_filename)
        
        # Copy the file
        shutil.copy2(file_path, destination_path)
        
        # Create the companion .md metadata file
        md_filename = f"FILE_{file_name_without_ext}.md"
        md_destination_path = os.path.join(self.needs_action_path, md_filename)
        
        # Create the metadata content with exact YAML frontmatter
        metadata_content = f"""---
type: file_drop
original_name: {original_name}
size: {file_size}
received: {timestamp}
priority: medium
status: pending
---
## File Drop for Processing

New file dropped into Inbox. Ready for analysis."""
        
        # Write the metadata file
        with open(md_destination_path, 'w', encoding='utf-8') as f:
            f.write(metadata_content)
        
        print(f"[WATCHER] File {original_name} copied to Needs_Action as {new_filename}")
        print(f"[WATCHER] Metadata created: {md_filename}")


class InboxWatcher:
    """Monitors the Inbox folder for new files."""
    
    def __init__(self, inbox_folder, needs_action_folder):
        self.inbox_folder = inbox_folder
        self.needs_action_folder = needs_action_folder
        self.observer = Observer()
        
    def start(self):
        """Start watching the Inbox folder."""
        event_handler = InboxHandler(
            inbox_path=self.inbox_folder,
            needs_action_path=self.needs_action_folder
        )
        
        self.observer.schedule(event_handler, self.inbox_folder, recursive=False)
        self.observer.start()
        print(f"[WATCHER] Started watching {self.inbox_folder}")
        print(f"[WATCHER] Will copy files to {self.needs_action_folder} with FILE_ prefix")
        
    def stop(self):
        """Stop watching the folder."""
        self.observer.stop()
        self.observer.join()
        print("[WATCHER] Stopped watching")


if __name__ == "__main__":
    # Define folder paths relative to current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    inbox_path = os.path.join(current_dir, "Inbox")
    needs_action_path = os.path.join(current_dir, "Needs_Action")
    
    # Verify folders exist
    if not os.path.exists(inbox_path):
        os.makedirs(inbox_path)
        print(f"[INFO] Created Inbox folder at {inbox_path}")
    
    if not os.path.exists(needs_action_path):
        os.makedirs(needs_action_path)
        print(f"[INFO] Created Needs_Action folder at {needs_action_path}")
    
    # Create the watcher
    watcher = InboxWatcher(inbox_path, needs_action_path)
    
    try:
        watcher.start()
        print("Inbox watcher is running. Press Ctrl+C to stop.")
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("\\nWatcher stopped by user.")