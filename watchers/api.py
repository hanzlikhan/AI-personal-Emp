"""
Silver Tier AI — Dashboard Backend
===================================
CORRECT start command:
  uvicorn watchers.api:socket_app --reload --port 8000
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import socketio
import asyncio
import re
import time
import json
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ── Directory Config ──────────────────────────────────────────────────────────
BASE             = Path(__file__).parent.parent
NEEDS_ACTION_DIR = BASE / "Needs_Action"
PENDING_DIR      = BASE / "Pending_Approval"
APPROVED_DIR     = BASE / "Approved"
DONE_DIR         = BASE / "Done"
REJECTED_DIR     = BASE / "Rejected"
LOGS_DIR         = BASE / "Logs"

for d in [NEEDS_ACTION_DIR, PENDING_DIR, APPROVED_DIR, DONE_DIR, REJECTED_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── FastAPI + Socket.IO ───────────────────────────────────────────────────────
app = FastAPI(title="Silver Tier API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

# IMPORTANT: serve socket_app, NOT app
socket_app = socketio.ASGIApp(sio, app)

_loop: asyncio.AbstractEventLoop | None = None


# ── Markdown parser helper ────────────────────────────────────────────────────
def parse_md_frontmatter(text: str) -> dict:
    """Parse YAML-like frontmatter from md files."""
    meta: dict = {}
    if not text.startswith("---"):
        return meta
    parts = text.split("---", 2)
    if len(parts) < 3:
        return meta
    for line in parts[1].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip().strip('"')
    meta["_body"] = parts[2].strip()
    return meta


def read_md_file(f: Path) -> dict:
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
        meta = parse_md_frontmatter(text)
        meta["filename"] = f.name
        meta["content"]  = text
        meta.setdefault("type", "unknown")
        return meta
    except Exception:
        return {"filename": f.name, "content": "", "type": "unknown"}


# ── File Watcher ──────────────────────────────────────────────────────────────
# ─── Event Handler ────────────────────────────────────────────────────────────

class DashboardEventHandler(FileSystemEventHandler):
    def _safe_emit(self, event_name: str, data: dict):
        if _loop and _loop.is_running():
            asyncio.run_coroutine_threadsafe(sio.emit(event_name, data), _loop)

    def on_created(self, event):
        if event.is_directory: return
        self._handle_event(event.src_path, "created")

    def on_modified(self, event):
        if event.is_directory: return
        self._handle_event(event.src_path, "modified")

    def on_moved(self, event):
         if event.is_directory: return
         self._handle_event(event.dest_path, "moved")
    
    def _handle_event(self, path_str, action):
        path = Path(path_str)
        try:
            filename = path.name
            folder = path.parent.name

            # Special handling for JSON cache files in watchers root
            if filename in ["gmail_history.json", "whatsapp_history.json", "facebook_history.json", "status.json"]:
                # specific event for history/status update
                if filename == "status.json":
                    self._safe_emit('status_update', {})
                elif "history" in filename:
                    service = filename.replace("_history.json", "")
                    try:
                        content = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                        self._safe_emit('history_update', {'service': service, 'data': content})
                    except: pass
                return

            # Normal folder watching
            if folder == "Needs_Action":
                content = path.read_text(encoding="utf-8", errors="ignore")
                self._safe_emit('inbox_update', {'action': action, 'filename': filename, 'content': content})
            elif folder == "Pending_Approval":
                content = path.read_text(encoding="utf-8", errors="ignore")
                self._safe_emit('approval_update', {'action': action, 'filename': filename, 'content': content})
            elif folder == "Logs":
                self._safe_emit('log_update', {'filename': filename})
            elif folder in ("Approved", "Rejected", "Done") and action == "moved":
                 self._safe_emit("status_update", {"folder": folder, "filename": filename})

        except Exception as e:
            print(f"Error handling event for {path}: {e}")

@app.on_event("startup")
async def startup():
    global _loop
    _loop    = asyncio.get_event_loop()
    watcher  = DashboardWatcher() # Using the new class name logic, but wait, I defined DashboardEventHandler above?
    # Keeping consistent with original class name DashboardWatcher if possible, or replacing. 
    # The original code has DashboardWatcher. I will use DashboardEventHandler class name to match my replacement content above,
    # BUT I need to make sure I update the startup function to use DashboardEventHandler.
    
    # Actually, let's keep the name distinct if I can't overwrite easily. 
    # Original class was DashboardWatcher. I'll replace it with DashboardEventHandler logic but rename it to DashboardWatcher to invoke less diff.
    pass 

# Retrying the replacement with correct class name to match previous context or just replacing the whole block.
# The original code used DashboardWatcher (lines 84-110). I will replace that block.

class DashboardWatcher(FileSystemEventHandler):
    def _safe_emit(self, event_name: str, data: dict):
        if _loop and _loop.is_running():
            asyncio.run_coroutine_threadsafe(sio.emit(event_name, data), _loop)

    def on_created(self, event):
        if event.is_directory: return
        self._handle_event(event.src_path, "created")

    def on_modified(self, event):
        if event.is_directory: return
        self._handle_event(event.src_path, "modified")

    def on_moved(self, event):
         if event.is_directory: return
         self._handle_event(event.dest_path, "moved")
    
    def _handle_event(self, path_str, action):
        path = Path(path_str)
        try:
            filename = path.name
            folder = path.parent.name

            # Special handling for JSON cache files in watchers root
            if filename in ["gmail_history.json", "whatsapp_history.json", "facebook_history.json", "status.json"]:
                # specific event for history/status update
                if filename == "status.json":
                    self._safe_emit('status_update', {})
                elif "history" in filename:
                    service = filename.replace("_history.json", "")
                    try:
                        content = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                        self._safe_emit('history_update', {'service': service, 'data': content})
                    except: pass
                return

            # Normal folder watching
            if folder == "Needs_Action":
                data = read_md_file(path)
                self._safe_emit('inbox_update', {'action': action, **data})
            elif folder == "Pending_Approval":
                data = read_md_file(path)
                self._safe_emit('approval_update', {'action': action, **data})
            elif folder == "Logs":
                self._safe_emit('log_update', {'filename': filename})
            elif folder in ("Approved", "Rejected", "Done") and action == "moved":
                 self._safe_emit("status_update", {"folder": folder, "filename": filename})

        except Exception as e:
            # print(f"Error handling event for {path}: {e}")
            pass

@app.on_event("startup")
async def startup():
    global _loop
    _loop    = asyncio.get_event_loop()
    watcher  = DashboardWatcher()
    observer = Observer()
    # Watch folders
    for d in [NEEDS_ACTION_DIR, PENDING_DIR, APPROVED_DIR, DONE_DIR, REJECTED_DIR, LOGS_DIR]:
        observer.schedule(watcher, str(d), recursive=False)
    
    # Watch root for JSON files (non-recursive)
    observer.schedule(watcher, str(BASE), recursive=False)
    
    observer.start()
    print("✅ Silver Tier Backend running — watching all directories & caches")
    print(f"📁 Root: {BASE}")


# ─── Models ────────────────────────────────────────────────────────────────────
class ApprovalRequest(BaseModel):
    filename: str

class ChatMessage(BaseModel):
    message: str


# ─── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Silver Tier API is running"}


@app.get("/stats")
async def get_stats():
    def count(d: Path) -> int:
        return len(list(d.glob("*.md"))) if d.exists() else 0
    return {
        "needs_action": count(NEEDS_ACTION_DIR),
        "pending":      count(PENDING_DIR),
        "approved":     count(APPROVED_DIR),
        "done":         count(DONE_DIR),
        "rejected":     count(REJECTED_DIR),
    }

@app.get("/status")
async def get_status():
    f = BASE / "status.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except: pass
    return {}

@app.get("/history/{service}")
async def get_history(service: str):
    f = BASE / f"{service}_history.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except: pass
    return []

@app.get("/pending")
async def get_pending():
    if not PENDING_DIR.exists():
        return []
    return [read_md_file(f) for f in sorted(PENDING_DIR.glob("*.md"), reverse=True)]


@app.get("/inbox/all")
async def get_inbox_all():
    """All items from Needs_Action — sorted newest first."""
    if not NEEDS_ACTION_DIR.exists():
        return []
    files = sorted(NEEDS_ACTION_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [read_md_file(f) for f in files[:50]]


@app.get("/inbox/gmail")
async def get_inbox_gmail():
    """Only Gmail emails from Needs_Action."""
    if not NEEDS_ACTION_DIR.exists():
        return []
    files = sorted(NEEDS_ACTION_DIR.glob("*gmail*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [read_md_file(f) for f in files[:30]]


@app.get("/inbox/whatsapp")
async def get_inbox_whatsapp():
    """Only WhatsApp messages from Needs_Action."""
    if not NEEDS_ACTION_DIR.exists():
        return []
    files = sorted(NEEDS_ACTION_DIR.glob("*WhatsApp*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [read_md_file(f) for f in files[:30]]


@app.get("/inbox/facebook")
async def get_inbox_facebook():
    """Only Facebook events from Needs_Action."""
    if not NEEDS_ACTION_DIR.exists():
        return []
    files = sorted(NEEDS_ACTION_DIR.glob("*Facebook*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [read_md_file(f) for f in files[:30]]


@app.get("/logs")
async def get_logs():
    """Recent log lines."""
    entries = []
    if LOGS_DIR.exists():
        for f in sorted(LOGS_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)[:3]:
            try:
                lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in lines[-50:]:
                    entries.append({"file": f.name, "line": line})
            except Exception:
                pass
    return entries[-100:]


@app.post("/approve")
async def approve(req: ApprovalRequest):
    src  = PENDING_DIR / req.filename
    dest = APPROVED_DIR / req.filename
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.filename}")
    src.rename(dest)
    await sio.emit("toast", {"type": "success", "message": f"✅ Approved: {req.filename}"})
    return {"status": "approved", "filename": req.filename}


@app.post("/reject")
async def reject(req: ApprovalRequest):
    src  = PENDING_DIR / req.filename
    dest = REJECTED_DIR / req.filename
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.filename}")
    src.rename(dest)
    await sio.emit("toast", {"type": "info", "message": f"❌ Rejected: {req.filename}"})
    return {"status": "rejected", "filename": req.filename}


@app.post("/chat")
async def chat(req: ChatMessage):
    ts       = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}_dashboard.md"
    path     = NEEDS_ACTION_DIR / filename
    content  = f"""---
type: manual
status: pending
source: dashboard_chat
created: "{time.strftime('%Y-%m-%dT%H:%M:%S')}"
priority: high
---
# Dashboard Instruction

{req.message}
"""
    path.write_text(content, encoding="utf-8")
    await sio.emit("toast", {"type": "info", "message": "📤 Instruction sent to AI"})
    return {"status": "sent", "filename": filename}


@app.post("/connect/{service}")
async def connect_service(service: str):
    """Trigger on-demand connection for a service."""
    # Logic: Fire a request to the MCP server OR just rely on the frontend 
    # finding that the service is now checking.
    # Actually, we can just trigger the check endpoint on the MCP server 
    # which will launch the browser if not open.
    
    if service in ["whatsapp", "facebook"]:
        # MCP Server is on port 3000
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # This endpoint on MCP server triggers the check/launch logic
                url = f"http://localhost:3000/check-{service}"
                async with session.get(url) as resp:
                    return await resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to trigger {service}: {e}")
    
    elif service == "gmail":
        # Gmail is python based. We can trigger a one-off check?
        # Or just tell user to check terminal. 
        # For now, just return ok as gmail watcher is autonomous.
        return {"status": "triggered", "message": "Gmail watcher is running in background"}

    return {"status": "unknown_service"}

# ── Socket Events ─────────────────────────────────────────────────────────────
@sio.on("connect")
async def on_connect(sid, environ):
    # print(f"🔌 Client connected: {sid}")
    pass

@sio.on("disconnect")
async def on_disconnect(sid):
    # print(f"🔌 Client disconnected: {sid}")
    pass
