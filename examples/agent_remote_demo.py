"""
Agent Server with Remote Tool Integration and MCP 2024-11 Protocol.
Demonstrates secure remote tool invocation with full JSON-RPC 2.0 protocol compliance.

Architecture:
- SecureMCPClient handles encryption/decryption (ECDH-AES256-GCM)
- MCPProtocolHandler manages JSON-RPC 2.0 protocol layer
- Tool responses signed with IBS to prevent tampering
- All communication is integrity-tracked and cryptographically verifiable

Usage:
1. Start the tool: `python examples/remote_tool.py`
2. Run this agent: 
& "./venv/Scripts/python.exe" examples/agent_remote_demo.py
"""

import sys
import os
import uuid
import time
import json
import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.integrity import HierarchicalVerkleMiddleware
from src.crypto.encoding import canonicalize_json
from src.config import get_settings
from src.transport.secure_mcp import SecureMCPClient
from src.transport.jsonrpc_protocol import MCPProtocolHandler, JSONRPCRequest, JSONRPCResponse
from src.agent import MCPServer

# ANSI Colors
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
DIM = "\033[2m"

# Configuration
TOOL_NAME = "remote_calc"
TOOL_HOST = "localhost"
TOOL_PORT = 5555
LOG_FILE = "remote_workflow.jsonl"

async def main():
    print(f"{BOLD}Starting Secure Remote Tool Agent Demo (MCP 2024-11 + WebSocket)...{RESET}")
    
    # Initialize hierarchical middleware with spans (handles accumulator, langfuse, and MCP events)
    session_id = "remote-agent-mcp-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    middleware = HierarchicalVerkleMiddleware(session_id=session_id)
    protocol_handler = MCPProtocolHandler(server_name="Remote Agent (Secure)")
    mcp_server = MCPServer(session_id=session_id)
    
    jsonrpc_messages: list[dict[str, Any]] = []
    
    print(f"{GREEN}[OK] IntegrityMiddleware initialized (unified accumulator + Langfuse){RESET}")
    if middleware.langfuse_client and middleware.trace_id:
        print(f"{GREEN}[OK] Langfuse tracing enabled (traces at http://localhost:3000){RESET}")
    else:
        print(f"{YELLOW}[INFO] Langfuse not available (optional - continuing without observability){RESET}")
    
    print(f"Session ID: {middleware.session_id}") 
    print(f"{GREEN}[OK] MCPProtocolHandler initialized (version 2024-11){RESET}")
    print(f"{GREEN}[OK] MCPServer initialized{RESET}\n")
    
    # 2. Connect to Remote Tool
    client = SecureMCPClient(TOOL_NAME, TOOL_HOST, TOOL_PORT, middleware)
    
    try:
        # Secure Handshake & Provisioning
        # Connects, performs ECDH, provisions IBS keys
        await client.connect_and_provision() 
        print(f"[Conn] Connected to '{TOOL_NAME}' on ws://{TOOL_HOST}:{TOOL_PORT} (Secure Channel Established)")
        
        # 3. Agent Workflow organized into spans
        print(f"\n{BOLD}Span 1: MCP Initialize Handshake{RESET}")
        
        # Start MCP Initialize span
        middleware.start_span("mcp_initialize")
        
        init_request_dict = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11",
                "clientInfo": {
                    "name": "Remote Agent Demo",
                    "version": "1.0"
                }
            },
            "id": "init-" + str(uuid.uuid4())
        }
        
        jsonrpc_messages.append(init_request_dict)
        
        # Record MCP initialize request in span
        middleware.record_event_in_span("mcp_initialize_request", init_request_dict, signer_id="client")
        
        init_response = protocol_handler.handle_request(init_request_dict)
        init_response_dict = init_response.to_dict()
        jsonrpc_messages.append(init_response_dict)
        
        # Record MCP initialize response in span
        middleware.record_event_in_span("mcp_initialize_response", init_response_dict, signer_id="server")
        
        print(f"{GREEN}[OK] MCP handshake complete (protocol: 2024-11){RESET}\n")
        
        # 4. Span: User Interaction and Prompt
        print(f"{BOLD}Span 2: User Interaction{RESET}")
        middleware.start_span("user_interaction")
        
        # Process User Prompt
        prompt = "Calculate 100 * 5"
        print(f"[Agent] Prompt: '{prompt}'")
        
        # Record Prompt in span
        middleware.record_event_in_span("user_prompt", {"prompt": prompt}, signer_id="user")
        
        
        # 5. Span: Tool Execution
        print(f"{BOLD}Span 3: Tool Execution{RESET}")
        middleware.start_span("tool_execution")
        
        # 4. Call Remote Tool via MCP JSON-RPC 2.0
        input_args = {"op": "mul", "a": 100, "b": 5}
        tool_call_request_id = str(uuid.uuid4())
        
        print(f"[Agent] Calling tool '{TOOL_NAME}' with args {input_args}")
        
        # Create JSON-RPC 2.0 tool call request
        tool_call_request_dict = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": TOOL_NAME,
                "arguments": input_args
            },
            "id": tool_call_request_id
        }
        
        jsonrpc_messages.append(tool_call_request_dict)
        
        # Record MCP tool call request in span
        middleware.record_event_in_span("mcp_tools_call_request", tool_call_request_dict, signer_id="client")
        
        # Record Tool Input
        middleware.record_event_in_span("tool_input", {"tool": TOOL_NAME, "args": input_args}, signer_id="client")
        
        # Execute Remote Call (Encrypted + Signed)
        start_time = time.time()
        response = await client.call_tool(input_args, tool_call_request_id)
        duration = time.time() - start_time
        
        result = response["result"]
        signature = response["signature"]
        
        print(f"{GREEN}[OK] Valid Signature received from '{TOOL_NAME}'{RESET}")
        print(f"   Result: {result}")
        
        # Create JSON-RPC 2.0 tool call response with signature
        tool_call_response_dict = {
            "jsonrpc": "2.0",
            "result": {
                "success": True,
                "toolName": TOOL_NAME,
                "output": result,
                "signature": signature,
                "verified": True,
                "timestamp": datetime.now().isoformat()
            },
            "id": tool_call_request_id
        }
        
        jsonrpc_messages.append(tool_call_response_dict)
        
        # Record MCP tool call response in span
        middleware.record_event_in_span("mcp_tools_call_response", tool_call_response_dict, signer_id="tool")
        
        # Record Tool Output
        middleware.record_event_in_span("tool_output", {"tool": TOOL_NAME, "result": result, "signature": signature}, signer_id="tool")
        
        
        # 6. Span: Final Response
        print(f"{BOLD}Span 4: Final Response{RESET}")
        middleware.start_span("final_response")
        
        # 5. Finalize and Create Commitment
        final_answer = f"The result is {result}"
        print(f"{GREEN}[OK] Final Answer: {final_answer}{RESET}")
        
        # Record final response in span
        middleware.record_event_in_span("final_response", {"answer": final_answer}, signer_id="server")
        
        # Finalize middleware (includes hierarchical Verkle roots and Langfuse integration)
        session_root, commitments, canonical_log_bytes = middleware.finalize()
        
        print(f"\n{BOLD}Commitment Finalized:{RESET} {YELLOW}{session_root}{RESET}")
        
        # Ensure canonical_log is string
        if isinstance(canonical_log_bytes, bytes):
            canonical_log = canonical_log_bytes.decode('utf-8')
        else:
            canonical_log = canonical_log_bytes
        
        log_file = "remote_workflow_agent_mcp.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(canonical_log)
        print(f"[Disk] Saved canonical log to: {log_file}")
        
        # Save hierarchical structure to local storage
        from pathlib import Path
        workflow_dir = Path(f"workflows/workflow_{middleware.session_id}")
        middleware.save_to_local_storage(workflow_dir)
        print(f"[Disk] Saved hierarchical structure to: {workflow_dir}")

        # In-Process Verification
        print(f"\n{CYAN}Verifying Integrity locally (Hierarchical Verkle + MCP 2024-11)...{RESET}")
        canonical_log_str = canonical_log if isinstance(canonical_log, str) else canonical_log.decode('utf-8')
        all_events = json.loads(canonical_log_str.strip())
        
        from src.crypto.verkle import VerkleAccumulator
        verifier = VerkleAccumulator(session_id="verify_session")
        for event in all_events:
            verifier.add_event(event)
        verifier.finalize()
        verified_root = verifier.get_root_b64()
        
        # Count MCP events and spans
        mcp_init_requests = sum(1 for e in all_events if e.get("type") == "mcp_initialize_request")
        mcp_init_responses = sum(1 for e in all_events if e.get("type") == "mcp_initialize_response")
        mcp_tool_requests = sum(1 for e in all_events if e.get("type") == "mcp_tools_call_request")
        mcp_tool_responses = sum(1 for e in all_events if e.get("type") == "mcp_tools_call_response")
        span_count = len(middleware.spans)
        
        if verified_root == commitments.event_accumulator_root:
            print(f"{GREEN}[OK] VERIFICATION SUCCESSFUL: Log matches Event Accumulator Root{RESET}")
            print(f"\n{BOLD}Hierarchical Verkle + MCP Protocol Summary:{RESET}")
            print(f"  - Protocol Version: 2024-11")
            print(f"  - JSON-RPC Version: 2.0")
            print(f"  - Spans: {span_count} (mcp_initialize, user_interaction, tool_execution, final_response)")
            print(f"  - Initialize Requests: {mcp_init_requests}")
            print(f"  - Initialize Responses: {mcp_init_responses}")
            print(f"  - Tool Call Requests: {mcp_tool_requests}")
            print(f"  - Tool Call Responses: {mcp_tool_responses}")
            print(f"  - Total Events: {len(all_events)}")
            print(f"  - Encryption: ECDH-AES256-GCM (SecureMCPClient)")
            print(f"  - Signatures: IBS-BLS12-381")
            print(f"  - Commitment Scheme: KZG + Verkle (per-span roots + session root)")
        else:
            print(f"{RED}[FAILED] VERIFICATION FAILED{RESET}")
        
        print(f"\n{BOLD}Verification Commands:{RESET}")
        print(f"{DIM}(Run these independently to verify the secure remote tool interaction){RESET}\n")
        print(f"{CYAN}Event Accumulator Root (for CLI verification):{RESET}")
        print(f"  {commitments.event_accumulator_root}\n")
        print(f"{CYAN}Session Root (hierarchical - combines all span roots):{RESET}")
        print(f"  {session_root}\n")
        
        print(f"{GREEN}1. Basic Verification (uses event accumulator root):{RESET}")
        print(f"   python -m src.tools.verify_cli verify {log_file} '{commitments.event_accumulator_root}'\n")
        
        print(f"{GREEN}2. Show Protocol Event Breakdown:{RESET}")
        print(f"   python -m src.tools.verify_cli verify {log_file} '{commitments.event_accumulator_root}' --show-protocol")
        print(f"   {DIM}(Visualize MCP handshake and encrypted tool invocation){RESET}\n")
        
        print(f"{GREEN}3. Extract Event Details:{RESET}")
        print(f"   python -m src.tools.verify_cli extract {log_file}")
        print(f"   {DIM}(Lists all {len(all_events)} events including MCP initialize and tool calls){RESET}\n")
        
        print(f"{GREEN}4. Export Proof for Auditing:{RESET}")
        print(f"   python -m src.tools.verify_cli export-proof {log_file} '{commitments.event_accumulator_root}' --output proof.json")
        print(f"   {DIM}(Generates portable proof for offline verification or compliance){RESET}\n")
        
    except Exception as e:
        print(f"\n{RED}❌ Error: {e}{RESET}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
