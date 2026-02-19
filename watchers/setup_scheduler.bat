@echo off
:: ============================================================
:: setup_scheduler.bat — Silver Tier Windows Task Scheduler Setup
:: Run this ONCE as Administrator to register scheduled tasks.
:: ============================================================
echo [SETUP] Registering Silver Tier Scheduler with Windows Task Scheduler...

set PYTHON=%~dp0..\\.venv\Scripts\pythonw.exe
set SCRIPT=%~dp0scheduler.py
set WATCHDOG=%~dp0scheduler.py

:: --- Task 1: Scheduler Daemon (daily at 08:45, restarts daily) ---
schtasks /Create /F ^
    /TN "SilverTierScheduler" ^
    /TR "\"%PYTHON%\" \"%SCRIPT%\" --daemon" ^
    /SC DAILY ^
    /ST 08:45 ^
    /RL HIGHEST ^
    /RU "%USERNAME%"

if %ERRORLEVEL% EQU 0 (
    echo [SETUP] OK: SilverTierScheduler registered (daily at 08:45)
) else (
    echo [SETUP] WARNING: Could not register SilverTierScheduler. Run as Administrator.
)

:: --- Task 2: Watchdog (every 30 minutes, auto-restart if daemon died) ---
schtasks /Create /F ^
    /TN "SilverTierWatchdog" ^
    /TR "\"%PYTHON%\" \"%WATCHDOG%\" --watchdog" ^
    /SC MINUTE ^
    /MO 30 ^
    /RL HIGHEST ^
    /RU "%USERNAME%"

if %ERRORLEVEL% EQU 0 (
    echo [SETUP] OK: SilverTierWatchdog registered (every 30 min)
) else (
    echo [SETUP] WARNING: Could not register SilverTierWatchdog. Run as Administrator.
)

echo.
echo [SETUP] Done. Registered tasks:
schtasks /Query /TN "SilverTierScheduler" /FO LIST 2>nul | findstr "Task Name\|Next Run\|Status"
schtasks /Query /TN "SilverTierWatchdog"  /FO LIST 2>nul | findstr "Task Name\|Next Run\|Status"

echo.
echo [SETUP] To test immediately:
echo   .venv\Scripts\python watchers\scheduler.py --simulate
echo.
echo [SETUP] To remove tasks:
echo   schtasks /Delete /TN "SilverTierScheduler" /F
echo   schtasks /Delete /TN "SilverTierWatchdog"  /F
pause
