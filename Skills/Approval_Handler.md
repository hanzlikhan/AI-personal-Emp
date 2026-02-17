---
name: "@Approval_Handler"
triggers: ["@Approval_Handler", "get approval", "approval workflow", "human review"]
author: "AI Employee"
version: "1.0"
category: "Workflow"
dependencies: []
---

# @Approval_Handler

## Description
Implements full human-in-the-loop logic for critical business decisions. Manages the approval workflow by moving items to Pending_Approval, waiting for human input, and processing results.

## Purpose
- Route items requiring human approval to /Pending_Approval/
- Monitor for human approval/rejection decisions
- Move items to /Approved/ or /Rejected/ based on decisions
- Maintain audit trail of all approval decisions

## Triggers
- `@Approval_Handler` - Initiate approval workflow
- `get approval` - Request human approval for item
- `approval workflow` - Start approval process
- `human review` - Submit for human review

## Steps
1. Receive item requiring approval
2. Move item to /Pending_Approval/ folder
3. Update dashboard to show pending approval
4. Wait for human decision (Approved/Rejected)
5. Monitor /Pending_Approval/ for status changes
6. When approved:
   - Move item to /Approved/ folder
   - Execute approved action
   - Log approval in system
7. When rejected:
   - Move item to /Rejected/ folder
   - Cancel requested action
   - Log rejection in system
8. Notify requesting skill of outcome

## @-mention Usage
- Use `@Approval_Handler` to initiate approval workflow
- Include item details when requesting approval
- Combine with other skills that require human oversight

## Handbook Reference
See Company_Handbook.md section 2.5 for approval process requirements and escalation procedures.

## Ralph Wiggum Loop Prevention
- Never bypass human approval for items requiring it
- Wait indefinitely for human decision before proceeding
- Maintain clear separation between approved/rejected items
- Log all approval decisions for accountability