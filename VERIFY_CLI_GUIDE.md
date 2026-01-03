# Verification CLI Guide

The Verification CLI is a public-facing tool that enables third-party verification of AI agent run integrity without requiring the full server infrastructure.

## Overview

The CLI provides three main commands:

1. **`verify`** - Reconstruct and verify agent run integrity
2. **`extract`** - Display metadata from canonical logs
3. **`export-proof`** - Generate audit-ready verification proofs

## Installation

The CLI is automatically available when you install the project:

```bash
pip install -e .
```

Access it via:

```bash
# Method 1: Python module
python -m src.tools.verify_cli

# Method 2: Direct CLI entry point (after pip install -e .)
verify --help
```

## Commands

### 1. Verify Command

Reconstructs the Verkle tree from a canonical log and verifies it matches the expected commitment.

**Usage:**
```bash
python -m src.tools.verify_cli verify <log_file> <root_b64> [OPTIONS]
```

**Arguments:**
- `log_file` - Path to the canonical event log (JSON format)
- `root_b64` - Expected Verkle root commitment (Base64-encoded)

**Options:**
- `--expected-hash TEXT` - Optional SHA-256 hash to verify log integrity
- `--verbose, -v` - Show detailed verification steps
- `--help` - Show help message

**Examples:**

```bash
# Basic verification
python -m src.tools.verify_cli verify ./run_log.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5"

# Verification with hash validation
python -m src.tools.verify_cli verify ./run_log.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5" \
  --expected-hash "d4fd76612a9b79bdc5ceac8b4378912d1ff235e816b88117bb87d2d7cf5c24a2"

# Verbose verification with detailed output
python -m src.tools.verify_cli verify ./run_log.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5" --verbose
```

**Exit Codes:**
- `0` - Verification passed, commitment matches
- `1` - Verification failed, commitment mismatch or other error

**Output Example:**

```
✓ Loaded canonical log (641 bytes)
✓ Parsed 4 events from log
Verifying Verkle tree root...

✓ Verification PASSED ✓
  Root matches: CtF/sK3Mj93lu7eXLCOFqwlAOsTP...
  Events verified: 4
```

### 2. Extract Command

Displays metadata from a canonical log without performing verification.

**Usage:**
```bash
python -m src.tools.verify_cli extract <log_file>
```

**Arguments:**
- `log_file` - Path to the canonical event log (JSON format)

**Examples:**

```bash
python -m src.tools.verify_cli extract ./run_log.json
```

**Output Example:**

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
  agent_completed................................ 1 events
  llm_response................................... 1 events
  tool_call...................................... 1 events

First Timestamp:   2025-01-02T12:00:00.000Z
Last Timestamp:    2025-01-02T12:00:03.000Z

Counter Range:     0 → 3

============================================================
```

### 3. Export Proof Command

Generates a JSON proof document containing verification results and metadata for audit trails.

**Usage:**
```bash
python -m src.tools.verify_cli export-proof <log_file> <root_b64> [OPTIONS]
```

**Arguments:**
- `log_file` - Path to the canonical event log (JSON format)
- `root_b64` - Expected Verkle root commitment (Base64-encoded)

**Options:**
- `--output, -o PATH` - Output file path (default: `proof.json`)
- `--include-events` - Include event summary and sample events in proof
- `--include-log` - Include the entire canonical log (Base64-encoded) in proof
- `--help` - Show help message

**Examples:**

```bash
# Basic proof export
python -m src.tools.verify_cli export-proof ./run_log.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5" \
  --output proof.json

# Proof with event summary
python -m src.tools.verify_cli export-proof ./run_log.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5" \
  --output proof.json \
  --include-events

# Comprehensive proof with full log (for archival)
python -m src.tools.verify_cli export-proof ./run_log.json "CtF/sK3Mj93lu7eXLCOFqwlAOsTP2jBKgeX1d5+TcUTgImYOO6ysBh9qncC6m/q5" \
  --output proof.json \
  --include-events \
  --include-log
```

**Proof JSON Structure:**

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
  },
  "sample_events": [
    { "session_id": "...", "event_type": "agent_started", ... },
    { "session_id": "...", "event_type": "tool_call", ... },
    { "session_id": "...", "event_type": "agent_completed", ... }
  ]
}
```

## Use Cases

### 1. Real-Time Verification

Verify an agent run immediately after it completes:

```bash
python -m src.tools.verify_cli verify ./logs/session_abc123.json "$ROOT_COMMITMENT" --verbose
```

### 2. Audit Trail Generation

Create a verifiable proof for compliance or security audits:

```bash
python -m src.tools.verify_cli export-proof ./logs/session_abc123.json "$ROOT_COMMITMENT" \
  --output audits/proof_2025_01_02.json \
  --include-events
```

### 3. Batch Verification

Script-based verification of multiple runs:

```bash
for log_file in ./logs/*.json; do
    session_id=$(basename "$log_file" .json)
    root=$(grep -o '"root":"[^"]*' "$log_file" | cut -d'"' -f4)
    
    echo "Verifying $session_id..."
    python -m src.tools.verify_cli verify "$log_file" "$root" || {
        echo "VERIFICATION FAILED: $session_id"
        exit 1
    }
done
```

### 4. Public Transparency

Publish proofs to a public verification server:

```bash
python -m src.tools.verify_cli export-proof ./logs/session_abc123.json "$ROOT_COMMITMENT" \
  --output /tmp/proof.json \
  --include-log

# Upload to verification server
curl -X POST https://verification.example.com/proofs \
  -H "Content-Type: application/json" \
  -d @/tmp/proof.json
```

## Canonical Log Format

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
  },
  ...
]
```

**Required Fields:**
- `session_id` - Unique identifier for the agent run
- `event_type` - Type of event (agent_started, tool_call, llm_response, etc.)
- `counter` - Sequential event counter (must be sequential starting from 0)
- `timestamp` - ISO 8601 timestamp
- `data` - Event-specific data

## Verification Algorithm

The CLI performs the following verification steps:

1. **Load Log**: Read and parse the canonical JSON log
2. **Hash Verification** (optional): Verify SHA-256 hash if provided
3. **Event Parsing**: Extract events and verify sequential counters
4. **Merkle Accumulation**: Reconstruct the Verkle tree by:
   - Canonically encoding each event
   - Computing SHA-256 hash of each encoded event
   - Creating a KZG polynomial commitment over the event hashes
5. **Root Comparison**: Compare computed root with expected commitment
6. **Result**: Return success if roots match, failure otherwise

## Security Considerations

1. **Hash Validation**: Always provide `--expected-hash` when available to detect log tampering
2. **Root Source**: Ensure the expected root comes from a trusted source
3. **Network**: When exchanging roots/logs over network, use TLS/SSL
4. **Proof Storage**: Store exported proofs in secure, immutable storage
5. **Audit Logs**: Log all verification activities for compliance

## Error Handling

The CLI provides clear error messages for common issues:

```
✗ Error: Log file not found: ./nonexistent.json
✗ Error: Invalid JSON in log file: Expecting value: line 1 column 1
✗ Error: Invalid Base64 root: Incorrect padding
✗ Hash mismatch!
  Expected: d4fd76612a9b79bdc5ceac8b4378912d1ff235e816b88117bb87d2d7cf5c24a2
  Actual:   aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
✗ Verification FAILED
  Expected root: CtF/sK3Mj93lu7eXLCOFqwlAOsTP...
  Computed root: AAAAAAAAAAAAAAAAAAAAAAAAAAAA...
```

## Performance

- **Verification Time**: ~0.1-0.5 seconds per 100 events (depends on CPU)
- **Memory Usage**: ~10-20 MB for logs with 1000+ events
- **Proof Export**: <1 second for typical runs

## Integration with CI/CD

```yaml
# GitHub Actions example
- name: Verify Agent Run
  run: |
    python -m src.tools.verify_cli verify logs/run.json "${{ secrets.EXPECTED_ROOT }}" \
      --expected-hash "${{ secrets.EXPECTED_HASH }}" \
      --verbose
```

## Further Information

- See [PROJECT_SUMMARY.md](../PROJECT_SUMMARY.md) for overall project architecture
- See [test_verify_cli.py](../tests/test_verify_cli.py) for usage examples
- See [verkle.py](../src/crypto/verkle.py) for cryptographic implementation details
