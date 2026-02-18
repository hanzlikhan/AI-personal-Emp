---
name: Monitor LinkedIn
description: Monitor LinkedIn for messages and notifications.
triggers: "New LinkedIn message or notification"
author: AI Employee
version: 1.0
---

# Monitor LinkedIn

## Description
This skill leverages `watchers/linkedin_watcher.py` to monitor LinkedIn using Playwright. It captures new messages and creates actionable tasks for the AI Agent.

## Components
- **Script**: `watchers/linkedin_watcher.py`
- **Output**: Creates markdown files in `/Needs_Action/[timestamp]_linkedin.md`
- **User Data**: Stores session in `watchers/linkedin_user_data/`

## Process
1. **Authentication**: Uses a persistent browser context. User must log in manually once.
2. **Polling**: Checks the messaging interface for unread conversations.
3. **Extraction**: captures the latest message text.
4. **Handoff**: Saves the content to `/Needs_Action` as a new task.

## Manual Execution
To start the monitor:
```bash
python watchers/linkedin_watcher.py
```

## AI Agent Responsibility
- **Analysis**: Classify the message (Recruiter, Sales Lead, Spam, Connection).
- **Sales Flow**: If a lead, draft a response using the `@LinkedIn_Poster` or similar capability (if expanded to messaging).
- **Spam**: Move to `/Done` or `/Rejected` immediately.
