---
name: "@Gmail_Watcher_Processor"
triggers: ["@Gmail_Watcher_Processor", "process email", "email watcher", "incoming mail"]
author: "AI Employee"
version: "1.0"
category: "Communication"
dependencies: []
---

# @Gmail_Watcher_Processor

## Description
Processes incoming emails and routes them for appropriate action. Monitors Gmail inbox for new messages and applies business logic to determine next steps.

## Purpose
- Monitor Gmail for incoming emails
- Categorize emails by priority and type
- Route emails for human approval when needed
- Handle automated responses where appropriate

## Triggers
- `@Gmail_Watcher_Processor` - Activate the email processing workflow
- `process email` - Process a specific email
- `email watcher` - Check for new emails
- `incoming mail` - Handle new incoming mail

## Steps
1. Check Gmail inbox for new unread messages
2. Parse email content (subject, body, sender)
3. Apply classification rules:
   - High priority: urgent client requests, complaints
   - Medium priority: business inquiries, meeting requests
   - Low priority: newsletters, promotional content
4. For high/medium priority emails:
   - Move to /Pending_Approval/ folder
   - Notify human operator via dashboard
   - AI drafts a response using `@Gmail_Watcher_Processor` and `create_draft` in `gmail_watcher.py`
   - Wait for approval before proceeding
5. For low priority emails:
   - AI may draft a response for review or archive if appropriate
6. After approval:
   - Use `send_email` in `gmail_watcher.py` to send the approved draft/message
7. Log all actions taken

## @-mention Usage
- Use `@Gmail_Watcher_Processor` to initiate email processing
- Include email ID or subject when referencing specific emails
- Combine with `@Approval_Handler` for approval workflows

## Handbook Reference
See Company_Handbook.md section 3.2 for email handling protocols and approval requirements.

## Ralph Wiggum Loop Prevention
- If email content is unclear, escalate to /Pending_Approval/
- Limit auto-responses to predefined templates only
- Never send emails without proper approval for business communications
- Maintain log of all email interactions for audit trail