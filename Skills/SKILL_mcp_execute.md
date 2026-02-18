---
name: MCP Execution
description: Learn how to use and execute actions via the configured MCP Servers.
---

# MCP Execution Skill

The Silver Tier AI uses Model Context Protocol (MCP) servers to perform external actions securely. The `reasoning_loop.py` acts as the MCP Client.

## Configured Servers

### Email MCP (`email_mcp.js`)
- **Tool**: `send_email`
- **Arguments**:
    - `to`: Recipient email address
    - `subject`: Email subject
    - `body`: Email text content
- **Usage**: Used automatically by `reasoning_loop.py` when an approved `type: email` task is executed.

## Workflow Integration

1.  **Approval**: Tasks start as approval requests in `/Pending_Approval`.
2.  **Trigger**: User moves file to `/Approved`.
3.  **Execution**: `approval_watcher.py` detects the file and calls `reasoning_loop.py --execute [filepath]`.
4.  **MCP Call**: `reasoning_loop.py` reads the file, determines it's an email, and calls the `email_mcp.js` script with the approprate arguments.

## Adding New MCP Servers

1.  Create the server script (e.g., `new_tool_mcp.js`).
2.  Update `mcp.json` to include the new server.
3.  Update `reasoning_loop.py`: `execute_action` to handle the new tool type and call the new script.
