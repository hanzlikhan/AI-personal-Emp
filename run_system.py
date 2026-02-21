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
            requests.get(url, timeout=5)
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
    
    # Kill old processes by Port (Robust cleanup)
    def kill_port(port):
        try:
            # Find PID using netstat
            cmd = f"netstat -ano | findstr :{port}"
            output = subprocess.check_output(cmd, shell=True).decode()
            lines = output.strip().split('\n')
            pids = set()
            for line in lines:
                parts = line.split()
                # Line format: TCP 0.0.0.0:8000 0.0.0.0:0 LISTENING 1234
                if len(parts) > 4 and str(port) in parts[1]:
                    pids.add(parts[-1])
            
            for pid in pids:
                if pid != "0":
                    log(f"Killing process on port {port} (PID {pid})...", "yellow")
                    os.system(f"taskkill /F /PID {pid} >nul 2>&1")
        except:
            pass

    kill_port(8000) # Backend
    kill_port(3001) # MCP
    os.system("taskkill /f /im node.exe >nul 2>&1") # Cleanup extra node

    
    # 1. Start Core Services (Background)
    # Quote the executable path to handle spaces in username
    python_exe = f'"{sys.executable}"'
    start_background_process("Backend API", f"{python_exe} -m uvicorn backend.main:socket_app --reload --port 8000", ROOT_DIR)
    start_background_process("MCP Server", f"node mcp_server.js", WATCHERS_DIR)

    log("Waiting for Core Services...", "yellow")
    log("Waiting for Core Services (up to 60s)...", "yellow")
    backend_ok = wait_for_endpoint("http://127.0.0.1:8000/health", timeout=60) # /health is faster
    mcp_ok = wait_for_endpoint("http://127.0.0.1:3001/health", timeout=60)
    
    if backend_ok and mcp_ok:
        log("Core Services Online!", "green")
    else:
        if not backend_ok: log("❌ Backend API failed to respond at http://127.0.0.1:8000/status", "red")
        if not mcp_ok: log("❌ MCP Server failed to respond at http://127.0.0.1:3001/health", "red")
        
        # Keep window open to see error
        log("Check the console windows for errors.", "red")
        cleanup()

    # 2. Status Check & Instructions
    log("Checking Integration Status...", "cyan")
    whatsapp_ok = check_integration("WhatsApp", "http://127.0.0.1:3001/check-whatsapp")
    facebook_ok = check_integration("Facebook", "http://127.0.0.1:3001/check-facebook")
    
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
    start_background_process("Approval Watcher", f"{python_exe} watchers/approval_watcher.py", ROOT_DIR)

    # 4. Launch Dashboard
    log("Launching Dashboard...", "cyan")
    start_background_process("Frontend", "npm run dev", DASHBOARD_DIR)
    
    time.sleep(5)
    webbrowser.open("http://localhost:3000")
    
    log("\nAll Systems GO! 🚀 (Headless Mode)", "green")
    log("Dashboard: http://localhost:3000", "white")
    log("Press Ctrl+C to stop all services.", "white")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
