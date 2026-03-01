"""
FastAPI Backend Server for AI Agent Chat (MCP 2026-02)

Serves the frontend chat page and provides API endpoints for:
- Conversation management (create, list, finalize)
- Per-prompt chat within conversations (with incremental Verkle roots)
- Backward-compatible simple /api/chat endpoint

Setup and run (Windows, PowerShell):
1. Activate the virtual environment:
       & "./venv/Scripts/Activate.ps1"
2. Install dependencies:
       pip install fastapi uvicorn
3. Run the server:
       & "./venv/Scripts/python.exe" backend/server.py

Visit http://localhost:8000 in your browser.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import sys

# Import backend modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from agent_backend import mcp_server, security_middleware
from conversation_manager import ConversationManager
from database import create_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing extra needed (db and conv_manager init above)
    yield
    # Shutdown: finalize open conversations and close database
    conv_manager.finalize_all()
    db.close()


app = FastAPI(lifespan=lifespan)

# Initialize database (SQLite by default, PostgreSQL if DATABASE_URL is set)
db = create_database()

# Initialize conversation manager (shared tools and security across conversations)
conv_manager = ConversationManager(mcp_server=mcp_server, security_middleware=security_middleware)

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


# --- Conversation API ---

@app.post("/api/conversations")
async def create_conversation():
    """Create a new conversation session."""
    conv = conv_manager.create_conversation()
    data = conv.get_summary()
    db.save_conversation(data)
    return data


@app.get("/api/conversations")
async def list_conversations():
    """List all conversations."""
    return db.list_conversations()


@app.post("/api/conversations/{conversation_id}/chat")
async def chat_in_conversation(conversation_id: str, request: Request):
    """Send a prompt within an existing conversation."""
    conv = conv_manager.get_conversation(conversation_id)
    if not conv:
        return {"error": f"Conversation {conversation_id} not found. Create one first."}

    data = await request.json()
    prompt = data.get("prompt", "")
    if not prompt:
        return {"error": "No prompt provided."}

    # Send prompt and get response (includes per-prompt Verkle root)
    result = await conv.send_prompt(prompt)

    # Save messages to database
    messages = conv.messages
    if len(messages) >= 2:
        user_msg = messages[-2]
        assistant_msg = messages[-1]
        db.save_message(
            conversation_id, user_msg["role"], user_msg["content"],
            user_msg["timestamp"], user_msg.get("prompt_index", 0)
        )
        db.save_message(
            conversation_id, assistant_msg["role"], assistant_msg["content"],
            assistant_msg["timestamp"], assistant_msg.get("prompt_index", 0)
        )

    # Save prompt root to database
    if conv.prompt_roots:
        db.save_prompt_root(conversation_id, conv.prompt_roots[-1])

    # Update conversation metadata in DB
    db.save_conversation(conv.get_summary())

    return {
        "response": result.get("output", ""),
        "conversation_id": conversation_id,
        "prompt_root": result.get("prompt_root"),
        "prompt_index": result.get("prompt_index"),
    }


@app.post("/api/conversations/{conversation_id}/finalize")
async def finalize_conversation(conversation_id: str):
    """Finalize a conversation: compute conversation-level Verkle root and save workflow."""
    result = conv_manager.finalize_conversation(conversation_id)
    if "error" not in result:
        db.save_integrity(conversation_id, result)
    return result


@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get all messages for a conversation."""
    return db.get_messages(conversation_id)


# --- Backward-compatible simple chat endpoint ---

@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """
    Simple chat endpoint (backward compatible).
    Creates a conversation per prompt, finalizes immediately.
    """
    data = await request.json()
    prompt = data.get("prompt", "")
    if not prompt:
        return {"response": "Error: No prompt provided."}

    # Create a temporary conversation for this single prompt
    conv = conv_manager.create_conversation()
    db.save_conversation(conv.get_summary())

    result = await conv.send_prompt(prompt)

    # Save messages
    for msg in conv.messages:
        db.save_message(
            conv.conversation_id, msg["role"], msg["content"],
            msg["timestamp"], msg.get("prompt_index", 0)
        )

    # Finalize immediately for single-prompt usage
    integrity = conv.finalize()
    if "error" not in integrity:
        db.save_integrity(conv.conversation_id, integrity)

    return {
        "response": result.get("output", ""),
        "conversation_id": conv.conversation_id,
        "conversation_root": integrity.get("conversation_root"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
