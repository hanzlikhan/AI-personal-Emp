"""
Silver Tier AI — Dashboard Backend (Fixed)
==========================================
Start command:
  uvicorn backend.main:socket_app --reload --port 8000
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import uvicorn
import socketio
import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Configuration ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
NEEDS_ACTION_DIR = BASE_DIR / 'Needs_Action'
WATCHERS_DIR = BASE_DIR / 'watchers'
MCP_SERVER_URL = "http://127.0.0.1:3001"

HISTORY_FILES = {
    "gmail":     BASE_DIR / "watchers" / "gmail_history.json",
    "whatsapp":  BASE_DIR / "watchers" / "whatsapp_history.json",
    "facebook":  BASE_DIR / "watchers" / "facebook_history.json",
}
STATUS_FILES = {
    "gmail":    BASE_DIR / "watchers" / "status_gmail.json",
    "whatsapp": BASE_DIR / "watchers" / "status_whatsapp.json",
    "facebook": BASE_DIR / "watchers" / "status_facebook.json",
}

# ─── FastAPI & Socket.IO ──────────────────────────────────────────────────────
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI(title="Silver Tier API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
socket_app = socketio.ASGIApp(sio, app)
START_TIME = datetime.now().isoformat()

# ─── Models ───────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    message: str

class ApprovalRequest(BaseModel):
    filename: str

# ─── Helpers ──────────────────────────────────────────────────────────────────
def load_json(path: Path) -> Any:
    if path and path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except:
            pass
    return [] if path and 'history' in str(path) else {}


def get_env(key: str) -> str:
    """Read a fresh value from .env file — never stale."""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line[len(key)+1:].strip().strip('"').strip("'")
    return os.environ.get(key, "")


async def generate_with_gemini(prompt: str) -> Optional[str]:
    """Call Gemini Flash to generate content."""
    api_key = get_env("GEMINI_API_KEY")
    if not api_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-001:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 500}
    }
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini error: {e}")
    return None



# ─── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Fast health check - no external calls, used by startup script."""
    return {"status": "ok", "started": START_TIME}


@app.get("/status")
async def get_status():
    """Aggregate status. Uses generous timeout so MCP DOM checks complete."""
    gmail_status = load_json(STATUS_FILES["gmail"])
    whatsapp_status = {"status": "offline"}
    facebook_status = {"status": "offline"}

    try:
        timeout = aiohttp.ClientTimeout(total=15)  # Generous - Playwright needs time
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(f"{MCP_SERVER_URL}/check-whatsapp") as resp:
                    if resp.status == 200:
                        whatsapp_status = await resp.json()
            except Exception as e:
                print(f"WA status check failed: {e}")

            try:
                async with session.get(f"{MCP_SERVER_URL}/check-facebook") as resp:
                    if resp.status == 200:
                        facebook_status = await resp.json()
            except Exception as e:
                print(f"FB status check failed: {e}")
    except Exception as e:
        print(f"Status check error: {e}")

    return {
        "gmail":     gmail_status,
        "whatsapp":  whatsapp_status,
        "facebook":  facebook_status,
    }


def normalize_wa_chats(chats: list) -> list:
    """Convert MCP chat data to dashboard-friendly format, deduplicated by sender."""
    seen = set()
    result = []
    now = datetime.now().isoformat()
    for chat in chats:
        sender = chat.get("sender", "").strip()
        # Skip empty or duplicate senders
        if not sender or sender in seen:
            continue
        # Skip entries where sender looks like a message preview (RTL marks, long text)
        if len(sender) > 50 or sender.startswith('\u202a') or sender.startswith('\u200e'):
            continue
        seen.add(sender)
        result.append({
            "id":        f"wa_{sender}",
            "service":   "whatsapp",
            "type":      "message",
            "sender":    sender,
            "from":      sender,
            "preview":   chat.get("preview", ""),
            "text":      chat.get("preview", ""),
            "subject":   f"WhatsApp from {sender}",
            "unread":    chat.get("count", 0) > 0,
            "count":     chat.get("count", 0),
            "timestamp": now,
        })
    return result


@app.get("/history/{service}")
async def get_history(service: str):
    if service not in HISTORY_FILES:
        raise HTTPException(status_code=404, detail="Service not found")

    # ── WhatsApp: call MCP directly (watcher file unreliable) ──────────────
    if service == "whatsapp":
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{MCP_SERVER_URL}/check-whatsapp") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "online":
                            chats = normalize_wa_chats(data.get("new_messages", []))
                            # Persist to file so webhook socket push works too
                            try:
                                HISTORY_FILES["whatsapp"].write_text(
                                    json.dumps(chats, indent=2, ensure_ascii=False), encoding="utf-8"
                                )
                            except: pass
                            return chats
        except Exception as e:
            print(f"WA history direct call failed: {e}")
        # Fallback to file
        return load_json(HISTORY_FILES[service])

    # ── Facebook: call MCP directly (same pattern as WhatsApp) ───────────────
    if service == "facebook":
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{MCP_SERVER_URL}/check-facebook") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "online":
                            now = datetime.now().isoformat()
                            entries = []
                            for fr in data.get("friend_requests", []):
                                entries.append({
                                    "id": f"fb_fr_{fr.get('name','')}",
                                    "service": "facebook", "type": "friend_request",
                                    "sender": fr.get("name", "Unknown"),
                                    "subject": f"Friend Request from {fr.get('name','')}",
                                    "preview": f"{fr.get('mutual_friends',0)} mutual friends",
                                    "text": f"Friend Request from {fr.get('name','')}",
                                    "unread": True, "timestamp": now,
                                })
                            for msg in data.get("messages", []):
                                entries.append({
                                    "id": f"fb_msg_{msg.get('sender','')}",
                                    "service": "facebook", "type": "message",
                                    "sender": msg.get("sender", "Unknown"),
                                    "subject": f"Message from {msg.get('sender','')}",
                                    "preview": msg.get("preview", ""),
                                    "text": msg.get("preview", ""),
                                    "unread": msg.get("count", 0) > 0,
                                    "count": msg.get("count", 0),
                                    "timestamp": now,
                                })
                            try:
                                HISTORY_FILES["facebook"].write_text(
                                    json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
                                )
                            except: pass
                            return entries
        except Exception as e:
            print(f"FB history direct call failed: {e}")
        return load_json(HISTORY_FILES[service])

    # ── Gmail: read from file ────────────────────────────────────────────────
    return load_json(HISTORY_FILES[service])


@app.get("/pending")
async def get_pending():
    """Get pending approval items from Pending_Approval folder."""
    PENDING_DIR = BASE_DIR / "Pending_Approval"
    if not PENDING_DIR.exists():
        return []
    items = []
    for f in sorted(PENDING_DIR.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        try:
            text = f.read_text(encoding='utf-8', errors='ignore')
            meta = {"filename": f.name, "type": "task", "content": text[:500]}
            # Parse frontmatter
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].splitlines():
                        if ":" in line:
                            k, _, v = line.partition(":")
                            meta[k.strip()] = v.strip().strip('"')
                    meta["content"] = parts[2].strip()[:500]
            items.append(meta)
        except Exception as e:
            print(f"Error reading {f.name}: {e}")
    return items


@app.get("/stats")
async def get_stats():
    def count(d: Path) -> int:
        return len(list(d.glob("*.md"))) if d.exists() else 0
    return {
        "needs_action": count(NEEDS_ACTION_DIR),
        "pending":      count(BASE_DIR / "Pending_Approval"),
        "approved":     count(BASE_DIR / "Approved"),
        "done":         count(BASE_DIR / "Done"),
        "rejected":     count(BASE_DIR / "Rejected"),
    }


@app.post("/connect/{service}")
async def connect_service(service: str):
    """Trigger browser-based connection for WhatsApp or Facebook."""
    if service in ["whatsapp", "facebook"]:
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{MCP_SERVER_URL}/connect-{service}") as resp:
                    data = await resp.json()
                    return data
        except Exception as e:
            return {"status": "error", "error": str(e)}
    elif service == "gmail":
        return {"status": "triggered", "message": "Gmail watcher is managed automatically."}
    return {"status": "unknown_service"}


@app.post("/approve")
async def approve(req: ApprovalRequest):
    src  = BASE_DIR / "Pending_Approval" / req.filename
    dest = BASE_DIR / "Approved" / req.filename
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.filename}")
    dest.parent.mkdir(exist_ok=True)
    src.rename(dest)
    await sio.emit("toast", {"type": "success", "message": f"✅ Approved: {req.filename}"})
    return {"status": "approved", "filename": req.filename}


@app.post("/reject")
async def reject(req: ApprovalRequest):
    src  = BASE_DIR / "Pending_Approval" / req.filename
    dest = BASE_DIR / "Rejected" / req.filename
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.filename}")
    dest.parent.mkdir(exist_ok=True)
    src.rename(dest)
    await sio.emit("toast", {"type": "info", "message": f"❌ Rejected: {req.filename}"})
    return {"status": "rejected", "filename": req.filename}


@app.post("/webhook/{service}")
async def receive_webhook(service: str, event: Request):
    """Called by watchers to push live data to dashboard."""
    try:
        data = await event.json()
    except:
        data = {}

    evt_type = data.get('type', 'status_update')

    # ── Always push latest history to dashboard via socket ──
    history_file = HISTORY_FILES.get(service)
    if history_file and history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding='utf-8'))
            await sio.emit('history_update', {'service': service, 'data': history})
            await sio.emit('inbox_update', {})
        except:
            pass

    # ── Toast only for genuine new messages (not noisy status polls) ──
    if evt_type == 'new_message':
        sender = data.get('sender') or data.get('from') or data.get('data', {}).get('sender') or 'Someone'
        if service == 'whatsapp':
            msg = f"💬 New WhatsApp message from **{sender}**"
        elif service == 'facebook':
            msg = f"👤 New Facebook message from **{sender}**"
        elif service == 'gmail':
            msg = f"📧 New Email from **{sender}**"
        else:
            msg = f"New {service} message"
        await sio.emit('toast', {'type': 'info', 'message': msg})

    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatMessage):
    """
    Smart chatbot endpoint with flexible intent detection.
    Understands natural English and Urdu patterns.
    Executes actions directly via MCP for email, WhatsApp, and Facebook.
    """
    message = req.message.strip()
    lower   = message.lower()

    async def send_reply(text: str, emit_type: str = "chat_reply"):
        await sio.emit(emit_type, {"role": "ai", "text": text})

    # ── INTENT: Send Email ────────────────────────────────────────────────
    # Patterns: "send email to foo@bar.com: msg", "email foo@bar.com: msg",
    #           "email bhejo foo@gmail.com ko: msg", "kisi ko email karo"
    is_email_intent = (
        ("email" in lower or "mail" in lower) and
        ("send" in lower or "bhejo" in lower or "karo" in lower or "kr" in lower or "likho" in lower or "@" in message)
    )
    email_match = re.search(r'([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', message)

    if is_email_intent and email_match:
        to_addr = email_match.group(1).strip()
        # Extract body: everything after the email address (and optional colon/separator)
        after_email = message[message.index(to_addr) + len(to_addr):].strip().lstrip(':').lstrip('-').strip()
        body = after_email if after_email else message
        # Try to extract subject
        subj_match = re.search(r'(?:subject|topic|regarding|re:?)[:\s]+([^\n.]+)', body, re.IGNORECASE)
        subject = subj_match.group(1).strip() if subj_match else "Message from Silver Tier AI"
        if subj_match:
            body = body[:subj_match.start()].strip() + body[subj_match.end():].strip()
        if not body or body == to_addr:
            body = message  # Fallback: use full message as body

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{MCP_SERVER_URL}/send-email",
                    json={"to": to_addr, "subject": subject, "body": body}
                ) as resp:
                    result = await resp.json()
                    if result.get("success"):
                        reply = f"✅ Email successfully sent to **{to_addr}**!"
                        await sio.emit("toast", {"type": "success", "message": reply})
                        await send_reply(reply)
                        return {"status": "sent", "to": to_addr}
                    else:
                        err = result.get("error", "Unknown error")
                        reply = f"❌ Email send karne mein masla hua: {err}\n\nCheck karo ke Gmail credentials (GMAIL_USER, GMAIL_APP_PASSWORD) `.env` file mein hain."
                        await send_reply(reply)
                        return {"status": "error", "error": err}
        except Exception as e:
            reply = f"❌ Email service se connection nahi: {e}"
            await send_reply(reply)
            return {"status": "error", "error": str(e)}

    elif is_email_intent and not email_match:
        reply = "📧 Email send karne ke liye email address batao:\n**Format:** `send email to someone@gmail.com: Your message here`"
        await send_reply(reply)
        return {"status": "needs_info"}

    # ── INTENT: Send WhatsApp ─────────────────────────────────────────────
    # Patterns: "whatsapp per msg karo John ko: hello", "send whatsapp to Name: msg"
    is_wa_intent = (
        ("whatsapp" in lower or "wp" in lower or "wts" in lower) and
        ("send" in lower or "msg" in lower or "message" in lower or "bhejo" in lower or
         "karo" in lower or "kr" in lower or "likho" in lower or "de" in lower)
    )
    # Extract contact name and message
    wa_match = re.search(
        r'(?:to|ko|se|")?([A-Za-z][A-Za-z0-9 \-_]{1,40})(?:"|ko|se)?\s*[:]\s*(.+)',
        message, re.IGNORECASE | re.DOTALL
    )
    # More patterns: "Name ko msg karo: hello"
    wa_match2 = re.search(
        r'(?:whatsapp\s+(?:per\s+)?)?(?:send\s+)?(?:message\s+)?(?:to\s+|ko\s+)?([A-Za-z][A-Za-z0-9 ]{1,40}?)(?:\s+ko)?\s*[:]\s*(.+)',
        message, re.IGNORECASE
    )
    final_wa_match = wa_match or wa_match2

    if is_wa_intent and final_wa_match:
        contact = final_wa_match.group(1).strip().strip('"').strip("'")
        wa_body = final_wa_match.group(2).strip()
        # Sanity check: contact shouldn't contain service-name words
        if any(w in contact.lower() for w in ["whatsapp", "message", "send", "mail", "facebook", "karo"]):
            contact_match2 = re.search(r'(?:to|ko)\s+"?([A-Za-z][A-Za-z0-9 ]{2,40}?)"?\s*:', message, re.IGNORECASE)
            if contact_match2:
                contact = contact_match2.group(1).strip()
        try:
            timeout = aiohttp.ClientTimeout(total=40)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{MCP_SERVER_URL}/send-whatsapp",
                    json={"contact": contact, "message": wa_body}
                ) as resp:
                    result = await resp.json()
                    if result.get("success"):
                        reply = f"✅ WhatsApp message **{contact}** ko bhej diya!"
                        await sio.emit("toast", {"type": "success", "message": reply})
                        await send_reply(reply)
                        return {"status": "sent", "contact": contact}
                    else:
                        err = result.get("error", "Unknown error")
                        reply = f"❌ WhatsApp masla: {err}"
                        if "not logged in" in err.lower():
                            reply += "\n\n👉 Dashboard mein **WhatsApp Connect** button press karo pehle."
                        await send_reply(reply)
                        return {"status": "error", "error": err}
        except Exception as e:
            reply = f"❌ WhatsApp service se connection nahi: {e}"
            await send_reply(reply)
            return {"status": "error", "error": str(e)}

    elif is_wa_intent and not final_wa_match:
        reply = "💬 WhatsApp message ke liye contact aur message batao:\n**Format:** `send whatsapp to \"Name\": Your message`"
        await send_reply(reply)
        return {"status": "needs_info"}

    # ── INTENT: Post to Facebook (AI-powered with image) ─────────────────
    # Patterns: "facebook per post karo: topic", "fb post about X", "facebook post banao X ke baare mein"
    is_fb_intent = (
        ("facebook" in lower or "fb" in lower) and
        ("post" in lower or "share" in lower or "status" in lower or "update" in lower or
         "dalo" in lower or "karo" in lower or "likho" in lower or "publish" in lower or "banao" in lower)
    )
    # Extract topic: after 'about', 'per', 'baare mein', colon, etc.
    fb_topic = None
    for pattern in [
        r'(?:about|baare\s+mein|topic|per)\s+["\']?([^:"\'\.]{3,120})',
        r'(?:post|share|dalo|karo|banao|publish)[:\s]+([^:]{3,120})',
        r'[:]\s*(.+)',
    ]:
        m = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
        if m:
            fb_topic = m.group(1).strip().rstrip('.')
            break

    if is_fb_intent:
        if not fb_topic:
            reply = "📘 Kaunse topic per Facebook post chahiye?\n**Format:** `Facebook per post karo AI technology ke baare mein`"
            await send_reply(reply)
            return {"status": "needs_info"}

        # Step 1: Generate post text with Gemini
        await send_reply(f"🤖 **'{fb_topic}'** ke baare mein post likh raha hoon aur image bhi bana raha hoon...")
        generated_text = await generate_with_gemini(
            f"""Write an engaging, professional Facebook post about: \"{fb_topic}\"
Requirements:
- 2-4 short paragraphs
- Include 2-3 relevant emojis naturally
- Professional yet friendly tone
- End with a call-to-action or engaging question
- Max 250 words
- Write in the same language as the topic (if Urdu/Hindi topic → write in that language)"""
        )
        post_text = generated_text if generated_text else fb_topic

        await send_reply(
            f"📝 Post ready:\n\n{post_text[:350]}{'...' if len(post_text) > 350 else ''}\n\n"
            f"🖼️ Image generate ho rahi hai...\n⏳ Facebook per post kar raha hoon..."
        )

        # Step 2: Post to Facebook via MCP (with image generation)
        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{MCP_SERVER_URL}/post-facebook-ai",
                    json={"text": post_text, "topic": fb_topic, "generate_image": True}
                ) as resp:
                    result = await resp.json()
                    if result.get("success"):
                        reply = f"✅ **Facebook post ho gaya!** 🎉\n\n📌 Topic: {fb_topic}\n🖼️ Image: {result.get('image_status', 'added')}"
                        await sio.emit("toast", {"type": "success", "message": "✅ Facebook post published!"})
                        await send_reply(reply)
                        return {"status": "posted", "topic": fb_topic}
                    else:
                        err = result.get("error", "Unknown error")
                        # Fallback: try plain text post
                        async with session.post(
                            f"{MCP_SERVER_URL}/post-facebook",
                            json={"text": post_text}
                        ) as resp2:
                            r2 = await resp2.json()
                            if r2.get("success"):
                                reply = f"✅ Facebook per post ho gaya! (image ke bina)\n\n*Image attach karne mein masla tha: {err}*"
                                await sio.emit("toast", {"type": "success", "message": "✅ Facebook post published!"})
                                await send_reply(reply)
                                return {"status": "posted_no_image"}
                        reply = f"❌ Facebook post masla: {err}"
                        if "not logged in" in err.lower():
                            reply += "\n\n👉 Dashboard mein **Facebook Connect** button press karo pehle."
                        await send_reply(reply)
                        return {"status": "error", "error": err}
        except Exception as e:
            reply = f"❌ Facebook service se connection nahi: {e}"
            await send_reply(reply)
            return {"status": "error", "error": str(e)}

    # ── GENERAL: Queue for AI reasoning ────────────────────────────────────
    ts_str   = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts_str}_dashboard_chat.md"
    filepath = NEEDS_ACTION_DIR / filename
    NEEDS_ACTION_DIR.mkdir(parents=True, exist_ok=True)

    content = f"""---
type: manual
status: pending
source: dashboard_chat
created: "{datetime.now().isoformat()}"
priority: high
---
# Dashboard Instruction

{message}
"""
    filepath.write_text(content, encoding='utf-8')

    reply = "📋 Instruction AI ke pass queue ho gaya. Thodi der mein **Approvals** tab check karo."
    await sio.emit("toast",       {"type": "info",  "message": reply})
    await send_reply(reply)
    await sio.emit("inbox_update", {})

    return {"status": "queued", "filename": filename}


# ─── Socket Events ────────────────────────────────────────────────────────────
@sio.on("connect")
async def on_connect(sid, environ):
    pass

@sio.on("disconnect")
async def on_disconnect(sid):
    pass


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:socket_app", host="0.0.0.0", port=8000, reload=True)
