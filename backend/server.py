"""
FastAPI Backend Server for AI Agent Chat (MCP 2026-02)
Serves the frontend chat page and provides an API endpoint for agent responses.

Setup and run (Windows, PowerShell):
1. Activate the virtual environment:
       & "./venv/Scripts/Activate.ps1"
2. Install dependencies:
       pip install fastapi uvicorn
3. Run the server:
       & "./venv/Scripts/python.exe" backend/server.py

Visit http://localhost:8000 in your browser.
"""

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import sys
import asyncio

# Import the agent backend
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from agent_backend import answer_prompt

app = FastAPI()

# Serve static files (frontend)

frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend')
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(frontend_path, "index.html")
    return FileResponse(index_file, media_type="text/html")

@app.get("/favicon.ico")
def favicon():
    return HTMLResponse("")


# Chat API endpoint connected to agent backend
@app.post("/api/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    prompt = data.get("prompt", "")
    if not prompt:
        return {"response": "Error: No prompt provided."}
    # Call the agent backend to get the answer
    response = await answer_prompt(prompt)
    return {"response": response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
