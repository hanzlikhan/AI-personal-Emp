@echo off
echo ============================================
echo   Silver Tier AI Employee — Startup
echo ============================================
echo.

REM 1. Start the Unified MCP Server (The Hands)
echo [1/6] Starting MCP Server (Email + WhatsApp + Facebook)...
start "MCP Server" cmd /k "cd /d %~dp0 && node watchers/mcp_server.js"
timeout /t 3 /nobreak >nul

REM 2. Start Orchestrator (The Brain — watches /Needs_Action)
echo [2/6] Starting Orchestrator...
start "Orchestrator" cmd /k "cd /d %~dp0 && python watchers/orchestrator.py"
timeout /t 2 /nobreak >nul

REM 3. Start Gmail Watcher (async, 30s polling)
echo [3/6] Starting Gmail Watcher...
start "Gmail Watcher" cmd /k "cd /d %~dp0 && python watchers/gmail_watcher.py"
timeout /t 1 /nobreak >nul

REM 4. Start WhatsApp Watcher (async, polls MCP every 30s)
echo [4/6] Starting WhatsApp Watcher...
start "WhatsApp Watcher" cmd /k "cd /d %~dp0 && python watchers/whatsapp_watcher.py"
timeout /t 1 /nobreak >nul

REM 5. Start Facebook Watcher (async, polls MCP every 30s)
echo [5/6] Starting Facebook Watcher...
start "Facebook Watcher" cmd /k "cd /d %~dp0 && python watchers/facebook_watcher.py"
timeout /t 1 /nobreak >nul

REM 6. Start LinkedIn Watcher (optional)
echo [6/6] Starting LinkedIn Watcher...
start "LinkedIn Watcher" cmd /k "cd /d %~dp0 && python watchers/linkedin_watcher.py"

echo.
echo ============================================
echo   All 6 systems launched!
echo   (6 terminal windows should be open)
echo.
echo   Platform  ^| Watcher         ^| Poll Interval
echo   ----------+------------------+--------------
echo   Gmail     ^| gmail_watcher    ^| 30s (async)
echo   WhatsApp  ^| whatsapp_watcher ^| 30s (async)
echo   Facebook  ^| facebook_watcher ^| 30s (async)
echo   LinkedIn  ^| linkedin_watcher ^| 60s
echo.
echo   To stop: Close each terminal window
echo   or press Ctrl+C in each window.
echo ============================================
pause
