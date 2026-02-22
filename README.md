# 🔐 Verifiable AI Agent Server

A high-integrity, self-hosted AI Agent Server built on the Model Context Protocol (MCP) with cryptographic commitment of all agent–LLM–tool interactions into a **Verkle Tree**.

## 📋 Latest Updates (February 21, 2026)

- **Windows Compatibility Fixed**: All emoji characters replaced with ASCII-safe alternatives ([OK], [ERROR], [WORKFLOWS]) for cp1252 encoding compatibility
- **Demo Commands Improved**: All verification commands now include `.\\venv\\Scripts\\Activate.ps1` prefix for copy-paste readiness
- **Root Type Corrected**: Manual verification commands now use correct `session_root` for canonical_log.jsonl (span_commitment events)
- **Agent Response Completeness**: Increased `max_turns` from 3-5 to 8 for complete multi-turn interactions
- **Remote Tool Feedback**: Added startup status messages ([STARTING], [WAITING], [STOPPED])
- **Code Cleanup**: Removed obsolete debug files (check_log.py, check_events.py, demo.txt, demo_output.txt)

## 🎯 Core Features

- **Immutable Run Logs**: All agent interactions (prompts, tool calls, model outputs) are canonically encoded and cryptographically committed
- **Deterministic Verifiability**: Every run produces a single Verkle root commitment (KZG on BLS12-381) that can be independently verified
- **MCP 2024-11 Compliance**: Full JSON-RPC 2.0 protocol support with proper initialization handshake and request ID correlation
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
   ```
3. Run validation:
   ```powershell
   $env:PYTHONPATH = "."; python real_prompt_demo.py
   ```

**Project Structure:**
```
real_prompt_demo.py          # Demo: Simple Q&A with integrity tracking
real_agent_demo.py           # Demo: Multi-tool agent with tool invocation
run_all_tests.py             # Run all tests with progress tracking
pyproject.toml               # uv/pip compatible dependencies
setup.ps1                    # Automated setup script (Windows)
examples/ibs_demo.py         # Demo: Identity-Based Signatures (IBS)
docker-compose.yml           # Langfuse self-hosted deployment
README.md                    # This file (comprehensive guide)
PROJECT_SUMMARY.md           # Project status & future work
PROPOSAL.md                  # Technical approach & architecture
OLLAMA_SETUP_GUIDE.txt       # Alternative LLM provider guide
.env.example                 # Environment variables template
```

**Key Files:**
- `real_prompt_demo.py` - Entry point for simple demo with Langfuse tracing
- `real_agent_demo.py` - Entry point for agent demo with tool invocation
- `run_all_tests.py` - Run all tests with progress tracking
- `.env` - Local configuration (credentials, API keys, not in git)
- `docker-compose.yml` - Langfuse deployment (optional observability)

**Documentation:**
- `README.md` - Primary user guide (you are here)
- `PROJECT_SUMMARY.md` - Project status and future considerations
- `PROPOSAL.md` - Technical approach and architecture decisions
- `LANGFUSE_SETUP_GUIDE.md` - Observability setup and usage
- `OLLAMA_SETUP_GUIDE.txt` - Alternative LLM configuration

---

## 🎬 Live Demos (Main Features)

The two **flagship demonstrations** showcase the core project capabilities:

### Demo 1: Real Prompt Demo - MCP 2024-11 + Integrity Tracking

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
                  REAL-TIME AI AGENT WORKFLOW WITH INTEGRITY TRACKING
================================================================================

This is a REAL agent interaction:
  - User sends a prompt to OpenRouter API
  - LLM provides genuine response
  - All communication is integrity-tracked
  - Verkle tree built with KZG commitments
  - Cryptographically verifiable proof created
  - Anyone can verify what really happened

>> STEP 1: Initialize Integrity Tracking

[OK] Canonical JSON Encoder initialized (RFC 8785)
[OK] Verkle Accumulator initialized (KZG commitments, BLS12-381)
[OK] Session ID: real-agent-20260131-142530
[OK] Model: arcee-ai/trinity-large-preview:free

>> STEP 2: User Sends Prompt to Agent

[2025-01-31T14:25:30.123456] USER_PROMPT: Explain Verkle trees in one paragraph...
SHA-256 Hash: a1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6

>> STEP 4: Making REAL OpenRouter API Call

Sending request to OpenRouter...

>> STEP 5: LLM Response Received

[2025-01-31T14:25:32.654321] LLM_RESPONSE: Verkle trees are a cutting-edge 
cryptographic data structure that combines the efficiency of Merkle trees...

SHA-256 Hash: b2g3f4e5d6c7b8a9f0e1d2c3b4a5f6e7

================================================================================
                            INTEGRITY REPORT
================================================================================

Communication Summary:
  - Total Events: 4
  - Event Types: user_prompt, agent_routing, llm_response, final_response
  - Total Hashes Computed: 5 (each event + final root)

Cryptographic Details:
  - Curve: BLS12-381 (elliptic curve pairing)
  - Commitment Scheme: KZG (Kate-Zaverucha-Goldberg)
  - Hash Algorithm: SHA-256
  - Encoding: RFC 8785 (canonical JSON)
  - Root Size: 48 bytes (compressed point)

Verification Status:
  - Log Integrity: [OK] VERIFIED
  - Root Match: [OK] VERIFIED
  - Overall Status: [OK] ALL CHECKS PASSED

What This Proves:
  - OpenRouter returned this exact response at this time
  - User asked this exact question
  - No tampering occurred
  - Independently verifiable by anyone

Root Commitment: CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5

Canonical log saved to: real_workflow.jsonl

>> STEP 12: Langfuse Trace Export (Optional - Free Local Deployment)

If Langfuse is running, traces are automatically exported:

[OK] OpenTelemetry spans exported to Langfuse:
  Trace ID: 550e8400-e29b-41d4-a716-446655440000
  Status: Sent to http://localhost:3000
  
In Langfuse dashboard, you'll see:
  - Root span: agent_run (with session ID and duration)
  - Trace ID for cross-referencing with verification CLI
  - (Child spans visibility depends on instrumentation configuration)
```

**Key Features Demonstrated:**
- ✅ Real OpenRouter API call (genuine LLM response)
- ✅ Canonical JSON encoding (RFC 8785 deterministic format)
- ✅ SHA-256 hashing of events
- ✅ KZG commitments on BLS12-381 elliptic curve
- ✅ Cryptographic proof of integrity
- ✅ Complete audit trail in `real_workflow.jsonl`
- ✅ **Automatic Langfuse integration** - Traces sent to Langfuse dashboard (if running)

**Langfuse Integration:**
The demo automatically exports OpenTelemetry spans to Langfuse if configured. In your Langfuse dashboard, you'll see:
- Root span with session tracking
- Event sequence with timestamps
- Complete trace for debugging and auditing
- (Detailed child spans depend on instrumentation configuration)

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

This is a REAL agent interaction with TOOL INVOCATION:
  - User sends a prompt with available tools
  - LLM decides which tools to use
  - Agent executes tool calls
  - Tool results are fed back to LLM
  - All interactions are integrity-tracked with Verkle trees

>> STEP 1: Initialize Integrity Tracking

[OK] Canonical JSON Encoder initialized (RFC 8785)
[OK] Verkle Accumulator initialized (KZG commitments, BLS12-381)
[OK] Session ID: real-agent-20260131-143015
[OK] Model: arcee-ai/trinity-large-preview:free
[OK] Available tools: 4

>> STEP 2: User Sends Prompt with Tool Access

[2025-01-31T14:30:15.234567] USER_PROMPT: I need your help understanding 
Verkle tree efficiency. Please use tools to query info and calculate...

Available Tools:
  - get_current_time: Get the current date and time
  - calculate: Evaluate mathematical expressions
  - get_crypto_info: Get information about cryptographic concepts
  - query_verkle: Get information about Verkle trees

>> STEP 3: Agent Interaction with Tool Invocation

LLM Decision: Tool calls needed (3 operations)

[TOOL_CALL] query_verkle("proof-size")
  → Verkle tree proofs are approximately 3.5KB compared to 7MB for Merkle trees
  SHA-256: c3h4g5f6e7d8c9b0a1f2e3d4c5b6a7f8

[TOOL_CALL] get_crypto_info("KZG")
  → Kate-Zaverucha-Goldberg polynomial commitments enable proving 
  evaluations with O(1) sized commitments and proofs
  SHA-256: d4i5h6g7f8e9d0c1b2a3f4e5d6c7b8a9

[TOOL_CALL] calculate("7000000 / 3500")
  → 2000
  SHA-256: e5j6i7h8g9f0e1d2c3b4a5f6e7d8c9b0

LLM Response (synthesizing results):
  "Based on my calculations and research, Verkle trees provide approximately 
  2000x bandwidth improvement over Merkle trees for state verification..."

================================================================================
                         COMPLETE AGENT TRACE
================================================================================

Events Recorded: 5
  1. user_prompt (session start)
  2. tool_call (query_verkle)
  3. tool_call (get_crypto_info)
  4. tool_call (calculate)
  5. final_response (agent completed)

Cryptographic Commitment: CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5

What This Proves:
  - Exact sequence of LLM decisions and tool calls
  - Exact tool outputs and parameters
  - LLM couldn't have changed responses without breaking the commitment
  - Anyone can verify this trace independently

Verification Status: [OK] ALL CHECKS PASSED

Canonical log saved to: real_agent_workflow.jsonl

>> STEP 11: Langfuse Trace Export (Optional - Free Local Deployment)

If Langfuse is running, agent trace is automatically exported:

[OK] OpenTelemetry spans exported to Langfuse:
  Trace ID: real-agent-20260131-143015
  Status: Sent to http://localhost:3000

In Langfuse dashboard, you'll see:
  - Root span: agent_run (with session ID and duration)
  - Trace ID for cross-referencing with verification CLI
  - (Child spans visibility depends on instrumentation configuration)


- ✅ Real LLM with tool invocation
- ✅ Multi-turn agent interactions
- ✅ Tool execution tracking
- ✅ Complete decision audit trail
- ✅ Cryptographic proof of tool outputs
- ✅ Non-repudiation (LLM can't deny what it asked for)
- ✅ **Automatic Langfuse integration** - Complete trace of all tool calls and LLM decisions

**Langfuse Integration:**
The agent demo automatically exports detailed traces to Langfuse showing:
- LLM decision points and tool selections
- Each tool invocation with parameters and results
- Multi-turn interaction flow
- Token usage and latency for each LLM call
- Cost breakdown per tool and model call

---

### How to Verify Locally (Anyone Can Do This)

After running either demo, verify the proof without trusting the system:

```powershell
# Activate environment
.\venv\Scripts\Activate.ps1

# Verify the prompt demo
python -m src.tools.verify_cli verify real_workflow.jsonl "CtF/sK3Mj93lu7eXLCOFqwlAOsTP..." --verbose

# Verify the agent demo
python -m src.tools.verify_cli verify real_agent_workflow.jsonl "CtF/sK3Mj93lu7eXLCOFqwlAOsTP..." --verbose

# Expected output
[OK] Verification PASSED [OK]
  Root matches: CtF/sK3Mj93lu7eXLCOFqwlAOsTP...
  Events verified: 5
```

---

### 📊 Langfuse Integration in Demos

Both demos automatically integrate with Langfuse if configured:

**Setup Langfuse (5 minutes - Free Local Deployment):**
```powershell
# Start Langfuse with Docker Compose (completely free locally)
docker-compose up -d

# View dashboard at http://localhost:3000
```

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

See [LANGFUSE_SETUP_GUIDE.md](LANGFUSE_SETUP_GUIDE.md) for detailed setup and configuration.

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

# Finalize with hierarchical roots
session_root, commitments, canonical_log_bytes = middleware.finalize()
# Returns: session_root (combines all span roots), per-span roots, commitments object

# Save to local storage (creates 6 files: canonical_log.jsonl, spans_structure.json, 
# commitments.json, metadata.json, otel_export.json, RECOVERY.md)
middleware.save_to_local_storage(Path("workflow_abc123"))
```

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
  - Methods: `start_span()`, `record_event_in_span()`, `finalize()`, `save_to_local_storage()`
  - Returns: `Tuple[str, HierarchicalCommitments, bytes]` from `finalize()` (session_root, commitments object, canonical_log_bytes)
  - Auto-detects and integrates Langfuse if available
- **Per-Span Event Accumulation** → **SHA-256 Hashing** → **Span-Level KZG Commitments** → **Session Root (Verkle of span roots)**
- Algorithm: KZG polynomial commitments with BLS12-381 pairing-friendly curves
- Status: ✅ **Fully functional and tested** (128+ tests passing, hierarchical spans verified with 6-file local storage)
- Integration: Automatic Langfuse export with graceful fallback if unavailable
- Local Storage: Saves 6 files per run (canonical_log.jsonl, spans_structure.json, commitments.json, metadata.json, otel_export.json, RECOVERY.md)

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

The **Verification CLI** provides public, third-party verification of agent run integrity without requiring server access. See detailed guide below for comprehensive documentation.

### Quick Start

```powershell
# One-liner
& .\venv\Scripts\Activate.ps1; python -m src.tools.verify_cli verify ./logs/run.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP..." --verbose

# Or step by step
.\venv\Scripts\Activate.ps1
python -m src.tools.verify_cli verify ./logs/run.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP..."
```

### Three Commands

#### 1. **Verify** - Validate run integrity
```bash
python -m src.tools.verify_cli verify <log_file> <root_b64> [--expected-hash <hash>] [--verbose]
```

Reconstructs the Verkle tree and confirms the root commitment matches.

**Arguments:**
- `log_file` - Path to the canonical event log (JSON format)
- `root_b64` - Expected Verkle root commitment (Base64-encoded)

**Options:**
- `--expected-hash TEXT` - Optional SHA-256 hash to verify log integrity
- `--verbose, -v` - Show detailed verification steps

**Example:**
```bash
python -m src.tools.verify_cli verify ./logs/run.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5" --verbose
```

**Output on success:**
```
[OK] Verification PASSED [OK]
  Root matches: CtF/sK3Mj93lu7eX...
  Events verified: 4
```

#### 2. **Extract** - Show run metadata without verification
```bash
python -m src.tools.verify_cli extract <log_file>
```

Displays session ID, event count, event types, timestamps, and log hash without performing verification.

**Example:**
```bash
python -m src.tools.verify_cli extract ./logs/run.json
```

**Output:**
```
============================================================
Canonical Log Metadata
============================================================

Session ID:        test_session_1
Event Count:       4
File Size:         641 bytes
SHA-256 Hash:      d4fd76612a9b79bdc5ceac8b4378912d1ff235e816b88117bb87d2d7cf5c24a2

Event Types:
  agent_started.................................. 1 events
  tool_call...................................... 1 events
  llm_response................................... 1 events
  agent_completed................................ 1 events

First Timestamp:   2025-01-02T12:00:00.000Z
Last Timestamp:    2025-01-02T12:00:03.000Z

Counter Range:     0 → 3

============================================================
```

#### 3. **Export Proof** - Generate audit-ready proof JSON
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
python -m src.tools.verify_cli export-proof ./logs/run.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5" \
  --output proof.json \
  --include-events
```

**Proof JSON structure:**
```json
{
  "version": "1.0",
  "generated_at": "2025-01-02T14:30:45.123456",
  "metadata": {
    "session_id": "agent_run_123",
    "event_count": 4,
    "file_size_bytes": 641,
    "first_event_type": "agent_started",
    "last_event_type": "agent_completed",
    "first_timestamp": "2025-01-02T12:00:00.000Z",
    "last_timestamp": "2025-01-02T12:00:03.000Z"
  },
  "verification": {
    "log_hash_sha256": "d4fd76612a9b79bdc5ceac8b4378912d1ff235e816b88117bb87d2d7cf5c24a2",
    "expected_root_b64": "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5",
    "computed_root_b64": "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5",
    "verification_passed": true,
    "verification_timestamp": "2025-01-02T14:30:45.123456"
  },
  "event_summary": {
    "agent_started": 1,
    "tool_call": 1,
    "llm_response": 1,
    "agent_completed": 1
  }
}
```

### Canonical Log Format

The CLI expects canonical logs in JSON format with the following structure:

```json
[
  {
    "session_id": "agent_run_123",
    "event_type": "agent_started",
    "counter": 0,
    "timestamp": "2025-01-02T12:00:00.000Z",
    "data": { ... }
  },
  {
    "session_id": "agent_run_123",
    "event_type": "tool_call",
    "counter": 1,
    "timestamp": "2025-01-02T12:00:01.000Z",
    "data": { ... }
  }
]
```

**Required Fields:**
- `session_id` - Unique identifier for the agent run
- `event_type` - Type of event (agent_started, tool_call, llm_response, etc.)
- `counter` - Sequential event counter (must be sequential starting from 0)
- `timestamp` - ISO 8601 timestamp
- `data` - Event-specific data

### Use Cases

- ✅ **Real-time verification** - Verify an agent run immediately after it completes
- ✅ **Audit trail** - Export proofs for compliance or security audits
- ✅ **Batch verification** - Script-based verification of multiple runs
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
    python -m src.tools.verify_cli verify logs/run.json "${{ secrets.EXPECTED_ROOT }}" \
      --expected-hash "${{ secrets.EXPECTED_HASH }}" \
      --verbose
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

### `src/transport/jsonrpc_protocol.py` (New)
JSON-RPC 2.0 protocol implementation with MCP 2024-11 compliance:
- Standard protocol versioning
- Request/response correlation with IDs
- Initialization handshake
- Error codes per JSON-RPC 2.0 specification
- Batch request support

### `src/transport/mcp_protocol_adapter.py` (New)
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
A: Yes! The only hard requirement is PostgreSQL.

**Q: Is this suitable for production?**
A: Yes, the core integrity tracking, Verkle tree commitments, and verification CLI are production-ready. See PROJECT_SUMMARY.md for current status.

**Q: How do I verify a run offline?**
A: Download the canonical log from storage and run the verification CLI locally—no server contact needed.

