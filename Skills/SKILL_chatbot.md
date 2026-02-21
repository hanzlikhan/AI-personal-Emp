---
name: Chatbot Interface
description: How to use the Silver Tier Chatbot to control the agent and getting real-time feedback.
version: 1.0
---

# Chatbot Interface

The Chatbot is the primary manual interface for the Silver Tier Agent. It resides in the Dashboard and allows you to issue natural language commands to the agent.

## Capabilities

The chatbot understands the following intents and routes them to the **Reasoning Loop** for execution:

1.  **Send Emails**:
    - "Send email to [email] with subject [subject]..."
    - "Email [Name] about [Topic]..."

2.  **WhatsApp**:
    - "Reply to latest WhatsApp message from [Name]"
    - "Send WhatsApp to [Name]: [Message]"

3.  **Facebook**:
    - "Post on Facebook: [Content]"
    - "Accept friend request from [Name]"
    - "Reply to FB message from [Name]"

4.  **General Instructions**:
    - "Analysis of the last email from [Name]"
    - "Draft a plan for [Project]"

## Architecture

1.  **Command Parsing**:
    - User types command in Dashboard Chat.
    - Backend (`/chat`) receives it and uses keyword matching/NLP to identify type.
    - Creates a task file in `/Needs_Action` (e.g., `20241010_chat_email.md`).

2.  **Execution**:
    - **Orchestrator** detects the new file.
    - **Reasoning Loop** (`reasoning_loop.py`) is triggered.
    - Agent Thinks → Analyzes → Drafts → Validates.

3.  **Feedback Loop**:
    - The Agent writes a Plan (`/Plans`) or Approval Request (`/Pending_Approval`).
    - **Orchestrator** detects these new artifacts.
    - Notifies Backend via Webhook.
    - Backend pushes a `chat_reply` WebSocket event to the Dashboard.
    - Statistics in dashboard automatically refresh.

## Usage

1.  Open Dashboard (`http://localhost:3000`).
2.  Navigate to "AI Chat" tab.
3.  Type instruction (e.g., "Send an email to hanzla@example.com saying hello").
4.  Watch the "Processing..." status.
5.  Wait for "Plan generated" or "Approval Required" notification.
6.  Go to "Approvals" tab to review and execute if needed.
