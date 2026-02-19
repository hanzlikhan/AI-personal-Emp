---
name: MCP Actions
description: MCP server endpoints — send email/WhatsApp/Facebook, session caching, rate limits, 3-retry back-off, structured performance logging.
priority: 3
version: 3.0
updated: 2026-02-19
---

# MCP Actions Skill (v3 — Fully Optimized)

`watchers/mcp_server.js` is the real-world action executor. All endpoints are rate-limited, retried on failure, use persistent Playwright browser sessions, and emit structured JSON performance logs.

---

## Server

```bash
node watchers/mcp_server.js      # Port 3000  (required for WA + FB watchers)

GET http://localhost:3000/health
```

Health response:
```json
{
  "status": "ok",
  "uptime_s": 3600,
  "sessions": { "whatsapp": "cached", "facebook": "none" },
  "gmail": "configured",
  "rate_limits": { "email": "3/5 used", "browser": "1/10 used" }
}
```

---

## Rate Limits (Token Bucket)

| Endpoint | Window | Limit | Exceeded Response |
|----------|--------|-------|-------------------|
| `/send-email` | 60 s | 5 calls | HTTP 429 + `Retry-After` header |
| All browser endpoints | 30 s | 10 calls | HTTP 429 + `Retry-After` header |
| `/check-whatsapp` | 30 s | 60 calls | HTTP 429 |
| `/check-facebook` | 30 s | 60 calls | HTTP 429 |

`approval_watcher.py` honours `Retry-After` header automatically.

---

## Session Caching (Playwright)

```
First call  → launch Chromium, login, cache context → ~8–12 s startup
Later calls → reuse cached browser context          → ~1–3 s
Crash       → try { use cached } catch { re-launch → re-login }
Idle >30min → browser kept alive (no auto-close)
Shutdown    → graceful close on SIGINT / SIGTERM
```

| Session | Service | Login method |
|---------|---------|-------------|
| `whatsapp` | WhatsApp Web | QR scan (one-time, then session persisted) |
| `facebook` | Facebook.com | Saved credentials from `.env` |

---

## withRetry Helper (3 Attempts)

```js
async function withRetry(fn, attempts = 3, baseDelayMs = 2000) {
    const t0 = Date.now();
    for (let i = 0; i < attempts; i++) {
        try {
            const result = await fn();
            logPerf({ endpoint: fn.name, elapsed_ms: Date.now()-t0, ok: true });
            return result;
        } catch (err) {
            const delay = baseDelayMs * Math.pow(2, i);   // 2s → 4s → 8s
            console.error(`Attempt ${i+1} failed: ${err.message} — retry in ${delay}ms`);
            if (i < attempts-1) await sleep(delay);
        }
    }
    logPerf({ endpoint: fn.name, elapsed_ms: Date.now()-t0, ok: false, error: "exhausted" });
    throw new Error(`${fn.name} failed after ${attempts} attempts`);
}
```

---

## Endpoint Reference

### POST /send-email
```json
Request:  { "to": "addr@example.com", "subject": "Re: Project", "body": "Hi..." }
Response: { "success": true, "messageId": "abc@gmail.com", "elapsed_ms": 2800 }
```
Backend: **Nodemailer → Gmail SMTP** (`EMAIL_USER` / `EMAIL_PASS` from `.env`)

---

### POST /send-whatsapp
```json
Request:  { "contact": "John Smith", "message": "Hi! Quick reply..." }
Response: { "success": true, "elapsed_ms": 4800 }
```
Backend: **Playwright → WhatsApp Web** (cached session)

---

### POST /post-facebook
```json
Request:  { "content": "Excited to share this update..." }
Response: { "success": true, "elapsed_ms": 3900 }
```
Backend: **Playwright → Facebook timeline**

---

### POST /accept-friend-facebook
```json
Request:  { "user_id": "Ahmed Khan" }   // or "next" for oldest pending
Response: { "success": true, "message": "Accepted: Ahmed Khan", "elapsed_ms": 2700 }
```

---

### POST /reject-friend-facebook
```json
Request:  { "user_id": "Spam Account" }
Response: { "success": true, "elapsed_ms": 2100 }
```

---

### POST /send-facebook-message
```json
Request:  { "recipient": "Sara Ali", "message": "Thanks for reaching out!" }
Response: { "success": true, "elapsed_ms": 5200 }
```

---

### GET /check-whatsapp
```json
Response: {
  "new_messages": [
    { "sender": "John Smith", "preview": "Are you free tomorrow?", "count": 2 }
  ]
}
```

---

### GET /check-facebook
```json
Response: {
  "friend_requests": [{ "name": "Ahmed Khan", "mutual_friends": 5, "user_id": "ak123" }],
  "messages":        [{ "sender": "Sara Ali", "preview": "Hi, wanted to ask..." }],
  "events":          [{ "type": "notification", "description": "Your post got 12 likes" }]
}
```

---

## Performance Benchmarks

| Action | Cold (new session) | Warm (cached) | Target |
|--------|--------------------|---------------|--------|
| `/send-email` | ~3 s | ~3 s | < 5 s |
| `/send-whatsapp` | ~12 s | ~5 s | < 8 s (warm) |
| `/post-facebook` | ~10 s | ~4 s | < 6 s (warm) |
| `/accept-friend-facebook` | ~8 s | ~3 s | < 5 s (warm) |
| `/reject-friend-facebook` | ~7 s | ~2 s | < 4 s (warm) |
| `/check-whatsapp` | ~2 s | ~0.5 s | < 1 s (warm) |

---

## Structured Performance Logging

All calls emit to stdout (captured by orchestrator):
```json
{"ts":"2026-02-19T09:00:01Z","endpoint":"/send-email","status":"ok","elapsed_ms":2800,"detail":"messageId=abc@gmail.com"}
{"ts":"2026-02-19T09:00:12Z","endpoint":"/send-whatsapp","status":"ok","elapsed_ms":4800,"detail":"contact=John Smith"}
{"ts":"2026-02-19T09:00:15Z","endpoint":"/accept-friend-facebook","status":"error","elapsed_ms":8000,"detail":"Timeout — attempt 3/3"}
```

Errors also written to `Logs/mcp_errors.log`.

---

## Adding a New Endpoint

```js
// 1. Add rate limit rule in server init
rateLimits['/new-endpoint'] = { window: 60000, max: 5 };

// 2. Implement handler
app.post('/new-endpoint', rateLimit, async (req, res) => {
    const { param } = req.body;
    await withRetry(async () => {
        // Playwright or API action
    });
    res.json({ success: true });
});
```

```markdown
// 3. Document in this skill file
// 4. Add type mapping in approval_watcher.py TYPE_TO_ENDPOINT
```
