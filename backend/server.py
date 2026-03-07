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
3. Run the server (HTTP - default):
       & "./venv/Scripts/python.exe" backend/server.py
   OR with HTTPS (self-signed certificates):
       python backend/generate_certs.py  # One-time cert generation
       & "./venv/Scripts/python.exe" backend/server.py --https

Visit http://localhost:8000 (HTTP) or https://localhost:8000 (HTTPS) in your browser.
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


def get_session_token(request: Request) -> str:
    """Extract the validated session token from request state (set by HTTPSecurityMiddleware)."""
    return getattr(request.state, "session_token", "")


def verify_conversation_access(conversation_id: str, session_token: str, db_record: dict) -> tuple[bool, str]:
    """
    Verify the current session owns this conversation.
    Access is allowed if:
    - No owner set (legacy conversation)
    - Owner matches current session
    - Owner session expired (reclaim ownership)
    """
    owner = db_record.get("owner_token")
    if not owner or owner == session_token:
        return True, ""
    # Owner exists but doesn't match — check if owner's session is still active
    if http_security.get_session(owner) is not None:
        return False, "Access denied: this conversation belongs to another session."
    # Owner session expired — reclaim
    db.update_conversation_owner(conversation_id, session_token)
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

# --- Security Headers Middleware (Native ASGI) ---

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """
    Native Starlette ASGI middleware that adds security response headers.
    More performant than BaseHTTPMiddleware with zero overhead.
    
    Headers added:
    - Content-Security-Policy: Prevents XSS by restricting script sources
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-Frame-Options: Prevents clickjacking
    - Referrer-Policy: Prevents referrer leakage
    - Permissions-Policy: Disables unnecessary browser features
    - Strict-Transport-Security: Enforces HTTPS (for production with TLS)
    """
    response = await call_next(request)
    
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), usb=(), "
        "magnetometer=(), gyroscope=(), accelerometer=()"
    )
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    
    return response

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
async def create_conversation(request: Request):
    """Create a new conversation session, bound to the requesting HTTP session."""
    session_token = get_session_token(request)
    conv = conv_manager.create_conversation()
    data = conv.get_summary()
    data["owner_token"] = session_token
    db.save_conversation(data)
    return data


@app.get("/api/conversations")
async def list_conversations(request: Request):
    """List conversations owned by the current session."""
    session_token = get_session_token(request)
    all_convs = db.list_conversations()
    visible = []
    for conv in all_convs:
        owner = conv.get("owner_token")
        if not owner or owner == session_token:
            visible.append(conv)
        elif http_security.get_session(owner) is None:
            # Owner session expired — reclaim for current session
            db.update_conversation_owner(conv["conversation_id"], session_token)
            conv["owner_token"] = session_token
            visible.append(conv)
        # else: owned by active session of another user — hide
    return visible


@app.post("/api/conversations/{conversation_id}/chat")
async def chat_in_conversation(conversation_id: str, request: Request):
    """Send a prompt within an existing conversation."""
    # Validate conversation_id format
    is_valid, error_msg = validate_conversation_id(conversation_id)
    if not is_valid:
        return {"error": error_msg}
    
    session_token = get_session_token(request)

    # Verify conversation exists and check ownership
    db_record = db.get_conversation(conversation_id)
    if not db_record:
        return {"error": f"Conversation {conversation_id} not found. Create one first."}
    has_access, access_err = verify_conversation_access(conversation_id, session_token, db_record)
    if not has_access:
        return {"error": access_err}
    if db_record.get("is_finalized"):
        return {"error": f"Conversation {conversation_id} is finalized (read-only)."}

    conv = conv_manager.get_conversation(conversation_id)

    # If not in memory, resume from database
    if not conv:
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
async def finalize_conversation(conversation_id: str, request: Request):
    """Finalize a conversation: compute conversation-level Verkle root and save workflow."""
    # Validate conversation_id format
    is_valid, error_msg = validate_conversation_id(conversation_id)
    if not is_valid:
        return {"error": error_msg}
    
    session_token = get_session_token(request)

    # Verify conversation exists and check ownership
    db_record = db.get_conversation(conversation_id)
    if not db_record:
        return {"error": f"Conversation {conversation_id} not found."}
    has_access, access_err = verify_conversation_access(conversation_id, session_token, db_record)
    if not has_access:
        return {"error": access_err}
    if db_record.get("is_finalized"):
        return {"error": f"Conversation {conversation_id} is already finalized."}

    conv = conv_manager.get_conversation(conversation_id)

    # Resume from DB if not in memory
    if not conv:
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
async def get_conversation_messages(conversation_id: str, request: Request):
    """Get all messages for a conversation."""
    # Validate conversation_id format
    is_valid, error_msg = validate_conversation_id(conversation_id)
    if not is_valid:
        return {"error": error_msg}
    
    # Verify ownership
    session_token = get_session_token(request)
    db_record = db.get_conversation(conversation_id)
    if db_record:
        has_access, access_err = verify_conversation_access(conversation_id, session_token, db_record)
        if not has_access:
            return {"error": access_err}
    
    return db.get_messages(conversation_id)


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
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
    
    # Check it exists and verify ownership
    db_record = db.get_conversation(conversation_id)
    if not db_record:
        return {"error": f"Conversation {conversation_id} not found."}
    
    session_token = get_session_token(request)
    has_access, access_err = verify_conversation_access(conversation_id, session_token, db_record)
    if not has_access:
        return {"error": access_err}

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
    import argparse
    from pathlib import Path
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Run the AI Agent Chat Backend Server")
    parser.add_argument("--https", action="store_true", help="Enable HTTPS with self-signed certificates")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the server on (default: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    args = parser.parse_args()
    
    # Check for environment variable override
    use_https = args.https or os.getenv("USE_HTTPS", "false").lower() in ("true", "1", "yes")
    
    # Prepare HTTPS config if requested
    ssl_keyfile = None
    ssl_certfile = None
    if use_https:
        project_root = Path(__file__).parent.parent
        certs_dir = project_root / "certs"
        cert_file = certs_dir / "localhost.crt"
        key_file = certs_dir / "localhost.key"
        
        if cert_file.exists() and key_file.exists():
            ssl_certfile = str(cert_file)
            ssl_keyfile = str(key_file)
            print(f"[HTTPS] Loading SSL certificates from {certs_dir}/")
        else:
            print(f"[ERROR] HTTPS requested but certificates not found at {certs_dir}/")
            print(f"  Generate certificates with: python backend/generate_certs.py")
            sys.exit(1)
    
    # Determine protocol
    protocol = "https" if use_https else "http"
    print(f"\n[Server] Starting on {protocol}://{args.host}:{args.port}")
    if use_https:
        print(f"[Server] ⚠️  Self-signed certificate in use. Browser will show security warning (expected).")
    
    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=True,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )
