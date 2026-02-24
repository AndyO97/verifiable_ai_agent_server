#!/usr/bin/env python3
"""Debug script to understand session root reconstruction"""
import json
import base64
from src.crypto.verkle import VerkleAccumulator

session_id = "real-prompt-mcp-20260224-163503"
workflow_dir = f"workflows/workflow_{session_id}"

# Load the commitments
with open(f"{workflow_dir}/commitments.json") as f:
    commitments = json.load(f)

session_root = commitments["session_root"]
span_roots = commitments["span_roots"]

print(f"Session Root (expected): {session_root}\n")
print(f"Span Roots:")
for span_id, root in span_roots.items():
    print(f"  {span_id}: {root[:30]}...")

# Load canonical log to get span names
with open(f"{workflow_dir}/canonical_log.json") as f:
    canonical_log = json.load(f)

span_names = {}
for event in canonical_log:
    span_id = event.get("span_id")
    span_name = event.get("span_name")
    if span_id and span_name and span_id not in span_names:
        span_names[span_id] = span_name

print(f"\nSpan Names:")
for span_id, span_name in span_names.items():
    print(f"  {span_id}: {span_name}")

# Reconstruct exactly as done in _finalize_current_span during recording
print(f"\n--- Reconstructing Session Root ---\n")
session_accumulator = VerkleAccumulator(session_id)

session_counter = 0
for span_id in sorted(span_roots.keys()):
    span_root_b64 = span_roots[span_id]
    span_root = base64.b64decode(span_root_b64)
    span_name = span_names.get(span_id, span_id)
    
    # This is what goes into session_accumulator
    span_event = {
        "session_id": session_id,
        "counter": session_counter,
        "event_type": "span_commitment",
        "span_id": span_id,
        "span_name": span_name,
        "span_root": span_root_b64,
        "event_count": 1,
    }
    
    print(f"Adding span_commitment (counter={session_counter}):")
    print(f"  {span_event}")
    print()
    
    session_accumulator.add_event(span_event)
    session_counter += 1

computed_root = session_accumulator.finalize()
computed_root_b64 = base64.b64encode(computed_root).decode()

print(f"Computed Root: {computed_root_b64}")
print(f"Expected Root: {session_root}")
print(f"Match: {computed_root_b64 == session_root}")
