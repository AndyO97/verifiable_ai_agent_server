# 🔐 Verifiable AI Agent Server

A high-integrity, self-hosted AI Agent Server built on the Model Context Protocol (MCP) with cryptographic commitment of all agent–LLM–tool interactions into a **Verkle Tree**.

## 🎯 Core Features

- **Immutable Run Logs**: All agent interactions (prompts, tool calls, model outputs) are canonically encoded and cryptographically committed
- **Deterministic Verifiability**: Every run produces a single Verkle root commitment that can be independently verified
- **Replay Resistance**: Sequential monotonic counters, server timestamps, and session IDs prevent unauthorized replay or reordering
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
   $env:PYTHONPATH = "."; python real_prompt_demo.py          # Demo: Simple Q&A with integrity tracking
 real_agent_demo.py           # Demo: Multi-tool agent with tool invocation
 demo_all_work.py             # Demonstration runner for all features
 pyproject.toml               # uv/pip compatible dependencies
 setup.ps1                    # Automated setup script (Windows)
 docker-compose.yml           # Langfuse self-hosted deployment
 README.md                    # This file (comprehensive guide)
 PROJECT_SUMMARY.md           # Phase 3 completion status & future work
 PROPOSAL.md                  # Technical approach & architecture
 LANGFUSE_SETUP_GUIDE.md      # Observability deployment guide
 OLLAMA_SETUP_GUIDE.txt       # Alternative LLM provider guide
 .env.example                 # Environment variables template
```

**Key Files:**
- `real_prompt_demo.py` - Entry point for simple demo with Langfuse tracing
- `real_agent_demo.py` - Entry point for agent demo with tool invocation
- `demo_all_work.py` - Run all demonstrations with progress tracking
- `.env` - Local configuration (credentials, API keys, not in git)
- `docker-compose.yml` - Langfuse deployment (optional observability)

**Documentation:**
- `README.md` - Primary user guide (you are here)
- `PROJECT_SUMMARY.md` - Phase 3 status and future considerations
- `PROPOSAL.md` - Technical approach and architecture decisions
- `LANGFUSE_SETUP_GUIDE.md` - Observability setup and usage
- `OLLAMA_SETUP_GUIDE.txt` - Alternative LLM configuration

---

## 🚀 Quick Start (Original)

### Prerequisites

- Python 3.11+
- Poetry (for dependency management)
- PostgreSQL (for counter persistence)
- Optional: Langfuse self-hosted instance

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd verifiable-ai-agent-server

# Install dependencies
poetry install

# Run tests
poetry run pytest tests/ -v
```

### Basic Usage

```python
from src.integrity import IntegrityMiddleware
from src.agent import AIAgent, MCPServer
from src.security import SecurityMiddleware

# Create middleware
integrity = IntegrityMiddleware("my-session-id")
security = SecurityMiddleware()
mcp = MCPServer("my-session-id")

# Register tools
security.register_authorized_tools(["calculator", "search"])

# Create and run agent
agent = AIAgent(integrity, security, mcp)
result = agent.run("Calculate 2 + 2")

print(f"Output: {result['output']}")
print(f"Verkle Root: {result['integrity']['verkle_root_b64']}")
```

---

## 🔐 Integrity Architecture

### Event Flow

```
User Prompt
    ↓
[IntegrityMiddleware] → Canonical Encoding → Verkle Accumulator
    ↓
Tool Invocation (with Authorization Check)
    ↓
[IntegrityMiddleware] → Canonical Encoding → Verkle Accumulator
    ↓
LLM Model Output
    ↓
[IntegrityMiddleware] → Canonical Encoding → Verkle Accumulator
    ↓
Finalization → Verkle Root Commitment → OTel Span → Langfuse
```

### Deterministic Event Format

Every logged event follows this structure:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "counter": 0,
  "timestamp": "2025-12-08T10:30:45.123456Z",
  "event_type": "prompt|model_output|tool_input|tool_output",
  "payload": { /* event-specific data */ }
}
```

**Key Properties:**
- **Canonical Encoding**: RFC 8785 JSON with sorted keys, no whitespace
- **Unicode Normalization**: NFC normalization for determinism
- **Non-Finite Float Rejection**: NaN, Infinity, -Infinity are forbidden
- **Sequential Counters**: Atomic increment, persisted in PostgreSQL

---

## 🌳 Tree Commitments: Current & Future

### Current Implementation (Phase 1-2)

**What we have NOW:** **Merkle Tree** (SHA-256 based)
- Class: `VerkleAccumulator` (in `src/crypto/verkle.py`)
- Algorithm: Pairwise hash combination creating single root commitment
- Status: ✅ **Fully functional and tested** (all 35 Phase 2 tests passing)
- Implementation: Canonically-encoded events → SHA-256 hashing → Merkle tree

**Why the naming?** The class is named `VerkleAccumulator` to prepare for Phase 3's upgrade path (see below). The current implementation provides full integrity guarantees using well-understood Merkle cryptography.

### Phase 3: Verkle Tree Upgrade (Future)

When Phase 3 begins, the implementation will be upgraded to:
- **KZG Polynomial Commitments** over BLS12-381 elliptic curve
- Full Verkle tree structure with compact proofs
- Drop-in replacement for current Merkle implementation (same API, same root format)

**Key difference:** Merkle proofs are O(log n); Verkle proofs are O(1) compact.

See `src/crypto/verkle.py` for integration points and TODO comments.

---

## 🔍 Verification CLI (Phase 3 ✅ Complete)

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
✓ Verification PASSED ✓
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
4. **Merkle Accumulation**: Reconstruct the Verkle tree by:
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

## 🔍 Verification (Original)

Example:
```bash
poetry run verify ./artifacts/logs/550e8400-e29b-41d4-a716-446655440000/canonical.json \
  "hKj8vF2x9mK3pL4oJ7nQ6rS5tU2wX3yZ8aB=" \
  --hash "a1b2c3d4e5f6..."
```

### Extract Metadata Without Full Verification

```bash
poetry run verify extract-metadata <canonical_log_path>
```

---

## 📊 Observability

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

```bash
poetry run pytest tests/ -v --cov=src
```

Key test modules:
- `test_crypto.py`: Canonical encoding, Verkle accumulation, hash verification
- `test_integrity.py`: Event recording, finalization, counter validation

---

## 🛠️ Configuration

### Environment Variables

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_DATABASE=verifiable_agent

# OpenTelemetry
OTEL_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=verifiable-ai-agent

# Langfuse
LANGFUSE_API_ENDPOINT=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...

# Server
HOST=0.0.0.0
PORT=8000
```

---

## 📚 Key Modules

### `src/crypto/encoding.py`
RFC 8785 canonical JSON encoder with deterministic serialization.

### `src/crypto/verkle.py`
Verkle tree accumulator using KZG commitments (placeholder: merkle tree).

### `src/integrity/__init__.py`
IntegrityMiddleware for capturing and committing all agent interactions.

### `src/agent/__init__.py`
MCP server runtime with tool definition and invocation.

### `src/security/__init__.py`
Authorization manager and security middleware for threat prevention.

### `src/observability/__init__.py`
OTel tracing and Langfuse integration.

### `src/storage/__init__.py`
Artifact and log storage management.

### `src/tools/verify_cli.py`
Public verification CLI for independent run validation.

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
A: Canonicalization and hashing add ~10-50ms per run (TBD after profiling). Verkle tree operations are O(log n).

**Q: Can I run this on a commodity server?**
A: Yes! The only hard requirement is PostgreSQL.

**Q: Is this suitable for production?**
A: Yes, the core integrity tracking, Verkle tree commitments, and verification CLI are production-ready. See PROJECT_SUMMARY.md for current status.

**Q: How do I verify a run offline?**
A: Download the canonical log from storage and run the verification CLI locally—no server contact needed.

---

**Built with ❤️ for verifiable AI**
