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
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

import requests as http_requests
from requests.auth import HTTPBasicAuth

# Import backend modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from agent_backend import mcp_server, security_middleware
from conversation_manager import ConversationManager
from database import create_database
from http_security import HTTPSecurityManager, HTTPSecurityMiddleware

# Config
from src.config import get_settings

# --- Input Validation Constants ---
import re

MAX_PROMPT_LENGTH = 10000  # Maximum prompt length in characters
MAX_CONVERSATION_ID_LENGTH = 256  # Maximum conversation ID length
CONVERSATION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9-]+$')  # Alphanumeric + hyphens only

def validate_conversation_id(conversation_id: str) -> tuple[bool, str]:
    """
    Validate conversation_id format.
    Must be alphanumeric + hyphens only, and under MAX_CONVERSATION_ID_LENGTH.
    
    Returns:
        (is_valid, error_message)
    """
    if not conversation_id or len(conversation_id) == 0:
        return False, "Conversation ID cannot be empty."
    
    if len(conversation_id) > MAX_CONVERSATION_ID_LENGTH:
        return False, f"Conversation ID exceeds maximum length of {MAX_CONVERSATION_ID_LENGTH} characters."
    
    if not CONVERSATION_ID_PATTERN.match(conversation_id):
        return False, "Conversation ID must contain only alphanumeric characters and hyphens."
    
    return True, ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing extra needed (db and conv_manager init above)
    yield
    # Shutdown: finalize open conversations and close database
    conv_manager.finalize_all()
    db.close()


app = FastAPI(lifespan=lifespan)

# Load settings for middleware configuration
settings = get_settings()

# --- HTTP Transport Security ---
http_security = HTTPSecurityManager()
app.add_middleware(HTTPSecurityMiddleware, security_manager=http_security)

# CORS: restrict to configured origins (default: same origin only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.get_origins_list(),
    allow_methods=settings.cors.get_methods_list(),
    allow_headers=settings.cors.get_headers_list(),
)

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


# --- Session initialization (HMAC key exchange) ---

@app.post("/api/session/init")
async def init_session(request: Request):
    """
    Initialize an authenticated HTTP session.
    Returns a session token and HMAC key for signing subsequent requests.
    No prior authentication required (first contact).
    """
    client_ip = request.client.host if request.client else "unknown"
    return http_security.create_session(client_ip)


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
    # Validate conversation_id format
    is_valid, error_msg = validate_conversation_id(conversation_id)
    if not is_valid:
        return {"error": error_msg}
    
    conv = conv_manager.get_conversation(conversation_id)

    # If not in memory, try to resume from database
    if not conv:
        db_record = db.get_conversation(conversation_id)
        if not db_record:
            return {"error": f"Conversation {conversation_id} not found. Create one first."}
        if db_record.get("is_finalized"):
            return {"error": f"Conversation {conversation_id} is finalized (read-only)."}
        messages = db.get_messages(conversation_id)
        conv = conv_manager.resume_conversation(conversation_id, db_record, messages)

    data = await request.json()
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return {"error": "No prompt provided."}
    
    # Validate prompt length
    if len(prompt) > MAX_PROMPT_LENGTH:
        return {"error": f"Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters. Current length: {len(prompt)}."}

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
    # Validate conversation_id format
    is_valid, error_msg = validate_conversation_id(conversation_id)
    if not is_valid:
        return {"error": error_msg}
    
    conv = conv_manager.get_conversation(conversation_id)

    # Resume from DB if not in memory
    if not conv:
        db_record = db.get_conversation(conversation_id)
        if not db_record:
            return {"error": f"Conversation {conversation_id} not found."}
        if db_record.get("is_finalized"):
            return {"error": f"Conversation {conversation_id} is already finalized."}
        messages = db.get_messages(conversation_id)
        conv = conv_manager.resume_conversation(conversation_id, db_record, messages)

    try:
        result = conv.finalize()
    except Exception as e:
        return {"error": f"Finalize failed: {str(e)}"}

    if "error" not in result:
        db.save_integrity(conversation_id, result)
    # Always persist conversation state (including is_finalized flag)
    db.save_conversation(conv.get_summary())
    return result


@app.get("/api/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get all messages for a conversation."""
    # Validate conversation_id format
    is_valid, error_msg = validate_conversation_id(conversation_id)
    if not is_valid:
        return {"error": error_msg}
    
    return db.get_messages(conversation_id)


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Delete a conversation entirely:
    1. Remove from in-memory ConversationManager + delete workflow folder
    2. Delete from database (conversations, messages, prompt_roots tables)
    3. Delete Langfuse traces for this session (best-effort)
    """
    # Validate conversation_id format
    is_valid, error_msg = validate_conversation_id(conversation_id)
    if not is_valid:
        return {"error": error_msg}
    
    # Check it exists
    db_record = db.get_conversation(conversation_id)
    if not db_record:
        return {"error": f"Conversation {conversation_id} not found."}

    # 1. Memory + workflow directory cleanup
    conv_result = conv_manager.delete_conversation(conversation_id)

    # 2. Database cleanup
    db_deleted = db.delete_conversation(conversation_id)

    # 3. Langfuse cleanup (best-effort)
    langfuse_deleted = _delete_langfuse_session(f"chat-{conversation_id}")

    return {
        "deleted": True,
        "conversation_id": conversation_id,
        "db_deleted": db_deleted,
        "workflow_dir_deleted": conv_result.get("workflow_dir_deleted", False),
        "langfuse_deleted": langfuse_deleted,
    }


def _delete_langfuse_session(session_id: str) -> dict:
    """
    Delete all Langfuse traces associated with a session ID.
    Uses the Langfuse REST API: GET traces by sessionId, then DELETE each trace.
    Best-effort — returns status without raising on failure.
    """
    try:
        settings = get_settings()
        endpoint = settings.langfuse.api_endpoint
        pub_key = settings.langfuse.public_key
        sec_key = settings.langfuse.secret_key

        if not pub_key or not sec_key:
            return {"skipped": True, "reason": "no_credentials"}

        auth = HTTPBasicAuth(pub_key, sec_key)

        # List traces for this session
        list_url = f"{endpoint}/api/public/traces?sessionId={session_id}"
        resp = http_requests.get(list_url, auth=auth, timeout=10)
        if resp.status_code != 200:
            return {"skipped": True, "reason": f"list_failed_{resp.status_code}"}

        traces = resp.json().get("data", [])
        if not traces:
            return {"traces_deleted": 0}

        # Delete each trace
        deleted_count = 0
        for trace in traces:
            trace_id = trace.get("id")
            if not trace_id:
                continue
            del_url = f"{endpoint}/api/public/traces/{trace_id}"
            del_resp = http_requests.delete(del_url, auth=auth, timeout=10)
            if del_resp.status_code in (200, 204):
                deleted_count += 1

        return {"traces_deleted": deleted_count, "traces_found": len(traces)}

    except Exception as e:
        return {"skipped": True, "reason": str(e)}


# --- Backward-compatible simple chat endpoint ---

@app.post("/api/chat")
async def chat_endpoint(request: Request):
    """
    Simple chat endpoint (backward compatible).
    Creates a conversation per prompt, finalizes immediately.
    """
    data = await request.json()
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return {"response": "Error: No prompt provided."}
    
    # Validate prompt length
    if len(prompt) > MAX_PROMPT_LENGTH:
        return {"response": f"Error: Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters. Current length: {len(prompt)}."}

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
