---
name: Watchers Integration
description: Learn how the AI's "Eyes" (Watchers) monitor external platforms and trigger the "Brain".
---

# Watchers Integration Skill

The "Watchers" are the sensory organs of the AI Employee. They monitor external platforms and create task files in `/Needs_Action` when important events occur.

## The Watchers

1.  **Gmail Watcher** (`gmail_watcher.py`)
    - **Function**: Checks for new unread emails every 60 seconds.
    - **Output**: Creates `.md` files in `/Needs_Action` for emails marked "IMPORTANT" or all unread (configurable).
    
2.  **WhatsApp Watcher** (`whatsapp_watcher.py`)
    - **Function**: Uses a browser to monitor WhatsApp Web for unread messages.
    - **Output**: Creates `.md` files for new messages.
    - **Note**: Requires a visible browser window.

3.  **LinkedIn Watcher** (`linkedin_watcher.py`)
    - **Function**: monitors LinkedIn Messaging for new DMs.
    - **Output**: Creates `.md` files for new messages.
    - **Note**: Requires a visible browser window.

## Managing the System

### Starting All Systems
Run the unified startup script:
```bash
start_silver_tier.bat
```
This launches:
- **Hands**: Email MCP Server
- **Brain**: Orchestrator
- **Eyes**: Gmail, WhatsApp, LinkedIn Watchers

### Stopping
- Close the individual terminal windows.
- Press `Ctrl+C` in the Orchestrator window.

## Workflow
1.  **Detection**: Watcher sees an event (e.g., new email).
2.  **Creation**: Watcher creates a file in `/Needs_Action` (e.g., `20240520_1000_gmail.md`).
3.  **Trigger**: Orchestrator detects the new file and launches `reasoning_loop.py`.
4.  **Action**: AI processes the file and may take action (Reply, Draft, etc.).
