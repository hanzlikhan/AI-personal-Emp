---
name: Watchers Integration (Async Optimized)
description: How the AI's Eyes monitor Gmail, WhatsApp, and Facebook, with async polling, rate limits, caching, retries, and .md task creation.
---

# Watchers Integration Skill (Async Optimized)

The **Watchers** are the sensory organs of the AI Employee. They run as background async daemons, poll platforms every **30 seconds**, and create rich Markdown task files in `/Needs_Action` when events occur.

## The 3 Watchers

### 1. Gmail Watcher (`gmail_watcher.py`)
- **Method**: Google Gmail API (OAuth2 / `credentials.json`)
- **Poll interval**: 30 seconds (`asyncio.sleep(30)`)
- **Cache**: In-memory set of seen message IDs (`_seen_ids`)
- **Retry**: 3 attempts, exponential back-off (5s → 10s → 20s)
- **Output type**: `type: email` in `.md` frontmatter
- **Action after .md**: Marks email as read, triggers `reasoning_loop.py`
- **Run once**: `python gmail_watcher.py --once`
- **Daemon**: `python gmail_watcher.py`

### 2. WhatsApp Watcher (`whatsapp_watcher.py`)
- **Method**: `aiohttp` → polls `GET /check-whatsapp` on MCP server (port 3000)
- **Poll interval**: 30 seconds
- **Cache**: `(sender, minute)` string key in `_processed_cache` set
- **Retry**: 3 attempts, exponential back-off
- **Output type**: `type: whatsapp_reply`
- **AI Suggestion**: "Suggested Reply Template" included in `.md`
- **MCP Action**: `POST /send-whatsapp { "contact": "...", "message": "..." }`
- **Trigger**: Spawns `reasoning_loop.py` as async subprocess
- **Requires**: MCP server running (`node watchers/mcp_server.js`)

### 3. Facebook Watcher (`facebook_watcher.py`)
- **Method**: `aiohttp` → polls `GET /check-facebook` on MCP server
- **Poll interval**: 30 seconds
- **Cache**: MD5 hash of `type|name|description|minute` in `_event_cache`
- **Retry**: 3 attempts, exponential back-off
- **Event types**:
  - `facebook_friend_request` → Mutual friend analysis + Accept/Reject suggestion
  - `facebook_message` → Reply suggestion
  - `facebook_notification` → General action suggestion
- **MCP Actions**:
  - Accept friend: `POST /accept-friend-facebook { "user_id": "..." }`
  - Post content: `POST /post-facebook { "content": "..." }`

---

## Error Handling Strategy

```
[Check fails]
    ↓
Retry attempt 1 → wait 5s
    ↓ (if fails)
Retry attempt 2 → wait 10s
    ↓ (if fails)
Retry attempt 3 → wait 20s
    ↓ (if all fail)
Log error → skip this cycle → try again in 30s
```

## Caching Mechanism

Each watcher uses an in-memory cache to prevent duplicate `.md` files:

| Watcher     | Cache Type        | Cache Key                  | Reset      |
|-------------|-------------------|----------------------------|------------|
| Gmail       | `set` of IDs      | Gmail message ID           | On restart |
| WhatsApp    | `set` of strings  | `sender|YYYYMMDD_HHMM`    | On restart |
| Facebook    | `set` of MD5s     | `type|name|desc|HHMM`     | On restart |

---

## .md File Structure

All task files include:
```yaml
---
type: email | whatsapp_reply | facebook_friend_request | facebook_message | facebook_notification
received: "ISO timestamp"
priority: high | normal
status: pending
---
```
Followed by: event details table, content preview, and **🤖 AI Instruction** block.

---

## Full System Flow

```
Platform → Watcher (async, 30s) → /Needs_Action/*.md
                                        ↓
                               Orchestrator (watchdog)
                                        ↓
                               reasoning_loop.py (Think → Plan → Action)
                                        ↓
                               /Pending_Approval/*.md
                                        ↓
                       Human approves → move to /Approved
                                        ↓
                       Approval Watcher → MCP Server → Real Action
```

## Starting All Watchers

```bat
start_silver_tier.bat
```

Or individually:
```bash
python watchers/gmail_watcher.py
python watchers/whatsapp_watcher.py
python watchers/facebook_watcher.py
```

**Prerequisite**: `node watchers/mcp_server.js` must be running for WhatsApp & Facebook watchers.
