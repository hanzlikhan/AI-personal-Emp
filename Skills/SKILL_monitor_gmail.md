---
name: Monitor Gmail
description: Monitor Gmail for new emails, detect urgent items, and trigger agent action.
triggers: "New email detected in Gmail, or scheduled check"
author: AI Employee
version: 1.0
---

# Monitor Gmail

## Description
This skill outlines the process for monitoring the Gmail inbox using the `gmail_watcher.py` script. It detects new emails, prioritizes them based on keywords (e.g., 'urgent', 'payment'), and acts as a generic sensing mechanism for the AI Agent.

## Components
- **Script**: `watchers/gmail_watcher.py`
- **Output**: Creates markdown files in `/Needs_Action/[timestamp]_gmail.md`
- **Key Files**: `credentials.json`, `token.pickle` (for authentication)

## Process
1. **Daemon Mode**: Run `python watchers/gmail_watcher.py` in the background.
2. **Detection**: The script polls the Gmail API for unread messages.
3. **Action**:
   - If an email is found, it extracts the sender, subject, and body.
   - A standardized markdown file is created in `/Needs_Action`.
   - The file includes frontmatter with `type: email` and `priority`.
4. **Trigger**: The creation of the file wakes the Orchestrator (and thus the Agent) to process the email.

## Manual Execution
To manually run a check:
```bash
python watchers/gmail_watcher.py
```

## AI Agent Responsibility
- **Review**: When woken by a new email task, read the `.md` file in `/Needs_Action`.
- **Analyze**: Determine if a response is needed or if it requires human approval.
- **Act**: Draft a response (using `gmail_watcher.py` functions or manual composition) or move to `/Pending_Approval`.
