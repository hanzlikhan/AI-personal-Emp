---
name: MCP Actions
description: All MCP server endpoints — schemas, rate limits, retry policy, and session caching.
---

# MCP Actions Skill

The **MCP Server** (`watchers/mcp_server.js`) is the Silver Tier's action executor. It receives structured requests from `approval_watcher.py` and performs real-world actions via Nodemailer and Playwright.

---

## 🚀 Starting the Server

```bash
node watchers/mcp_server.js
# or via start_silver_tier.bat
```

Health check: `GET http://localhost:3000/health`

---

## 🔒 Rate Limits

| Endpoint | Limit |
|----------|-------|
| `/send-email` | 5 calls / 60 seconds |
| All browser endpoints | 10 calls / 30 seconds |

Exceeded → HTTP 429 response.

---

## ♻️ Retry Policy (withRetry)

All endpoints wrap their action in `withRetry(fn, 3)`:

```
Attempt 1 → wait 2s on failure
Attempt 2 → wait 4s on failure
Attempt 3 → throw final error
```

---

## 💾 Session Caching

Playwright contexts are **held open** between requests:
```
First call  → launch browser + cache context
Later calls → reuse cached context (3–5x faster)
Crash       → auto-recreate on next call
Shutdown    → graceful close (SIGINT/SIGTERM)
```

Session keys: `whatsapp`, `facebook`

---

## 📋 Endpoint Reference

### POST /send-email
```json
{ "to": "email@example.com", "subject": "Subject", "body": "Email body text" }
```
**Response:** `{ "success": true, "messageId": "..." }`
**Backend:** Nodemailer → Gmail SMTP

---

### POST /send-whatsapp
```json
{ "contact": "John Smith", "message": "Hi! Your message here." }
```
**Response:** `{ "success": true, "message": "WhatsApp message sent" }`
**Backend:** Playwright → WhatsApp Web (persistent session)

---

### POST /post-facebook
```json
{ "content": "Post content here" }
```
**Response:** `{ "success": true, "message": "Posted to Facebook" }`
**Backend:** Playwright → Facebook timeline composer

---

### POST /accept-friend-facebook
```json
{ "user_id": "Ahmed Khan" }   // or "next" / "latest"
```
**Response:** `{ "success": true, "message": "Accepted friend request for Ahmed Khan" }`
**Backend:** Playwright → `/friends/requests` → click Confirm

---

### POST /reject-friend-facebook
```json
{ "user_id": "Unknown User" }
```
**Response:** `{ "success": true, "message": "Rejected friend request from Unknown User" }`
**Backend:** Playwright → `/friends/requests` → click Delete Request

---

### POST /send-facebook-message
```json
{ "recipient": "John Smith", "message": "Hi, thanks for reaching out!" }
```
**Response:** `{ "success": true, "message": "Facebook message sent to John Smith" }`
**Backend:** Playwright → Messenger thread

---

### GET /check-whatsapp
```json
{ "new_messages": [{ "sender": "John", "preview": "Hey...", "count": 3 }] }
```

---

### GET /check-facebook
```json
{
  "friend_requests": [{ "name": "Ahmed", "mutual_friends": 5 }],
  "messages":        [{ "sender": "Sara", "preview": "Hello..." }],
  "events":          [{ "type": "notification", "description": "..." }]
}
```

---

### GET /health
```json
{
  "status": "ok",
  "uptime": 3600,
  "sessions": { "whatsapp": "cached", "facebook": "none" },
  "gmail": "configured"
}
```

---

## 🔄 Approval → Execution Flow

```
/Approved/email_approval.md
        ↓
approval_watcher.py (async)
        ↓
parse frontmatter:
  type: email
  suggested_mcp_endpoint: send-email
  target: client@example.com
        ↓
aiohttp POST /send-email { to, subject, body }
  [3 retries with back-off if needed]
        ↓
MCP server → Nodemailer → Gmail SMTP
        ↓
success → move to /Done
```

---

## 🛠️ Setup Requirements

```bash
# Node dependencies (in watchers/)
npm install express-rate-limit

# Python dependencies
pip install aiohttp watchdog

# .env required fields
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=your_app_password
```
