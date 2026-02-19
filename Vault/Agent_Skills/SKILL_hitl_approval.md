---
name: HITL Approval
description: Human-in-the-Loop flow — Pending_Approval file format, async approval_watcher, direct MCP execution, 3-retry, time-tracking, notifications.
priority: 4
version: 3.0
updated: 2026-02-19
---

# HITL Approval Skill (v3 — Fully Optimized)

All sensitive actions require human sign-off before execution. The AI writes a structured `.md` to `/Pending_Approval/`. A human reviews, edits if needed, and moves to `/Approved/`. The async `approval_watcher.py` detects the move in < 2 s and executes via MCP with 3-retry back-off.

---

## Full Approval Flow

```
reasoning_loop.py  (CoT: VALIDATE step — confidence scored)
    ↓  writes /Pending_Approval/YYYYMMDD_HHMMSS_approval.md
    ↓
[Human reviews in any text editor or file manager]
    ↓  OPTION A: Move to /Approved/         ← EXECUTE
    ↓  OPTION B: Delete the file            ← REJECT
    ↓  OPTION C: Edit content, then move    ← MODIFY & EXECUTE
    ↓
approval_watcher.py  (watchdog — detects in < 2 s via watchdog lib)
    ↓  t0 = time.monotonic()
    ↓  parse frontmatter (YAML) → build MCP payload
    ↓  aiohttp POST → localhost:3000/{endpoint}
    ↓  with_retry(3 attempts, 5s → 10s → 20s back-off)
    ↓  elapsed = time.monotonic() - t0
    ↓  on success → move to /Done/  +  log_perf(ok=true)
    ↓  on all fail → move to /Done/ with ERROR note  +  log_perf(ok=false)
```

---

## Pending Approval File Format

```yaml
---
type: email                             # see TYPE_TO_ENDPOINT table below
status: pending_approval
confidence: high                        # high | medium | low
cot_model: gemini                       # which model generated this
cot_time_s: 18.4                        # how long CoT took
suggested_mcp_endpoint: send-email      # exact endpoint to call
target: client@example.com             # recipient
subject: "Re: Project Update"           # email subject (emails only)
created: "2026-02-19T09:00:18"
---

# Approval Request — EMAIL

**AI Reasoning:**
[ANALYZE] Client email mentions Friday deadline — high urgency. Professional tone required.
[VALIDATE] Confidence: HIGH. No sensitive disclosures. Appropriate length.

**Proposed Content:**
Hi John,

I'll have the full report ready by Friday morning. Please let me know if you need anything sooner.

Best regards

---
> ✅ Move to /Approved/ to EXECUTE  |  🗑 Delete to REJECT  |  ✏ Edit content above first, then move
```

---

## TYPE_TO_ENDPOINT Mapping (auto-resolved by `approval_watcher.py`)

| `type` field | Frontmatter read | MCP endpoint called |
|-------------|-----------------|-------------------|
| `email` | `target`, `subject`, body | `POST /send-email` |
| `whatsapp` / `whatsapp_reply` | `target` or `sender`, body | `POST /send-whatsapp` |
| `facebook_friend_request` | `person`, `user_id` | `POST /accept-friend-facebook` |
| `reject_friend` | `person`, `user_id` | `POST /reject-friend-facebook` |
| `facebook_message` | `sender`, body | `POST /send-facebook-message` |
| `post_facebook` | body | `POST /post-facebook` |
| `linkedin_post` | body | `POST /post-linkedin` |

---

## approval_watcher.py — Async Execution

```python
async def execute_approval(path: Path):
    t0 = time.monotonic()
    fm = parse_frontmatter(path)
    payload = build_payload(fm, body=read_body(path))
    endpoint = TYPE_TO_ENDPOINT[fm["type"]]

    async def call_mcp():
        async with aiohttp.ClientSession() as s:
            r = await s.post(f"http://localhost:3000/{endpoint}", json=payload)
            r.raise_for_status()
            return await r.json()

    try:
        result = await with_retry(call_mcp, attempts=3, delays=[5, 10, 20])
        move_to_done(path, note=f"✅ Done — {result}")
        log_perf("approval", endpoint, time.monotonic()-t0, ok=True)
    except Exception as e:
        move_to_done(path, note=f"❌ ERROR after 3 retries: {e}")
        log_perf("approval", endpoint, time.monotonic()-t0, ok=False)
```

---

## Retry Strategy

```
Attempt 1 → wait 5 s  (MCP may be momentarily busy)
Attempt 2 → wait 10 s (browser session may be restarting)
Attempt 3 → wait 20 s (one last chance)
All fail  → /Done/ with ERROR note + Dashboard.md alert
```

---

## Confidence Levels

| Confidence | Meaning | Human action |
|-----------|---------|-------------|
| `high` | AI certain — draft looks good | Quick review, usually approve |
| `medium` | Some ambiguity — review carefully | Edit if wording feels off |
| `low` | Complex / sensitive | Thorough review mandatory — likely needs rewording |

**Low-confidence files get `⚠️ LOW CONFIDENCE` prefix in filename.**

---

## Performance Metrics

Logged to `Logs/approval_log.jsonl`:
```json
{"ts":"2026-02-19T09:01:00","endpoint":"/send-email","elapsed_s":3.1,"ok":true,"attempts":1}
{"ts":"2026-02-19T09:05:12","endpoint":"/send-whatsapp","elapsed_s":14.8,"ok":true,"attempts":2}
{"ts":"2026-02-19T09:10:05","endpoint":"/accept-friend-facebook","elapsed_s":35.0,"ok":false,"attempts":3}
```

| Metric | Target | Actual |
|--------|--------|--------|
| File detection → MCP call | < 2 s | ~1.5 s |
| MCP (warm session) | < 8 s | ~3–5 s |
| End-to-end (approve → done) | < 10 s | ~5–7 s |

---

## Dashboard.md Auto-Update

After each execution, `approval_watcher.py` updates `Dashboard.md`:
```markdown
## Last Action
- 2026-02-19T09:01:00 ✅ EMAIL sent to client@example.com
- 2026-02-19T09:05:12 ✅ WHATSAPP sent to John Smith
- 2026-02-19T09:10:05 ❌ FACEBOOK friend accept FAILED (timeout × 3)
```

---

## Running the Watcher

```bash
python watchers/approval_watcher.py     # always-on daemon
# Auto-started by start_silver_tier.bat
```

---

## 3-Service Example (End-to-End)

### Gmail
```
/Pending_Approval/20260219_090018_email_john.md
  → Edit body if needed → move to /Approved/
  → approval_watcher → POST /send-email → ✅ delivered in 3 s
```

### WhatsApp
```
/Pending_Approval/20260219_090100_whatsapp_sara.md
  → Review → move to /Approved/
  → approval_watcher → POST /send-whatsapp → ✅ sent in 5 s
```

### Facebook
```
/Pending_Approval/20260219_090200_facebook_friend_ahmed.md
  → Review → move to /Approved/
  → approval_watcher → POST /accept-friend-facebook → ✅ accepted in 3 s
```
