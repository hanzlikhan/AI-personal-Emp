# Bronze Tier Setup Instructions

## Installation
Run this command to install required packages:

```bash
pip install watchdog
```

## Running the File System Watcher
To start the watcher, run:

```bash
python watchers/filesystem_watcher.py
```

## Testing the Full Flow
1. Open another terminal/command prompt in the same directory
2. Create a test file in the Inbox:
   ```bash
   echo "Test file for processing" > Inbox/test_file.txt
   ```
3. Check that a corresponding .md file was created in Needs_Action
4. The watcher should have detected the file and created a processing request

## Verifying the System Works
- Check that a new .md file appeared in the Needs_Action folder
- Verify the file contains proper metadata and suggested actions
- The system should be monitoring for new files continuously

## Stopping the Watcher
Press Ctrl+C in the terminal where the watcher is running to stop it.

## Additional Notes
- The watcher runs continuously until stopped
- All file events in the Inbox folder are monitored
- Processing requests are created automatically in Needs_Action
- Remember to implement the ProcessNeedsAction skill to handle the requests