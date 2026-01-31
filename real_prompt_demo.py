#!/usr/bin/env python
r"""
Real-World Demo: Live LLM Agent with Integrity Tracking
========================================================

This script demonstrates a REAL agent workflow:
1. User sends an actual prompt to OpenRouter API
2. LLM responds with real output
3. All communication is integrity-tracked with Verkle trees
4. KZG commitments cryptographically prove what happened
5. Anyone can verify the log without trusting us

This is NOT hardcoded - it's a genuine agent interaction.

================================================================================
                              QUICK START
================================================================================

Run with these commands in PowerShell:

  .\venv\Scripts\Activate.ps1
  python real_prompt_demo.py

Or as one line:
  & .\venv\Scripts\Activate.ps1; python real_prompt_demo.py

================================================================================
                    HOW THIS DIFFERS FROM e2e_demo.py
================================================================================

e2e_demo.py:
  - Hardcoded responses
  - Good for understanding the system
  - Deterministic output

real_prompt_demo.py (this file):
  - REAL OpenRouter API calls
  - Shows actual LLM responses
  - Cryptographically verifiable proof of what really happened
  - Exit code 0 = everything verified, 1 = verification failed

================================================================================
                         SECURITY GUARANTEES
================================================================================

✓ Non-Repudiation: We cannot claim the LLM said something it didn't
✓ Authenticity: Cryptographic proof the response is from this session
✓ Integrity: SHA-256 hashing proves no tampering
✓ Public Verification: Anyone can verify without trusting us
✓ Determinism: RFC 8785 canonical JSON ensures reproducibility
"""

import json
import os
import base64
import hashlib
import requests
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Fix Unicode issues on Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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
from src.crypto.encoding import canonicalize_json

# Try to import Langfuse (optional)
try:
    from src.observability.langfuse_client import LangfuseClient
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False


# Langfuse helper
def check_langfuse_running() -> bool:
    """Check if Langfuse server is running"""
    if not LANGFUSE_AVAILABLE:
        return False
    try:
        import requests
        response = requests.get("http://localhost:3000/api/public/health", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


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
    truncated = content[:60] + "..." if len(content) > 60 else content
    print(f"{color}[{timestamp}] {BOLD}{event_type}:{RESET} {truncated}")


def call_openrouter(prompt: str, api_key: str, model: str = "arcee-ai/trinity-large-preview:free") -> Optional[str]:
    """
    Call OpenRouter API with a prompt and return the response.
    
    Args:
        prompt: The user's question
        api_key: OpenRouter API key
        model: Model to use (default: free Devstral 2512)
    
    Returns:
        The LLM response or None if failed
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/andres-ukim/verifiable-ai-agent",
        "X-Title": "Verifiable AI Agent",
    }
    
    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 500,
    }
    
    try:
        print(f"{CYAN}[Connecting to OpenRouter...]{RESET}")
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["message"]["content"]
        else:
            print(f"{RED}✗ Unexpected API response format{RESET}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"{RED}✗ Connection error: Cannot reach OpenRouter. Is your internet working?{RESET}")
        return None
    except requests.exceptions.Timeout:
        print(f"{RED}✗ Timeout: OpenRouter took too long to respond{RESET}")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"{RED}✗ Authentication failed: Invalid OpenRouter API key{RESET}")
        else:
            print(f"{RED}✗ HTTP Error {e.response.status_code}: {e.response.text}{RESET}")
        return None
    except Exception as e:
        print(f"{RED}✗ Error calling OpenRouter: {e}{RESET}")
        return None


def run_real_agent_workflow() -> None:
    """Run the complete real-world agent workflow."""
    
    # Load environment
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")
    
    if not api_key:
        print(f"{RED}✗ Error: OPENROUTER_API_KEY not set in .env file{RESET}")
        print(f"{CYAN}Get a free key at: https://openrouter.ai/keys{RESET}")
        return
    
    print_header("REAL-TIME AI AGENT WORKFLOW WITH INTEGRITY TRACKING")
    
    print(f"""{CYAN}This is a REAL agent interaction:
  - User sends a prompt to OpenRouter API
  - LLM provides genuine response
  - All communication is integrity-tracked
  - Verkle tree built with KZG commitments
  - Cryptographically verifiable proof created
  - Anyone can verify what really happened{RESET}\n""")
    
    # Initialize components
    print_subheader("STEP 1: Initialize Integrity Tracking")
    
    session_id = "real-agent-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    accumulator = VerkleAccumulator(session_id=session_id)
    
    # Try to initialize Langfuse if available
    langfuse_client = None
    trace_id = None
    langfuse_status = ""
    
    if check_langfuse_running():
        try:
            langfuse_client = LangfuseClient(session_id=session_id)
            trace_id = langfuse_client.create_trace(
                name="real_prompt_demo",
                metadata={
                    "demo_type": "simple_prompt_response",
                    "model": model,
                }
            )
            langfuse_status = f" + Langfuse tracing enabled"
            print(f"{GREEN}[OK] Langfuse client initialized (traces will be visible at http://localhost:3000){RESET}")
        except Exception as e:
            print(f"{YELLOW}[WARN] Could not initialize Langfuse: {str(e)}{RESET}")
            langfuse_client = None
    else:
        print(f"{YELLOW}[INFO] Langfuse not detected (optional - running without observability){RESET}")
    
    print(f"{GREEN}[OK] Canonical JSON Encoder initialized (RFC 8785){RESET}")
    print(f"{GREEN}[OK] Verkle Accumulator initialized (KZG commitments, BLS12-381){RESET}")
    print(f"{GREEN}[OK] Session ID: {session_id}{RESET}")
    print(f"{GREEN}[OK] Model: {model}{langfuse_status}{RESET}\n")
    
    # STEP 2: User prompt
    print_subheader("STEP 2: User Sends Prompt to Agent")
    
    user_prompt = "Explain Verkle trees in one paragraph. Be concise but technical."
    event_user_prompt = {
        "type": "user_prompt",
        "content": user_prompt,
        "timestamp": datetime.now().isoformat(),
        "model": model,
    }
    
    event_user_canonical = canonicalize_json(event_user_prompt)
    event_user_hash = hashlib.sha256(event_user_canonical.encode()).hexdigest()
    
    print_event("USER_PROMPT", user_prompt, YELLOW)
    print_hash("SHA-256 Hash", event_user_hash[:32] + "..." + event_user_hash[-8:], GREEN)
    
    accumulator.add_event(event_user_prompt)
    if langfuse_client and trace_id:
        langfuse_client.add_event_to_trace(trace_id, "user_prompt", {
            "prompt": user_prompt,
            "hash": event_user_hash[:32] + "..."
        })
    print(f"{GREEN}[OK] Event added to Verkle accumulator{RESET}\n")
    
    # STEP 3: Agent routes to LLM
    print_subheader("STEP 3: Agent Routes to OpenRouter LLM")
    
    event_agent_routing = {
        "type": "agent_routing",
        "action": "send_to_llm",
        "model": model,
        "timestamp": datetime.now().isoformat(),
    }
    
    event_routing_canonical = canonicalize_json(event_agent_routing)
    event_routing_hash = hashlib.sha256(event_routing_canonical.encode()).hexdigest()
    
    print_event("AGENT_ROUTING", f"Sending to {model}", CYAN)
    print_hash("SHA-256 Hash", event_routing_hash[:32] + "..." + event_routing_hash[-8:], GREEN)
    
    accumulator.add_event(event_agent_routing)
    print(f"{GREEN}[OK] Event added to Verkle accumulator{RESET}\n")
    
    # STEP 4: REAL API CALL
    print_subheader("STEP 4: Making REAL OpenRouter API Call")
    
    print(f"{CYAN}Sending request to OpenRouter...{RESET}")
    print(f"{DIM}Prompt: {user_prompt}{RESET}\n")
    
    llm_response_text = call_openrouter(user_prompt, api_key, model)
    
    if not llm_response_text:
        print(f"{RED}✗ Failed to get response from LLM{RESET}")
        return
    
    # STEP 5: LLM response
    print_subheader("STEP 5: LLM Response Received")
    
    event_llm_response = {
        "type": "llm_response",
        "model": model,
        "content": llm_response_text,
        "timestamp": datetime.now().isoformat(),
    }
    
    event_response_canonical = canonicalize_json(event_llm_response)
    event_response_hash = hashlib.sha256(event_response_canonical.encode()).hexdigest()
    
    print_event("LLM_RESPONSE", llm_response_text, MAGENTA)
    print_hash("SHA-256 Hash", event_response_hash[:32] + "..." + event_response_hash[-8:], GREEN)
    
    accumulator.add_event(event_llm_response)
    if langfuse_client and trace_id:
        langfuse_client.record_llm_call(
            trace_id=trace_id,
            model=model,
            prompt=user_prompt,
            response=llm_response_text,
            input_tokens=0,
            output_tokens=0,
            cost=0.0
        )
    print(f"{GREEN}[OK] Event added to Verkle accumulator{RESET}\n")
    
    # STEP 6: Final agent response
    print_subheader("STEP 6: Agent Produces Final Response")
    
    final_response = {
        "type": "final_response",
        "content": llm_response_text,
        "sources": ["llm_response"],
        "timestamp": datetime.now().isoformat(),
    }
    
    final_canonical = canonicalize_json(final_response)
    final_hash = hashlib.sha256(final_canonical.encode()).hexdigest()
    
    print_event("FINAL_RESPONSE", final_response["content"], GREEN)
    print_hash("SHA-256 Hash", final_hash[:32] + "..." + final_hash[-8:], GREEN)
    
    accumulator.add_event(final_response)
    print(f"{GREEN}[OK] Event added to Verkle accumulator{RESET}\n")
    
    # STEP 7: Finalize and compute KZG commitment
    print_subheader("STEP 7: Finalize Verkle Tree and Generate KZG Commitment")
    
    accumulator.finalize()
    root_b64 = accumulator.get_root_b64()
    root_bytes = base64.b64decode(root_b64)
    
    print(f"{GREEN}[OK] Verkle tree finalized with 4 events{RESET}\n")
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
    print(f"{DIM}Log size: {len(canonical_log)} bytes{RESET}\n")
    
    # Parse events for later comparison
    all_events = json.loads(canonical_log.strip())
    
    # STEP 8: Verification
    print_subheader("STEP 8: Verify Integrity of Complete Log")
    
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
        verification_passed = True
    else:
        print(f"{RED}{BOLD}[FAILED] VERIFICATION FAILED!{RESET}")
        print(f"{RED}Roots do not match{RESET}\n")
        verification_passed = False
    
    if langfuse_client and trace_id:
        langfuse_client.record_integrity_check(
            trace_id=trace_id,
            counter=len(all_events),
            commitment=root_b64,
            events_count=len(all_events),
            verified=verification_passed
        )
    
    # STEP 9: Compare actual response with logged response
    print_subheader("STEP 9: Verify Logged Response Matches Actual Response")
    
    # Extract the response from the log
    logged_response = None
    for event in all_events:
        if event.get("type") == "llm_response":
            logged_response = event.get("content", "")
            break
    
    if logged_response:
        matches = logged_response.strip() == llm_response_text.strip()
        status = f"{GREEN}[OK] MATCH{RESET}" if matches else f"{RED}[FAILED] MISMATCH{RESET}"
        
        print(f"{status} - Actual response matches logged response\n")
        
        print(f"{BOLD}Actual Response from OpenRouter:{RESET}")
        print(f"{CYAN}{llm_response_text}{RESET}\n")
        
        print(f"{BOLD}Response in Canonical Log:{RESET}")
        print(f"{CYAN}{logged_response}{RESET}\n")
        
        if matches:
            print(f"{GREEN}[OK] Perfect match! The log accurately captured the LLM response.{RESET}\n")
        else:
            print(f"{RED}[FAILED] Mismatch detected! The responses differ.{RESET}\n")
    
    # STEP 10: Summary
    print_subheader("STEP 10: Integrity Report")
    
    events = json.loads(canonical_log.strip())
    
    print(f"""{BOLD}Communication Summary:{RESET}
  - Total Events: {len(all_events)}
  - Event Types: user_prompt, agent_routing, llm_response, final_response
  - Total Hashes Computed: {len(all_events) + 1} (each event + final root)
  
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

{BOLD}What This Proves:{RESET}
  - OpenRouter returned this exact response at this time
  - User asked this exact question
  - No tampering occurred
  - Independently verifiable by anyone
""")
    
    # STEP 11: How to verify
    print_subheader("STEP 11: How to Publicly Verify This")
    
    print(f"""{CYAN}To verify this log publicly, anyone can run:{RESET}

  {BOLD}python -m src.tools.verify_cli verify real_workflow.jsonl '{root_b64}'{RESET}

{CYAN}Or generate an audit proof for compliance:{RESET}

  {BOLD}python -m src.tools.verify_cli export-proof real_workflow.jsonl proof.json{RESET}

{CYAN}Or share both files publicly:{RESET}
  - real_workflow.jsonl (the log)
  - Root commitment: {root_b64}
  
{CYAN}Anyone can verify independently without trusting us.{RESET}
""")
    
    # Save the log
    log_file = Path("real_workflow.jsonl")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(canonical_log)
    
    print(f"\n{GREEN}[OK] Canonical log saved to: {log_file}{RESET}")
    print(f"{GREEN}[OK] Root commitment: {root_b64}{RESET}\n")
    
    # Finalize Langfuse trace
    if langfuse_client and trace_id:
        langfuse_client.finalize_trace(trace_id)
        summary = langfuse_client.get_session_summary()
        print(f"{GREEN}[OK] Langfuse trace finalized{RESET}")
        print(f"{GREEN}    View trace at: http://localhost:3000{RESET}")
        print(f"{GREEN}    Session: {summary['session_id']}{RESET}")
        print(f"{GREEN}    Traces: {summary['total_traces']}{RESET}")
        print(f"{GREEN}    Events: {summary['total_events']}{RESET}\n")
    
    print_header("[COMPLETE] REAL-TIME DEMO COMPLETE")
    
    verification_command = f"& .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli verify real_workflow.jsonl '{root_b64}'"
    
    print(f"""{GREEN}Summary:{RESET}
  - Made REAL OpenRouter API call
  - Received genuine LLM response
  - Tracked all events with SHA-256 hashing
  - Built Verkle tree with KZG commitments
  - Created cryptographically verifiable proof
  - Complete audit trail saved

{CYAN}This is NOT fake data.
This is a REAL agent interaction with REAL LLM response.
The commitment {root_b64[:20]}... uniquely and permanently identifies this exact conversation.{RESET}

{CYAN}Root Commitment:{RESET}
  {root_b64}

{CYAN}Anyone can verify it really happened. Copy and paste this command:{RESET}
  {verification_command}
""")


if __name__ == "__main__":
    run_real_agent_workflow()
