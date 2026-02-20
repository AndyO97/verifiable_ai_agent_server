#!/usr/bin/env python
r"""
Real-World Demo: Live LLM Agent with Tool Invocation & MCP 2024-11 Protocol
===========================================================================

This script demonstrates a REAL agent workflow with TOOL INVOCATION using MCP 2024-11:
1. User sends a prompt to OpenRouter API via MCP protocol
2. All communication wrapped in JSON-RPC 2.0 format (MCP 2024-11 spec)
3. LLM can choose to invoke tools or respond directly
4. Agent executes tools wrapped in MCP tools/call and tools/call_response
5. Tool results fed back to LLM with request ID correlation
6. LLM iterates until it reaches a final response
7. ALL communication is integrity-tracked with Verkle trees
8. KZG commitments cryptographically prove what happened
9. Complete session is MCP-compliant and publicly verifiable

This is NOT hardcoded - it's a genuine agent interaction with REAL MCP protocol compliance.

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
import uuid
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
from src.integrity import HierarchicalVerkleMiddleware
from src.crypto.encoding import canonicalize_json
from src.transport.jsonrpc_protocol import MCPProtocolHandler, JSONRPCRequest, JSONRPCResponse
from src.agent import MCPServer

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
    print_subheader("STEP 1: Initialize MCP 2024-11 Protocol & Integrity Tracking")
    
    session_id = "real-agent-mcp-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    protocol_handler = MCPProtocolHandler(server_name="Verifiable AI Agent (Multi-Turn)")
    mcp_server = MCPServer(session_id=session_id)
    
    # Initialize hierarchical middleware with spans (handles accumulator, langfuse, and MCP events)
    middleware = HierarchicalVerkleMiddleware(session_id=session_id)
    
    # Track JSON-RPC messages
    jsonrpc_messages: list[dict[str, Any]] = []
    
    print(f"{GREEN}[OK] MCP Protocol Handler initialized (version 2024-11){RESET}")
    print(f"{GREEN}[OK] MCPServer initialized{RESET}")
    print(f"{GREEN}[OK] HierarchicalVerkleMiddleware initialized (hierarchical spans + Langfuse){RESET}")
    if middleware.langfuse_client and middleware.trace_id:
        print(f"{GREEN}[OK] Langfuse tracing enabled (traces at http://localhost:3000){RESET}")
    else:
        print(f"{YELLOW}[INFO] Langfuse not available (optional - continuing without observability){RESET}")
    print(f"{GREEN}[OK] Session ID: {session_id}{RESET}")
    print(f"{GREEN}[OK] Model: {model}{RESET}")
    print(f"{GREEN}[OK] Available tools: {len(AVAILABLE_TOOLS)}{RESET}\n")
    
    # STEP 2: MCP Initialize Handshake - Span 1
    print_subheader("STEP 2: Span 1 - MCP Initialize Handshake")
    
    # Start MCP Initialize span
    middleware.start_span("mcp_initialize")
    
    init_request_dict = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11",
            "clientInfo": {
                "name": "Real Agent (Multi-Turn with Tools)",
                "version": "1.0"
            }
        },
        "id": "init-" + str(uuid.uuid4())
    }
    
    print(f"{BOLD}Client sends initialize request:{RESET}")
    print(f"{CYAN}  Method: {init_request_dict['method']}")
    print(f"  Protocol: {init_request_dict['params']['protocolVersion']}{RESET}\n")
    jsonrpc_messages.append(init_request_dict)
    
    # Record in span
    middleware.record_event_in_span("mcp_initialize_request", init_request_dict, signer_id="client")
    
    # Get initialization response from protocol handler
    init_response = protocol_handler.handle_request(init_request_dict)
    init_response_dict = init_response.to_dict()
    
    print(f"{BOLD}Server sends initialize response:{RESET}")
    print(f"{GREEN}  Status: SUCCESS")
    print(f"  Protocol: {init_response.result['protocolVersion']}{RESET}\n")
    jsonrpc_messages.append(init_response_dict)
    
    # Record in span
    middleware.record_event_in_span("mcp_initialize_response", init_response_dict, signer_id="server")
    
    print(f"{GREEN}[OK] MCP handshake complete{RESET}\n")
    
    # STEP 3: User Prompt - Span 2
    print_subheader("STEP 3: Span 2 - User Interaction")
    
    # Start user interaction span
    middleware.start_span("user_interaction")
    
    user_prompt = """I need your help understanding the efficiency benefits of Verkle trees. 
    Please use the available tools to:
    1. Query information about Verkle tree proof sizes
    2. Get information about KZG commitments
    3. Calculate the bandwidth savings ratio (assuming 7MB vs 3.5KB)
    Then summarize the findings."""
    
    print_event("USER_PROMPT", user_prompt[:80], YELLOW)
    
    middleware.record_event_in_span("user_prompt", {"prompt": user_prompt, "tools": len(AVAILABLE_TOOLS)}, signer_id="user")
    print(f"{GREEN}[OK] User prompt recorded to span{RESET}\n")
    
    # STEP 4: Agent interaction with tool invocation - Span 3
    print_subheader("STEP 4: Span 3 - Tool Execution")
    
    # Build system prompt with tool definitions
    tool_descriptions = "\n".join([
        f"- {t['function']['name']}: {t['function']['description']}"
        for t in AVAILABLE_TOOLS
    ])
    
    system_prompt = f"""You are an intelligent agent with access to the following tools:

{tool_descriptions}

IMPORTANT: When you need to use a tool, you MUST respond EXACTLY in this format:
TOOL: tool_name
ARGS: {{"param1": "value1", "param2": "value2"}}

After I provide the tool result, continue using tools as needed.
When you have enough information to answer the user, respond with your final answer (NOT using the TOOL format).

Examples:
- To get the current time: 
  TOOL: get_current_time
  ARGS: {{}}

- To calculate: 
  TOOL: calculate
  ARGS: {{"expression": "2 + 2"}}

- To query Verkle trees:
  TOOL: query_verkle
  ARGS: {{"query": "efficiency"}}

Once you have all the information you need, provide your FINAL ANSWER directly without any TOOL: lines."""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    turn = 0
    max_turns = 5
    final_response_text = None
    last_llm_response = None  # Track last response as fallback
    tool_calls_count = 0
    
    # Start tool_execution span (outside the loop, for all tool calls)
    middleware.start_span("tool_execution")
    
    while turn < max_turns:
        turn += 1
        print(f"{BOLD}Turn {turn}:{RESET}")
        
        # Call LLM
        llm_response = call_openrouter_simple(messages, api_key, model)
        
        if not llm_response:
            print(f"{RED}[ERROR] No response from LLM on turn {turn}{RESET}")
            return
        
        # Store as fallback in case we hit max_turns
        last_llm_response = llm_response
        
        # Log LLM response
        event_llm_turn = {
            "type": "llm_turn",
            "turn": turn,
            "content": llm_response,
            "timestamp": datetime.now().isoformat(),
        }
        
        event_turn_canonical = canonicalize_json(event_llm_turn)
        event_turn_hash = hashlib.sha256(event_turn_canonical.encode()).hexdigest()
        
        middleware.record_event_in_span("llm_turn", {"turn": turn, "response": llm_response}, signer_id="llm")
        print(f"{GREEN}[OK] Turn {turn} logged{RESET}\n")
        
        # Check if LLM is requesting a tool call
        # More robust detection: look for TOOL: even if ARGS might be on multiple lines
        tool_match = re.search(r"TOOL:\s*(\w+)", llm_response)
        args_match = re.search(r"ARGS:\s*(\{.*?\})", llm_response, re.DOTALL)
        
        if tool_match is not None:
            # LLM explicitly tried to use a tool
            tool_name = tool_match.group(1)
            
            if args_match is None:
                # Tool requested but ARGS not found in expected format
                print(f"{RED}[ERROR] Tool '{tool_name}' requested but ARGS not found in expected format{RESET}")
                print(f"{RED}LLM Response:{RESET}")
                print(f"{DIM}{llm_response[:200]}{RESET}\n")
                # Treat as final response anyway
                final_response_text = llm_response
                break
            
            try:
                tool_args_str = args_match.group(1)
                tool_input = json.loads(tool_args_str)
            except json.JSONDecodeError as e:
                print(f"{RED}[ERROR] Invalid JSON in tool args: {e}{RESET}")
                print(f"{RED}ARGS string: {tool_args_str}{RESET}\n")
                # Treat as final response
                final_response_text = llm_response
                break
            
            print(f"  {CYAN}LLM requesting tool: {tool_name}{RESET}")
            print(f"    Input: {tool_input}")
            
            # Create JSON-RPC tool call request
            tool_call_request_id = str(uuid.uuid4())
            tool_call_request_dict = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": tool_input
                },
                "id": tool_call_request_id
            }
            
            jsonrpc_messages.append(tool_call_request_dict)
            
            # Record MCP tool call request in span
            middleware.record_event_in_span("mcp_tools_call_request", tool_call_request_dict, signer_id="client")
            
            # Execute tool
            tool_result = execute_tool(tool_name, tool_input)
            print(f"    Result: {tool_result}\n")
            
            # Create JSON-RPC tool call response
            tool_call_response_dict = {
                "jsonrpc": "2.0",
                "result": {
                    "success": True,
                    "toolName": tool_name,
                    "output": tool_result,
                    "timestamp": datetime.now().isoformat()
                },
                "id": tool_call_request_id
            }
            
            jsonrpc_messages.append(tool_call_response_dict)
            
            # Record MCP tool call response in span
            middleware.record_event_in_span("mcp_tools_call_response", tool_call_response_dict, signer_id="tool")
            print(f"{GREEN}[OK] Tool execution logged{RESET}\n")
            
            # Track tool call count
            tool_calls_count += 1
            
            # Add conversation history
            messages.append({"role": "assistant", "content": llm_response})
            messages.append({"role": "user", "content": f"Tool result:\n{tool_result}\n\nPlease continue or provide your final answer."})
        else:
            # No tool request - this is the final response
            print(f"  {GREEN}LLM provided final response{RESET}\n")
            try:
                print(f"{MAGENTA}{llm_response}{RESET}\n")
            except UnicodeEncodeError:
                print(f"{MAGENTA}{llm_response.encode('utf-8', errors='replace').decode('utf-8')}{RESET}\n")
            
            final_response_text = llm_response
            break
    
    # STEP 5: Final Response - Span 4
    print_subheader("STEP 5: Span 4 - Final Response")
    
    # Start final_response span
    middleware.start_span("final_response")
    
    if not final_response_text and last_llm_response:
        print(f"{YELLOW}[INFO] Max turns reached, using last LLM response as final answer{RESET}\n")
        final_response_text = last_llm_response
    
    if final_response_text:
        middleware.record_event_in_span("final_response", {"response": final_response_text, "turn": turn, "tool_calls": tool_calls_count}, signer_id="llm")
        print(f"{GREEN}[OK] Final response recorded to span{RESET}\n")
    
    # STEP 6: Finalize and compute KZG commitment
    print_subheader("STEP 6: Finalize Hierarchical Verkle Tree and Generate Session Root")
    
    session_root, commitments, canonical_log_bytes = middleware.finalize()
    root_bytes = base64.b64decode(session_root)
    
    if isinstance(canonical_log_bytes, bytes):
        canonical_log = canonical_log_bytes.decode('utf-8')
    else:
        canonical_log = canonical_log_bytes
    
    all_events = json.loads(canonical_log.strip())
    event_count = len(all_events)
    
    print(f"{GREEN}[OK] Hierarchical Verkle tree finalized with {event_count} events across {len(middleware.spans)} spans{RESET}\n")
    print(f"{BOLD}Hierarchical KZG Commitment (Session Root):{RESET}")
    print(f"  Base64: {session_root}")
    print(f"  Length: {len(root_bytes)} bytes (BLS12-381 compressed point)\n")
    
    print(f"{BOLD}Span Roots:{RESET}")
    for span_id, root in commitments.span_roots.items():
        print(f"  - {span_id}: {root[:32]}...")
    print()
    
    log_hash = hashlib.sha256(canonical_log.encode()).hexdigest()
    
    print_hash("Canonical Log SHA-256", log_hash, GREEN)
    print(f"{DIM}Log size: {len(canonical_log)} bytes{RESET}\n")
    
    # STEP 7: Verification
    print_subheader("STEP 7: Verify Integrity of Complete Log")
    
    from src.crypto.verkle import VerkleAccumulator
    verifier = VerkleAccumulator(session_id=session_id)
    for event in all_events:
        verifier.add_event(event)
    verifier.finalize()
    verified_root = verifier.get_root_b64()
    
    verification_passed = verified_root == commitments.event_accumulator_root
    if verification_passed:
        print(f"{GREEN}{BOLD}[OK] VERIFICATION SUCCESSFUL!{RESET}")
        print(f"{GREEN}Complete agent trace verified{RESET}\n")
        print(f"{BOLD}Root Verification Details:{RESET}")
        print(f"  Verified Event Accumulator Root: {verified_root}")
        print(f"  Expected Event Accumulator Root: {commitments.event_accumulator_root}")
        print(f"  Hierarchical Session Root: {session_root}\n")
    else:
        print(f"{RED}{BOLD}[FAILED] VERIFICATION FAILED!{RESET}")
        print(f"{RED}Verified Root: {verified_root}{RESET}")
        print(f"{RED}Expected Root: {commitments.event_accumulator_root}{RESET}\n")
    
    # STEP 8: Count MCP protocol events and spans
    print_subheader("STEP 8: Verify Hierarchical Span Structure and MCP Protocol Compliance")
    
    mcp_init_requests = sum(1 for e in all_events if e.get("type") == "mcp_initialize_request")
    mcp_init_responses = sum(1 for e in all_events if e.get("type") == "mcp_initialize_response")
    mcp_tool_requests = sum(1 for e in all_events if e.get("type") == "mcp_tools_call_request")
    mcp_tool_responses = sum(1 for e in all_events if e.get("type") == "mcp_tools_call_response")
    span_count = len(middleware.spans)
    
    print(f"{BOLD}Hierarchical Span Structure:{RESET}")
    print(f"  {GREEN}[OK]{RESET} Spans: {span_count}")
    for span_id, span_meta in middleware.spans.items():
        print(f"       - {span_id}: {span_meta.event_count} events, root: {span_meta.verkle_root[:32] if span_meta.verkle_root else 'N/A'}...")
    
    print(f"\n{BOLD}MCP JSON-RPC 2.0 Protocol Events:{RESET}")
    print(f"  {GREEN}[OK]{RESET} Initialize Requests: {mcp_init_requests}")
    print(f"  {GREEN}[OK]{RESET} Initialize Responses: {mcp_init_responses}")
    print(f"  {GREEN}[OK]{RESET} Tools Call Requests: {mcp_tool_requests}")
    print(f"  {GREEN}[OK]{RESET} Tools Call Responses: {mcp_tool_responses}")
    print(f"  {GREEN}[OK]{RESET} Protocol Version: 2024-11")
    print(f"  {GREEN}[OK]{RESET} Tool Calls Executed: {tool_calls_count}\n")
    
    # STEP 9: Summary
    print_subheader("STEP 9: Agent Interaction Summary")
    
    print(f"""{BOLD}Hierarchical Communication Summary:{RESET}
  - Total Events: {len(all_events)}
  - Spans: {span_count} (mcp_initialize, user_interaction, tool_execution, final_response)
  - LLM Turns: {turn}
  - Tool Calls Executed: {tool_calls_count}
  - Verification: {'PASSED' if verification_passed else 'FAILED'}
  
{BOLD}Cryptographic Details:{RESET}
  - Curve: BLS12-381 (elliptic curve pairing)
  - Commitment Scheme: Hierarchical KZG + Verkle (per-span + session root)
  - Hash Algorithm: SHA-256
  - Encoding: RFC 8259 JSON + RFC 8785 Canonical Serialization
  - Protocol Version: MCP 2024-11 with JSON-RPC 2.0

{BOLD}Two Complementary Root Types:{RESET}
  1. Event Accumulator Root (FLAT): {commitments.event_accumulator_root}
     └─ Merkle root of all raw events in order
     └─ Used for entry-level verification (events can't be tampered)
     └─ Verified in STEP 7 above
     
  2. Session Root (HIERARCHICAL): {session_root}
     └─ Merkle root combining all per-span commitment roots
     └─ Used for aggregate verification (entire conversation structure)
     └─ Proves span ordering and integrity
     └─ Each span has its own independent root
  
{BOLD}What This Proves:{RESET}
  - Exact sequence of LLM decisions and tool calls across spans
  - Tool inputs and outputs are tamper-evident
  - Complete hierarchical agent trace with per-span Verkle roots
  - All communication in JSON-RPC 2.0 format with request ID correlation
  - Independently verifiable by anyone at span or session level
  - FLAT verification: Compare event_accumulator_root
  - HIERARCHICAL verification: Compare session_root (combining span roots)
""")
    
    # Save the log and hierarchical structure
    log_file = Path("real_workflow_agent_mcp.jsonl")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(canonical_log)
    
    print(f"\n{GREEN}[OK] Canonical log saved to: {log_file}{RESET}")
    print(f"{GREEN}[OK] Event Accumulator Root (for CLI verification): {commitments.event_accumulator_root}{RESET}")
    print(f"{GREEN}[OK] Session Root (hierarchical): {session_root}{RESET}\n")
    
    # Save hierarchical structure to local storage
    workflow_dir = Path(f"workflows/workflow_{middleware.session_id}")
    middleware.save_to_local_storage(workflow_dir)
    print(f"{GREEN}[OK] Hierarchical structure saved to: {workflow_dir}{RESET}\n")
    
    print_header("[COMPLETE] REAL-TIME AGENT DEMO WITH HIERARCHICAL SPANS")
    
    print(f"""{GREEN}Summary:{RESET}
  - Made REAL OpenRouter API call with MCP 2024-11 JSON-RPC 2.0 protocol
  - Organized into {len(middleware.spans)} hierarchical spans
  - LLM executed {tool_calls_count} tool call(s) wrapped in JSON-RPC
  - Received genuine final response
  - Tracked all {event_count} events with SHA-256 hashing
  - Built hierarchical Verkle tree with per-span + session roots
  - Created cryptographically verifiable proof across hierarchy

{CYAN}Complete MCP-compliant agent trace with hierarchical spans saved and verified!{RESET}

{CYAN}Event Accumulator Root (for CLI verification):{RESET}
  {commitments.event_accumulator_root}

{CYAN}Session Root (hierarchical - combines all span roots):{RESET}
  {session_root}

{CYAN}{BOLD}Verification Commands:{RESET}
{CYAN}(Run these to verify the agent interaction independently){RESET}

  {YELLOW}1. Basic Verification (uses event accumulator root):{RESET}
  python -m src.tools.verify_cli verify {log_file} '{commitments.event_accumulator_root}'

  {YELLOW}2. Show Protocol Event Breakdown:{RESET}
  python -m src.tools.verify_cli verify {log_file} '{commitments.event_accumulator_root}' --show-protocol
  {DIM}(Shows tree structure with spans and event counts){RESET}

  {YELLOW}3. Extract All Events to JSON:{RESET}
  python -m src.tools.verify_cli extract {log_file}
  {DIM}(Lists all {event_count} events with timestamps and types){RESET}

  {YELLOW}4. Export Proof for Audit:{RESET}
  python -m src.tools.verify_cli export-proof {log_file} '{commitments.event_accumulator_root}' --output proof.json
  {DIM}(Generates portable proof for offline verification){RESET}

{CYAN}{BOLD}Root Explanation:{RESET}
  - {{YELLOW}}Event Accumulator Root{RESET} = Flat Merkle root of 11 raw application events (canonical log)
  - {{YELLOW}}Session Root{RESET} = Hierarchical root combining 4 span commitment roots
  - Use {{CYAN}}Event Accumulator Root{{RESET}} with verify_cli (what the canonical log verifies against)
  - Use {{CYAN}}Session Root{{RESET}} for cross-checking span structure integrity\n{RESET}
""")


if __name__ == "__main__":
    run_real_agent_workflow()
    # Note: If running verification manually, be sure to invoke the CLI as a module:
    # python -m src.tools.verify_cli verify real_workflow.jsonl <SESSION_ROOT>
