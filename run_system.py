import os
import sys
import time
import subprocess
import webbrowser
import requests
import signal
import shutil

# Configuration
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHERS_DIR = os.path.join(ROOT_DIR, "watchers")
DASHBOARD_DIR = os.path.join(ROOT_DIR, "dashboard")

SERVICES = {}

def log(msg, color="white"):
    colors = {
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "white": "\033[0m"
    }
    c = colors.get(color, "\033[0m")
    # Clear line before printing to handle potential overlaps
    print(f"\r{c}[Silver Tier] {msg}\033[0m", flush=True)

def check_dependencies():
    required = ["aiohttp", "requests", "uvicorn", "watchdog", "python-socketio"]
    missing = []
    for req in required:
        module_name = req.replace("-", "_") 
        if req == "python-socketio": module_name = "socketio"
        try:
            __import__(module_name)
        except ImportError:
            missing.append(req)
    
    if missing:
        log(f"Installing missing dependencies: {', '.join(missing)}...", "yellow")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        log("Dependencies installed!", "green")
        
    global requests
    import requests

def start_background_process(name, command, cwd):
    """Starts a process in the background, logging output into separate files."""
    log(f"Starting {name} (Background)...", "cyan")
    log_file = os.path.join(cwd, f"{name.replace(' ', '_').lower()}.log")
    
    try:
        with open(log_file, "w") as f:
            if sys.platform == "win32":
                # STARTUPINFO to hide window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                proc = subprocess.Popen(
                    command, 
                    cwd=cwd, 
                    shell=True,
                    creationflags=subprocess.CREATE_NEW_CONSOLE, 
                    startupinfo=startupinfo,
                    stdout=f, 
                    stderr=subprocess.STDOUT 
                )
            else:
                proc = subprocess.Popen(
                    command, 
                    cwd=cwd, 
                    shell=True,
                    stdout=f,
                    stderr=subprocess.STDOUT
                )
        SERVICES[name] = proc
        return proc
    except Exception as e:
        log(f"Failed to start {name}: {e}", "red")
        return None

def wait_for_endpoint(url, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(url, timeout=1)
            return True
        except:
            time.sleep(1)
    return False

def check_integration(service_name, endpoint):
    """Checks integration status via API endpoint."""
    try:
        # Timeout increased to 35s to ensure the background check (which may take up to 30s)
        # completes and closes its window BEFORE we return false/true.
        # This prevents the "disappearing window" race condition.
        resp = requests.get(endpoint, timeout=35)
        if resp.status_code == 200:
            data = resp.json()
            # Basic validation based on service
            if service_name == "WhatsApp":
                # Check for 'new_messages' key or valid response
                return True 
            if service_name == "Facebook":
                # Check status field from our new fast-fail logic
                if data.get('status') == 'offline': return False
                return True
            return True
        return False
    except:
        return False



def cleanup():
    log("\nShutting down...", "red")
    for name, proc in SERVICES.items():
        try:
            # Windows robust kill
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
    sys.exit(0)

def main():
    os.system("cls" if os.name == "nt" else "clear")
    log("Initializing Silver Tier AI System...", "green")
    
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    check_dependencies()
    
    # Kill old processes
    os.system("taskkill /f /im uvicorn.exe >nul 2>&1")
    os.system("taskkill /f /im node.exe >nul 2>&1")
    
    # 1. Start Core Services (Background)
    # Quote the executable path to handle spaces in username
    python_exe = f'"{sys.executable}"'
    start_background_process("Backend API", f"{python_exe} -m uvicorn watchers.api:socket_app --port 8000", ROOT_DIR)
    start_background_process("MCP Server", f"node mcp_server.js", WATCHERS_DIR)

    log("Waiting for Core Services...", "yellow")
    log("Waiting for Core Services (up to 60s)...", "yellow")
    backend_ok = wait_for_endpoint("http://localhost:8000/health", timeout=60)
    mcp_ok = wait_for_endpoint("http://localhost:3000/health", timeout=60)
    
    if backend_ok and mcp_ok:
        log("Core Services Online!", "green")
    else:
        if not backend_ok: log("❌ Backend API failed to respond at http://localhost:8000/health", "red")
        if not mcp_ok: log("❌ MCP Server failed to respond at http://localhost:3000/health", "red")
        
        # Keep window open to see error
        log("Check the console windows for errors.", "red")
        cleanup()

    # 2. Status Check & Instructions
    log("Checking Integration Status...", "cyan")
    whatsapp_ok = check_integration("WhatsApp", "http://localhost:3000/check-whatsapp")
    facebook_ok = check_integration("Facebook", "http://localhost:3000/check-facebook")
    
    if whatsapp_ok and facebook_ok:
        log("✅ All Integrations Active (Headless Mode)", "green")
    else:
        log("ℹ  Some integrations are offline. Running in Background.", "white")
        if not whatsapp_ok: log("   - WhatsApp: Use Dashboard 'Connect' button to scan QR", "yellow")
        if not facebook_ok: log("   - Facebook: Use Dashboard 'Connect' button to login", "yellow")

    # 3. Launch Watchers (Background)
    log("Launching Autonomous Agents...", "cyan")
    start_background_process("Gmail Watcher", f"{python_exe} watchers/gmail_watcher.py", ROOT_DIR)
    start_background_process("WhatsApp Watcher", f"{python_exe} watchers/whatsapp_watcher.py", ROOT_DIR)
    start_background_process("Facebook Watcher", f"{python_exe} watchers/facebook_watcher.py", ROOT_DIR)
    # Fixed: Run orchestrator.py (daemon) instead of reasoning_loop.py (one-off)
    start_background_process("AI Brain", f"{python_exe} watchers/orchestrator.py", ROOT_DIR)

    # 4. Launch Dashboard
    log("Launching Dashboard...", "cyan")
    start_background_process("Frontend", "npm run dev", DASHBOARD_DIR)
    
    time.sleep(5)
    webbrowser.open("http://localhost:3008")
    
    log("\nAll Systems GO! 🚀 (Headless Mode)", "green")
    log("Dashboard: http://localhost:3008", "white")
    log("Press Ctrl+C to stop all services.", "white")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
