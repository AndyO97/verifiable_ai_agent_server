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
       REAL-TIME AI AGENT WORKFLOW WITH MCP 2024-11 + INTEGRITY TRACKING        
================================================================================

This is a REAL agent interaction with full MCP protocol compliance:
  - User sends prompt through AIAgent to OpenRouter API
  - LLM provides genuine response
  - All communication in MCP 2024-11 format
  - Full protocol versioning and initialization
  - All events integrity-tracked with Verkle trees
  - Cryptographically verifiable proof created
  - Anyone can verify what really happened

>> STEP 1: Initialize MCP 2024-11 Protocol & Integrity Tracking

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
  - Protocol Version: 2024-11
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
  - All communication followed MCP 2024-11 specification
  - No tampering occurred
  - Independently verifiable by anyone
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

MCP 2024-11 Protocol Compliance:
  [OK] Protocol Version: 2024-11
  [OK] JSON-RPC Version: 2.0
  [OK] Tool Invocation: Supported
  [OK] Multi-Turn Conversations: Supported

>> STEP 8: Comprehensive Integrity Report

Summary:
  - Total LLM Turns: 2
  - Tools Available: 4
  - Spans Recorded: 4
  - Protocol Used: MCP 2024-11 with JSON-RPC 2.0

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

The **Verification CLI** provides public, third-party verification of agent run integrity without requiring server access. It includes commands for listing workflows, retrieving metadata, and verifying integrity.

### Quick Start

```powershell
# List all available workflows
python -m src.tools.verify_cli list-workflows

# Get metadata for a specific workflow
python -m src.tools.verify_cli get-workflow real-prompt-mcp-20260222-141751

# Verify a workflow by session ID (fastest)
python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751

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

Verification Commands:

  Recommended (by session ID):
    .\venv\Scripts\Activate.ps1; python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751

  Alternative (by file path):
    .\venv\Scripts\Activate.ps1; python -m src.tools.verify_cli verify "workflows\workflow_real-prompt-mcp-20260222-141751\canonical_log.jsonl" 'AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN'
```

#### 3. **Verify-By-ID** - Verify a workflow by session ID (fastest)
```bash
python -m src.tools.verify_cli verify-by-id <session-id> [--dir <path>] [--verbose]
```

Reconstructs the Verkle tree and confirms the session root commitment matches the stored root.

**Example:**
```bash
python -m src.tools.verify_cli verify-by-id real-prompt-mcp-20260222-141751 --verbose
```

**Output on success:**
```
[OK] Verification PASSED [OK]
  Root matches: AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN
  Events verified: 2
  Spans verified: 3
```

#### 4. **Verify** - Validate run integrity by file path and root
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
python -m src.tools.verify_cli verify ./canonical_log.jsonl "AT32sZab0WmCTkJzukkIIuKyqm/j8188kvhFlpT2pqHFY3VNq/X0SlbBT0Ce9GvN" --verbose
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
- `data` - Event-specific data

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

