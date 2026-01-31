#!/usr/bin/env python3
"""Quick test to verify Langfuse integration works end-to-end."""

import sys
import time
from src.observability.langfuse_client import LangfuseClient

# Initialize Langfuse (credentials loaded from .env)
langfuse_client = LangfuseClient(session_id="test-integration")

# Create a trace
trace_id = langfuse_client.create_trace(
    name="test_integration",
    user_id="test-user",
    metadata={"test": True, "integration": "langfuse"}
)

# Add some events
langfuse_client.add_event_to_trace(
    trace_id,
    "event_1",
    {"data": "test event 1", "level": "info"},
    level="info"
)

time.sleep(0.1)

langfuse_client.add_event_to_trace(
    trace_id,
    "event_2",
    {"data": "test event 2"},
    level="info"
)

# Finalize the trace (this sends to Langfuse)
langfuse_client.finalize_trace(trace_id)

print("\n✅ Test complete! Check Langfuse UI at http://localhost:3000")
print(f"   Trace ID: {trace_id}")
print(f"   Session: {langfuse_client.session_id}")
