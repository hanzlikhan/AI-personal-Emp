import os
import sys
import yaml
import re
import argparse
from datetime import datetime
import subprocess
import json
import requests
# Configuration

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLANS_DIR = os.path.join(BASE_DIR, "..", "Plans")
DONE_DIR = os.path.join(BASE_DIR, "..", "Done")
PENDING_APPROVAL_DIR = os.path.join(BASE_DIR, "..", "Pending_Approval")
DASHBOARD_PATH = os.path.join(BASE_DIR, "..", "Dashboard.md")

def read_file_content(filepath):
    """
    Reads file and extracts frontmatter and content.
    Simple implementation assuming Standard Markdown with YAML frontmatter.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Very basic YAML parsing
    try:
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                return frontmatter, body
    except Exception as e:
        print(f"[REASONING] Error parsing YAML: {e}")
    
    return {}, content

def create_plan(task_id, steps):
    """
    Creates a plan file in /Plans
    """
    if not os.path.exists(PLANS_DIR):
        os.makedirs(PLANS_DIR)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{task_id}_plan.md"
    filepath = os.path.join(PLANS_DIR, filename)
    
    content = f"""---
status: planned
created: {datetime.now().isoformat()}
---

# Plan for {task_id}

## Execution Steps
"""
    for i, step in enumerate(steps, 1):
        content += f"{i}. {step}\n"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[REASONING] Plan created: {filename}")

def call_mcp_http(endpoint, payload):
    """
    Calls the local MCP HTTP server.
    """
    url = f"http://localhost:3000/{endpoint}"
    try:
        print(f"[REASONING] 🌐 POST {url}")
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        print(f"[REASONING] MCP Response: {result}")
        return result.get("success", False)
    except requests.exceptions.RequestException as e:
        print(f"[REASONING] ❌ Error calling MCP server: {e}")
        print(f"[REASONING] ⚠️  Ensure 'node watchers/email_mcp.js' is running!")
        return False

def execute_action(action, **kwargs):
    """
    Executes a specific tool action.
    """
    is_execution_mode = kwargs.get('execution_mode', False)

    if action == "email_draft":
        if is_execution_mode:
            # EXECUTE via HTTP MCP
            print(f"[REASONING] Executing Email via MCP (HTTP)...")
            payload = {
                "to": kwargs.get('to'),
                "subject": kwargs.get('subject'),
                "body": kwargs.get('body')
            }
            call_mcp_http("send-email", payload)
        else:
            # PLAN: Create approval request
            content = kwargs.get('body')
            metadata = {
                'target': kwargs.get('to'),
                'subject': kwargs.get('subject')
            }
            create_approval_request("email", content, metadata)
        
    elif action == "linkedin_post":
        if is_execution_mode:
            # EXECUTE via HTTP MCP
             print(f"[REASONING] Executing LinkedIn via MCP (HTTP)...")
             payload = {"content": kwargs.get('content')}
             call_mcp_http("post-linkedin", payload)
        else:
            # PLAN: Create approval request
            create_approval_request("linkedin", kwargs.get('content'))

    elif action == "whatsapp_send":
         if is_execution_mode:
             # EXECUTE via HTTP MCP
             print(f"[REASONING] Executing WhatsApp via MCP (HTTP)...")
             payload = {
                 "contact": kwargs.get('contact'),
                 "message": kwargs.get('message')
             }
             call_mcp_http("send-whatsapp", payload)
         else:
             # PLAN: Create approval request
             content = kwargs.get('message')
             metadata = {
                 'target': kwargs.get('contact') 
             }
             create_approval_request("whatsapp", content, metadata)

    elif action == "log_dashboard":
        # Append to Dashboard (Simplified)
        print(f"[REASONING] Logging to Dashboard: {kwargs.get('message')}")

def create_approval_request(type, content, metadata=None):
    if not os.path.exists(PENDING_APPROVAL_DIR):
        os.makedirs(PENDING_APPROVAL_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{type}_approval.md"
    filepath = os.path.join(PENDING_APPROVAL_DIR, filename)
    
    metadata_str = ""
    if metadata:
        for key, value in metadata.items():
            metadata_str += f"{key}: \"{value}\"\n"

    file_content = f"""---
type: {type}
status: pending_approval
{metadata_str}---
# Approval Request

**Content:**
{content}
"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(file_content)
    print(f"[REASONING] Created approval request: {filename}")

def process_task(filepath):
    print(f"\n[REASONING] 🧠 Processing: {os.path.basename(filepath)}")
    
    frontmatter, body = read_file_content(filepath)
    task_type = frontmatter.get('type', 'unknown')
    
    steps = []
    
    # 1. THINK & PLAN
    if task_type == 'email':
        subject = frontmatter.get('subject', 'No Subject')
        priority = frontmatter.get('priority', 'normal')
        
        if priority == 'high' or 'urgent' in subject.lower():
            steps.append("Identify Urgent Email")
            steps.append(f"Draft Reply to {frontmatter.get('from')}")
            create_plan("email_response", steps)
            
            # 2. ACT
            reply_body = f"Received your urgent email regarding '{subject}'. We are looking into it immediately."
            execute_action("email_draft", to=frontmatter.get('from'), subject=f"Re: {subject}", body=reply_body)
            
        else:
            steps.append("Log Normal Email")
            create_plan("email_log", steps)
            execute_action("log_dashboard", message=f"Received email: {subject}")

    elif task_type == 'whatsapp':
        sender = frontmatter.get('sender', 'Unknown')
        execute_action("log_dashboard", message=f"WhatsApp from {sender}")
        
    elif task_type == 'linkedin_opportunity':
        steps.append("Analyze Opportunity")
        steps.append("Draft LinkedIn Post")
        create_plan("linkedin_strategy", steps)
        
        # ACT: Generative logic (Simulated - in real app would use LLM)
        topic = frontmatter.get('context', 'Industry Update')
        body_snippet = body[:100] if body else "No details"
        post_content = f"🚀 Update: {topic}\n\n{body}\n\n#AI #SilverTier #Innovation"
        
        execute_action("linkedin_post", content=post_content)

    # 3. CONCLUDE
    # Move to Done
    if not os.path.exists(DONE_DIR):
        os.makedirs(DONE_DIR)
    
    new_path = os.path.join(DONE_DIR, os.path.basename(filepath))
    try:
        os.rename(filepath, new_path)
        print(f"[REASONING] Task moved to Done: {os.path.basename(filepath)}")
    except Exception as e:
        print(f"[REASONING] proccessed but failed to move file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filepath", help="Path to the task file")
    parser.add_argument("--execute", action="store_true", help="Execute the task (skip planning/approval creation)")
    args = parser.parse_args()
    
    if os.path.exists(args.filepath):
        try:
            # If execute mode, we parse the file (which is likely an approval request or original task)
            # and trigger the action directly.
            # But wait, approval_watcher passes the *approved* file.
            # We need to adapt process_task to handle execution logic or creating plans.
            
            # Simple hack: Pass execution_mode to process_task
            
            print(f"\n[REASONING] 🧠 Processing: {os.path.basename(args.filepath)} (Execute: {args.execute})")
    
            frontmatter, body = read_file_content(args.filepath)
            task_type = frontmatter.get('type', 'unknown')
            
            # If standard task processing (Planning)
            if not args.execute:
                 process_task(args.filepath)
            
            # If Execution Mode (Triggered by Approval Watcher)
            else:
                # Based on type, execute action
                if task_type == 'email':
                    # Extract details from metadata or body
                    # Approval files have metadata in frontmatter
                    target = frontmatter.get('target', frontmatter.get('from')) # 'from' fallback
                    subject = frontmatter.get('subject', 'No Subject')
                    body_content = body
                    
                    execute_action("email_draft", to=target, subject=subject, body=body_content, execution_mode=True)
                    
                elif task_type == 'linkedin':
                    execute_action("linkedin_post", content=body, execution_mode=True)
                    
                elif task_type == 'whatsapp':
                    target = frontmatter.get('target')
                    execute_action("whatsapp_send", contact=target, message=body, execution_mode=True)
                
                # Move to Done (Here, because we are the executor triggered by approved file)
                # If call_mcp_http returns True (or generally if we reached here without raising exception)
                # we should let approval_watcher handle the move, OR do it here if run separately.
                # Since approval_watcher calls this via subprocess.run(check=True), if we don't crash, it moves the file.
                # So we just print success.
                print(f"[REASONING] ✅ Execution passed to MCP.")
                
        except Exception as e:
            print(f"[REASONING] Error: {e}")
    else:
        print(f"[REASONING] File not found: {args.filepath}")
