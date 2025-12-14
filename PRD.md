# 📄 **Product Requirements Document (PRD v4): Verifiable AI Agent Server**

## 1. Goal

To build a **high-integrity, self-hosted AI Agent Server** based on the Model Context Protocol (MCP), ensuring immutability, deterministic verifiability, and replay-resistance for all agent–LLM–tool interactions. All run logs must be cryptographically committed into a **Verkle Tree** using deterministic canonical serialization and a single Verkle root per run.

---

## 2. Success Metrics

* **Integrity:** 100% of agent interactions (prompts, LLM responses, tool invocations, tool results) successfully committed into the Verifiable Verkle Tree with a deterministic Verkle root recorded.
* **Replay-Resistance:** Each committed event includes a **server timestamp**, **run-scoped monotonic counter**, and **session ID**, preventing replay or re-ordering.
* **Performance & Latency:** Cryptographic operations (encoding, hashing, tree accumulation) must add minimal overhead to agent response time:
  - Integrity middleware overhead: <50ms per event
  - Verkle root computation: <100ms per finalization
  - No noticeable latency increase perceived by end users
  - Tool execution time should not be significantly impacted by integrity tracking
* **Observability:** 99.9% of spans successfully exported to Langfuse and viewable in the UI.
* **Security:** Penetration testing confirms no prompt-based unauthorized tool invocation.

---

## 3. Architecture & Technology Stack

| Component               | Technology                                                       | Role                                             |
| ----------------------- | ---------------------------------------------------------------- | ------------------------------------------------ |
| MCP Agent Framework     | FastMCP                                                          | Core agent runtime, message routing, tool schema |
| Programming Language    | Python 3.11+                                                     | Implementation language                          |
| Log Integrity Structure | Custom Verkle Tree using KZG polynomial commitments on BLS12-381 | Full-run integrity commitment                    |
| Observability Layer     | Langfuse (Self-hosted)                                           | Trace, latency, and cost visualization           |
| Telemetry Transport     | OpenTelemetry (OTel) SDK                                         | Distributed tracing                              |
| Databases               | PostgreSQL / ClickHouse                                          | Langfuse OLTP/OLAP backend                       |
| Caching / Queue         | Redis / Valkey                                                   | Langfuse async queue/worker optimization         |

**Verkle Cryptographic Implementation Note:**
The Verkle tree will utilize **KZG polynomial commitments over BLS12-381**, implemented using PyECC or Arkworks bindings (via FFI if required).

---

## 4. Feature Requirements

### 4.1 Core Agent Functionality

| ID   | Requirement               | Detail                                                     |
| ---- | ------------------------- | ---------------------------------------------------------- |
| FR-1 | MCP Server Implementation | Use FastMCP for HTTP/WebSocket message transport           |
| FR-2 | Tool Definition           | Strictly typed schema enforcement for all tools (Pydantic) |
| FR-3 | LLM Integration           | All model calls route through the Integrity Middleware     |

---

### 4.2 Log Integrity Layer — Verkle Trees

| ID       | Requirement              | Detail                                                                                                |
| -------- | ------------------------ | ----------------------------------------------------------------------------------------------------- |
| FR-4     | Integrity Middleware     | Capture each event: prompt, tool input/output, and **final** model output                             |
| FR-5     | Deterministic Encoding   | **RFC 8785 canonical JSON**, Unicode normalized (NFC), reject non-finite floats                       |
| FR-6     | Replay Resistance        | Each node includes `<session_id, monotonic_counter, server_timestamp>`                                |
| FR-6a    | Counter Persistence      | Monotonic counter stored in PostgreSQL; atomic increment; system refuses startup if rollback detected |
| FR-7     | Finalization Policy      | Verkle tree finalized exactly once per agent run                                                      |
| FR-7a    | Streaming Policy         | Only final LLM output is hashed/committed (no token/stream chunk logging)                             |
| **FR-8** | Verkle Root Logging      | Verkle root stored as **Base64-encoded string** on the root OTel span                                 |
| FR-9     | Raw Artifact Storage     | Canonical log stored in offline storage (S3 or Blob)                                                  |
| FR-10    | Integrity Hash           | SHA-256 of canonical log stored alongside root                                                        |
| FR-11    | Verification CLI         | CLI reconstructs tree and validates root vs logged commitment                                         |
| FR-11a   | Public Verification Tool | CLI must be released open-source, enabling third-party validation                                     |

---

### 4.3 Failure & Crash Handling

| ID    | Requirement             | Detail                                                                  |
| ----- | ----------------------- | ----------------------------------------------------------------------- |
| FR-12 | Partial Commit Capture  | If the run aborts, partial tree state and error cause must be committed |
| FR-13 | Canonical Partial State | Partial accumulator uses same canonical JSON format                     |
| FR-14 | Trace Marking           | Langfuse span must display status **incomplete**                        |

---

## 5. Observability (OTel / Langfuse)

| ID    | Requirement            | Detail                                                    |
| ----- | ---------------------- | --------------------------------------------------------- |
| FR-15 | Span Coverage          | Every MCP event generates a trace span                    |
| FR-16 | Export Target          | OTLP → Langfuse self-hosted endpoint                      |
| FR-17 | Cost & Latency Metrics | Track `llm.token_usage`, `llm.cost_usd`, `latency_ms`     |
| FR-18 | Root Visibility        | Verkle root appears as Base64 attribute on root span      |
| FR-19 | Integrity Attribution  | Every span includes session_id, counter, server_timestamp |

---

## 5.1 Performance & Latency Requirements

| ID    | Requirement              | Detail                                                                                           |
| ----- | ------------------------ | ------------------------------------------------------------------------------------------------ |
| FR-20 | Minimal Integrity Overhead | Integrity middleware adds <50ms per event (encoding, hashing, counter operations)                |
| FR-21 | Fast Tree Finalization    | Verkle root computation completes in <100ms, even for runs with 100+ events                     |
| FR-22 | Tool Execution Unimpacted  | Tool invocation latency not significantly increased by integrity tracking (<5% overhead)         |
| FR-23 | Latency Benchmarking      | All phases include latency benchmarks measuring tool call roundtrip time                         |
| FR-24 | Database Counter Speed    | PostgreSQL counter increments (<5ms) do not become bottleneck for high-frequency tool calls      |
| FR-25 | Negligible User Impact    | End-to-end agent response time increase should be imperceptible (<10% impact to LLM latency)    |

---

## 6. Security Requirements

### 6.1 Agent Controls

* Replay and tamper resistance guaranteed via canonical encoding + counters.

* Unauthorized tool invocation:

  * Block the action
  * Log span as `security_event`
  * Return neutral failure response (`"Action blocked: unauthorized tool access."`)
  * Do not expose tool capability map to model

* Tool isolation: adhere to least-privilege MCP principles.

* Schema enforcement for every input and output.

### 6.2 Python / Infra Security

* Dependency locking using Poetry or UV
* Required linting and typing: Ruff + Mypy
* Secrets via environment variables (`pydantic-settings`)
* TLS/SSL enforced for DB & Langfuse connections
* Disk encryption for PostgreSQL and ClickHouse

---

## 7. Definition: Agent Run Context

```
Agent Run =
  Initial User Prompt →
  (zero or more tool interactions) →
  Final LLM Completion →
  Verkle Finalization Event
```

* One and only **one Verkle root** per run
* No per-chunk or per-message roots

---

## 8. Deterministic Event Specification

```
{
  "session_id": <uuidv4>,
  "counter": <uint64 monotonic, persisted>,
  "timestamp": <ISO8601 UTC, server-generated>,
  "event_type": <prompt|model_output|tool_input|tool_output>,
  "payload": <canonical JSON>
}
```

**Timestamp Source Requirement:**
`timestamp` must be derived exclusively from the **trusted host OS clock synchronized via NTP**. Local time tampering must be administratively prevented.

**Canonicalization Requirements:**

* RFC 8785 canonical JSON
* Unicode normalization: NFC
* Reject: NaN, Infinity, -Infinity
* No Python dynamic object dumps

---

## 9. Development & Testing Schedule

### Phase 1 – Foundation (Weeks 1–2)

* FastMCP server + tool scaffolding
* Deploy self-hosted Langfuse
* Verify basic OTel telemetry export
* Establish baseline latency metrics (no integrity overhead)

### Phase 2 – Integrity Layer (Weeks 3–4)

* Canonical encoder implementation
* Verkle accumulator integration
* Verkle root committed to root span
* Benchmark integrity middleware latency (<50ms per event)
* Measure tool execution overhead from integrity tracking
* Validate end-to-end latency impact (<10% increase)

### Phase 3 – Verification & Security (Weeks 5–6)

* Public verification CLI release
* Unauthorized tool access fail-stop tests
* Replay resistance validation
* Performance regression testing across all phases
* Optimize hot paths if latency exceeds targets

### Phase 4 – Cloud Storage & Production Hardening (Future / Post-Phase 3)

**Note:** The following features are lower priority and will be implemented after Phase 3 is complete:

* S3 backend integration (currently using LocalFileStore)
* Azure Blob Storage backend integration
* Production hardening (NTP synchronization, encryption at rest)
* Load testing and performance profiling
* Advanced security audits and penetration testing
* Latency optimization for high-volume event streams

**Rationale:** Phases 1–3 establish a working, verifiable prototype with local storage and fundamental integrity guarantees. Cloud storage and production hardening are valuable but not blocking for the core MVP. They will be prioritized after the prototype is validated and working end-to-end.

---

## 10. Verification Workflow

1. Download canonical log payload (S3/Blob)
2. Run public verification CLI
3. CLI recomputes Verkle root
4. Compare root against Base64 commitment stored in Langfuse + SHA-256 hash
5. Any mismatch indicates tampering or replay attempt

