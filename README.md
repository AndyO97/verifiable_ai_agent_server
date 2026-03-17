# 🔐 Verifiable AI Agent Server

A high-integrity, self-hosted AI Agent Server built on the Model Context Protocol (MCP) with cryptographic commitment of all agent–LLM–tool interactions into a **Verkle Tree**.

## 📋 Latest Updates (March 13, 2026)

- **MCPHost Architecture**: Explicit MCP Host class (MCPHost) orchestrates server/client interactions with encapsulated authorization and integrity tracking
- **AI Agent Chat Server**: Full-featured web chat interface with FastAPI backend — the primary way to interact with the agent and its tools
- **Conversation Management**: Create, resume, finalize, and delete conversations with full DB + workflow + Langfuse cleanup
- **HTTP Transport Security**: HMAC-SHA256 request signing, anti-replay nonces, session tokens, rate limiting — all transparent to the user
- **Conversation History Sidebar**: Browse, switch, and manage past conversations from a collapsible sidebar
- **5 Integrated Tools**: Weather (OpenWeatherMap), Currency Exchange, Math Calculator, Wikipedia Search, Datetime — all with IBS-signed outputs
- **Conversation Resume**: Seamlessly continue conversations after server restart
- **Per-Prompt Verkle Roots**: Each prompt/response pair gets its own cryptographic commitment; conversation-level root combines them all
- **Tool Call Parsing**: Fixed support for tool calls with and without arguments — handles both `{"tool": "datetime"}` and `{"tool": "add", "args": {...}}`

## 🎯 Core Features

- **Web Chat Interface**: Full-featured AI agent chat with FastAPI backend, conversation sidebar, and per-prompt Verkle roots
- **HTTP Transport Security**: HMAC-SHA256 request signing, session tokens, nonce-based anti-replay, rate limiting, and CORS restrictions
- **Immutable Run Logs**: All agent interactions (prompts, tool calls, model outputs) are canonically encoded and cryptographically committed
- **Deterministic Verifiability**: Every run produces a single Verkle root commitment (KZG on BLS12-381) that can be independently verified
- **MCP 2025-11-25 Compliance**: Full JSON-RPC 2.0 protocol support with MCPHost orchestration, proper initialization handshake, and request ID correlation
- **MCPHost Orchestration**: Explicit MCPHost class manages server lifecycle, tool authorization, integrity recording, and client registration — encapsulating all protocol concerns
- **Unified Integrity Middleware**: Single middleware object manages both cryptographic commitment and observability (Langfuse)
- **Replay Resistance**: Sequential monotonic counters, server timestamps, and session IDs prevent unauthorized replay or reordering
- **Identity-Based Signatures**: Tools cryptographically sign their own outputs using keys derived from their names (BLS12-381), ensuring zero-trust authenticity
- **Public Verification**: Open-source verification CLI allows third-party validation without trusting the server
- **Observability**: Full OpenTelemetry integration with Langfuse for trace, latency, and cost visualization
- **Security-First**: Authorization middleware, prompt injection protection, and zero-trust tool invocation

---

## � Quick Start

### Prerequisites

- **Python 3.11+** (check with `python --version`)
- **pip** (included with Python)
- Optional: PostgreSQL (for production counter persistence)
- Optional: Langfuse self-hosted instance (for observability)


### Installation (Recommended: uv)

#### Option 1: Automated Setup (Recommended)

```powershell
# Windows PowerShell
.\setup.ps1
```

This will:
1. ✅ Check Python 3.11+ installation
2. ✅ Install uv (if not present)
3. ✅ Create virtual environment
4. ✅ Install all dependencies (dev + production)
5. ✅ Run tests to verify setup
6. ✅ Create `.env` template

#### Option 2: Manual Setup

```powershell
# 1. Install uv (fastest Python package manager)
pip install uv

# 2. Create virtual environment
uv venv

# 3. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 4. Install dependencies
uv pip install -e ".[dev]"


# 5. Run tests
python -m pytest tests/ -v
```

---

## 🌐 AI Agent Chat Server (⭐ Primary Feature)

The chat server is the main way to interact with the Verifiable AI Agent. It provides a full-featured web chat interface backed by FastAPI, with per-prompt cryptographic integrity, conversation management, and HTTP transport security — all accessible from your browser.

### How to Run

```powershell
# 1. Activate virtual environment
.\venv\Scripts\Activate.ps1

# 2. Install server dependencies (if not already)
pip install fastapi uvicorn

# 3. Start the server
python backend/server.py
```

Open **http://localhost:8000** in your browser. The chat interface loads automatically.

### HTTPS Setup (Optional)

By default, the HMAC session key is transmitted over HTTP. For secure local development with encrypted key exchange:

```powershell
# 1. Generate self-signed certificates (one-time)
python backend/generate_certs.py

# 2. Start server with HTTPS
python backend/server.py --https

# OR use environment variable
$env:USE_HTTPS='true'
python backend/server.py

# 3. Visit https://localhost:8000 (accept certificate warning)
```

**Certificate Details:**
- Algorithm: RSA 2048-bit, SHA-256
- Validity: 365 days from generation
- Subject Alt Names: localhost, *.localhost, 127.0.0.1  
- Storage: `certs/localhost.crt` and `certs/localhost.key` (not committed to git)

**Notes:**
- Browser will show security warning (expected for self-signed certs)
- HTTP remains the default (remove `--https` flag to use unencrypted transport)
- For production: replace with CA-signed certificates (e.g., Let's Encrypt)

### LLM Rate Limiting Configuration

The system includes **token-based rate limiting** to prevent Denial-of-Service attacks at the LLM inference layer (Security Gap 15.2). Configure these limits via environment variables in `.env`:

```bash
# Maximum total tokens per session per time window (~1000 pages of text)
LLM_RATE_LIMITER_TOKEN_LIMIT_PER_WINDOW=500000

# Time window for token tracking (seconds) — 1 hour
LLM_RATE_LIMITER_WINDOW_SIZE_SEC=3600

# Estimated tokens in average LLM response (used to calculate cost)
LLM_RATE_LIMITER_ESTIMATED_RESPONSE_TOKENS=2000

# Prompt complexity threshold (0-100 scale; above this triggers warning logs)
LLM_RATE_LIMITER_COMPLEXITY_THRESHOLD=60.0
```

**How It Works:**
1. **Token Budget**: Each session has a token budget per hour (default: 500,000 tokens per hour)
2. **Estimation**: Incoming prompts are estimated at 1 token per 4 characters, plus response estimate
3. **Rejection**: Requests that would exceed the token budget are rejected with error code `-32008`
4. **Complexity Scoring**: Prompts are scored for complexity (code patterns, tool invocations, sentence length); high-complexity prompts are logged for monitoring

**Example Rate Limit Response:**
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32008,
    "message": "LLM token budget exceeded for this time window",
    "data": {
      "details": "Your prompt would require 8,000 tokens; only 500 remain in your budget.",
      "limit": 50000,
      "window_sec": 3600
    }
  }
}
```

### Chat Interface Features

| Feature | Description |
|---------|-------------|
| **Conversation Sidebar** | Collapsible sidebar lists all conversations with date, message count, and status badges (Active / Finalized). Click to switch, use the wastebasket button to delete. |
| **Multiple Conversations** | Create new conversations with the "+ New" button. The previous conversation is automatically finalized (Verkle root computed). |
| **Conversation Resume** | Conversations persist in SQLite. Restarting the server does not lose any data — conversations resume seamlessly. |
| **Conversation Deletion** | Delete a conversation entirely: removes DB records, workflow artifacts on disk, and Langfuse traces (best-effort). Auto-selects the most recent remaining conversation. |
| **5 Integrated Tools** | The agent has access to: **Weather** (OpenWeatherMap), **Currency Exchange** (exchangerate-api), **Math Calculator** (local eval), **Wikipedia Search** (REST API), **Datetime** (local). The LLM decides which tools to invoke. |
| **Per-Prompt Verkle Roots** | Every prompt/response pair gets its own cryptographic Verkle root. The sidebar shows verified status per prompt. |
| **Conversation-Level Root** | When finalized, a conversation-level Verkle root is computed from all prompt roots — a single commitment covering the entire chat history. |
| **IBS Tool Signatures** | Tool outputs are cryptographically signed using Identity-Based Signatures (Cha-Cheon over BLS12-381). Keys are derived from tool names — no PKI required. |
| **Langfuse Observability** | All interactions are traced to Langfuse (if configured) with session grouping, per-turn generations, and cost tracking. |
| **Auto-Select on Load** | On page load, the most recent conversation is automatically selected and its messages displayed. |

### HTTP Transport Security

All API requests between the browser and server are cryptographically protected:

```
Browser                                   FastAPI Server
───────                                   ──────────────
1. POST /api/session/init  ──────────>    Generate session_token + hmac_key
   <────── { session_token, hmac_key }

2. Every subsequent API call includes:
   Headers:
     X-Session-Token: <token>
     X-Timestamp:     <unix_ms>
     X-Nonce:         <random_hex>
     X-Signature:     HMAC-SHA256(hmac_key, timestamp|nonce|method|path|body)

   Server validates:
     ✓ Token exists and not expired (1-hour TTL)
     ✓ Timestamp within ±30s window (anti-replay)
     ✓ Nonce never reused (anti-replay, 2-min cache)
     ✓ HMAC signature matches (tamper resistance)
     ✓ Rate limit not exceeded (60 req/min/IP)
```

- **Session Tokens**: 48-character hex tokens with 1-hour TTL, generated via `os.urandom(24)`
- **HMAC Keys**: 64-character hex keys (256-bit), generated via `os.urandom(32)`
- **Browser Signing**: Uses the Web Crypto API (`crypto.subtle.importKey` + `crypto.subtle.sign`) for native HMAC-SHA256
- **CORS Restriction**: Only `http://127.0.0.1:8000` and `http://localhost:8000` are allowed origins
- **Bypass Paths**: Static assets, favicon, and `/api/session/init` bypass HMAC checks

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/session/init` | Initialize HMAC session (returns token + key) |
| `POST` | `/api/conversations` | Create a new conversation |
| `GET` | `/api/conversations` | List all conversations (newest first) |
| `POST` | `/api/conversations/{id}/chat` | Send a prompt within a conversation |
| `POST` | `/api/conversations/{id}/finalize` | Finalize and compute conversation root |
| `GET` | `/api/conversations/{id}/messages` | Get all messages for a conversation |
| `DELETE` | `/api/conversations/{id}` | Delete conversation (DB + workflow + Langfuse) |
| `POST` | `/api/chat` | Simple one-shot chat (backward compatible) |

**Error Response Format (JSON-RPC 2.0 Compliant):**

All error responses follow the JSON-RPC 2.0 specification with structured error codes:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32602,
    "message": "Invalid params: prompt field is required",
    "data": {/* optional context */}
  }
}
```

Standard error codes:
- `-32602`: Invalid params (validation errors, missing fields, format errors)
- `-32603`: Internal error (server-side failures, LLM errors, database errors)
- `-32001` to `-32010`: Custom server errors (conversation not found, access denied, finalized conversation, etc.)

### Architecture

```
frontend/
  index.html          # Chat UI with sidebar layout
  script.js           # HMAC signing, conversation management, secureFetch()
  style.css           # Responsive layout, sidebar, badges

backend/
  server.py           # FastAPI app with all endpoints + security middleware
  agent_backend.py    # MCP server with 5 tools, SecurityMiddleware
  conversation_manager.py  # Per-conversation sessions, Verkle lifecycle
  database.py         # SQLite/PostgreSQL abstraction (conversations, messages, prompt_roots)
  http_security.py    # HTTPSecurityManager + HTTPSecurityMiddleware (HMAC, nonces, rate limits)
```

### Why uv?

**uv** is 10-100x faster than pip/Poetry and uses standard PEP 517/518 format.

- ⚡ Ultra-fast dependency installation (5-30s vs 2-5min)
- 📦 Works with all Python tooling (pip, poetry, etc.)
- 🪶 Lightweight (~30MB vs Poetry ~200MB)
- 🔒 Deterministic resolution (reproducible builds)

### Running Tests

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run all tests (124 tests, ~3-4 minutes)
python -m pytest tests/ -v

# Run all tests with summary (3-4 minutes)
python run_all_tests.py

# Run specific feature tests (< 1 minute each)
python -m pytest tests/test_kzg.py -v              # KZG (23 tests)
python -m pytest tests/test_otel_spans.py -v       # OTel (21 tests)
python -m pytest tests/test_langfuse.py -v         # Langfuse (32 tests)
python -m pytest tests/test_counter_persistence.py -v  # Counter (13 tests)
```

### Daily Development

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Format code
black src/ tests/

# Lint
ruff check src/

# Type checking
mypy src/

# Deactivate
deactivate
```

### LLM Configuration (OpenRouter or Ollama)

The project supports two LLM providers. Choose one:

#### Option 1: OpenRouter.ai (⭐ RECOMMENDED - No local setup)

**Setup** (2 minutes):

1. Get free API key: https://openrouter.ai/keys
2. Edit `.env` file:
   ```bash
   OPENROUTER_API_KEY=sk-or-YOUR_API_KEY_HERE
   OPENROUTER_MODEL=LLM_MODEL_HERE
   ```
3. Run validation:
   ```powershell
   $env:PYTHONPATH = "."; python real_prompt_demo.py
   ```

**Project Structure:**
```
backend/                     # FastAPI chat server
  server.py                  #   Main server with all API endpoints
  agent_backend.py           #   MCP server with 5 tools
  conversation_manager.py    #   Conversation session lifecycle
  database.py                #   SQLite/PostgreSQL persistence
  http_security.py           #   HMAC + nonce + rate-limit middleware
frontend/                    # Browser chat UI
  index.html                 #   Chat page with sidebar
  script.js                  #   HMAC signing + conversation management
  style.css                  #   Responsive layout + sidebar styles
real_prompt_demo.py          # Demo: Simple Q&A with integrity tracking
real_agent_demo.py           # Demo: Multi-tool agent with tool invocation
examples/
  agent_multi_tool_demo.py   # Demo: CLI multi-tool agent (5 tools, 5 prompts)
  agent_remote_demo.py       # Demo: Secure remote tool invocation
  remote_tool.py             # Remote tool used in agent_remote_demo.py
run_all_tests.py             # Run all tests with progress tracking
pyproject.toml               # uv/pip compatible dependencies
setup.ps1                    # Automated setup script (Windows)
docker-compose.yml           # Langfuse self-hosted deployment
README.md                    # This file (comprehensive guide)
PROJECT_SUMMARY.md           # Project status & future work
PROPOSAL.md                  # Technical approach & architecture
OLLAMA_SETUP_GUIDE.txt       # Alternative LLM provider guide
.env.example                 # Environment variables template
```

**Key Files:**
- `backend/server.py` - Chat server entry point (run with `python backend/server.py`)
- `backend/agent_backend.py` - MCP server with 5 tools shared by chat server and CLI demos
- `real_prompt_demo.py` - Entry point for simple demo with Langfuse tracing
- `real_agent_demo.py` - Entry point for agent demo with tool invocation
- `examples/agent_multi_tool_demo.py` - CLI multi-tool demo (5 tools, 5 prompts)
- `examples/agent_remote_demo.py` - Entry point for agent demo with remote tool invocation
- `run_all_tests.py` - Run all tests with progress tracking
- `.env` - Local configuration (credentials, API keys, not in git)
- `docker-compose.yml` - Langfuse deployment (optional observability)

**Documentation:**
- `README.md` - Primary user guide (you are here)
- `PROJECT_SUMMARY.md` - Project status and future considerations
- `PROPOSAL.md` - Technical approach and architecture decisions
- `OLLAMA_SETUP_GUIDE.txt` - Alternative LLM configuration

---

## 🔒 Security

### Tool Authorization

The security middleware enforces a whitelist of authorized tools:

```python
security = SecurityMiddleware()
security.register_authorized_tools(["calculator", "search"])

# Unauthorized attempts are:
# - Logged as security_event
# - Blocked with neutral response
# - Tool capability map NOT exposed to model
```

### Replay Resistance

Prevents tampering through:
1. **Session ID**: Unique per run
2. **Monotonic Counter**: Atomic increment, persisted
3. **Server Timestamp**: From trusted NTP-synced clock
4. **Canonical Encoding**: Deterministic serialization

---

## 📚 Key Modules

### `src/crypto/encoding.py`
RFC 8785 canonical JSON encoder with deterministic serialization and support for event normalization.

### `src/crypto/verkle.py`
Verkle tree accumulator using KZG commitments over BLS12-381 elliptic curve. Produces tamper-proof root commitments.

### `src/integrity/hierarchical_integrity.py` (Hierarchical Verkle)
**HierarchicalVerkleMiddleware**: Extends IntegrityMiddleware with span-based event organization
- OpenTelemetry-compatible span management (mcp_initialize, user_interaction, tool_execution, final_response)
- Per-span Verkle roots with independent accumulators
- Session-level root combining all span roots
- Methods: `start_span()`, `record_event_in_span()`, `finalize()`, `save_to_local_storage()`, `export_to_otel_format()`
- Automatic Langfuse integration with graceful fallback
- Returns tuple from `finalize()`: `(session_root, HierarchicalCommitments, canonical_log_bytes)`
- Local storage: Saves complete hierarchical structure to disk (6 files per run)
- Tool signatures preserved: IBS signatures on tool outputs still recorded and verifiable

### `src/agent/__init__.py` - MCPHost Architecture (Enhanced)
**MCPHost**: New orchestration class that encapsulates MCP 2025-11-25 protocol concerns:
- **Host responsibilities**: Server lifecycle, client registration, tool authorization checks
- **Tool invocation**: `invoke_tool()` and `invoke_tool_async()` methods handle authorization, integrity recording, and execution
- **Key methods**:
  - `invoke_tool(tool_call)` — Sync path: check authorization → record input → execute → record output
  - `invoke_tool_async(tool_call)` — Async path: same semantics but awaits async tool handlers
  - `register_remote_tool()` — Register tools from remote sources (SecureMCPClient)
  - `list_tools()` — Return available tools to the LLM
- **Integrity integration**: Unauthorized attempts and tool outputs are both recorded for audit purposes
- **MCP 2025-11-25 compliant**: Full protocol support with capabilities advertisement

**AIAgent (Simplified)**: Now focuses solely on LLM loop logic:
- Constructor: `AIAgent(mcp_host: MCPHost, llm_client: LLMClient)` (simplified from 4 parameters)
- Delegates all tool execution to `mcp_host.invoke_tool()` and `mcp_host.invoke_tool_async()`
- Organizes prompts, manages conversation history, handles multi-turn reasoning
- Result: Clean separation of concerns (LLM loop vs. tool execution)

### `src/transport/jsonrpc_protocol.py`
JSON-RPC 2.0 protocol implementation with MCP 2025-11-25 compliance:
- Standard protocol versioning
- Request/response correlation with IDs
- Initialization handshake
- Error codes per JSON-RPC 2.0 specification
- Batch request support

### `src/transport/mcp_protocol_adapter.py`
Adapter bridging MCPServer with JSON-RPC 2.0 protocol layer. Handles method routing and MCP specification compliance.

### `src/agent/__init__.py` (Enhanced)
MCP server runtime with:
- Tool definition, registration, and invocation
- Resource management (files, audit logs)
- Prompt templates with argument rendering
- Server capabilities advertisement
- Notification system for event subscription

### `src/security/__init__.py`
Authorization manager and security middleware for threat prevention. Tool whitelist enforcement.

### `src/observability/__init__.py`
OTel tracing and Langfuse integration. Automatic OTel span export when Langfuse is configured.

### `src/storage/__init__.py`
Artifact and log storage management.

### `src/tools/verify_cli.py`
Public verification CLI for independent run validation. Three commands: `verify`, `extract`, `export-proof`.

---

## 🎬 Live Demos

> **Tip:** The best way to experience the agent is through the **Chat Server** (see [AI Agent Chat Server](#-ai-agent-chat-server--primary-feature) above). The demos below are standalone scripts useful for understanding the cryptographic internals.

### CLI Demo: Multi-Tool Agent (agent_multi_tool_demo.py)

A standalone CLI demo with the same 5 tools as the chat server (weather, currency, math, wikipedia, datetime) and 5 predefined prompts for quick testing:

```powershell
.\venv\Scripts\Activate.ps1
python examples/agent_multi_tool_demo.py
```

Change `PROMPT_INDEX` in the script to select which prompt/tool combination to test. Produces a full workflow folder with canonical logs, commitments, and OTel export.

### Demo 1: Real Prompt Demo - MCP 2025-11-25 + Integrity Tracking

**What it shows:** Complete Q&A interaction with full MCP JSON-RPC 2.0 handshake and cryptographic commitment

```powershell
# Setup (one time)
.\venv\Scripts\Activate.ps1

# Run the demo
python real_prompt_demo.py
```

**What you'll see:**

```
================================================================================
       REAL-TIME AI AGENT WORKFLOW WITH MCP 2025-11-25 + INTEGRITY TRACKING        
================================================================================

This is a REAL agent interaction with full MCP protocol compliance:
  - User sends prompt through AIAgent to OpenRouter API
  - LLM provides genuine response
  - All communication in MCP 2025-11-25 format
  - Full protocol versioning and initialization
  - All events integrity-tracked with Verkle trees
  - Cryptographically verifiable proof created
  - Anyone can verify what really happened

>> STEP 1: Initialize MCP 2025-11-25 Protocol & Integrity Tracking

[OK] MCP Protocol Handler initialized (version 2024-11)
[OK] MCPServer initialized
[OK] HierarchicalVerkleMiddleware initialized
[OK] Langfuse tracing enabled (traces at http://localhost:3000)
[OK] Session ID: real-prompt-mcp-20260222-143944
[OK] Model: arcee-ai/trinity-large-preview:free

>> STEP 2: Initialize LLM Client

[OK] OpenRouter LLM client connected

>> STEP 3: User Interaction

[2026-02-22T14:39:51.086031] USER_PROMPT: Explain Verkle trees in one paragraph.
[OK] User prompt recorded

>> STEP 4: Making REAL OpenRouter API Call via AIAgent

Sending request to OpenRouter...
Prompt: Explain Verkle trees in one paragraph. Be concise but technical.

>> STEP 5: LLM Response

[2026-02-22T14:40:09.989373] LLM_RESPONSE: Verkle trees are a data structure that 
enables efficient verification of large amounts of data in blockchain systems...
[OK] LLM response received and recorded

>> STEP 6: Finalize Hierarchical Verkle Tree and Generate Session Root

[OK] Verkle tree finalized with integrity verification

Cryptographic Commitment:
  Session Root (Base64): DmBn8+/fBTI3uYOIxP9hHwUK8E6m6EfUye6o3CJC4PoDChpKNPhvgQa
RJ+QZjk/6

Hierarchical Span Structure:
  - real-prompt-mcp-20260222-143944_agent_run_0: 1 events
  - real-prompt-mcp-20260222-143944_agent_turn_1_1: 1 events
  - real-prompt-mcp-20260222-143944_agent_finalize_2: 0 events

>> STEP 7: Verify Integrity of Complete Log

[OK] VERIFICATION SUCCESSFUL!
Complete agent trace verified

Root Verification Details:
  Session Root (Hierarchical): DmBn8+/fBTI3uYOIxP9hHwUK8E6m6EfUye6o3CJC4PoDChpKN
PhvgQaRJ+QZjk/6

>> STEP 8: Comprehensive Integrity Report

Interaction Summary:
  - Total Spans: 3
  - Protocol Version: 2025-11-25
  - LLM: arcee-ai/trinity-large-preview:free

Cryptographic Details:
  - Curve: BLS12-381 (elliptic curve pairing)
  - Commitment Scheme: Hierarchical KZG + Verkle (per-span + session root)
  - Hash Algorithm: SHA-256
  - Encoding: RFC 8785 JSON Canonical + OpenTelemetry
  - Root Size: 48 bytes (compressed point)

Verification Status:
  - Log Integrity: [OK] VERIFIED
  - Session Root Match: [OK] VERIFIED
  - Hierarchical Spans: [OK] VERIFIED
  - Response Authenticity: [OK] VERIFIED
  - Overall Status: [OK] ALL CHECKS PASSED

What This Proves:
  - OpenRouter returned this exact response at this time
  - User asked this exact question
  - All communication followed MCP 2025-11-25 specification
  - No tampering occurred
  - Independently verifiable by anyone
```

**Key Features Demonstrated:**
- ✅ Real OpenRouter API call (genuine LLM response)
- ✅ Canonical JSON encoding (RFC 8785 deterministic format)
- ✅ SHA-256 hashing of events
- ✅ KZG commitments on BLS12-381 elliptic curve
- ✅ Cryptographic proof of integrity
- ✅ Complete audit trail in `workflows/workflow_{session_id}/` (find by session ID)
- ✅ **Automatic Langfuse integration** - Traces sent to Langfuse dashboard (if running)

**Langfuse Integration:**
The demo automatically exports OpenTelemetry spans to Langfuse if configured. In your Langfuse dashboard, you'll see:
- **Session**: Groups the entire agent run (useful for organizing multiple traces)
- **Trace**: The main Q&A interaction with complete metadata
- **Generation**: LLM call with prompt, response, and cost breakdown
  - Per-turn visibility: One generation per LLM turn (created during agent execution)
  - Token usage: Input/output token counts from OpenRouter
  - Cost tracking: Input/output costs in USD with automatic aggregation
- Span hierarchy with timestamps and duration metrics
- Complete event sequence for debugging and auditing

---

### Demo 2: Real Agent Demo - Tool Invocation & Multi-Turn

**What it shows:** Agent with tool access, decision-making, and multi-turn interaction

```powershell
# Run the agent demo
python real_agent_demo.py
```

**What you'll see:**

```
================================================================================
          REAL-TIME AI AGENT WITH TOOL INVOCATION & INTEGRITY TRACKING
================================================================================

This is a REAL agent interaction with TOOL INVOCATION using AIAgent:
  - User sends a prompt with available tools
  - LLM decides which tools to use
  - AIAgent executes tool calls
  - Tool results are fed back to LLM
  - All interactions are integrity-tracked with Verkle trees
  - Complete agent trace is cryptographically verifiable

>> STEP 1: Initialize AIAgent with LLM Client & Middleware

[OK] IntegrityMiddleware initialized (hierarchical spans + Langfuse)
[OK] Langfuse tracing enabled (traces at http://localhost:3000)
[OK] MCPServer initialized with 4 tools
[OK] Session ID: real-agent-mcp-20260222-144247
[OK] Model: arcee-ai/trinity-large-preview:free
[OK] OpenRouter LLM client connected
[OK] AIAgent initialized with OpenRouter

>> STEP 2: Run Agent with Multi-Turn Tool Invocation

[2026-02-22T14:42:53.740201] USER_PROMPT: I need your help understanding the efficiency benefits of Ve...
[OK] User prompt recorded

LLM Decision: Tool calls needed

[TOOL_CALL] query_verkle('proof sizes')
  → No information available for 'proof sizes'. Available queries: efficiency, proof-size...
  [OK] Tool executed and recorded

>> STEP 3: Agent Execution Results

Final Output:
I see that the tools have been executed, but I don't have any specific information about what was requested or what the results were. Could you please provide more context or clarify what you'd like me to do with the tool outputs?

Execution Summary:
  Turns: 2
  Session ID: real-agent-mcp-20260222-144247
  Model: arcee-ai/trinity-large-preview:free

>> STEP 4: Finalize Hierarchical Verkle Tree and Generate Session Root

[OK] Hierarchical Verkle tree finalized with integrity verification

Cryptographic Commitment:
  Session Root (Base64): ECUu4fr//g4ZPLX65PFfWPGgYeLail+ViFCK6VsW1WUmuwce842m/PI1mfXWpuRB

Hierarchical Span Structure:
  - real-agent-mcp-20260222-144247_agent_run_0: 1 events
  - real-agent-mcp-20260222-144247_agent_turn_1_1: 2 events
  - real-agent-mcp-20260222-144247_agent_turn_2_2: 1 events
  - real-agent-mcp-20260222-144247_agent_finalize_3: 0 events

>> STEP 5: Verify Integrity of Complete Log

[OK] VERIFICATION SUCCESSFUL!
Complete agent trace verified

Root Verification Details:
  Session Root (Hierarchical): ECUu4fr//g4ZPLX65PFfWPGgYeLail+ViFCK6VsW1WUmuwce842m/PI1mfXWpuRB

>> STEP 6: Verify Hierarchical Span Structure and MCP Protocol Compliance

Hierarchical Span Structure:
  [OK] Spans: 4
       - real-agent-mcp-20260222-144247_agent_run_0: 1 events
       - real-agent-mcp-20260222-144247_agent_turn_1_1: 2 events
       - real-agent-mcp-20260222-144247_agent_turn_2_2: 1 events
       - real-agent-mcp-20260222-144247_agent_finalize_3: 0 events

MCP 2025-11-25 Protocol Compliance:
  [OK] Protocol Version: 2025-11-25
  [OK] JSON-RPC Version: 2.0
  [OK] Tool Invocation: Supported
  [OK] Multi-Turn Conversations: Supported

>> STEP 8: Comprehensive Integrity Report

Summary:
  - Total LLM Turns: 2
  - Tools Available: 4
  - Spans Recorded: 4
  - Protocol Used: MCP 2025-11-25 with JSON-RPC 2.0

Cryptographic Details:
  - Curve: BLS12-381 (elliptic curve pairing)
  - Commitment Scheme: Hierarchical KZG + Verkle (per-span + session root)
  - Hash Algorithm: SHA-256
  - Encoding: RFC 8785 JSON Canonical Serialization

What This Proves:
  - Exact sequence of LLM decisions and tool calls across spans
  - Tool inputs and outputs are tamper-evident
  - Complete hierarchical agent trace with per-span Verkle roots
  - All communication in JSON-RPC 2.0 format with request ID correlation
  - Independently verifiable by anyone at span or session level
```

**Key Features Demonstrated:**
- ✅ Real LLM with tool invocation
- ✅ Multi-turn agent interactions
- ✅ Tool execution tracking
- ✅ Complete decision audit trail in `workflows/workflow_{session_id}/`
- ✅ Cryptographic proof of tool outputs
- ✅ Non-repudiation (LLM can't deny what it asked for)
- ✅ **Automatic Langfuse integration** - Complete trace of all tool calls and LLM decisions (find workflow by session ID)

**Langfuse Integration:**
The agent demo automatically exports detailed traces to Langfuse showing:
- **Session**: Groups all traces for the agent session
- **Trace**: The main agent execution flow with metadata
- **Generations**: One per LLM turn (multi-turn support)
  - Per-turn visibility: See each LLM decision and reasoning
  - Token usage: Input/output tokens tracked per turn
  - Cost breakdown: USD costs per LLM call with automatic aggregation
  - Model selection: Shows which model was used for each turn
- LLM decision points and tool selections
- Each tool invocation with parameters and results
- Multi-turn interaction flow with latency breakdown
- Complete audit trail for debugging and compliance

---

### Demo 3: Secure Remote Tool Agent - ECDH-AES256-GCM + IBS Signatures

**What it shows:** Agent with encrypted remote tool access, split between secure client and server processes

```powershell
# Terminal 1 - Start remote tool (WebSocket server)
.\venv\Scripts\Activate.ps1
python examples/remote_tool.py

# Terminal 2 - Run secure agent (connects to remote tool)
.\venv\Scripts\Activate.ps1
python examples/agent_remote_demo.py
```

**What's unique:** This demo proves **secure remote tool invocation across process/network boundaries**:
- **ECDH-AES256-GCM Encryption**: Client and remote tool exchange Diffie-Hellman keys, establish shared secret, encrypt all messages
- **IBS Key Provisioning**: During handshake, remote tool receives Identity-Based Signature keys derived from its name (BLS12-381)
- **Signed Tool Responses**: Tool outputs cryptographically signed by the remote tool (not the client), proving authenticity
- **Secure Channel Integrity**: All remote tool messages tracked in integrity log (canonical encoding + Verkle commitment)
- **Replay Prevention**: Session IDs and monotonic counters prevent unauthorized message replay

**What you'll see:**

```
[OK] IntegrityMiddleware initialized (unified accumulator + Langfuse)
[OK] Langfuse tracing enabled (traces at http://localhost:3000)
Session ID: remote-agent-mcp-20260223-120530

[Conn] Connected to 'remote_calc' on ws://localhost:5555 (Secure Channel Established)
[OK] ECDH-AES256-GCM secure channel established
[OK] IBS key provisioning complete

[OK] Remote tool registered with MCPServer
[OK] OpenRouterClient initialized (model: arcee-ai/trinity-large-preview:free)
[OK] AIAgent initialized with remote tools

User Request: I need you to help me perform a calculation using the remote tool...

LLM Decision: Tool calls needed

[TOOL_CALL] remote_calc('2048 + 512 - 256')
  [Encrypted] Message sent to remote tool
  [Verified] Tool signature valid (IBS-BLS12-381)
  → Result received and recorded

[OK] Agent execution completed with 2 turn(s)

Cryptographic Commitment:
  Session Root: ECUu4fr//g4ZPLX65PFfWPGgYeLail+ViFCK6VsW1WUmuwce842m/PI1mfXWpuRB

Hierarchical Span Structure:
  - remote-agent-mcp-20260223-120530_agent_run_0: 1 events
  - remote-agent-mcp-20260223-120530_mcp_initialize_1: 2 events
  - remote-agent-mcp-20260223-120530_tool_execution_2: 3 events (with remote tool response)
  - remote-agent-mcp-20260223-120530_agent_finalize_3: 0 events

[OK] VERIFICATION SUCCESSFUL: Remote agent interaction verified
```

**Key Features Demonstrated:**
- ✅ Real encrypted WebSocket connection between client and remote tool
- ✅ Secure handshake with ECDH key exchange
- ✅ IBS key provisioning (tool receives signing keys)
- ✅ Remote tool responses cryptographically signed (non-repudiation)
- ✅ Integrity of encrypted messages verified via Verkle tree
- ✅ Complete audit trail including encrypted channel metadata
- ✅ Identical verification workflow as other demos (same verification CLI commands)

**How This Proves Remote Tool Authenticity:**

The key insight: **Tool output signatures cannot be forged by the client**. Even if the client is compromised:
1. ✅ Client cannot create valid signatures (missing tool's IBS private key)
2. ✅ Remote tool signs its own responses (signature proves authenticity)
3. ✅ Signatures recorded in canonical log (part of Verkle commitment)
4. ✅ Verifier confirms signature matches tool's public key (derived from tool name)

Result: Anyone can verify that the tool executed the request and returned that exact response, even if the client was untrusted.

**Langfuse Integration:**
Same as Demo 2 - automatic spans showing:
- Session grouping
- Encrypted message trace
- Per-turn LLM decisions
- Tool invocation flow
- Complete latency breakdown per encrypted message

---

### How to Verify Locally (Anyone Can Do This)

After running any demo, verify the proof without trusting the system:

```powershell
# Activate environment
.\venv\Scripts\Activate.ps1

# List all workflows (find the session ID)
python -m src.tools.verify_cli list-workflows

# Verify by session ID (easiest - finds workflow automatically)
python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-143944 --verbose

# Or verify by file path directly
python -m src.tools.verify_cli verify "workflows/workflow_real-prompt-mcp-20260222-143944/canonical_log.jsonl" "DmBn8+/fBTI3uYOIxP9hHwUK8E..." --verbose

# Expected output
[OK] Verification PASSED [OK]
  Root matches: DmBn8+/fBTI3uYOIxP9hHwUK8E...
  Events verified: 2
  Spans verified: 3
```

---

### � Recovery from Data Loss

Each workflow is stored as a self-contained directory with 5 cryptographically verifiable files:

**Workflow Files (Located in `workflows/workflow_{session_id}/`):**
- `canonical_log.jsonl` - All raw events with signatures (source of truth for verification)
- `spans_structure.json` - OpenTelemetry span organization and hierarchy
- `commitments.json` - Verkle tree roots and cryptographic commitments
- `metadata.json` - Session metadata (timestamps, event counts, log hash)
- `otel_export.json` - Complete span trace in OpenTelemetry JSON format
- `crypto_params.json` - Cryptographic parameters: scheme and Master Public Key (MPK) for IBS signature verification

**Recovery Scenarios:**

**Scenario 1: Langfuse Dashboard Lost**
If your Langfuse instance becomes unavailable or is deleted:
1. You still have complete cryptographic proof in `canonical_log.jsonl`
2. All span structure is preserved in `spans_structure.json`
3. Session root in `commitments.json` allows complete verification
4. Run verification CLI to independently prove nothing was tampered with:
   ```powershell
   python -m src.tools.verify_cli verify-by-id {session_id} --verbose
   ```

**Scenario 2: Verify Span Integrity**
To verify individual spans match the session root:
```powershell
python -m src.tools.verify_cli verify "workflows/workflow_{session_id}/canonical_log.jsonl" "{session_root}" --verbose
```

**Scenario 3: Export for Long-Term Archival**
Create an audit-ready proof document:
```powershell
python -m src.tools.verify_cli export-proof "workflows/workflow_{session_id}/canonical_log.jsonl" "{session_root}" \
  --output proof.json \
  --include-events
```

**Why This Design Works:**
- ✅ **Self-Contained**: Each workflow is independent, no external dependencies
- ✅ **Cryptographically Verifiable**: Commitment is deterministic proof of integrity
- ✅ **Human-Readable**: Access `canonical_log.jsonl` to see all events
- ✅ **Platform-Agnostic**: Works without Langfuse, PostgreSQL, or any external systems
- ✅ **Audit-Ready**: Complete lineage from event occurrence to cryptographic proof

**Key Insight:**
The Langfuse dashboard provides observability and trace visualization, but the cryptographic proof exists independently in the workflow directory. You can delete Langfuse and still verify everything using the verification CLI.

---

### �📊 Langfuse Integration in Demos

All three demos automatically integrate with Langfuse if configured:

**Setup Langfuse (5 minutes - Free Local Deployment):**
```powershell
# Start Langfuse with Docker Compose (completely free locally)
docker-compose up -d

# View dashboard at http://localhost:3000
```

**Note:** Current demos use in-memory counters (no database persistence). For production counter persistence, configure PostgreSQL via environment variables (see Configuration section).

**What you'll see in Langfuse:**

Langfuse receives OpenTelemetry traces showing:
- Root span with trace ID
- Session/run identifier
- Total execution duration
- Trace can be cross-referenced with verification CLI using trace ID

**Optional metadata** (if demo sends it):
- Custom attributes and tags
- Event payloads
- Performance metrics

**Note:** Child span visibility in the dashboard depends on the OpenTelemetry instrumentation configuration. The root span is always visible.

**Key Points:**
- ✅ **Completely free** - Self-hosted Docker deployment, no cost
- ✅ **Real-time visibility** - Watch traces appear as agent runs
- ✅ **Audit trail** - Traces are independently verifiable via verification CLI
- ✅ **Zero trust required** - Traces don't prove integrity (verification CLI does), but provide monitoring
- ✅ **Automatic export** - OTel spans sent to Langfuse automatically when configured

---

##  Integrity Architecture

### Event Flow with Hierarchical Verkle Middleware

```
User Prompt
    ↓
[HierarchicalVerkleMiddleware.start_span("user_interaction")] → Record event in span
    ↓
MCP Initialize Handshake (JSON-RPC 2.0)
    ↓
[HierarchicalVerkleMiddleware.start_span("mcp_initialize")] → Record events → Per-span Verkle root
    ↓
Tool Invocation (with IBS Authorization & Signature)
    ↓
[HierarchicalVerkleMiddleware.start_span("tool_execution")] → Record tool call + response → Signature verified
    ↓
LLM Model Output / Final Response
    ↓
[HierarchicalVerkleMiddleware.start_span("final_response")] → Record response with span root
    ↓
Finalization → Session Root (combines all span roots) → Commitments file → Local storage
    ↓
OTel Export → Auto-export to Langfuse (if enabled)
```

### Hierarchical Span-Based Middleware Pattern

Before: Flat event stream with single root  
After: Hierarchical spans with per-span roots + session root

```python
# Initialize hierarchical middleware (auto-detects Langfuse)
middleware = HierarchicalVerkleMiddleware(session_id="agent-run-001")

# Span 1: MCP Initialize handshake
middleware.start_span("mcp_initialize")
middleware.record_event_in_span("mcp_initialize_request", request_dict, signer_id="client")
middleware.record_event_in_span("mcp_initialize_response", response_dict, signer_id="server")

# Span 2: User interaction
middleware.start_span("user_interaction")
middleware.record_event_in_span("user_prompt", {"prompt": "..."}, signer_id="user")

# Span 3: Tool execution (with IBS signatures)
middleware.start_span("tool_execution")
middleware.record_event_in_span("tool_input", {"tool": "search", "args": {...}}, signer_id="client")
middleware.record_event_in_span("tool_output", {"result": {...}, "signature": sig}, signer_id="tool")

# Span 4: Final response
middleware.start_span("final_response")
middleware.record_event_in_span("final_response", {"answer": "..."}, signer_id="llm")

# Optional: Record LLM generation for observability (Langfuse) - DOES NOT modify integrity log
# This is called per LLM turn for per-turn visibility in Langfuse dashboard
generation_id = middleware.record_llm_generation(
    prompt="What is Verkle?",
    response="Verkle trees are...",
    model="arcee-ai/trinity-large",
    name="llm_call_turn_1",
    input_tokens=15,
    output_tokens=42,
    input_cost=0.0015,
    output_cost=0.0021,
    total_cost=0.0036,
    turn=1
)
# Returns: generation_id (for Langfuse tracing), or empty string if Langfuse unavailable

# Finalize with hierarchical roots
session_root, commitments, canonical_log_bytes = middleware.finalize()
# Returns: session_root (combines all span roots), per-span roots, commitments object

# Save to local storage (creates 5 files: canonical_log.jsonl, spans_structure.json, 
# commitments.json, metadata.json, otel_export.json)
middleware.save_to_local_storage(Path("workflow_abc123"))
```

**Key Pattern:**
- **Integrity Recording** (`record_event_in_span`): Modifies canonical log and Verkle commitments
- **Observability Recording** (`record_llm_generation`): Langfuse-only, does NOT affect integrity log
- **Separation of Concerns**: Integrity is cryptographically protected, observability is for dashboarding

### Deterministic Event Format

Application events follow this structure:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "counter": 0,
  "timestamp": "2025-12-08T10:30:45.123456Z",
  "event_type": "prompt|model_output|tool_input|tool_output|mcp_initialize_request|mcp_tools_call_request|...",
  "payload": { /* event-specific data */ },
  "signature": "base64-encoded-ibs-signature",
  "signer_id": "server|tool_name"
}
```

MCP protocol events include the full JSON-RPC 2.0 message:

```json
{
  "type": "mcp_initialize_request|mcp_tools_call_response|...",
  "jsonrpc": { /* complete JSON-RPC 2.0 dict */ },
  "timestamp": "2025-12-08T10:30:45.123456Z",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Key Properties:**
- **Canonical Encoding**: RFC 8785 JSON with sorted keys, no whitespace
- **Unicode Normalization**: NFC normalization for determinism
- **Non-Finite Float Rejection**: NaN, Infinity, -Infinity are forbidden
- **Sequential Counters**: Atomic increment, persisted in PostgreSQL
- **JSON-RPC Compliance**: All protocol events wrapped in JSON-RPC 2.0 format
- **Request ID Correlation**: tools/call requests matched with responses via ID

---

## 🌳 Cryptographic Commitments: Hierarchical Verkle Trees with KZG

### Current Implementation: Hierarchical KZG Polynomial Commitments with Per-Span + Session Roots

**What we have:** **Hierarchical Verkle Commitments** over BLS12-381 elliptic curve
- **HierarchicalVerkleMiddleware** (in `src/integrity/hierarchical_integrity.py`)
  - Organizes events into OpenTelemetry-compatible spans
  - Each span gets its own Verkle root (per-span commitment)
  - Session root combines all span roots into single commitment
  - Methods: `start_span()`, `record_event_in_span()`, `record_llm_generation()`, `finalize()`, `save_to_local_storage()`
  - `record_event_in_span()`: Records integrity-critical events (modifies canonical log and Verkle)
  - `record_llm_generation()`: Records LLM generations for observability ONLY (Langfuse-only, no integrity changes)
  - Returns: `Tuple[str, HierarchicalCommitments, bytes]` from `finalize()` (session_root, commitments object, canonical_log_bytes)
  - Auto-detects and integrates Langfuse if available
- **Per-Span Event Accumulation** → **SHA-256 Hashing** → **Span-Level KZG Commitments** → **Session Root (Verkle of span roots)**
- Algorithm: KZG polynomial commitments with BLS12-381 pairing-friendly curves
- Status: ✅ **Fully functional and tested** (128+ tests passing, hierarchical spans verified with 6-file local storage)
- Integration: Automatic Langfuse export with graceful fallback if unavailable
- Local Storage: Saves 5 files per run (canonical_log.jsonl, spans_structure.json, commitments.json, metadata.json, otel_export.json)

### Key Properties

- **Cryptographic Scheme**: Kate-Zaverucha-Goldberg (KZG) polynomial commitments
- **Elliptic Curve**: BLS12-381 (pairing-friendly curve used in Ethereum, Zcash)
- **Commitment Size**: 48 bytes (compressed G1 point)
- **Proof Efficiency**: O(1) compact proofs (vs O(log n) for Merkle trees)
- **Stateless Verification**: Proofs don't require full state tree

### How Hierarchical Verkle Works

1. **Events organized into spans** (mcp_initialize, user_interaction, tool_execution, final_response)
2. **Per-span processing**:
   - Events canonically encoded using RFC 8785 (deterministic JSON)
   - SHA-256 hashes created for each event within the span
   - Span accumulator builds KZG commitment from all events in that span
   - Per-span Verkle root computed and stored
3. **Session-level processing**:
   - All span roots collected into session accumulator
   - Session root computed as KZG commitment of span roots
   - Complete hierarchical commitment structure created
4. **Verification support**:
   - Span-level verification: Verify individual span integrity
   - Session-level verification: Verify all spans combine correctly
   - Full session root verification: Proves entire agent run integrity
5. **Anyone can verify** the session root matches the complete log without trusting the server

See `src/crypto/verkle.py` for implementation details and trusted setup parameters.

---

## 🔍 Verification CLI

The **Verification CLI** provides public, third-party verification of agent run integrity without requiring server access. It includes commands for listing workflows, retrieving metadata, and verifying integrity.

### Quick Start

```powershell
# List all available workflows
python -m src.tools.verify_cli list-workflows

# Get metadata for a specific workflow
python -m src.tools.verify_cli get-workflow real-prompt-mcp-20260222-141751

# Verify a workflow by session ID (fastest)
python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751

# Verify with tool signature verification
python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751 --verify-signatures --verbose

# Or verify by file path and root commitment
python -m src.tools.verify_cli verify ./canonical_log.jsonl "AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN" --verbose
```

### Six Commands

#### 1. **List-Workflows** - Show all available workflows
```bash
python -m src.tools.verify_cli list-workflows [--dir <path>]
```

Lists all workflows with basic metadata.

**Example:**
```bash
python -m src.tools.verify_cli list-workflows
```

**Output:**
```
[WORKFLOWS] Available Workflows (5 total)

Session ID                                         Timestamp                 Root                 Events
-----------------------------------------------------------------------------------------------------------------------
real-agent-mcp-20260220-161646                     2026-02-20T15:17:54       EmyfvcUc/Uci...     19
real-prompt-mcp-20260222-141149                    2026-02-22T13:12:17       ClZxy9RVIccr...     2
real-prompt-mcp-20260222-141751                    2026-02-22T13:18:10       AT32sZab0WmC...     2
real-prompt-mcp-20260222-143944                    2026-02-22T13:40:09       DmBn8+/fBTI3...     2
remote-agent-mcp-20260221-223427                   2026-02-21T21:34:52       GU8oGeJSxPfm...     4

[NOTE] To verify a specific workflow:
   verify-by-id <session-id>
   get-workflow <session-id>
```

#### 2. **Get-Workflow** - Show detailed metadata for a specific workflow
```bash
python -m src.tools.verify_cli get-workflow <session-id> [--dir <path>]
```

Displays session ID, timestamp, session root, span roots, event count, event types, and file paths.

**Example:**
```bash
python -m src.tools.verify_cli get-workflow real-prompt-mcp-20260222-141751
```

**Output:**
```
[WORKFLOW] Details: real-prompt-mcp-20260222-141751

Metadata:
  Timestamp: 2026-02-22T13:18:10.894176+00:00
  Event Count: 2
  Span Count: 3

Cryptographic Commitments:
  Session Root: AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN

Span Roots:
  real-prompt-mcp-20260222-141751_agent_run_0: DABHke5IGpNS2IY1hrMnkTzHv0JrM4SWCzrVY...
  real-prompt-mcp-20260222-141751_agent_turn_1_1: AoDmz3hXKzMX364Ar4k38S83ySBHPDFHrwb1q...
  real-prompt-mcp-20260222-141751_agent_finalize_2: AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA...

Files:
  Canonical Log: workflows\workflow_real-prompt-mcp-20260222-141751\canonical_log.jsonl
  Metadata: workflows\workflow_real-prompt-mcp-20260222-141751\metadata.json
  Commitments: workflows\workflow_real-prompt-mcp-20260222-141751\commitments.json
  Crypto Params: workflows\workflow_real-prompt-mcp-20260222-141751\crypto_params.json (for signature verification)

Verification Commands:

  Recommended (by session ID):
    .\venv\Scripts\Activate.ps1; python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751

  Alternative (by file path):
    .\venv\Scripts\Activate.ps1; python -m src.tools.verify_cli verify "workflows\workflow_real-prompt-mcp-20260222-141751\canonical_log.jsonl" 'AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN'
```

#### 3. **Verify-By-ID** - Verify a workflow by session ID (fastest)
```bash
python -m src.tools.verify_cli verify-by-id <session-id> [--dir <path>] [--verbose] [--verify-signatures]
```

Reconstructs the Verkle tree and confirms the session root commitment matches the stored root. Optionally verifies IBS signatures on tool outputs.

**Options:**
- `--verbose, -v` - Show detailed verification steps
- `--verify-signatures` - Also verify Identity-Based Signatures (IBS) on tool outputs
- `--show-protocol` - Show protocol event breakdown

**Example (Verkle root only):**
```bash
python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751 --verbose
```

**Example (Verkle root + tool signatures):**
```bash
python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751 --verbose --verify-signatures
```

**Output on success (Verkle only):**
```
[OK] Verification PASSED [OK]
  Root matches: AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN
  Events verified: 2
  Spans verified: 3
```

**Output on success (with signature verification):**
```
[OK] Verification PASSED [OK]
  Root matches: AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN
  Events verified: 2
  Spans verified: 3

Verifying IBS signatures...
  Signatures verified: 2
  [OK] All 2 signatures verified
```

#### 4. **Verify** - Validate run integrity by file path and root
```bash
python -m src.tools.verify_cli verify <log_file> <root_b64> [--expected-hash <hash>] [--verbose] [--verify-signatures]
```

Reconstructs the Verkle tree and confirms the root commitment matches. Optionally verifies IBS signatures on tool outputs.

**Arguments:**
- `log_file` - Path to the canonical event log (JSON format)
- `root_b64` - Expected Verkle root commitment (Base64-encoded)

**Options:**
- `--expected-hash TEXT` - Optional SHA-256 hash to verify log integrity
- `--verbose, -v` - Show detailed verification steps
- `--verify-signatures` - Also verify Identity-Based Signatures (IBS) on tool outputs
- `--show-protocol` - Show protocol event breakdown

**Example (Verkle root only):**
```bash
python -m src.tools.verify_cli verify ./canonical_log.jsonl "AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN" --verbose
```

**Example (Verkle root + tool signatures):**
```bash
python -m src.tools.verify_cli verify ./canonical_log.jsonl "AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN" --verify-signatures --verbose
```

**Output on success:**
```
[OK] Verification PASSED [OK]
  Root matches: AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN
  Events verified: 2
```

#### 5. **Extract** - Show run metadata without verification
```bash
python -m src.tools.verify_cli extract <log_file>
```

Displays session ID, event count, event types, timestamps, and log hash without performing verification.

**Example:**
```bash
python -m src.tools.verify_cli extract ./canonical_log.jsonl
```

**Output:**
```
============================================================
Canonical Log Metadata
============================================================

Session ID:        real-prompt-mcp-20260222-141751
Event Count:       2
File Size:         641 bytes
SHA-256 Hash:      d4fd76612a9b79bdc5ceac8b4378912d1ff235e816b88117bb87d2d7cf5c24a2

Event Types:
  user_prompt....................................... 1 events
  model_output...................................... 1 events

First Timestamp:   2026-02-22T13:17:55.000Z
Last Timestamp:    2026-02-22T13:18:10.000Z

Counter Range:     0 → 1

============================================================
```

#### 6. **Export-Proof** - Generate audit-ready proof JSON
```bash
python -m src.tools.verify_cli export-proof <log_file> <root_b64> [--output <path>] [--include-events] [--include-log]
```

Creates a JSON proof document containing verification results and metadata for audit trails and archival.

**Arguments:**
- `log_file` - Path to the canonical event log (JSON format)
- `root_b64` - Expected Verkle root commitment (Base64-encoded)

**Options:**
- `--output, -o PATH` - Output file path (default: `proof.json`)
- `--include-events` - Include event summary and sample events in proof
- `--include-log` - Include the entire canonical log (Base64-encoded) in proof

**Example:**
```bash
python -m src.tools.verify_cli export-proof ./canonical_log.jsonl "AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN" \
  --output proof.json \
  --include-events
```

**Proof JSON structure:**
```json
{
  "version": "1.0",
  "generated_at": "2026-02-22T13:30:45.123456",
  "metadata": {
    "session_id": "real-prompt-mcp-20260222-141751",
    "event_count": 2,
    "file_size_bytes": 641,
    "first_event_type": "user_prompt",
    "last_event_type": "model_output",
    "first_timestamp": "2026-02-22T13:17:55.000Z",
    "last_timestamp": "2026-02-22T13:18:10.000Z"
  },
  "verification": {
    "log_hash_sha256": "d4fd76612a9b79bdc5ceac8b4378912d1ff235e816b88117bb87d2d7cf5c24a2",
    "expected_root_b64": "AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN",
    "computed_root_b64": "AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN",
    "verification_passed": true,
    "verification_timestamp": "2026-02-22T13:30:45.123456"
  },
  "event_summary": {
    "user_prompt": 1,
    "model_output": 1
  }
}
```

### Canonical Log Format

The CLI expects canonical logs in JSON format with the following structure:

```json
[
  {
    "session_id": "real-agent-<timestamp>",
    "event_type": "user_prompt|model_output|tool_input|tool_output|...",
    "counter": 0,
    "timestamp": "2026-02-22T13:17:55.000Z",
    "data": { ... }
  }
]
```

**Required Fields:**
- `session_id` - Unique identifier for the agent run
- `event_type` - Type of event
- `counter` - Sequential event counter (must be sequential starting from 0)
- `timestamp` - ISO 8601 timestamp
- `attributes` - Event-specific data (OTel standard)

**Signature Fields (optional, used when `--verify-signatures`):**
- `signature` - IBS signature as string representation of (U, V) G1 point tuple
- `signer_id` - Identity of signer (tool name or "server")
- `span_id` - The span this event belongs to

### Tool Signature Verification (IBS-Based Authenticity)

Any workflow may include **Identity-Based Signatures (IBS)** on tool outputs, proving that the tool (not the client) created that response. To verify these signatures:

```powershell
# Verify Verkle root AND tool signatures
python -m src.tools.verify_cli verify-by-id {session_id} --verify-signatures --verbose

# Or with file path
python -m src.tools.verify_cli verify ./canonical_log.jsonl "{root_b64}" --verify-signatures --verbose
```

**How Tool Signatures Work:**

1. **Key Provisioning**: Each tool receives an Identity-Based Signature (IBS) private key derived from its name using BLS12-381 elliptic curve cryptography (Cha-Cheon scheme)
2. **Signing**: When a tool produces output, it cryptographically signs the output with its IBS private key
3. **Verification**: The public Master Key (MPK) is exported to `crypto_params.json` in the workflow directory
4. **Third-Party Verification**: Anyone can use the public MPK to verify that the signature is valid for that tool identity and that exact output

**What This Proves:**
- ✅ The tool output is authentic (signed by the tool, not forged by the client)
- ✅ The tool identity is correct (derived from tool name using IBS)
- ✅ The exact output cannot be changed without invalidating the signature
- ✅ Non-repudiation: The tool cannot deny creating that response

**Signature Verification Output:**
```
Verifying IBS signatures...
  [OK] Event 5 (tool_output): signature valid (signer: weather)
  [OK] Event 8 (tool_output): signature valid (signer: calculator)
  Signatures verified: 2
  [OK] All 2 signatures verified
```

**Files Required for Signature Verification:**
- `canonical_log.jsonl` - Contains signed events with `signature` and `signer_id` fields
- `crypto_params.json` - Contains the Master Public Key (MPK) for signature verification

Both files are automatically saved to the workflow directory and included in all workflow artifacts.

### Use Cases

- ✅ **Real-time verification** - Verify an agent run immediately after it completes
- ✅ **Workflow browsing** - List and inspect all available workflows
- ✅ **Batch verification** - Script-based verification of multiple runs using verify-by-id
- ✅ **Audit trail** - Export proofs for compliance or security audits
- ✅ **Public transparency** - Share proofs to a verification server without server access
- ✅ **Offline verification** - Download log and verify locally without network

### Verification Algorithm

The CLI performs the following verification steps:

1. **Load Log**: Read and parse the canonical JSON log
2. **Hash Verification** (optional): Verify SHA-256 hash if provided
3. **Event Parsing**: Extract events and verify sequential counters
4. **KZG Accumulation**: Reconstruct the Verkle tree by:
   - Canonically encoding each event (RFC 8785)
   - Computing SHA-256 hash of each encoded event
   - Creating a KZG polynomial commitment over the event hashes
5. **Root Comparison**: Compare computed root with expected commitment
6. **Result**: Return success if roots match, failure otherwise

### Security Considerations

1. **Hash Validation**: Always provide `--expected-hash` when available to detect log tampering
2. **Root Source**: Ensure the expected root comes from a trusted source (e.g., signed commitment)
3. **Network**: When exchanging roots/logs over network, use TLS/SSL
4. **Proof Storage**: Store exported proofs in secure, immutable storage
5. **Audit Logs**: Log all verification activities for compliance

### Performance

- **Verification Time**: ~0.1-0.5 seconds per 100 events (CPU-dependent)
- **Memory Usage**: ~10-20 MB for logs with 1000+ events
- **Proof Export**: <1 second for typical runs

### CI/CD Integration

```yaml
# GitHub Actions example
- name: Verify Agent Run
  run: |
    python -m src.tools.verify_cli verify-by-id "${{ env.SESSION_ID }}" --verbose
```

### Testing

Comprehensive CLI tests verify all commands:
```powershell
python -m pytest tests/test_verify_cli.py -v
```

---

##  Observability

### OpenTelemetry Export

All agent events generate OTel spans exported to Langfuse:

```python
# Automatic span generation
- agent_run (root span)
  - model.invoke
  - tool.{tool_name}
  - ...
```

### Attributes

Every span includes:
- `session_id`: Run identifier
- `integrity.counter`: Sequential event number
- `integrity.timestamp`: Server timestamp
- `verkle.root_b64`: Commitment (on root span only)

### Configuration

```python
# .env
OTEL_OTLP_ENDPOINT=http://localhost:4317
LANGFUSE_API_ENDPOINT=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

## 🧪 Testing

Run the full test suite:

```powershell
python -m pytest tests/ -v --cov=src
```

Key test modules:
- `test_crypto.py`: Canonical encoding, Verkle accumulation, hash verification
- `test_integrity.py`: Event recording, finalization, counter validation

---

## 🛠️ Configuration

### Environment Variables

```bash
# PostgreSQL (optional - for production counter persistence and replay detection)
# If not configured, counter uses in-memory storage (session data lost on restart)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_DATABASE=verifiable_agent

# OpenTelemetry (optional - for observability and tracing)
# If not configured, agent runs without distributed tracing
# Exports traces to OTLP endpoint (default: localhost:4317)
OTEL_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=verifiable-ai-agent

# Langfuse (optional - for trace visualization and observability dashboard)
# Requires Langfuse running (see LANGFUSE_SETUP_GUIDE.md)
# Traces from OpenTelemetry are exported to Langfuse automatically
LANGFUSE_API_ENDPOINT=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...

# Server
HOST=0.0.0.0
PORT=8000
```

**PostgreSQL Details:**
- ✅ **Fully integrated** for atomic counter persistence
- ✅ Provides replay attack detection and monotonic counter enforcement
- ⚠️ **Optional for development**: Demos work without it (counter data not persisted across server restarts)
- ✅ **Recommended for production**: Enables stateless counter validation and recovery
- Dependencies: `sqlalchemy`, `psycopg2-binary` (already in pyproject.toml)

**OpenTelemetry Details:**
- ✅ **Fully integrated** for distributed tracing and observability
- ✅ Provides hierarchical span management with automatic duration measurement
- ✅ Exports spans to OTLP endpoint (typically Langfuse or Jaeger)
- ⚠️ **Optional for development**: Demos work without it (graceful fallback if OTEL_AVAILABLE=False)
- ✅ **Recommended with Langfuse**: See LANGFUSE_SETUP_GUIDE.md for dashboard visualization
- Dependencies: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp` (already in pyproject.toml)
- Test coverage: 21 tests in [tests/test_otel_spans.py](tests/test_otel_spans.py)

**Langfuse Details:**
- ✅ **Fully integrated** for trace visualization and cost analysis
- ✅ Receives traces from OpenTelemetry OTLP exporter
- ⚠️ **Optional**: Can run without it (OTel traces go to configured OTLP endpoint)
- ✅ **Recommended for observability**: Dashboard shows span hierarchy, duration, tokens, costs
- Setup: 5 minutes with Docker Compose (see LANGFUSE_SETUP_GUIDE.md)

## 📖 References

- **Model Context Protocol (MCP)**: https://modelcontextprotocol.io/
- **RFC 8785 JSON Canonicalization**: https://tools.ietf.org/html/rfc8785
- **Verkle Trees**: https://verkle.dev/
- **KZG Commitments**: https://dankradfeist.de/ethereum/2020/06/16/kate-polynomial-commitments.html
- **OpenTelemetry**: https://opentelemetry.io/
- **Langfuse**: https://langfuse.com/

---

## 📝 License

[Specify your license here]

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

---

## ❓ FAQ

**Q: What's the performance overhead of integrity tracking?**
A: Canonicalization and hashing add ~10-50ms per run (TBD after profiling). KZG polynomial commitments provide O(1) compact proof verification.

**Q: Can I run this on a commodity server?**
A: Yes! SQLite is the default (zero configuration). PostgreSQL is optional for production counter persistence.

**Q: How do I use the chat interface?**
A: Run `python backend/server.py`, open http://localhost:8000, and start chatting. The agent has 5 tools it can invoke based on your prompts. All interactions are cryptographically committed.

**Q: Is this suitable for production?**
A: Yes, the core integrity tracking, Verkle tree commitments, and verification CLI are production-ready. See PROJECT_SUMMARY.md for current status.

**Q: How do I verify a run offline?**
A: Download the canonical log from storage and run the verification CLI locally—no server contact needed.

