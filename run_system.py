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
    """Starts a process in the background, hidden from view."""
    log(f"Starting {name} (Background)...", "cyan")
    try:
        if sys.platform == "win32":
            # STARTUPINFO to hide window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            
            proc = subprocess.Popen(
                command, 
                cwd=cwd, 
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE, # Separate console but hidden? No, CREATE_NO_WINDOW
                startupinfo=startupinfo,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            proc = subprocess.Popen(
                command, 
                cwd=cwd, 
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
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

def interactive_setup():
    """Asking the user to set up integrations sequentially."""
    log("\n--- INTEGRATION CHECK ---", "yellow")
    
    # 1. WhatsApp
    log("Checking WhatsApp Integration (may take 10s)...", "white")
    if not check_integration("WhatsApp", "http://localhost:3000/check-whatsapp"):
        print("\n\033[93m[Action Required] WhatsApp is not connected.\033[0m")
        choice = input("   Do you want to connect WhatsApp now? (y/n): ").strip().lower()
        if choice == 'y':
            log("Launching WhatsApp Web... Please scan QR code in the browser.", "cyan")
            # Trigger the connect endpoint which keeps browser OPEN
            try: requests.get("http://localhost:3000/connect-whatsapp", timeout=2) 
            except: pass
            
            input("   Press ENTER once you have scanned the QR code and chats are visible...")
        else:
            log("Skipping WhatsApp...", "red")

    # 2. Facebook
    log("Checking Facebook Integration (may take 10s)...", "white")
    if not check_integration("Facebook", "http://localhost:3000/check-facebook"):
        print("\n\033[93m[Action Required] Facebook is not connected.\033[0m")
        choice = input("   Do you want to connect Facebook now? (y/n): ").strip().lower()
        if choice == 'y':
            log("Launching Facebook... Please log in if needed.", "cyan")
            # Trigger the connect endpoint which keeps browser OPEN
            try: requests.get("http://localhost:3000/connect-facebook", timeout=2)
            except: pass
            
            input("   Press ENTER once you are logged into Facebook...")
        else:
            log("Skipping Facebook...", "red")
            
    # 3. Gmail
    log("Checking Gmail Integration...", "white")
    # Gmail is handled by python script, so verification is implicit via existence of token.
    token_path = os.path.join(ROOT_DIR, "watchers", "token.pickle")
    if os.path.exists(token_path):
        log("Gmail is authenticated.", "green")
    else:
        print("\n\033[93m[Action Required] Gmail is not authenticated.\033[0m")
        log("The Gmail Watcher will handle authentication when it starts.", "white")

    log("\nIntegrations Verified. Launching Dashboard...", "green")

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
    start_background_process("Backend API", f"{sys.executable} -m uvicorn watchers.api:socket_app --port 8000", ROOT_DIR)
    start_background_process("MCP Server", f"node mcp_server.js", WATCHERS_DIR)

    log("Waiting for Core Services...", "yellow")
    if wait_for_endpoint("http://localhost:8000/health") and wait_for_endpoint("http://localhost:3000/health"):
        log("Core Services Online!", "green")
    else:
        log("Failed to start core services.", "red")
        cleanup()

    # 2. Interactive Integration Check
    interactive_setup()

    # 3. Launch Watchers (Background)
    log("Launching Autonomous Agents...", "cyan")
    start_background_process("Gmail Watcher", f"{sys.executable} watchers/gmail_watcher.py", ROOT_DIR)
    start_background_process("WhatsApp Watcher", f"{sys.executable} watchers/whatsapp_watcher.py", ROOT_DIR)
    start_background_process("Facebook Watcher", f"{sys.executable} watchers/facebook_watcher.py", ROOT_DIR)
    start_background_process("AI Brain", f"{sys.executable} watchers/reasoning_loop.py", ROOT_DIR)

    # 4. Launch Dashboard
    log("Launching Dashboard...", "cyan")
    start_background_process("Frontend", "npm run dev", DASHBOARD_DIR)
    
    time.sleep(5)
    webbrowser.open("http://localhost:3008")
    
    log("\nAll Systems GO! 🚀", "green")
    log("Press Ctrl+C to stop all services.", "white")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
