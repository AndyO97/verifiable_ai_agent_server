#!/usr/bin/env python
"""
Simple Langfuse Test: Create Session -> Trace -> Generation

This script tests the Langfuse API directly with hardcoded data.
Run: python test_langfuse_simple.py
"""

import os
import uuid
import requests
from datetime import datetime, timezone
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Langfuse configuration
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")

API_ENDPOINT = f"{LANGFUSE_HOST}/api/public/ingestion"

def send_batch(items: list[dict]) -> bool:
    """Send a batch of items to Langfuse."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        print("ERROR: Missing Langfuse credentials in .env")
        return False
    
    auth = HTTPBasicAuth(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
    
    try:
        response = requests.post(
            API_ENDPOINT,
            json={"batch": items},
            auth=auth,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        return response.status_code in (200, 201, 207)
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def main():
    print("=" * 60)
    print("Langfuse Simple Test: Session -> Trace -> Generation")
    print("=" * 60)
    
    # Generate IDs
    session_id = f"test-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    trace_id = str(uuid.uuid4())
    generation_id_1 = str(uuid.uuid4())
    generation_id_2 = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    print(f"\nSession ID: {session_id}")
    print(f"Trace ID: {trace_id}")
    print(f"Generation 1 ID: {generation_id_1}")
    print(f"Generation 2 ID: {generation_id_2}")
    print(f"Timestamp: {now}")
    print()
    
    # Step 1: Create Trace (with session_id to create/link session)
    print("Step 1: Creating Trace...")
    trace_item = {
        "type": "trace-create",
        "id": trace_id,
        "timestamp": now,
        "body": {
            "id": trace_id,
            "name": "test_interaction",
            "sessionId": session_id,  # This links to/creates the session
            "userId": "test-user",
            "input": "What is 2+2?",
            "metadata": {"test": True},
            "tags": ["test", "simple"],
        }
    }
    
    success = send_batch([trace_item])
    print(f"Trace created: {success}\n")
    
    if not success:
        print("Failed to create trace, stopping.")
        return
    
    # Step 2: Create Generation 1 (linked to trace)
    print("Step 2: Creating Generation 1...")
    generation_item_1 = {
        "type": "generation-create",
        "id": generation_id_1,
        "timestamp": now,
        "body": {
            "id": generation_id_1,
            "traceId": trace_id,  # Link to trace
            "type": "GENERATION",
            "name": "llm_call_turn_1",
            "model": "test-model",
            "modelParameters": {"temperature": 0.7},
            "input": "What is 2+2?",
            "output": "Let me calculate that for you. 2+2 equals 4.",
            "version": "1.0.0",
            "startTime": now,
            "endTime": now,
            "usageDetails": {
                "input": 10,
                "output": 15,
                "total": 25,
            },
            "costDetails": {
                "input": 0.0001,
                "output": 0.0002,
                "total": 0.0003,
            },
            "metadata": {"turn": 1, "test": True},
        }
    }
    
    success = send_batch([generation_item_1])
    print(f"Generation 1 created: {success}\n")
    
    # Step 3: Create Generation 2 (also linked to same trace)
    print("Step 3: Creating Generation 2...")
    generation_item_2 = {
        "type": "generation-create",
        "id": generation_id_2,
        "timestamp": now,
        "body": {
            "id": generation_id_2,
            "traceId": trace_id,  # Link to same trace
            "type": "GENERATION",
            "name": "llm_call_turn_2",
            "model": "test-model",
            "modelParameters": {"temperature": 0.7},
            "input": "Now what is 10 * 5?",
            "output": "10 multiplied by 5 equals 50.",
            "version": "1.0.0",
            "startTime": now,
            "endTime": now,
            "usageDetails": {
                "input": 8,
                "output": 10,
                "total": 18,
            },
            "costDetails": {
                "input": 0.00008,
                "output": 0.00015,
                "total": 0.00023,
            },
            "metadata": {"turn": 2, "test": True},
        }
    }
    
    success = send_batch([generation_item_2])
    print(f"Generation 2 created: {success}\n")
    
    # Step 4: Update trace with output
    print("Step 3: Updating Trace with output...")
    trace_update = {
        "type": "trace-create",  # Use trace-create for updates too
        "id": trace_id,
        "timestamp": now,
        "body": {
            "id": trace_id,
            "output": "Final answer: 10 * 5 = 50",
        }
    }
    
    success = send_batch([trace_update])
    print(f"Trace updated: {success}\n")
    
    print("=" * 60)
    print("Done! Check Langfuse at http://localhost:3000")
    print(f"Look for session: {session_id}")
    print(f"Trace should have 2 generations with aggregated costs")
    print("=" * 60)


if __name__ == "__main__":
    main()
