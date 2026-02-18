@echo off
echo Starting Silver Tier AI Employee...

REM 1. Start Email MCP Server (The Hands)
start "Email MCP Server" cmd /k "node watchers/email_mcp.js"

REM 2. Start Orchestrator (The Brain)
start "Orchestrator" cmd /k "python watchers/orchestrator.py"

REM 3. Start Gmail Watcher (The Eyes - Email)
start "Gmail Watcher" cmd /k "python watchers/gmail_watcher.py"

REM 4. Start WhatsApp Watcher (The Eyes - WhatsApp)
REM NOTE: This will open a browser window. Do not close it.
start "WhatsApp Watcher" cmd /k "python watchers/whatsapp_watcher.py"

REM 5. Start LinkedIn Watcher (The Eyes - LinkedIn)
REM NOTE: This will open a browser window. Do not close it.
start "LinkedIn Watcher" cmd /k "python watchers/linkedin_watcher.py"

echo All systems initialized.
echo Monitor the separate terminal windows for logs.
pause
