---
name: Task Analyzer
description: Analyzes files in /Needs_Action, identifies type, creates action plans, checks for approvals
triggers: "@Task_Analyzer or when complex task analysis is needed"
author: AI Employee
version: 1.0
---

# Task Analyzer

## Description
This skill analyzes all files in /Needs_Action, identifies the type (file drop, email, WhatsApp, etc.), creates a simple action plan in Plan.md, checks if approval is needed (e.g., payments, sensitive info), uses Ralph Wiggum loop mindset for multi-step tasks, and remains proactive while referencing the handbook.

## Steps
1. Analyze all files in /Needs_Action folder
2. Identify the type of each file (file drop, email, WhatsApp, etc.)
3. Create a simple action plan in Plan.md
4. Check if approval is needed (payments, sensitive info) → if yes, write to /Pending_Approval
5. Apply Ralph Wiggum loop mindset for multi-step tasks (keep going until complete)
6. Reference Company_Handbook.md for all actions

## Detailed Process
- Scan /Needs_Action for all files
- Categorize each file by type (email, file_drop, payment_request, etc.)
- Determine if approval is required based on content (especially for payments > $500)
- If approval needed, move to /Pending_Approval folder
- If no approval needed, create action plan in Plan.md
- For multi-step tasks, implement Ralph Wiggum persistence (keep working until done)
- Ensure all actions comply with Company_Handbook.md

## Examples
Input: Payment_Request.md in /Needs_Action containing amount > $500
Process: Identify as payment request, check amount against policy, flag for approval
Output: Payment_Request.md moved to /Pending_Approval for manual review

Input: Email_Request.md in /Needs_Action with simple inquiry
Process: Identify as email request, create response plan in Plan.md
Output: Plan.md with response steps, Email_Request.md processed

## Usage
@Task_Analyzer - Analyze and categorize all pending tasks in /Needs_Action with intelligent routing

## Approval Logic
- Check for payment amounts > $500 → route to /Pending_Approval
- Check for sensitive information → route to /Pending_Approval
- Simple tasks → create action plan in Plan.md

## Ralph Wiggum Mindset
For any multi-step task, keep iterating and working until completion. If blocked, document the issue and try alternative approaches rather than giving up.