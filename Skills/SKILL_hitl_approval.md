---
name: HITL Approval Workflow
description: Manage human-in-the-loop approval processes for sensitive actions (Email, LinkedIn, WhatsApp).
---

# Human-in-the-Loop Approval Workflow

This skill ensures that sensitive actions proposed by the AI are reviewed by a human before execution.

## Workflow Overview

1.  **Proposal**: The AI (via `reasoning_loop.py`) identifies a need for a sensitive action (e.g., sending an email).
2.  **Creation**: Instead of executing potentially dangerous actions directly, the AI creates a file in `/Pending_Approval/`.
    - Format: `YYYYMMDD_HHMMSS_[type]_approval.md`
    - Content: YAML frontmatter with metadata (`type`, `target`, `status: pending_approval`) and the proposed content.
3.  **Review**: The user reviews the file in `/Pending_Approval/`.
4.  **Approval**: To approve, the user moves the file to `/Approved/`.
5.  **Execution**: The `approval_watcher.py` (part of the Orchestrator) detects the file in `/Approved/` and executes the corresponding action via CLI tools.
6.  **Completion**: The file is moved to `/Done/` upon successful execution.

## Supported Actions

### Email
- **File Type**: `type: email`
- **Metadata**: `target` (recipient email), `subject`
- **Executor**: `gmail_watcher.py --send [target] [subject] [body]`

### LinkedIn Post
- **File Type**: `type: linkedin`
- **Metadata**: None (content is in body)
- **Executor**: `linkedin_watcher.py --post [content]`

### WhatsApp Message
- **File Type**: `type: whatsapp`
- **Metadata**: `target` (contact name)
- **Executor**: `whatsapp_watcher.py --send [contact] [message]`

## Agentic Usage

When the AI Agent needs to perform one of these actions, it MUST create an approval request file rather than calling the tool directly.

```python
# Example: Requesting LinkedIn Post
create_approval_request("linkedin", "My new post content")
```
