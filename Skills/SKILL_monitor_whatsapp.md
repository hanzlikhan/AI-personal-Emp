---
name: Monitor WhatsApp
description: Monitor WhatsApp Web for new messages and auto-respond.
triggers: "New WhatsApp message detected"
author: AI Employee
version: 1.0
---

# Monitor WhatsApp

## Description
This skill uses `watchers/whatsapp_watcher.py` (powered by Playwright) to monitor WhatsApp Web for incoming messages. It handles simple auto-replies and escalates complex messages to the AI Agent.

## Components
- **Script**: `watchers/whatsapp_watcher.py`
- **Output**: Creates markdown files in `/Needs_Action/[timestamp]_whatsapp.md`
- **User Data**: Stores session in `watchers/whatsapp_user_data/`

## Process
1. **Setup**: The user must scan the QR code on the first run.
2. **Monitoring**: The script watches for unread badges on the chat list.
3. **Response Logic**:
   - **Simple** ("hi", "test"): Auto-replies with "Received, processing."
   - **Complex**: Extracts message content and saves to `/Needs_Action` for AI processing.
4. **Files**: Created files have `type: whatsapp` in frontmatter.

## Manual Execution
To start the monitor:
```bash
python watchers/whatsapp_watcher.py
```
*Note: Requires a visible browser window initially for QR scan.*

## AI Agent Responsibility
- **Context**: Read the message content from the generated task file.
- **Reasoning**: distinct personal messages from business inquiries.
- **Action**: 
  - If business: Draft a reply logic (to be implemented via response tool).
  - If personal: Mark as low priority or ignore based on handbook.
