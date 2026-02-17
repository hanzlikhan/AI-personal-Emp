import os
import json
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class DropFolderHandler(FileSystemEventHandler):
    """Handles file drop and modification events in the inbox folder."""
    
    def __init__(self, inbox_path, needs_action_path):
        self.inbox_path = inbox_path
        self.needs_action_path = needs_action_path
        # Dictionary to store file contents for comparison
        self.file_contents_cache = {}
        
        # Load initial file contents if they exist
        for filename in os.listdir(self.inbox_path):
            filepath = os.path.join(self.inbox_path, filename)
            if os.path.isfile(filepath):
                self._cache_file_content(filepath)
    
    def on_created(self, event):
        if event.is_directory:
            return
            
        # Handle new file creation
        self.process_new_file(event.src_path)
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Handle file modifications
        if self.is_in_inbox(event.src_path):
            self.process_modified_file(event.src_path)
    
    def on_moved(self, event):
        if event.is_directory:
            return
            
        # Handle file moves to the inbox
        if self.is_in_inbox(event.dest_path):
            self.process_new_file(event.dest_path)
    
    def is_in_inbox(self, file_path):
        """Check if the file is in the inbox folder."""
        return os.path.dirname(file_path) == self.inbox_path
    
    def _cache_file_content(self, file_path):
        """Cache the content of a file for later comparison."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.file_contents_cache[file_path] = content
        except Exception:
            # If we can't read the file, cache an empty string
            self.file_contents_cache[file_path] = ""
    
    def process_new_file(self, file_path):
        """Process a new file dropped in the inbox."""
        if not os.path.isfile(file_path):
            return
            
        # Cache the content of the new file
        self._cache_file_content(file_path)
            
        # Extract file information
        original_name = os.path.basename(file_path)
        file_ext = os.path.splitext(original_name)[1]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Create a new markdown file in Needs_Action
        new_filename = f"{original_name.replace(file_ext, '')}_{int(datetime.now().timestamp())}.md"
        new_filepath = os.path.join(self.needs_action_path, new_filename)
        
        # Create metadata and content
        content = f"""# {original_name} Processing Request

## Metadata
- Type: file_drop
- Original Name: {original_name}
- Timestamp: {timestamp}
- Status: pending
- Source Path: {file_path}

## Suggested Actions
- [ ] Review file contents
- [ ] Determine appropriate processing steps
- [ ] Execute required actions
- [ ] Update status to completed
- [ ] Move to Done folder when finished

## Notes
_Add any relevant notes or observations here_

## File Contents Preview
```
{self.read_file_preview(file_path)}
```

---
_Processed by File System Watcher at {timestamp}_
"""
        
        # Write the new file
        with open(new_filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            
        print(f"[WATCHER] Created processing request for {original_name} -> {new_filename}")
    
    def process_modified_file(self, file_path):
        """Process a file that has been modified in the inbox."""
        if not os.path.isfile(file_path):
            return
            
        # Get the current content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception:
            current_content = "[Binary file or unreadable content]"
        
        # Get the previous content from cache
        previous_content = self.file_contents_cache.get(file_path, "")
        
        # Check if content actually changed
        if current_content != previous_content:
            # Update the cache with the new content
            self.file_contents_cache[file_path] = current_content
            
            # Extract file information
            original_name = os.path.basename(file_path)
            file_ext = os.path.splitext(original_name)[1]
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Create a new markdown file in Needs_Action for the modification
            new_filename = f"{original_name.replace(file_ext, '')}_MODIFIED_{int(datetime.now().timestamp())}.md"
            new_filepath = os.path.join(self.needs_action_path, new_filename)
            
            # Create metadata and content highlighting the changes
            content = f"""# {original_name} Modification Detected

## Metadata
- Type: file_modification
- Original Name: {original_name}
- Timestamp: {timestamp}
- Status: pending
- Source Path: {file_path}

## Change Summary
- File was modified in the Inbox
- Previous size: {len(previous_content)} characters
- Current size: {len(current_content)} characters

## Suggested Actions
- [ ] Review the changes made to the file
- [ ] Determine if the modifications require action
- [ ] Validate the updated content
- [ ] Process the modified file as needed
- [ ] Update status to completed when reviewed

## Notes
_Add any relevant notes about the changes made_

## Previous Content Preview
```
{self._get_content_preview(previous_content)}
```

## Current Content Preview
```
{self._get_content_preview(current_content)}
```

## Changes Identified
- Content of the file has been altered
- Review the differences above to understand what changed

---
_Processed by File System Watcher at {timestamp}_
"""
            
            # Write the new file
            with open(new_filepath, 'w', encoding='utf-8') as f:
                f.write(content)
                
            print(f"[WATCHER] Created modification notice for {original_name} -> {new_filename}")
        else:
            # Content didn't actually change, just update the cache
            self._cache_file_content(file_path)
    
    def _get_content_preview(self, content, max_lines=10):
        """Get a preview of content with proper handling of different content types."""
        if content.startswith("[Binary file") or content == "[Binary file or unreadable content]":
            return content
            
        lines = content.split('\n')
        if len(lines) <= max_lines:
            return content
        else:
            return '\n'.join(lines[:max_lines]) + "\n... (truncated)"
    
    def read_file_preview(self, file_path, max_lines=10):
        """Read a preview of the file contents."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append("... (truncated)")
                        break
                    lines.append(line.rstrip())
                return "\n".join(lines)
        except Exception:
            # If we can't read as text, return a binary indicator
            return "[Binary file - content not readable as text]"


class BaseWatcher:
    """Base class for file system watchers."""
    
    def __init__(self, watch_folder, needs_action_folder):
        self.watch_folder = watch_folder
        self.needs_action_folder = needs_action_folder
        self.observer = Observer()
        
    def start(self):
        """Start watching the folder."""
        event_handler = DropFolderHandler(
            inbox_path=self.watch_folder,
            needs_action_path=self.needs_action_folder
        )
        
        self.observer.schedule(event_handler, self.watch_folder, recursive=False)
        self.observer.start()
        print(f"[WATCHER] Started watching {self.watch_folder}")
        print(f"[WATCHER] Will create processing requests in {self.needs_action_folder}")
        
    def stop(self):
        """Stop watching the folder."""
        self.observer.stop()
        self.observer.join()
        print("[WATCHER] Stopped watching")


if __name__ == "__main__":
    # Define folder paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    inbox_path = os.path.join(current_dir, "..", "Inbox")
    needs_action_path = os.path.join(current_dir, "..", "Needs_Action")
    
    # Create the watcher
    watcher = BaseWatcher(inbox_path, needs_action_path)
    
    try:
        watcher.start()
        print("File system watcher is running. Press Ctrl+C to stop.")
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("\nWatcher stopped by user.")