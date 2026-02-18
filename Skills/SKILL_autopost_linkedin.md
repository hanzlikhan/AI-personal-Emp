---
name: Autonomous LinkedIn Posting
description: Generate and post content to LinkedIn with human approval.
triggers: "New opportunity detected or manual request"
author: AI Employee
version: 1.0
---

# Autonomous LinkedIn Posting

## Description
This skill enables the Agent to autonomously draft LinkedIn posts based on business events (like new collections or verified opportunities) and post them using the `linkedin_mcp.js` script after human approval.

## Components
- **Script**: `node watchers/linkedin_mcp.js "Content"`
- **Workflow**: Watcher -> Plan -> Approval -> Post

## Process

1.  **Trigger**:
    - `linkedin_watcher.py` or `orchestrator.py` detects an opportunity (e.g., `[timestamp]_linkedin_opportunity.md`).
    
2.  **Drafting (Agent)**:
    - Agent reads the opportunity.
    - Agent uses **Ralph Wiggum Loop** to brainstorm and draft a post.
    - Agent creates a file: `/Pending_Approval/linkedin_post_request.md` with the proposed content.

3.  **Approval (Human)**:
    - User reviews the file in `/Pending_Approval`.
    - User moves it to `/Approved` (or Agent checks for explicit "Approved" status if using a different flow).

4.  **Posting (Agent/MCP)**:
    - Once approved, Agent executes:
      ```bash
      node watchers/linkedin_mcp.js "Finalized Post Content"
      ```
    - Agent moves the request file to `/Done`.

## Ralph Wiggum Loop for Content
- **Idea**: "What's the core message?"
- **Draft**: "Write it simple first."
- **Refine**: "Add emojis? Check constraints?"
- **Final**: "Ready for approval."

## Example Command
```bash
node watchers/linkedin_mcp.js "Excited to announce our new Silver Tier AI capabilities! 🚀 #AI #Automation"
```
