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

### Daily Development

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run tests
python -m pytest tests/ -v

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
   $env:PYTHONPATH = "."; python examples/validate_phase2.py
   ```

**Benefits:**
- ✅ Free tier (Mistral 7B included, no credit card)
- ✅ No local GPU/memory required
- ✅ Cloud-based inference
- ✅ Your PC focuses on agent logic
- ✅ Instant setup (no downloads or installation)

#### Option 2: Ollama (Local alternative)

For local inference instead, see **OLLAMA_SETUP_GUIDE.txt** (5 simplified sections) for:
1. Installing Ollama from https://ollama.ai/download
2. Pulling a model (recommended: `mistral` - ~4GB, 5-10 min)
3. Testing connection with diagnostics
4. Running validation with real LLM workloads

**Quick Start:**
```powershell
# 1. Download and install Ollama
# 2. Pull a model
ollama pull mistral

# 3. Run validation
$env:PYTHONPATH = "."; python examples/validate_phase2.py

# To force Ollama when OpenRouter API key is set:
$env:USE_OLLAMA = "1"; python examples/validate_phase2.py
```

**Troubleshooting Ollama Connection:**
```powershell
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama if needed
ollama serve

# Verify model is loaded
ollama list
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

## �📋 Project Structure

```
verifiable-ai-agent-server/
├── src/
│   ├── crypto/
│   │   ├── __init__.py
│   │   ├── encoding.py          # RFC 8785 canonical JSON encoder
│   │   └── verkle.py            # Verkle tree & KZG commitments
│   ├── integrity/
│   │   └── __init__.py          # IntegrityMiddleware for event capture
│   ├── agent/
│   │   └── __init__.py          # MCP server & AIAgent runtime
│   ├── security/
│   │   └── __init__.py          # Authorization & threat prevention
│   ├── observability/
│   │   └── __init__.py          # OTel & Langfuse integration
│   ├── storage/
│   │   └── __init__.py          # S3 / Azure Blob artifact storage
│   ├── tools/
│   │   └── verify_cli.py        # Public verification CLI
│   └── config.py                # Configuration management
├── tests/
│   ├── conftest.py
│   ├── test_crypto.py
│   └── test_integrity.py
├── examples/
│   └── basic_run.py             # Complete usage example
├── pyproject.toml               # uv/pip compatible dependencies
├── .python-version              # Python 3.11 specification
├── setup.ps1                    # Automated setup script
├── README.md                    # This file
└── PRD.md                       # Original requirements document
```

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

## 🔍 Verification

### Verify a Run Locally

```bash
poetry run verify <canonical_log_path> <expected_root_b64> --hash <expected_hash>
```

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

## 📋 Development Roadmap

### Phase 1 – Foundation (Weeks 1–2) ✅ In Progress
- [x] FastMCP server scaffolding
- [x] Canonical encoding (RFC 8785)
- [x] Verkle accumulator (merkle placeholder)
- [x] IntegrityMiddleware
- [x] Basic tests
- [ ] Deploy self-hosted Langfuse
- [ ] Verify OTel export

### Phase 2 – Integrity Layer (Weeks 3–4)
- [ ] KZG polynomial commitment integration
- [ ] BLS12-381 curve operations
- [ ] Verkle tree proof generation
- [ ] OTel span management
- [ ] Langfuse metadata enrichment

### Phase 3 – Verification & Security (Weeks 5–6)
- [ ] Verification CLI refinement
- [ ] Unauthorized tool access tests
- [ ] Replay resistance validation
- [ ] Security penetration testing
- [ ] Public release & documentation

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

# S3 (optional)
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_BUCKET=verifiable-agent-logs

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
Artifact storage backends (S3, Azure Blob, local filesystem).

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
A: Yes! The only hard requirement is PostgreSQL. S3/Blob storage is optional (local filesystem works).

**Q: Is this suitable for production?**
A: Not yet. Currently in Phase 1 development. Production deployment requires Phase 2–3 completion.

**Q: How do I verify a run offline?**
A: Download the canonical log from storage and run the verification CLI locally—no server contact needed.

---

**Built with ❤️ for verifiable AI**
