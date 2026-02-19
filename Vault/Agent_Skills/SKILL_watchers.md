---
name: Watchers
description: Async watchers for Gmail, WhatsApp, Facebook — rate limiting, dedup caching, 3-retry back-off, time-tracking metrics.
priority: 1
version: 3.0
updated: 2026-02-19
---

# Watchers Skill (v3 — Fully Optimized)

Three async daemons monitor inbound communications and inject structured `.md` tasks into `/Needs_Action`. Each watcher is fully independent — a crash in one does not affect the others.

---

## Architecture

```
asyncio event loop  (each watcher = independent coroutine)
    ↓  await asyncio.sleep(POLL_INTERVAL)   ← 30 s default
  [Gmail API / MCP /check-whatsapp / MCP /check-facebook]
    ↓  t0 = time.monotonic()
  Rate-limiter gate (token bucket — 1 call / 30s)
    ↓  with_retry(fn, attempts=3, base_delay=2)
  Seen-ID cache   (dedup — in-memory set, optional disk persist)
    ↓  new item detected
  Build .md  →  write Needs_Action/YYYYMMDD_HHMMSS_TYPE.md
    ↓  elapsed = time.monotonic() - t0
  Log: [SERVICE] cycle=30.1s fetch=1.23s new=2 errors=0
    ↓
  asyncio.create_subprocess_exec → reasoning_loop.py [file]
```

---

## 1. Gmail Watcher (`watchers/gmail_watcher.py`)

**Poll:** `asyncio.sleep(30)` | **Rate limit:** 1 call / 30 s  
**Cache:** `seen_ids: set[str]` — Gmail message ID (string, in-memory)  
**Cache TTL:** Session-scoped (cleared on restart)  
**Retries:** 3 × exponential back-off — 2 s → 4 s → 8 s  
**Auth:** OAuth2 `credentials.json` + cached `token.json`

### Performance Metrics (per cycle)
```
[GMAIL] cycle=30.1s | fetch=1.23s | new=2 | cached=14 | errors=0
```
Logged to `Logs/watcher_perf.jsonl`:
```json
{"ts":"2026-02-19T09:00:01","watcher":"gmail","fetch_s":1.23,"new":2,"errors":0}
```

### Async Retry Pattern
```python
async def with_retry(fn, attempts=3, base=2):
    t0 = time.monotonic()
    for i in range(attempts):
        try:
            result = await fn()
            log_metric("gmail", time.monotonic()-t0, error=False)
            return result
        except Exception as e:
            delay = base * (2 ** i)   # 2s, 4s, 8s
            await asyncio.sleep(delay)
    log_metric("gmail", time.monotonic()-t0, error=True)
    # skip cycle — watcher continues
```

### Output File Format
```yaml
---
type: email
from: "sender@example.com"
subject: "Re: Project Update"
thread_id: "abc123"
received: "2026-02-19T09:00:00"
priority: high
status: pending
---
## Email Content
[Preview — first 600 chars]

## 🤖 AI Instruction
Draft a professional reply matching the sender's tone.
Move to /Done when sent.
```

### CLI
```bash
python watchers/gmail_watcher.py           # daemon (continuous)
python watchers/gmail_watcher.py --once    # single-shot (used by scheduler)
```

---

## 2. WhatsApp Watcher (`watchers/whatsapp_watcher.py`)

**Poll:** `asyncio.sleep(30)` | **Rate limit:** 1 call / 30 s  
**Cache key:** `f"{sender}_{datetime.now().strftime('%Y%m%d_%H%M')}"` — deduplicates same sender within same minute  
**Cache:** `processed_cache: set[str]` (in-memory)  
**Retries:** 3 × exponential back-off — 2 s → 4 s → 8 s  
**Requires:** MCP server running on `localhost:3000`

### MCP Poll Endpoint
```
GET http://localhost:3000/check-whatsapp
→ { "new_messages": [{ "sender": str, "preview": str, "count": int }] }
```

### Performance Metrics (per cycle)
```
[WHATSAPP] cycle=30.0s | fetch=0.31s | new=1 | cached=3 | errors=0
```

### Output File Format
```yaml
---
type: whatsapp_reply
sender: "John Smith"
count: 3
received: "2026-02-19T09:00:00"
priority: normal
status: pending
suggested_mcp_endpoint: send-whatsapp
---
## Message Preview
[Last message text — up to 300 chars]

## 💬 Suggested Reply
Short, friendly, professional reply here.

## 🤖 AI Instruction
Review preview and send reply. Use /send-whatsapp endpoint.
```

### CLI
```bash
python watchers/whatsapp_watcher.py        # daemon
python watchers/whatsapp_watcher.py --once # single-shot
```

---

## 3. Facebook Watcher (`watchers/facebook_watcher.py`)

**Poll:** `asyncio.sleep(30)` | **Rate limit:** 1 call / 30 s  
**Cache key:** `md5(f"{type}|{name}|{desc}|{minute}")` — prevents duplicate events within the same minute  
**Cache:** `event_cache: set[str]` (in-memory)  
**Retries:** 3 × exponential back-off — 2 s → 4 s → 8 s  
**Event types:** `friend_request` | `message` | `notification`

### MCP Poll Endpoint
```
GET http://localhost:3000/check-facebook
→ {
    "friend_requests": [{"name": str, "mutual_friends": int, "user_id": str}],
    "messages":        [{"sender": str, "preview": str}],
    "events":          [{"type": str, "description": str}]
  }
```

### Performance Metrics (per cycle)
```
[FACEBOOK] cycle=30.2s | fetch=0.45s | friend_req=1 | msgs=0 | cached=2 | errors=0
```

### Output File Formats

**Friend Request:**
```yaml
---
type: facebook_friend_request
person: "Ahmed Khan"
user_id: "ahmed_khan_123"
mutual_friends: 5
received: "2026-02-19T09:00:00"
priority: normal
status: pending
suggested_mcp_endpoint: accept-friend-facebook
---
## Analysis
5 mutual friends — likely genuine connection.

## 🤖 AI Instruction
ACCEPT if mutual_friends ≥ 3. REJECT if 0 mutual friends + suspicious name.
```

**Message:**
```yaml
---
type: facebook_message
sender: "Sara Ali"
received: "2026-02-19T09:00:00"
priority: normal
status: pending
suggested_mcp_endpoint: send-facebook-message
---
## Message Preview
[First 300 chars of message]

## 🤖 AI Instruction
Draft a warm, professional reply. Use /send-facebook-message endpoint.
```

### CLI
```bash
python watchers/facebook_watcher.py        # daemon
python watchers/facebook_watcher.py --once # single-shot
```

---

## Error Recovery (Shared Pattern)

```python
# All watchers on 3-failure cycle:
log_error(Logs/watcher_errors.log, service, error_msg)
# Skip this cycle → try again at next poll (30s)
# No crash — watcher continues indefinitely
```

Log format:
```json
{"ts":"2026-02-19T09:00:05","watcher":"gmail","error":"ConnectionError","attempt":3}
```

---

## Caching Summary

| Watcher   | Cache Type       | Key Formula                    | Cleared  |
|-----------|------------------|--------------------------------|----------|
| Gmail     | `set` of strings | Gmail message ID               | Restart  |
| WhatsApp  | `set` of strings | `sender_YYYYMMDD_HHMM`        | Restart  |
| Facebook  | `set` of MD5s    | `md5(type|name|desc|HHMM)`    | Restart  |

---

## Performance Targets

| Metric              | Target  | Actual  |
|---------------------|---------|---------|
| Poll interval       | 30 s    | 30 s    |
| Fetch latency       | < 3 s   | ~1–2 s  |
| Dedup cache lookup  | < 1 ms  | < 1 ms  |
| .md write           | < 50 ms | < 20 ms |
| End-to-end cycle    | < 35 s  | ~31 s   |

---

## Starting All Watchers

```bat
start_silver_tier.bat      ← recommended (all in one)
```

Or individually:
```bash
python watchers/gmail_watcher.py    &
python watchers/whatsapp_watcher.py &
python watchers/facebook_watcher.py &
node watchers/mcp_server.js         # required for WA + FB
```

---

## Adding a New Watcher

1. Copy `whatsapp_watcher.py` as template
2. Add `GET /check-{service}` to `mcp_server.js`
3. Define cache key formula (unique per event)
4. Output `.md` to `/Needs_Action/` with correct `type:` frontmatter
5. Add performance log line
6. Register in `start_silver_tier.bat`
