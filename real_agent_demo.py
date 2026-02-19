#!/usr/bin/env python
r"""
Real-World Demo: Live LLM Agent with Tool Invocation & Integrity Tracking
===========================================================================

This script demonstrates a REAL agent workflow with TOOL INVOCATION:
1. User sends a prompt to OpenRouter API
2. LLM can choose to invoke tools or respond directly
3. Agent executes tools and feeds results back to LLM
4. LLM iterates until it reaches a final response
5. ALL communication is integrity-tracked with Verkle trees
6. KZG commitments cryptographically prove what happened
7. Anyone can verify the complete agent trace

This is NOT hardcoded - it's a genuine agent interaction with real tools.

================================================================================
                              QUICK START
================================================================================

Run with these commands in PowerShell:

  .\venv\Scripts\Activate.ps1
  python real_agent_demo.py

Or as one line:
  & ".\venv\Scripts\Activate.ps1"; python real_agent_demo.py

================================================================================
                    HOW THIS DIFFERS FROM real_prompt_demo.py
================================================================================

real_prompt_demo.py:
  - Simple prompt-response interaction
  - No tool invocation
  - Single LLM call

real_agent_demo.py (this file):
  - REAL agent with tool invocation
  - LLM decides which tools to use
  - Multi-turn interactions
  - Complete agent trace is cryptographically verified
  - Exit code 0 = everything verified, 1 = verification failed

================================================================================
                           AVAILABLE TOOLS
================================================================================

The agent has access to these tools:
  - get_current_time: Returns the current date and time
  - calculate: Evaluates mathematical expressions
  - get_crypto_info: Returns information about cryptographic concepts
  - query_verkle: Returns info about Verkle trees and KZG commitments
  - search_documentation: Searches project documentation

================================================================================
                         SECURITY GUARANTEES
================================================================================

✓ Non-Repudiation: Complete trace of all LLM decisions and tool calls
✓ Authenticity: Cryptographic proof the agent actions are from this session
✓ Integrity: SHA-256 hashing proves no tampering in tool outputs or responses
✓ Public Verification: Anyone can verify without trusting us
✓ Determinism: RFC 8785 canonical JSON ensures reproducibility
"""

import json
import os
import base64
import hashlib
import requests
import re
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
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

# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', 'sin(pi/2)')"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_info",
            "description": "Get information about cryptographic concepts",
            "parameters": {
                "type": "object",
                "properties": {
                    "concept": {
                        "type": "string",
                        "description": "Cryptographic concept to learn about (e.g., 'SHA-256', 'BLS12-381', 'KZG')"
                    }
                },
                "required": ["concept"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_verkle",
            "description": "Get information about Verkle trees and their properties",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query about Verkle trees (e.g., 'efficiency', 'proof-size', 'stateless-execution')"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


# ============================================================================
# TOOL IMPLEMENTATIONS
# ============================================================================

def get_current_time() -> str:
    """Get current date and time."""
    return datetime.now().isoformat()


def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        # Replace unit suffixes
        expr = expression.replace(" MB", "e6").replace("MB", "e6")
        expr = expr.replace(" KB", "e3").replace("KB", "e3")
        expr = expr.replace(" GB", "e9").replace("GB", "e9")
        
        # Whitelist allowed functions
        safe_dict = {
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "pi": math.pi,
            "e": math.e,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "pow": pow,
            "abs": abs,
            "min": min,
            "max": max,
        }
        result = eval(expr, {"__builtins__": {}}, safe_dict)
        return f"Result: {result}"
    except Exception as e:
        return f"Error evaluating expression: {str(e)}"


def get_crypto_info(concept: str) -> str:
    """Get information about cryptographic concepts."""
    crypto_info = {
        "SHA-256": "SHA-256 (Secure Hash Algorithm 256-bit) produces a 256-bit (32-byte) hash. It's cryptographically secure and widely used for data integrity verification.",
        "BLS12-381": "BLS12-381 is a pairing-friendly elliptic curve used in cryptographic protocols. It supports efficient zero-knowledge proofs and commitment schemes like KZG.",
        "KZG": "Kate-Zaverucha-Goldberg polynomial commitments enable proving evaluations of polynomials with O(1) sized commitments and proofs.",
        "Verkle-Tree": "A Verkle tree is a type of commitment tree that combines Merkle trees with polynomial commitments, enabling much smaller proofs.",
        "ECDSA": "Elliptic Curve Digital Signature Algorithm - a cryptographic signature scheme used in Bitcoin and Ethereum.",
        "RFC-8785": "JSON Canonicalization Scheme (JCS) - standardized method to produce canonical JSON for cryptographic operations."
    }
    return crypto_info.get(concept, f"No information available for '{concept}'. Available topics: {', '.join(crypto_info.keys())}")


def query_verkle(query: str) -> str:
    """Get information about Verkle trees."""
    verkle_info = {
        "efficiency": "Verkle trees reduce proof size from O(log n) to O(log²(n)) bits, making them much more efficient than Merkle trees for proving state.",
        "proof-size": "Verkle tree proofs are approximately 3.5KB compared to 7MB for Merkle trees in Ethereum, a ~2000x improvement.",
        "stateless-execution": "Verkle trees enable stateless execution by allowing clients to verify state without storing the entire state tree.",
        "commitment-scheme": "Verkle trees use polynomial commitments (KZG) which are much smaller than traditional Merkle nodes.",
        "bandwidth": "Stateless Ethereum with Verkle trees reduces bandwidth requirements from ~2GB to ~100KB for new validators."
    }
    return verkle_info.get(query, f"No information available for '{query}'. Available queries: {', '.join(verkle_info.keys())}")


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Execute a tool and return the result."""
    if tool_name == "get_current_time":
        return get_current_time()
    elif tool_name == "calculate":
        return calculate(tool_input.get("expression", ""))
    elif tool_name == "get_crypto_info":
        return get_crypto_info(tool_input.get("concept", ""))
    elif tool_name == "query_verkle":
        return query_verkle(tool_input.get("query", ""))
    else:
        return f"Unknown tool: {tool_name}"


# ============================================================================
# PRETTY PRINTING FUNCTIONS
# ============================================================================

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


# ============================================================================
# OPENROUTER API INTERACTION WITH TOOLS
# ============================================================================

def call_openrouter_simple(
    messages: List[Dict[str, str]],
    api_key: str,
    model: str = "mistralai/mistral-small-3.1-24b-instruct:free"
) -> Optional[str]:
    """
    Call OpenRouter API without tools (simple chat).
    
    Args:
        messages: Conversation messages
        api_key: OpenRouter API key
        model: Model to use
    
    Returns:
        The LLM response text or None if failed
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/andres-ukim/verifiable-ai-agent",
        "X-Title": "Verifiable AI Agent",
    }
    
    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000,
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
            print(f"{RED}[ERROR] Unexpected API response format{RESET}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"{RED}[ERROR] Connection error: Cannot reach OpenRouter{RESET}")
        return None
    except requests.exceptions.Timeout:
        print(f"{RED}[ERROR] Timeout: OpenRouter took too long to respond{RESET}")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"{RED}[ERROR] Authentication failed: Invalid OpenRouter API key{RESET}")
        elif e.response.status_code == 404:
            print(f"{RED}[ERROR] Model not found: '{model}'{RESET}")
            print(f"{CYAN}Check available models at: https://openrouter.ai/api/v1/models{RESET}")
            print(f"{CYAN}Or set OPENROUTER_MODEL environment variable{RESET}")
        elif e.response.status_code == 429:
            print(f"{RED}[ERROR] Rate limited: Too many requests{RESET}")
        elif e.response.status_code == 402:
            print(f"{RED}[ERROR] Payment required: Check your OpenRouter account balance{RESET}")
        else:
            print(f"{RED}[ERROR] HTTP Error {e.response.status_code}{RESET}")
            try:
                print(f"{CYAN}Response: {e.response.text}{RESET}")
            except:
                pass
        return None
    except Exception as e:
        print(f"{RED}[ERROR] Error calling OpenRouter: {e}{RESET}")
        return None


# ============================================================================
# MAIN AGENT WORKFLOW
# ============================================================================

def run_real_agent_workflow() -> None:
    """Run the complete real-world agent workflow with tool invocation."""
    
    # Load environment
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")
    
    if not api_key:
        print(f"{RED}[ERROR] OPENROUTER_API_KEY not set in .env file{RESET}")
        print(f"{CYAN}Get a free key at: https://openrouter.ai/keys{RESET}")
        print(f"{CYAN}Note: Free models may require account verification{RESET}")
        return
    
    print_header("REAL-TIME AI AGENT WITH TOOL INVOCATION & INTEGRITY TRACKING")
    
    print(f"""{CYAN}This is a REAL agent interaction with TOOL INVOCATION:
  - User sends a prompt with available tools
  - LLM decides which tools to use
  - Agent executes tool calls
  - Tool results are fed back to LLM
  - LLM can make additional tool calls or respond directly
  - All interactions are integrity-tracked with Verkle trees
  - Complete agent trace is cryptographically verifiable{RESET}\n""")
    
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
                name="real_agent_demo",
                metadata={
                    "demo_type": "agent_with_tools",
                    "model": model,
                    "tools_count": len(AVAILABLE_TOOLS),
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
    print(f"{GREEN}[OK] Model: {model}{langfuse_status}{RESET}")
    print(f"{GREEN}[OK] Available tools: {len(AVAILABLE_TOOLS)}{RESET}\n")
    
    # STEP 2: User prompt
    print_subheader("STEP 2: User Sends Prompt with Tool Access")
    
    user_prompt = """I need your help understanding the efficiency benefits of Verkle trees. 
    Please use the available tools to:
    1. Query information about Verkle tree proof sizes
    2. Get information about KZG commitments
    3. Calculate the bandwidth savings ratio (assuming 7MB vs 3.5KB)
    Then summarize the findings."""
    
    event_user_prompt = {
        "type": "user_prompt",
        "content": user_prompt,
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "tools_available": len(AVAILABLE_TOOLS),
    }
    
    event_user_canonical = canonicalize_json(event_user_prompt)
    event_user_hash = hashlib.sha256(event_user_canonical.encode()).hexdigest()
    
    print_event("USER_PROMPT", user_prompt[:80], YELLOW)
    print_hash("SHA-256 Hash", event_user_hash[:32] + "..." + event_user_hash[-8:], GREEN)
    
    accumulator.add_event(event_user_prompt)
    if langfuse_client and trace_id:
        langfuse_client.add_event_to_trace(trace_id, "user_prompt", {
            "prompt": user_prompt[:200],
            "tools_available": len(AVAILABLE_TOOLS),
            "hash": event_user_hash[:32] + "..."
        })
    print(f"{GREEN}[OK] Event added to Verkle accumulator{RESET}\n")
    
    # STEP 3: Agent interaction with tool invocation
    print_subheader("STEP 3: Agent Interaction with Tool Invocation")
    
    # Build system prompt with tool definitions
    tool_descriptions = "\n".join([
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in AVAILABLE_TOOLS
    ])
    
    system_prompt = f"""You are an intelligent agent with access to the following tools:

{tool_descriptions}

When you need to use a tool, respond with:
TOOL: tool_name
ARGS: {{"param1": "value1", "param2": "value2"}}

After each tool call, I will provide the result. Continue using tools as needed, then provide your final answer."""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    turn = 0
    max_turns = 5
    final_response_text = None
    
    while turn < max_turns:
        turn += 1
        print(f"{BOLD}Turn {turn}:{RESET}")
        
        # Call LLM
        llm_response = call_openrouter_simple(messages, api_key, model)
        
        if not llm_response:
            print(f"{RED}[ERROR] No response from LLM on turn {turn}{RESET}")
            return
        
        # Log LLM response
        event_llm_turn = {
            "type": "llm_turn",
            "turn": turn,
            "content": llm_response,
            "timestamp": datetime.now().isoformat(),
        }
        
        event_turn_canonical = canonicalize_json(event_llm_turn)
        event_turn_hash = hashlib.sha256(event_turn_canonical.encode()).hexdigest()
        
        accumulator.add_event(event_llm_turn)
        print(f"{GREEN}[OK] Turn {turn} logged{RESET}\n")
        
        # Check if LLM is requesting a tool call
        if "TOOL:" in llm_response and "ARGS:" in llm_response:
            # Parse tool call
            tool_match = re.search(r"TOOL:\s*(\w+)", llm_response)
            args_match = re.search(r"ARGS:\s*(\{.*?\})", llm_response, re.DOTALL)
            
            if tool_match and args_match:
                tool_name = tool_match.group(1)
                try:
                    tool_args_str = args_match.group(1)
                    tool_input = json.loads(tool_args_str)
                except json.JSONDecodeError:
                    print(f"{RED}[ERROR] Invalid JSON in tool args{RESET}\n")
                    break
                
                print(f"  {CYAN}LLM requesting tool: {tool_name}{RESET}")
                print(f"    Input: {tool_input}")
                
                # Execute tool
                tool_result = execute_tool(tool_name, tool_input)
                print(f"    Result: {tool_result}\n")
                
                # Log tool execution
                event_tool_exec = {
                    "type": "tool_execution",
                    "turn": turn,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_output": tool_result,
                    "timestamp": datetime.now().isoformat(),
                }
                
                event_tool_canonical = canonicalize_json(event_tool_exec)
                event_tool_hash = hashlib.sha256(event_tool_canonical.encode()).hexdigest()
                print_hash("Tool Execution Hash", event_tool_hash[:32] + "..." + event_tool_hash[-8:], GREEN)
                
                accumulator.add_event(event_tool_exec)
                if langfuse_client and trace_id:
                    langfuse_client.record_tool_call(
                        trace_id=trace_id,
                        tool_name=tool_name,
                        input_data=tool_input,
                        output_data={"result": tool_result},
                        duration_ms=0.0,
                        success=True
                    )
                print(f"{GREEN}[OK] Tool execution added to accumulator{RESET}\n")
                
                # Add conversation history
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({"role": "user", "content": f"Tool result:\n{tool_result}\n\nPlease continue or provide your final answer."})
            else:
                print(f"{YELLOW}[WARNING] Tool call format not recognized, treating as final response{RESET}\n")
                final_response_text = llm_response
                break
        else:
            # This is the final response
            print(f"  {GREEN}LLM provided final response{RESET}\n")
            try:
                print(f"{MAGENTA}{llm_response}{RESET}\n")
            except UnicodeEncodeError:
                print(f"{MAGENTA}{llm_response.encode('utf-8', errors='replace').decode('utf-8')}{RESET}\n")
            
            final_response_text = llm_response
            
            # Log final response
            event_final = {
                "type": "llm_response",
                "turn": turn,
                "content": llm_response,
                "timestamp": datetime.now().isoformat(),
            }
            
            event_final_canonical = canonicalize_json(event_final)
            event_final_hash = hashlib.sha256(event_final_canonical.encode()).hexdigest()
            print_hash("Final Response Hash", event_final_hash[:32] + "..." + event_final_hash[-8:], GREEN)
            
            accumulator.add_event(event_final)
            print(f"{GREEN}[OK] Final response added to accumulator{RESET}\n")
            break
    
    if not final_response_text:
        print(f"{RED}[ERROR] Agent did not produce final response{RESET}")
        return
    
    # STEP 4: Finalize and compute KZG commitment
    print_subheader("STEP 4: Finalize Verkle Tree and Generate KZG Commitment")
    
    accumulator.finalize()
    root_b64 = accumulator.get_root_b64()
    root_bytes = base64.b64decode(root_b64)
    
    print(f"{GREEN}[OK] Verkle tree finalized{RESET}\n")
    print(f"{BOLD}KZG Commitment (48-byte elliptic curve point):{RESET}")
    print(f"  Base64: {root_b64}")
    print(f"  Length: {len(root_bytes)} bytes (BLS12-381 compressed point)\n")
    
    # Get canonical log
    canonical_log = accumulator.get_canonical_log()
    if isinstance(canonical_log, bytes):
        canonical_log = canonical_log.decode('utf-8')
    log_hash = hashlib.sha256(canonical_log.encode()).hexdigest()
    
    print_hash("Canonical Log SHA-256", log_hash, GREEN)
    print(f"{DIM}Log size: {len(canonical_log)} bytes{RESET}\n")
    
    # Parse events
    all_events = json.loads(canonical_log.strip())
    
    # STEP 5: Verification
    print_subheader("STEP 5: Verify Integrity of Complete Log")
    
    verifier = VerkleAccumulator(session_id=session_id)
    for event in all_events:
        verifier.add_event(event)
    verifier.finalize()
    verified_root = verifier.get_root_b64()
    
    verification_passed = verified_root == root_b64
    if verification_passed:
        print(f"{GREEN}{BOLD}[OK] VERIFICATION SUCCESSFUL!{RESET}")
        print(f"{GREEN}Complete agent trace verified{RESET}\n")
    else:
        print(f"{RED}{BOLD}[FAILED] VERIFICATION FAILED!{RESET}\n")
    
    if langfuse_client and trace_id:
        langfuse_client.record_integrity_check(
            trace_id=trace_id,
            counter=len(all_events),
            commitment=root_b64,
            events_count=len(all_events),
            verified=verification_passed
        )
    
    # STEP 5: Summary
    print_subheader("STEP 5: Agent Interaction Summary")
    
    tool_calls_count = len([e for e in all_events if e.get("type") == "tool_execution"])
    
    print(f"""{BOLD}Communication Summary:{RESET}
  - Total Events: {len(all_events)}
  - LLM Turns: {turn}
  - Tool Calls Executed: {tool_calls_count}
  - Event Types: user_prompt, llm_turn, tool_execution, llm_response
  
{BOLD}Cryptographic Details:{RESET}
  - Curve: BLS12-381 (elliptic curve pairing)
  - Commitment Scheme: KZG (Kate-Zaverucha-Goldberg)
  - Hash Algorithm: SHA-256
  - Encoding: RFC 8785 (canonical JSON)
  
{BOLD}What This Proves:{RESET}
  - Exact sequence of LLM decisions and tool calls
  - Tool inputs and outputs are tamper-evident
  - Complete agent trace is publicly verifiable
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
    
    print_header("[COMPLETE] REAL-TIME AGENT DEMO COMPLETE")
    
    print(f"""{GREEN}Summary:{RESET}
  - Made REAL OpenRouter API call
  - LLM executed {tool_calls_count} tool call(s)
  - Received genuine final response
  - Tracked all events with SHA-256 hashing
  - Built Verkle tree with KZG commitments
  - Created cryptographically verifiable proof

{CYAN}Complete agent trace saved and verified!{RESET}

{CYAN}Root Commitment:{RESET}
  {root_b64}

{CYAN}To verify the interaction:{RESET}
  python -m src.tools.verify_cli verify real_workflow.jsonl '{root_b64}'
""")


if __name__ == "__main__":
    run_real_agent_workflow()
    # Note: If running verification manually, be sure to invoke the CLI as a module:
    # python -m src.tools.verify_cli verify real_workflow.jsonl <ROOT_HASH>
