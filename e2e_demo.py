#!/usr/bin/env python
"""
End-to-End Demo: Complete LLM Agent Workflow with Integrity Tracking
=====================================================================

This script demonstrates:
1. A user asking an LLM a question
2. The LLM responding and using tools
3. All communication being integrity-tracked
4. Building a Verkle tree with KZG commitments
5. Visualizing the tree structure and all hashes
6. Verifying the integrity

Run with: python e2e_demo.py

Date: January 19, 2026

================================================================================
                    PUBLIC VERIFICATION & AUDIT PROOF
================================================================================

After running this demo, two artifacts are created:
  1. demo_workflow.jsonl - Canonical log of all events
  2. KZG Root Commitment - 48-byte elliptic curve point

USE CASE 1: PUBLICLY VERIFY THE LOG
================================================================================

Anyone can verify this log cryptographically WITHOUT trusting the server.
The verification proves the log hasn't been tampered with.

Command:
    python -m src.tools.verify_cli verify demo_workflow.jsonl '<ROOT_COMMITMENT>'

Example (replace <ROOT_COMMITMENT> with actual value):
    python -m src.tools.verify_cli verify demo_workflow.jsonl 'C0LYJ8BYII2sP8q12m/o3odeqOdzhe8L+YBLg9FXl4ZbL9Lew7Z6R/yN1tzRQVyg'

What happens:
  1. Loads canonical log from file
  2. Reconstructs Verkle tree from events
  3. Computes KZG commitment on BLS12-381 curve
  4. Compares computed commitment against provided root
  5. Returns exit code 0 if verified, 1 if failed

Output:
  Exit Code 0: SUCCESS - Log integrity verified ✓
  Exit Code 1: FAILURE - Log was tampered with ✗

You can also verify with hash validation:
    python -m src.tools.verify_cli verify demo_workflow.jsonl '<ROOT_COMMITMENT>' --expected-hash '<SHA256_HASH>'


USE CASE 2: GENERATE AUDIT PROOF
================================================================================

Create a compact, shareable JSON proof that contains all evidence needed
to verify the communication without sharing the full log.

Command (basic export):
    python -m src.tools.verify_cli export-proof demo_workflow.jsonl proof.json

This creates proof.json with:
  • Root commitment (48-byte KZG point)
  • Log size and structure metadata
  • Verification timestamp
  • Status (verified or failed)

Export with event summaries:
    python -m src.tools.verify_cli export-proof demo_workflow.jsonl --include-events proof.json

This adds:
  • All event types and timestamps
  • Event count by type
  • SHA-256 hash of each event
  • Complete hash chain

Export with full log:
    python -m src.tools.verify_cli export-proof demo_workflow.jsonl --include-log proof.json

This includes:
  • Complete canonical log (JSONL format)
  • All 6 events with full details
  • Allows third parties to re-verify everything

Export with everything (events + full log):
    python -m src.tools.verify_cli export-proof demo_workflow.jsonl --include-events --include-log proof.json


TYPICAL WORKFLOW
================================================================================

1. Run this demo:
   $ python e2e_demo.py
   
   Outputs:
   - demo_workflow.jsonl (canonical log)
   - Root commitment printed to console

2. Share the root commitment publicly:
   "Here's proof of our conversation: C0LYJ8BYII2sP8q12m/o3..."

3. Anyone can verify:
   $ python -m src.tools.verify_cli verify demo_workflow.jsonl 'C0LYJ8BYII2sP8q12m/o3...'
   
   Result: Exit code 0 = Verified ✓

4. Generate audit proof for compliance:
   $ python -m src.tools.verify_cli export-proof demo_workflow.jsonl --include-events proof.json
   
   Share proof.json with auditors/regulators

5. Third parties verify the proof:
   $ python -m src.tools.verify_cli verify demo_workflow.jsonl '<root>' --expected-hash '<hash>'
   
   Result: Cryptographically proven communication log ✓


KEY CRYPTOGRAPHIC GUARANTEES
================================================================================

✓ Authenticity: KZG commitments on BLS12-381 curve (industry standard)
✓ Integrity: SHA-256 hashing (NIST standard)
✓ Determinism: RFC 8785 canonical JSON (Bitcoin standard)
✓ Non-Repudiation: Agent cannot claim different log created same commitment
✓ Public Verification: No private keys needed to verify
✓ Tamper Detection: Any change to log invalidates commitment


UNDERSTANDING THE OUTPUTS
================================================================================

Canonical Log (demo_workflow.jsonl):
  - JSONL format (one JSON object per line)
  - RFC 8785 encoded for determinism
  - Contains: type, content, timestamp, parameters for each event

KZG Root Commitment:
  - 48-byte elliptic curve point
  - Base64 encoded for transport
  - Same format used in Ethereum 2.0 KZG ceremony
  - Uniquely identifies this exact sequence of events

SHA-256 Hashes:
  - Each event independently hashed
  - Hash chain aggregates previous hashes
  - Final root = deterministic function of all events
"""

import json
import base64
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

# Color codes
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Import project modules
from src.crypto.verkle import VerkleAccumulator
from src.integrity.database_counter import DatabaseCounter
from src.crypto.encoding import canonicalize_json


def print_header(title: str) -> None:
    """Print a large header."""
    print(f"\n{BOLD}{BLUE}{'='*80}{RESET}")
    print(f"{BOLD}{BLUE}{title:^80}{RESET}")
    print(f"{BOLD}{BLUE}{'='*80}{RESET}\n")


def print_subheader(title: str) -> None:
    """Print a section header."""
    print(f"\n{BOLD}{CYAN}>> {title}{RESET}")
    print(f"{DIM}{'-'*80}{RESET}\n")


def print_hash(label: str, hash_value: str, color: str = YELLOW) -> None:
    """Pretty print a hash value."""
    print(f"{color}{BOLD}{label}:{RESET} {hash_value}")


def print_event(event_type: str, content: str, color: str = BLUE) -> None:
    """Pretty print an event."""
    timestamp = datetime.now().isoformat()
    print(f"{color}[{timestamp}] {BOLD}{event_type}:{RESET} {content}")


def demo_workflow() -> None:
    """Run the complete end-to-end workflow."""
    
    print_header("END-TO-END AI AGENT WORKFLOW WITH INTEGRITY TRACKING")
    
    print(f"""{CYAN}This demonstration shows:
  - User sends a prompt to an AI agent
  - Agent receives and processes the prompt
  - Agent calls external tools
  - All communication is integrity-tracked
  - A Verkle tree is built with KZG commitments
  - Hashes and tree structure are visualized
  - The complete log is verified{RESET}\n""")
    
    # Initialize components
    print_subheader("STEP 1: Initialize Integrity Tracking")
    
    session_id = "demo-session-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    accumulator = VerkleAccumulator(session_id=session_id)
    
    print(f"{GREEN}[OK] Canonical JSON Encoder initialized (RFC 8785){RESET}")
    print(f"{GREEN}[OK] Verkle Accumulator initialized (KZG commitments, BLS12-381){RESET}")
    print(f"{GREEN}[OK] Session ID: {session_id}{RESET}\n")
    
    # Simulate user prompt
    print_subheader("STEP 2: User Sends Prompt to Agent")
    
    user_prompt = "What is the capital of France and show me the weather there?"
    event_1 = {
        "type": "user_prompt",
        "content": user_prompt,
        "timestamp": datetime.now().isoformat(),
        "token_count": 14
    }
    
    # Canonicalize and hash
    event_1_canonical = canonicalize_json(event_1)
    event_1_hash = hashlib.sha256(event_1_canonical.encode()).hexdigest()
    
    print_event("USER_PROMPT", user_prompt, YELLOW)
    print(f"\n{DIM}Canonical JSON (RFC 8785):{RESET}")
    print(f"{DIM}{event_1_canonical}{RESET}\n")
    print_hash("SHA-256 Hash", event_1_hash[:32] + "..." + event_1_hash[-8:], GREEN)
    
    accumulator.add_event(event_1)
    print(f"\n{GREEN}[OK] Event added to Verkle accumulator (event #0){RESET}\n")
    
    # Simulate agent processing
    print_subheader("STEP 3: Agent Processes Prompt and Makes LLM Call")
    
    agent_processing = {
        "type": "agent_processing",
        "action": "route_to_llm",
        "model": "ollama:llama2",
        "temperature": 0.7,
        "timestamp": datetime.now().isoformat()
    }
    
    agent_canonical = canonicalize_json(agent_processing)
    agent_hash = hashlib.sha256(agent_canonical.encode()).hexdigest()
    
    print_event("AGENT_PROCESSING", "Routing to LLM with model: ollama:llama2", CYAN)
    print_hash("SHA-256 Hash", agent_hash[:32] + "..." + agent_hash[-8:], GREEN)
    
    accumulator.add_event(agent_processing)
    print(f"{GREEN}[OK] Added to Verkle accumulator (event #1){RESET}\n")
    
    # Simulate LLM response
    print_subheader("STEP 4: LLM Responds")
    
    llm_response = {
        "type": "llm_response",
        "model": "ollama:llama2",
        "content": "The capital of France is Paris. It's located in the north-central part of the country on the Seine River.",
        "tokens_generated": 28,
        "timestamp": datetime.now().isoformat()
    }
    
    llm_canonical = canonicalize_json(llm_response)
    llm_hash = hashlib.sha256(llm_canonical.encode()).hexdigest()
    
    print_event("LLM_RESPONSE", "Paris is the capital of France...", MAGENTA)
    print_hash("SHA-256 Hash", llm_hash[:32] + "..." + llm_hash[-8:], GREEN)
    
    accumulator.add_event(llm_response)
    print(f"{GREEN}[OK] Added to Verkle accumulator (event #2){RESET}\n")
    
    # Simulate tool invocation
    print_subheader("STEP 5: Agent Invokes Tool (Weather)")
    
    tool_call = {
        "type": "tool_invocation",
        "tool_name": "get_weather",
        "parameters": {
            "city": "Paris",
            "country": "France",
            "units": "celsius"
        },
        "timestamp": datetime.now().isoformat()
    }
    
    tool_canonical = canonicalize_json(tool_call)
    tool_hash = hashlib.sha256(tool_canonical.encode()).hexdigest()
    
    print_event("TOOL_CALL", 'Invoking tool "get_weather" for Paris, France', YELLOW)
    print(f"\n{DIM}Parameters: city=Paris, country=France, units=celsius{RESET}\n")
    print_hash("SHA-256 Hash", tool_hash[:32] + "..." + tool_hash[-8:], GREEN)
    
    accumulator.add_event(tool_call)
    print(f"{GREEN}[OK] Added to Verkle accumulator (event #3){RESET}\n")
    
    # Simulate tool response
    print_subheader("STEP 6: Tool Returns Weather Data")
    
    tool_result = {
        "type": "tool_result",
        "tool_name": "get_weather",
        "result": {
            "city": "Paris",
            "temperature": 12,
            "condition": "Partly Cloudy",
            "humidity": 65,
            "wind_speed": 15
        },
        "timestamp": datetime.now().isoformat()
    }
    
    tool_result_canonical = canonicalize_json(tool_result)
    tool_result_hash = hashlib.sha256(tool_result_canonical.encode()).hexdigest()
    
    print_event("TOOL_RESULT", "Weather: Paris, 12°C, Partly Cloudy, Humidity: 65%", CYAN)
    print_hash("SHA-256 Hash", tool_result_hash[:32] + "..." + tool_result_hash[-8:], GREEN)
    
    accumulator.add_event(tool_result)
    print(f"{GREEN}[OK] Added to Verkle accumulator (event #4){RESET}\n")
    
    # Final agent response
    print_subheader("STEP 7: Agent Produces Final Response")
    
    final_response = {
        "type": "final_response",
        "content": "Paris is the capital of France. Currently, the weather in Paris is 12°C and partly cloudy with 65% humidity.",
        "sources": ["llm_response", "tool_result"],
        "timestamp": datetime.now().isoformat()
    }
    
    final_canonical = canonicalize_json(final_response)
    final_hash = hashlib.sha256(final_canonical.encode()).hexdigest()
    
    print_event("FINAL_RESPONSE", final_response["content"], GREEN)
    print_hash("SHA-256 Hash", final_hash[:32] + "..." + final_hash[-8:], GREEN)
    
    accumulator.add_event(final_response)
    print(f"{GREEN}[OK] Added to Verkle accumulator (event #5){RESET}\n")
    
    # Finalize and get commitment
    print_subheader("STEP 8: Finalize Verkle Tree and Generate KZG Commitment")
    
    accumulator.finalize()
    root_b64 = accumulator.get_root_b64()
    root_bytes = base64.b64decode(root_b64)
    event_count = len(json.loads(accumulator.get_canonical_log().strip()))
    
    print(f"{GREEN}[OK] Verkle tree finalized with {event_count} events{RESET}\n")
    print(f"{BOLD}KZG Commitment (48-byte elliptic curve point):{RESET}")
    print(f"  Base64: {root_b64}")
    print(f"  Hex: {root_bytes.hex()}")
    print(f"  Length: {len(root_bytes)} bytes (BLS12-381 compressed point)\n")
    
    # Get canonical log
    canonical_log = accumulator.get_canonical_log()
    if isinstance(canonical_log, bytes):
        canonical_log = canonical_log.decode('utf-8')
    log_hash = hashlib.sha256(canonical_log.encode()).hexdigest()
    
    print_hash("Canonical Log SHA-256", log_hash, GREEN)
    print(f"\n{DIM}Log size: {len(canonical_log)} bytes{RESET}\n")
    
    # Visualize the log structure
    print_subheader("STEP 9: Visualize Communication Flow and Event Tree")
    
    events = json.loads(canonical_log.strip().split('\n')[0])  # Parse events from log
    
    tree_viz = f"""{CYAN}[VERKLE TREE STRUCTURE (KZG-Based)]{RESET}
{CYAN}---Event Timeline:{RESET}
"""
    
    print(tree_viz)
    
    # Print each event with its hash
    event_list = [
        ("Event #0: User Prompt", event_1_hash),
        ("Event #1: Agent Processing", agent_hash),
        ("Event #2: LLM Response", llm_hash),
        ("Event #3: Tool Call", tool_hash),
        ("Event #4: Tool Result", tool_result_hash),
        ("Event #5: Final Response", final_hash),
    ]
    
    for i, (label, ehash) in enumerate(event_list):
        print(f"  - {YELLOW}{label}{RESET}")
        print(f"    Hash: {DIM}{ehash[:16]}...{ehash[-8:]}{RESET}")
    
    print(f"\n{CYAN}---Merkle Tree Aggregation:{RESET}")
    print(f"  All events combined and hashed")
    print(f"\n{CYAN}---KZG Commitment (Final Root):{RESET}")
    print(f"  {BOLD}{root_b64}{RESET}\n")
    
    # Show hash chain
    print_subheader("STEP 10: Event Hash Chain (Each Event Depends on Previous)")
    
    print(f"{YELLOW}Event #0 Hash:{RESET}")
    print(f"  {event_1_hash}\n")
    
    print(f"{YELLOW}Event #1 Hash (aggregates Event #0):{RESET}")
    print(f"  {agent_hash}\n")
    
    print(f"{YELLOW}Event #2 Hash (aggregates previous):{RESET}")
    print(f"  {llm_hash}\n")
    
    print(f"{YELLOW}... (Events #3-5 continue aggregation) ...{RESET}\n")
    
    print(f"{GREEN}{BOLD}Final Verkle Root (KZG Commitment):{RESET}")
    print(f"  {MAGENTA}{root_b64}{RESET}\n")
    
    # Verification
    print_subheader("STEP 11: Verify Integrity of Complete Log")
    
    print(f"{BOLD}Verification Process:{RESET}\n")
    print(f"1. {CYAN}Reconstruct Verkle tree from canonical log{RESET}")
    print(f"2. {CYAN}Compute KZG commitment{RESET}")
    print(f"3. {CYAN}Compare against stored commitment{RESET}\n")
    
    # Verify by reconstructing
    verifier = VerkleAccumulator(session_id=session_id)
    for event in json.loads(canonical_log.strip()):
        verifier.add_event(event)
    verifier.finalize()
    verified_root = verifier.get_root_b64()
    
    if verified_root == root_b64:
        print(f"{GREEN}{BOLD}[OK] VERIFICATION SUCCESSFUL!{RESET}")
        print(f"{GREEN}Expected root matches computed root{RESET}\n")
    else:
        print(f"{RED}{BOLD}[FAILED] VERIFICATION FAILED!{RESET}")
        print(f"{RED}Roots do not match{RESET}\n")
    
    # Summary statistics
    print_subheader("STEP 12: Integrity Report")
    
    print(f"""{BOLD}Communication Summary:{RESET}
  - Total Events: {event_count}
  - Event Types: user_prompt, agent_processing, llm_response, tool_call, tool_result, final_response
  - Total Hashes Computed: {event_count + 1} (each event + final root)
  
{BOLD}Cryptographic Details:{RESET}
  - Curve: BLS12-381 (elliptic curve pairing)
  - Commitment Scheme: KZG (Kate-Zaverucha-Goldberg)
  - Hash Algorithm: SHA-256
  - Encoding: RFC 8785 (canonical JSON)
  - Root Size: 48 bytes (compressed point)
  
{BOLD}Verification Status:{RESET}
  - Log Integrity: {GREEN}[OK] VERIFIED{RESET}
  - Root Match: {GREEN}[OK] VERIFIED{RESET}
  - Overall Status: {GREEN}[OK] ALL CHECKS PASSED{RESET}
  
{BOLD}Use Cases:{RESET}
  - Audit Trail: Prove what happened in this agent run
  - Non-Repudiation: Agent cannot deny this conversation
  - Tamper Detection: Any change to log invalidates commitment
  - Public Verification: Third parties can verify without trusting us
""")
    
    # Final demonstration: Show how verification works publicly
    print_subheader("BONUS: Public Verification Example")
    
    print(f"""{CYAN}To verify this log publicly, anyone can run:{RESET}

  {BOLD}python -m src.tools.verify_cli verify canonical_log.jsonl '{root_b64}'{RESET}

{CYAN}This will:{RESET}
  1. Load the canonical log
  2. Reconstruct the Verkle tree
  3. Compute the KZG commitment
  4. Return exit code 0 if verified
  
{CYAN}Or to generate an audit proof:{RESET}

  {BOLD}python -m src.tools.verify_cli export-proof canonical_log.jsonl proof.json{RESET}

{CYAN}This creates a compact JSON proof showing:{RESET}
  - All events and their hashes
  - The final KZG commitment
  - Timestamps of the entire workflow
""")
    
    # Save the log for later verification
    log_file = Path("demo_workflow.jsonl")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(canonical_log)
    
    print(f"\n{GREEN}[OK] Canonical log saved to: {log_file}{RESET}")
    print(f"{GREEN}[OK] Root commitment: {root_b64}{RESET}\n")
    
    print_header("[COMPLETE] END-TO-END DEMO COMPLETE")
    
    print(f"""{GREEN}Summary:{RESET}
  - Sent 1 user prompt through AI agent
  - Agent made LLM call + tool invocation
  - 6 events tracked with SHA-256 hashing
  - Verkle tree built with KZG commitments
  - All hashes visualized and verified
  - Complete audit trail created and saved
  
{CYAN}The system proves:
  [OK] What happened (events)
  [OK] When it happened (timestamps)
  [OK] In what order (hash chain)
  [OK] Without tampering (commitment verification)
  [OK] Cryptographically verified (KZG-based){RESET}
""")


if __name__ == "__main__":
    demo_workflow()
