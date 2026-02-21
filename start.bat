@echo off
title Silver Tier AI — Full System Startup
color 0A
echo.
echo  ========================================
echo   Silver Tier AI — Full System Startup
echo  ========================================
echo.

REM Kill old processes on ports 8000 and 3008
echo [Clearing ports 8000, 3000, 3001...]
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3008') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3001') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 >nul

set ROOT=%~dp0

REM 1. Backend (FastAPI + Socket.IO)
echo [1/5] Starting Backend on port 8000...
start "Backend" cmd /k "cd /d %ROOT% && uvicorn watchers.api:socket_app --reload --port 8000"
timeout /t 3 >nul

REM 2. MCP Server (WhatsApp + Facebook)
echo [2/5] Starting MCP Server on port 3001...
start "MCP Server" cmd /k "cd /d %ROOT%\watchers && node mcp_server.js"
timeout /t 4 >nul

REM 3. Gmail Watcher
echo [3/5] Starting Gmail Watcher...
start "Gmail Watcher" cmd /k "cd /d %ROOT% && python watchers/gmail_watcher.py"
timeout /t 2 >nul

REM 4. WhatsApp Watcher
echo [4/5] Starting WhatsApp Watcher...
start "WhatsApp Watcher" cmd /k "cd /d %ROOT% && python watchers/whatsapp_watcher.py"
timeout /t 1 >nul

REM 5. Facebook Watcher
echo [5/7] Starting Facebook Watcher...
start "Facebook Watcher" cmd /k "cd /d %ROOT% && python watchers/facebook_watcher.py"
timeout /t 1 >nul

REM 6. Reasoning Loop (The Brain)
echo [6/7] Starting AI Brain (Reasoning Loop)...
start "AI Brain" cmd /k "cd /d %ROOT% && python watchers/reasoning_loop.py"
timeout /t 2 >nul

REM 7. Frontend (Next.js)
echo [7/7] Starting Frontend on port 3000...
start "Frontend" cmd /k "cd /d %ROOT%\dashboard && npm run dev"

echo.
echo  ========================================
echo   All 6 services are starting!
echo.
echo   Backend:   http://localhost:8000/health
echo   Dashboard: http://localhost:3000
echo  ========================================
echo.
echo   NOTE: First time? You need to:
echo   1. Add your credentials.json in watchers/
echo   2. Scan WhatsApp QR code in MCP window
echo   3. Login to Facebook in MCP window
echo.
pause
