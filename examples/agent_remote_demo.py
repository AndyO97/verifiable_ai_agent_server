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

from src.integrity import IntegrityMiddleware
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

# Configuration
TOOL_NAME = "remote_calc"
TOOL_HOST = "localhost"
TOOL_PORT = 5555
LOG_FILE = "remote_workflow.jsonl"

async def main():
    print(f"{BOLD}Starting Secure Remote Tool Agent Demo (MCP 2024-11 + WebSocket)...{RESET}")
    
    # 1. Initialize Integrity & MCP Protocol
    middleware = IntegrityMiddleware()
    protocol_handler = MCPProtocolHandler(server_name="Remote Agent (Secure)")
    mcp_server = MCPServer(session_id=middleware.session_id)
    
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
        
        # 3. Agent Workflow and MCP Initialize Handshake
        print(f"\n{BOLD}MCP Initialize Handshake:{RESET}")
        
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
        
        # Record MCP initialize request in middleware
        middleware.record_mcp_event("mcp_initialize_request", init_request_dict)
        
        init_response = protocol_handler.handle_request(init_request_dict)
        init_response_dict = init_response.to_dict()
        jsonrpc_messages.append(init_response_dict)
        
        # Record MCP initialize response in middleware
        middleware.record_mcp_event("mcp_initialize_response", init_response_dict)
        
        print(f"{GREEN}[OK] MCP handshake complete (protocol: 2024-11){RESET}\n")
        
        # Process User Prompt
        prompt = "Calculate 100 * 5"
        print(f"[Agent] Prompt: '{prompt}'")
        
        # Record Prompt
        middleware.record_prompt(prompt)
        
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
        
        # Record MCP tool call request in middleware
        middleware.record_mcp_event("mcp_tools_call_request", tool_call_request_dict)
        
        # Record Tool Input
        middleware.record_tool_input(TOOL_NAME, input_args)
        
        # Execute Remote Call (Encrypted + Signed)
        start_time = time.time()
        response = await client.call_tool(input_args, tool_call_request_id)
        duration = time.time() - start_time
        
        result = response["result"]
        signature = response["signature"]
        
        print(f"{GREEN}✅ Valid Signature received from '{TOOL_NAME}'{RESET}")
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
        
        # Record MCP tool call response in middleware
        middleware.record_mcp_event("mcp_tools_call_response", tool_call_response_dict)
        
        # Record Tool Output
        middleware.record_tool_output(TOOL_NAME, result, signature=signature)
        
        # 5. Finalize and Create Commitment
        final_answer = f"The result is {result}"
        middleware.record_model_output(final_answer)
        
        # Finalize middleware (includes all event and Langfuse integration)
        root_b64, canonical_log = middleware.finalize()
        
        print(f"\n{BOLD}Commitment Finalized:{RESET} {YELLOW}{root_b64}{RESET}")
        
        # Ensure canonical_log is bytes
        if isinstance(canonical_log, str):
            canonical_log_bytes = canonical_log.encode('utf-8')
        else:
            canonical_log_bytes = canonical_log
        
        log_file = "remote_workflow_agent_mcp.jsonl"
        with open(log_file, "wb") as f:
            f.write(canonical_log_bytes)
        print(f"[Disk] Saved canonical log to: {log_file}")

        # In-Process Verification
        print(f"\n{CYAN}Verifying Integrity locally (MCP 2024-11 protocol)...{RESET}")
        log_text = canonical_log_bytes.decode('utf-8') if isinstance(canonical_log_bytes, bytes) else canonical_log_bytes
        all_events = json.loads(log_text.strip())
        
        from src.crypto.verkle import VerkleAccumulator
        verifier = VerkleAccumulator(session_id="verify_session")
        for event in all_events:
            verifier.add_event(event)
        verifier.finalize()
        verified_root = verifier.get_root_b64()
        
        # Count MCP events
        mcp_init_requests = sum(1 for e in all_events if e.get("type") == "mcp_initialize_request")
        mcp_init_responses = sum(1 for e in all_events if e.get("type") == "mcp_initialize_response")
        mcp_tool_requests = sum(1 for e in all_events if e.get("type") == "mcp_tools_call_request")
        mcp_tool_responses = sum(1 for e in all_events if e.get("type") == "mcp_tools_call_response")
        
        if verified_root == root_b64:
            print(f"{GREEN}✅ VERIFICATION SUCCESSFUL: Log matches Commitment{RESET}")
            print(f"\n{BOLD}MCP Protocol Compliance Summary:{RESET}")
            print(f"  - Protocol Version: 2024-11")
            print(f"  - JSON-RPC Version: 2.0")
            print(f"  - Initialize Requests: {mcp_init_requests}")
            print(f"  - Initialize Responses: {mcp_init_responses}")
            print(f"  - Tool Call Requests: {mcp_tool_requests}")
            print(f"  - Tool Call Responses: {mcp_tool_responses}")
            print(f"  - Total Events: {len(all_events)}")
            print(f"  - Encryption: ECDH-AES256-GCM (SecureMCPClient)")
            print(f"  - Signatures: IBS-BLS12-381")
        else:
            print(f"{RED}❌ VERIFICATION FAILED{RESET}")
        
        print(f"\n{BOLD}To verify independently:{RESET}")
        print(f"python -m src.tools.verify_cli verify {log_file} '{root_b64}'")
        
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
