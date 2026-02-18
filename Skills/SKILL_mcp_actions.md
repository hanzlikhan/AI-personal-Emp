---
name: MCP Actions
description: Execute real-world actions (Email, WhatsApp, LinkedIn) via the local MCP HTTP Server.
---

# MCP Actions Skill

The Silver Tier AI uses a local Node.js HTTP server ("The Hands") to perform external actions.

## Server Control

Before executing any actions, ensure the MCP server is running:

```bash
node watchers/email_mcp.js
```
*Port: 3000*

## Supported Tools

### 1. Send Email
- **Endpoint**: `POST /send-email`
- **Body**: `{ "to": "email@example.com", "subject": "Subject", "body": "Content" }`

### 2. Send WhatsApp
- **Endpoint**: `POST /send-whatsapp`
- **Body**: `{ "contact": "Name", "message": "Content" }`

### 3. Post LinkedIn
- **Endpoint**: `POST /post-linkedin`
- **Body**: `{ "content": "Post text" }`

## Workflow

1.  **Approval**: User moves task file to `/Approved`.
2.  **Trigger**: `approval_watcher.py` triggers `reasoning_loop.py --execute`.
3.  **Action**: `reasoning_loop.py` sends HTTP POST request to `localhost:3000`.
4.  **Logging**: Server logs action to console; `reasoning_loop.py` confirms success.

## Troubleshooting

- **Error**: `Connection refused`
- **Fix**: Start the server! `node watchers/email_mcp.js`
