
import os
import shutil
import glob
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from pathlib import Path

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

# Directories to watch
DIRECTORIES = {
    "Needs_Action": os.path.join(ROOT_DIR, "Needs_Action"),
    "Pending_Approval": os.path.join(ROOT_DIR, "Pending_Approval"),
    "Approved": os.path.join(ROOT_DIR, "Approved"),
    "Done": os.path.join(ROOT_DIR, "Done"),
    "Plans": os.path.join(ROOT_DIR, "Plans"),
    "Inbox": os.path.join(ROOT_DIR, "Inbox"),
}

app = FastAPI(title="Silver Tier Agent API")

# Enable CORS for Next.js Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class FileItem(BaseModel):
    name: str
    path: str
    size: int
    modified: str
    type: str

class ContentResponse(BaseModel):
    content: str
    frontmatter: Optional[str] = None

class ActionRequest(BaseModel):
    filename: str
    
# --- Helpers ---
def get_file_info(filepath: str) -> FileItem:
    stat = os.stat(filepath)
    return FileItem(
        name=os.path.basename(filepath),
        path=filepath,
        size=stat.st_size,
        modified=str(stat.st_mtime),
        type="file"
    )

# --- Endpoints ---

@app.get("/")
def health_check():
    return {"status": "Silver Tier API Online 🚀"}

@app.get("/stats")
def get_stats():
    """Returns counts of files in key directories."""
    stats = {}
    for name, path in DIRECTORIES.items():
        if os.path.exists(path):
            count = len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])
            stats[name] = count
        else:
            stats[name] = 0
    return stats

@app.get("/files/{folder}")
def list_files(folder: str):
    """Lists files in a specific folder (e.g., Needs_Action)."""
    if folder not in DIRECTORIES:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    dir_path = DIRECTORIES[folder]
    if not os.path.exists(dir_path):
        return []
        
    files = []
    # Sort by modification time (newest first)
    paths = sorted(Path(dir_path).glob("*"), key=os.path.getmtime, reverse=True)
    
    for p in paths:
        if p.is_file():
            files.append(get_file_info(str(p)))
            
    return files

@app.get("/read")
def read_file(path: str):
    """Reads content of a file."""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/approve")
def approve_file(request: ActionRequest):
    """Moves a file from Pending_Approval to Approved."""
    src = os.path.join(DIRECTORIES["Pending_Approval"], request.filename)
    dst = os.path.join(DIRECTORIES["Approved"], request.filename)
    
    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="File not found in Pending_Approval")
        
    try:
        if not os.path.exists(DIRECTORIES["Approved"]):
            os.makedirs(DIRECTORIES["Approved"])
        shutil.move(src, dst)
        return {"status": "approved", "file": request.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reject")
def reject_file(request: ActionRequest):
    """Deletes a file from Pending_Approval."""
    src = os.path.join(DIRECTORIES["Pending_Approval"], request.filename)
    
    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        os.remove(src)
        return {"status": "rejected", "file": request.filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Ensure directories exist
    for path in DIRECTORIES.values():
        if not os.path.exists(path):
            os.makedirs(path)
            
    uvicorn.run(app, host="0.0.0.0", port=8000)
