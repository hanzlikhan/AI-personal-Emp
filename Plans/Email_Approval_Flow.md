# Email Approval Workflow

This document describes the end-to-end process for handling emails that require a reply.

## Workflow Steps

1.  **Detection**: `gmail_watcher.py` detects a new unread email and creates a record in `/Needs_Action`.
2.  **Analysis**: The `@Gmail_Watcher_Processor` skill analyzes the email content.
3.  **Drafting**: 
    - AI generates a suggested reply.
    - AI uses `create_draft` in `gmail_watcher.py` to create a draft in Gmail.
    - AI moves the processing task to `/Pending_Approval`.
4.  **Human Review**: 
    - The user reviews the draft in Gmail or the record in `/Pending_Approval`.
    - User moves the record to `/Approved`.
5.  **Execution**: 
    - AI detects the approval and uses `send_email` (or sends the draft) via `gmail_watcher.py`.
    - Record moved to `/Done`.

## Safety Rules
- **DO NOT** auto-send business-critical emails.
- **ALWAYS** route client communications through `/Pending_Approval`.
- Use the `Dashboard.md` to track pending approvals.
