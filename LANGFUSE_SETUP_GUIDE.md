# Langfuse Self-Hosted Setup Guide

## Overview

Langfuse is an open-source LLM observability platform providing:
- **Trace Collection**: Capture all agent interactions (LLM calls, tool invocations, verifications)
- **Cost Tracking**: Monitor LLM API costs across sessions
- **Visualization Dashboard**: Interactive UI to explore traces and analytics
- **OTLP Integration**: Direct OpenTelemetry span export

This guide covers self-hosted deployment using Docker Compose.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- 2GB free disk space
- 1GB available RAM

### 1. Start Langfuse

```bash
# Navigate to project root
cd /path/to/verifiable_ai_agent_server

# Start Langfuse services (postgres + langfuse server)
docker-compose up -d

# View logs
docker-compose logs -f langfuse_server

# Expected: "✓ Langfuse is running at http://localhost:3000"
```

### 2. Access Dashboard

```
URL: http://localhost:3000
Email: admin@example.com (default)
Password: password (default)
```

### 3. Verify Deployment

```bash
# Check services status
docker-compose ps

# Expected output:
# NAME              STATUS
# langfuse_db       Up (healthy)
# langfuse_server   Up (healthy)

# Test OTLP receiver
curl http://localhost:4317/health
```

---

## Configuration

### Environment Variables

Create or update your `.env` file:

```bash
# Langfuse
LANGFUSE_API_ENDPOINT=http://localhost:3000
LANGFUSE_ADMIN_EMAIL=admin@example.com
LANGFUSE_ADMIN_PASSWORD=your_secure_password

# PostgreSQL (shared with Langfuse)
POSTGRES_PASSWORD=your_secure_password
POSTGRES_USER=langfuse

# OpenTelemetry
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_SERVICE_NAME=verifiable-ai-agent

# Auth (change in production)
NEXTAUTH_SECRET=your_unique_secret_key_here
```

### Production Configuration

For production deployment:

1. **Change Default Credentials**
   ```bash
   # In docker-compose.yml or .env
   LANGFUSE_ADMIN_EMAIL=your_email@company.com
   LANGFUSE_ADMIN_PASSWORD=<generate_strong_password>
   NEXTAUTH_SECRET=<generate_random_secret>
   ```

2. **Enable HTTPS**
   ```yaml
   # docker-compose.yml - Update langfuse_server
   environment:
     NEXTAUTH_URL: https://langfuse.example.com  # Use actual domain
   ```

3. **Configure PostgreSQL Backup**
   ```bash
   # Add to docker-compose.yml volumes
   volumes:
     - /backup/langfuse:/backup  # External backup path
   ```

4. **Update OTLP Endpoint**
   ```bash
   # For remote agents
   OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse.example.com:4317
   ```

---

## Integration with Agent

### 1. Initialize Langfuse Client

```python
from src.observability.langfuse_client import create_langfuse_client

# In your agent initialization
langfuse = create_langfuse_client(session_id="my-session-001")

# Create trace for this run
trace_id = langfuse.create_trace(
    name="agent_run",
    metadata={
        "session_id": "my-session-001",
        "counter": 0,
        "timestamp": "2025-12-22T10:30:00Z"
    }
)
```

### 2. Record LLM Calls

```python
# After LLM API call
langfuse.record_llm_call(
    trace_id=trace_id,
    model="mistral-7b",
    prompt="What is 2 + 2?",
    response="2 + 2 = 4",
    input_tokens=15,
    output_tokens=8,
    cost=0.00015  # Cost in USD
)
```

### 3. Record Tool Invocations

```python
# After tool execution
langfuse.record_tool_call(
    trace_id=trace_id,
    tool_name="calculator",
    input_data={"operation": "add", "a": 2, "b": 2},
    output_data={"result": 4},
    duration_ms=45.2,
    success=True
)
```

### 4. Record Integrity Checks

```python
# After verification
langfuse.record_integrity_check(
    trace_id=trace_id,
    counter=5,
    commitment="A18sig5Q+rV8sf3y8/nnWKPgFfCZPFZLsRcW062Sii0=",
    events_count=6,
    verified=True
)
```

### 5. Finalize and Export

```python
# Complete trace
langfuse.finalize_trace(trace_id)

# Get session summary
summary = langfuse.get_session_summary()
print(f"Session {summary['session_id']} completed:")
print(f"  Traces: {summary['total_traces']}")
print(f"  Total Cost: ${summary['total_cost']:.4f}")
```

---

## Monitoring & Maintenance

### Check Service Health

```bash
# Verify all services
docker-compose ps

# View service logs
docker-compose logs langfuse_server --tail=50
docker-compose logs postgres --tail=50

# Test API health
curl http://localhost:3000/api/public/health
```

### Database Management

```bash
# Connect to Langfuse database
docker-compose exec postgres psql -U langfuse -d langfuse

# List traces (SQL)
SELECT trace_id, name, created_at FROM traces LIMIT 10;

# View total cost tracked
SELECT SUM(cost) FROM traces WHERE created_at > now() - interval '24 hours';
```

### Backup Database

```bash
# Create backup
docker-compose exec postgres pg_dump -U langfuse langfuse > backup.sql

# Restore from backup
cat backup.sql | docker-compose exec -T postgres psql -U langfuse langfuse
```

### Stop & Cleanup

```bash
# Stop services (data preserved)
docker-compose stop

# Start again
docker-compose start

# Remove everything (warning: deletes data!)
docker-compose down -v
```

---

## Debugging

### Common Issues

**Port Already in Use**
```bash
# Change port in docker-compose.yml
# 3000:3000 -> 3001:3000 (use 3001 instead)

docker-compose down
docker-compose up -d
```

**Database Connection Error**
```bash
# Verify postgres is healthy
docker-compose logs postgres

# Wait for postgres to be ready
docker-compose exec postgres pg_isready -U langfuse
```

**OTLP Not Receiving Spans**
```bash
# Check OTLP endpoint is accessible
curl http://localhost:4317/health

# Verify client configuration
# Should have: OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### View Detailed Logs

```bash
# Real-time logs with timestamps
docker-compose logs -f --timestamps

# Show specific service
docker-compose logs -f langfuse_server

# View last 100 lines
docker-compose logs --tail=100
```

---

## Cost Tracking Reference

### Supported Models

The client automatically tracks costs for common models:

| Model | Cost/1K Input | Cost/1K Output |
|-------|---------------|----------------|
| Mistral 7B | $0.00015 | $0.0005 |
| GPT-3.5 | $0.0005 | $0.0015 |
| GPT-4 | $0.03 | $0.06 |
| Claude 3 | $0.003 | $0.015 |

See `langfuse_client.py` for exact cost calculation.

---

## Architecture

```
Agent Application
    ↓
LangfuseClient (src/observability/langfuse_client.py)
    ↓
    ├─→ Traces (events, costs, metadata)
    └─→ OTLP Export (if configured)
           ↓
    Langfuse Server (localhost:3000)
           ↓
    PostgreSQL Database (localhost:5433)
```

### Data Flow

1. **Agent Initialization**: Create Langfuse client with session_id
2. **Event Recording**: LLM calls, tool invocations, integrity checks
3. **Trace Aggregation**: Group events into traces
4. **Finalization**: Mark trace complete with cost totals
5. **Visualization**: View traces in dashboard

---

## OpenTelemetry Integration

Langfuse also receives spans from OpenTelemetry:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("agent_step") as span:
    span.set_attribute("session_id", "my-session")
    span.set_attribute("counter", 0)
    # ... agent logic ...
```

Spans are automatically exported to Langfuse via OTLP protocol.

---

## Next Steps

1. ✅ Docker Compose deployment ready
2. ✅ Langfuse client module ready
3. ⏳ **Task 5**: Wire OTel spans throughout execution flow
4. ⏳ **Task 6**: Create latency benchmarks
5. ⏳ **Task 7**: Update verification CLI

See `PROJECT_SUMMARY.md` for Phase 3 roadmap.
