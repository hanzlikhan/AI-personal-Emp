@echo off
start cmd /k "python watchers/api_server.py"
start cmd /k "cd dashboard && set PORT=3005 && npm run dev"
echo Silver Tier Dashboard Launching...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3008
pause
