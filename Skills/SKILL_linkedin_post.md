---
name: LinkedIn Posting
description: Instructions for the AI to post updates to LinkedIn via the MCP server.
---

# LinkedIn Posting Skill

The Silver Tier AI agent can autonomously draft and post updates to LinkedIn to generate sales opportunities.

## Workflow

1.  **Opportunity Detection**: 
    - `linkedin_watcher.py` detects a business event (or is manually triggered).
    - Creates a task file in `/Needs_Action` with `type: linkedin_opportunity`.

2.  **Drafting & Planning**:
    - `reasoning_loop.py` analyzes the opportunity.
    - Drafts a post content (e.g., "Excited to share...").
    - Creates an Approval Request in `/Pending_Approval`.

3.  **Human Approval**:
    - User reviews the draft in `/Pending_Approval`.
    - User moves the file to `/Approved`.

4.  **Execution (MCP)**:
    - `approval_watcher.py` triggers `reasoning_loop.py --execute`.
    - `reasoning_loop.py` sends a `POST` request to `http://localhost:3000/post-linkedin`.
    - `email_mcp.js` delegates to `linkedin_mcp.js`.
    - **Actions**:
        1.  Launches Browser (Visible).
        2.  Navigates to LinkedIn.
        3.  Creates Post.
        4.  Clicks Post (or simulates).

## Manual Trigger

To simulate an opportunity for testing:
```bash
python watchers/linkedin_watcher.py --simulate
```

To just post immediately (Testing only):
```bash
python watchers/linkedin_watcher.py --post "My content here"
```
*(Note: Watcher CLI direct post is separate from the MCP flow)*
