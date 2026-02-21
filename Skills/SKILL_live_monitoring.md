# Skill: Live Monitoring & Real-time Dashboard

## Overview
The Silver Tier dashboard now uses a **push-based architecture** for real-time updates using WebSockets (Socket.IO) and a lightweight FastAPI backend.

### Architecture
- **Backend**: `backend/main.py` (FastAPI + python-socketio)
  - Serves REST APIs (`/status`, `/history`, `/stats`)
  - Manages WebSocket connections for live push events (`history_update`, `toast`)
  - Receives Webhooks (`/webhook/{service}`) from local watchers
- **Frontend**: `dashboard/app/page.tsx` (Next.js + socket.io-client)
  - Connects to backend WS
  - Listens for updates and refreshes state instantly
- **Watchers**: `watchers/*.py` (Python Daemons)
  - Poll external services (Gmail API, MCP Browser Automation)
  - On new event -> Create `.md` in `/Needs_Action` -> **POST /webhook/{service}** to backend

## How to Add a New Live Service
To add a new service (e.g., LinkedIn, Slack):

1. **Create Watcher**: `watchers/new_service_watcher.py`
   - Poll your service.
   - On event, create `.md` task file.
   - **Crucial**: Call `notify_backend(event_type, data)`:
     ```python
     async with aiohttp.ClientSession() as session:
         await session.post("http://localhost:8000/webhook/new_service", json={...})
     ```

2. **Update Backend**: `backend/main.py`
   - Add `HISTORY_FILES` entry.
   - Handle `webhook/new_service` logic (if special handling needed).

3. **Update Dashboard**:
   - Add new tab in `Dashboard.tsx`.
   - Listen for `history_update` for the new service.

## Debugging
- **Backend Logs**: `backend_api.log` (if redirected) or terminal output.
- **Watcher Logs**: `watchers/*.log`.
- **Frontend**: Check Browser Console for Socket.IO connection status.

## Commands
- **Start Backend**: `uvicorn backend.main:socket_app --reload --port 8000`
- **Start Watcher**: `python watchers/gmail_watcher.py`
