---
title: Silver Tier Agent Skills
description: Optimized skills vault — v3. Load in priority order.
version: 3.0
updated: 2026-02-19
---

# Silver Tier — Agent Skills Vault (v3)

Central reference for all AI agent capabilities. Read skills in **priority order** (1 → 6). Fall back to `Skills/` for legacy reference docs.

---

## Skill Index

| Priority | File | Covers | Version |
|----------|------|--------|---------|
| 1 | [SKILL_watchers.md](./SKILL_watchers.md) | Gmail, WhatsApp, Facebook monitoring | v3 |
| 2 | [SKILL_reasoning_loop.md](./SKILL_reasoning_loop.md) | CoT (THINK→ANALYZE→DRAFT→VALIDATE), plan cache, model waterfall | v3 |
| 3 | [SKILL_mcp_actions.md](./SKILL_mcp_actions.md) | MCP endpoints, Playwright session cache, rate limits | v3 |
| 4 | [SKILL_hitl_approval.md](./SKILL_hitl_approval.md) | Approval flow, async execution, 3-retry | v3 |
| 5 | [SKILL_scheduling.md](./SKILL_scheduling.md) | Cron jobs, auto-recovery, watchdog, CEO briefing | v3 |
| 6 | [SKILL_chat_interface.md](./SKILL_chat_interface.md) | Terminal chat, manual instructions, inline approval | v2 |

**Fallback:** `Skills/` (legacy v1 reference docs — used if topic not in Vault)

---

## End-to-End System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  INPUTS                                                         │
│  Scheduler (08:55-09:05)  Real-time watchers  Manual chat.py   │
└──────────────────┬──────────────────┬───────────────┬──────────┘
                   ▼                  ▼               ▼
         ┌─────────────────────────────────────────────┐
         │         /Needs_Action/*.md  (injected)       │
         └──────────────────────┬──────────────────────┘
                                ▼
         ┌──────────────────────────────────────────────┐
         │  reasoning_loop.py — CoT (THINK→ANALYZE→     │
         │  DRAFT→VALIDATE) + plan cache + model        │
         │  waterfall (Gemini→Groq→Claude→Mock)         │
         └──────────────┬──────────────────────────────┘
                        │
              ┌─────────▼─────────┐
              │  /Plans/*.md      │  (archived plan)
              └───────────────────┘
              ┌─────────▼──────────────────┐
              │  /Pending_Approval/*.md    │  (human review)
              └─────────┬──────────────────┘
                        │
              [Human: Move → /Approved/  or  Delete]
                        │
              ┌─────────▼──────────────────┐
              │  approval_watcher.py       │
              │  aiohttp POST + 3-retry    │
              └─────────┬──────────────────┘
                        ▼
         ┌──────────────────────────────────────────────┐
         │  mcp_server.js :3000                         │
         │  Nodemailer (email) / Playwright (WA, FB)    │
         │  Rate-limited + session-cached              │
         └──────────────┬───────────────────────────────┘
                        ▼
              ┌─────────────────┐
              │  /Done/*.md     │  Task archived
              └─────────────────┘
```

---

## Performance Targets (v3)

| Component | Target | Actual |
|-----------|--------|--------|
| Watcher poll cycle | 30 s | 30 s |
| Plan cache hit | < 10 ms | ~5 ms |
| CoT cold run (4 AI calls, Gemini) | < 30 s | ~15–25 s |
| CoT fallback to Mock | < 2 s | ~0.5 s |
| File detect → MCP call (approval) | < 2 s | ~1.5 s |
| Email send (warm) | < 5 s | ~3 s |
| WhatsApp send (warm) | < 8 s | ~5 s |
| Facebook action (warm) | < 6 s | ~3–4 s |
| Job scheduling accuracy | ± 60 s | ± 60 s |

---

## Directory Map

```
/Inbox/             ← Raw incoming files (future use)
/Needs_Action/      ← Watchers + Scheduler inject tasks here
/Plans/             ← reasoning_loop writes CoT plans
/Pending_Approval/  ← reasoning_loop writes approval requests
/Approved/          ← Human moves here to execute
/Done/              ← Completed + archived tasks
/Rejected/          ← Deleted approval files (tracked)
/Logs/              ← All performance + error logs (JSONL)
/Vault/Agent_Skills/← This folder — canonical skill reference
/Skills/            ← Legacy docs (fallback)
```

---

## End-to-End Test (3 Services)

Run in order:
```bash
# 1. Verify MCP server
curl http://localhost:3000/health

# 2. Gmail test
python tests/test_e2e.py --service gmail

# 3. WhatsApp test
python tests/test_e2e.py --service whatsapp

# 4. Facebook test
python tests/test_e2e.py --service facebook

# 5. Review logs
Get-Content Logs\approval_log.jsonl | tail -10
```

Expected: 3 entries in `approval_log.jsonl` with `"ok": true`.
