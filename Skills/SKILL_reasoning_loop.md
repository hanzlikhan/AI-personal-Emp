---
name: Autonomous Reasoning Loop
description: The cognitive engine that processes tasks from /Needs_Action and executes tools.
triggers: "Orchestrator detects new file in /Needs_Action"
author: AI Employee
version: 1.0
---

# Autonomous Reasoning Loop

## Description
This skill defines the logic flow for the "Proto-Agent" script (`reasoning_loop.py`). It reads tasks, plans actions using the "Ralph Wiggum" iterative mindset, and executes tools autonomously.

## The Loop Process
1.  **Read**: Parse the content and metadata of the file in `/Needs_Action`.
2.  **Think**:
    - "What is this?" (Email, WhatsApp, LinkedIn?)
    - "Is it urgent?" (Check priority/keywords)
    - "Do I need approval?" (Financial, sensitive content)
3.  **Plan**:
    - Create a file in `/Plans/[timestamp]_plan.md`.
    - List the steps: "1. Draft Reply, 2. Send" or "1. Log info".
4.  **Act**:
    - **Email**: Call `gmail_watcher.py --draft` or `--send`.
    - **WhatsApp**: Log action (since auto-reply is handled by watcher).
    - **LinkedIn**: Call `linkedin_mcp.js` (if approved).
5.  **Conclude**:
    - Move source file to `/Done`.
    - Update `Dashboard.md` (optional).

## Logic Rules (Simulated Agent)
- **Email**:
    - If "Status: Urgent" -> Draft reply immediately.
    - If "Payment" -> Move to `/Pending_Approval`.
- **WhatsApp**:
    - If "Business" -> Log in dashboard.
    - If "Personal" -> Ignore/Log.
- **LinkedIn**:
    - If "Opportunity" -> Draft post in `/Pending_Approval`.

## Tool Usage
- `python watchers/gmail_watcher.py --draft "to@example.com" "Subject" "Body"`
- `node watchers/linkedin_mcp.js "Content"`
