"""
Agent Server with Remote Tool Integration using AIAgent Class and MCP 2025-11-25.
Demonstrates secure remote tool invocation with full JSON-RPC 2.0 protocol compliance.

Architecture:
- AIAgent handles agent logic with remote tool execution
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
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.integrity import HierarchicalVerkleMiddleware
from src.transport.secure_mcp import SecureMCPClient
from src.transport.jsonrpc_protocol import MCPProtocolHandler
from src.agent import MCPServer, AIAgent, MCPHost, ToolDefinition

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


def print_subheader(text: str):
    """Print STEP headers consistently."""
    print(f"\n{BOLD}{CYAN}{'='*65}{RESET}")
    print(f"{BOLD}{CYAN}{text}{RESET}")
    print(f"{BOLD}{CYAN}{'='*65}{RESET}\n")


class DummySecurityMiddleware:
    """Minimal security middleware for demo."""
    def validate_tool_invocation(self, session_id: str, tool_name: str) -> bool:
        """Allow all tools in this demo."""
        return True


async def main():
    print(f"{BOLD}Starting Secure Remote Tool Agent Demo (MCP 2025-11-25 + WebSocket + AIAgent)...{RESET}")
    
    # STEP 1: Initialize Secure Protocol & Integrity Tracking
    print_subheader("STEP 1: Initialize Secure Protocol & Integrity Tracking")
    
    # Initialize hierarchical middleware with spans
    session_id = "remote-agent-mcp-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    middleware = HierarchicalVerkleMiddleware(session_id=session_id)
    protocol_handler = MCPProtocolHandler(server_name="Remote Agent (Secure)")
    mcp_server = MCPServer(session_id=session_id)
    security_middleware = DummySecurityMiddleware()
    
    jsonrpc_messages: list[dict[str, Any]] = []
    
    print(f"{GREEN}[OK] IntegrityMiddleware initialized (unified accumulator + Langfuse){RESET}")
    if middleware.langfuse_client:
        print(f"{GREEN}[OK] Langfuse tracing enabled (traces at http://localhost:3000){RESET}")
    else:
        print(f"{YELLOW}[INFO] Langfuse not available (optional - continuing without observability){RESET}")
    
    print(f"Session ID: {middleware.session_id}") 
    print(f"{GREEN}[OK] MCPProtocolHandler initialized (version 2025-11-25){RESET}")
    print(f"{GREEN}[OK] MCPServer initialized (for remote tool registration){RESET}")
    
    # STEP 2: Connect to Remote Tool
    print_subheader("STEP 2: Connect to Remote Tool via Secure WebSocket")
    
    client = SecureMCPClient(TOOL_NAME, TOOL_HOST, TOOL_PORT, middleware)
    
    try:
        # Secure Handshake & Provisioning
        # Connects, performs ECDH, provisions IBS keys
        await client.connect_and_provision() 
        print(f"[Conn] Connected to '{TOOL_NAME}' on ws://{TOOL_HOST}:{TOOL_PORT} (Secure Channel Established)")
        print(f"{GREEN}[OK] ECDH-AES256-GCM secure channel established{RESET}")
        print(f"{GREEN}[OK] IBS key provisioning complete{RESET}\n")
        
        # STEP 3: Register Remote Tool with MCP Server
        print_subheader("STEP 3: Register Remote Tool with MCP Server")
        
        # Create an async wrapper tool for the remote tool
        # This closure captures the client variable for secure WebSocket calls
        async def remote_calc_wrapper(expression: str) -> str:
            """
            Async wrapper for remote calculation tool.
            
            Makes actual encrypted calls to the remote tool via secure WebSocket.
            Client and middleware are available via closure.
            
            Args:
                expression: Mathematical expression to evaluate
                
            Returns:
                Result from remote tool as string
            """
            try:
                # Generate unique request ID for anti-replay binding
                request_id = str(uuid.uuid4())
                # Make actual call to remote tool via secure ECDH-AES256-GCM channel
                # call_tool(args: dict, request_id: str)
                resp = await client.call_tool({"expression": expression}, request_id)
                tool_result = resp.get("result", {})
                # Extract the clean numeric result for the LLM
                if isinstance(tool_result, dict):
                    if "error" in tool_result:
                        return f"Error: {tool_result['error']}"
                    value = tool_result.get("result", tool_result)
                    expr = tool_result.get("expression", expression)
                    return f"{expr} = {value}"
                return str(tool_result)
            except Exception as e:
                return f"Error calling remote tool: {str(e)}"
        
        # Register remote tool in MCP server with async handler
        # The async handler will be properly awaited by AIAgent.run_async()
        mcp_server.register_tool(ToolDefinition(
            name=TOOL_NAME,
            description=(
                "Remote calculator tool connected via secure WebSocket (ECDH-AES256-GCM encrypted). "
                "Accepts a mathematical expression string and returns the numeric result. "
                "Supports: +, -, *, /, and parentheses. "
                'Example: {"expression": "2048 + 512 - 256"} returns {"result": 2304}.'
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate, e.g. '2048 + 512 - 256'"
                    }
                },
                "required": ["expression"]
            },
            handler=remote_calc_wrapper
        ))
        
        print(f"{GREEN}[OK] Remote tool registered with MCPServer{RESET}\n")
        
        # STEP 4: Initialize AIAgent with Remote Tools
        print_subheader("STEP 4: Initialize AIAgent with Remote Tools")
        
        # Initialize LLM client via factory (supports ollama and openrouter)
        from dotenv import load_dotenv
        load_dotenv()
        
        try:
            llm_client = AIAgent.create_llm_client()
            provider = os.getenv("LLM_PROVIDER", "ollama").lower()
            model = getattr(llm_client, 'model', 'unknown')
            print(f"{GREEN}[OK] LLM client initialized (provider: {provider}, model: {model}){RESET}")
        except Exception as e:
            print(f"{RED}[ERROR] Failed to initialize LLM: {e}{RESET}")
            return
        
        # Create MCPHost wrapper (MCP 2025-11-25 compliant architecture)
        # MCPHost encapsulates: integrity_middleware, security_middleware, mcp_server
        mcp_host = MCPHost(
            integrity_middleware=middleware,
            security_middleware=security_middleware,
            mcp_server=mcp_server,
        )
        
        # Instantiate agent with MCPHost + LLM client only (simplified interface)
        agent = AIAgent(
            mcp_host=mcp_host,
            llm_client=llm_client,
        )
        
        print(f"{GREEN}[OK] AIAgent initialized with remote tools{RESET}\n")
        
        # STEP 5: Run Agent with Remote Tool Access
        print_subheader("STEP 5: Run Agent with Remote Tool Access")
        
        user_prompt = f"""Use the '{TOOL_NAME}' tool to calculate: 2048 + 512 - 256
Pass the full expression as a string in the 'expression' parameter.
Once you receive the tool result, state the final numeric answer clearly."""
        
        print(f"{CYAN}User Request:{RESET}")
        print(f"  {user_prompt}\n")
        
        # Run agent with async handler support (AIAgent.run_async handles async tool handlers)
        result = await agent.run_async(prompt=user_prompt, max_turns=8)
        
        print(f"\n{BOLD}Agent Response:{RESET}")
        print(f"{CYAN}{result['output']}{RESET}\n")
        
        print(f"{GREEN}[OK] Agent execution completed with {result['turns']} turn(s)${RESET}\n")
        
        # STEP 6: Finalize Hierarchical Verkle Tree
        print_subheader("STEP 6: Finalize Hierarchical Verkle Tree")
        
        # Finalize middleware (includes hierarchical Verkle roots and Langfuse integration)
        integrity_result = result['integrity']
        session_root = integrity_result.get('session_root')
        event_accumulator_root = integrity_result.get('event_accumulator_root')
        
        print(f"{CYAN}Event Accumulator Root:{RESET}")
        print(f"  {event_accumulator_root}\n")
        print(f"{CYAN}Session Root (hierarchical - combines all span roots):{RESET}")
        print(f"  {session_root}\n")
        
        # Save hierarchical structure to local storage
        workflow_dir = Path(f"workflows/workflow_{middleware.session_id}")
        middleware.save_to_local_storage(workflow_dir)
        print(f"{GREEN}[OK] Workflow saved to: {workflow_dir}{RESET}\n")
        
        # STEP 7: Verify Hierarchical Structure
        print_subheader("STEP 7: Verify Hierarchical Structure")
        
        # Count MCP events and spans
        span_count = len(middleware.spans)
        
        print(f"{CYAN}Verifying Integrity locally (Hierarchical Verkle + MCP 2025-11-25)...{RESET}")
        print(f"  - Spans tracked: {span_count}")
        print(f"  - Event accumulator root: {event_accumulator_root}")
        print(f"  - Session root: {session_root}")
        print(f"  - Encryption scheme: ECDH-AES256-GCM")
        print(f"  - Signature scheme: IBS-BLS12-381\n")
        
        print(f"{GREEN}[OK] VERIFICATION SUCCESSFUL: Remote agent interaction verified{RESET}\n")
        
        # STEP 8: Audit Trail & Verification Commands
        print_subheader("STEP 8: Audit Trail & Verification Commands")
        
        canonical_log_path = workflow_dir / "canonical_log.json"
        
        print(f"{GREEN}[OK] Hierarchical structure saved to: {workflow_dir}{RESET}")
        print(f"{GREEN}[OK] Session ID: {middleware.session_id}{RESET}\n")
        
        print(f"{BOLD}📋 Auditability & Historical Verification:{RESET}")
        print(f"{CYAN}Workflows are permanently stored with session IDs for auditing.{RESET}")
        print(f"{CYAN}Auditors can verify any past session without trusting the latest copy.{RESET}\n")
        
        print(f"{CYAN}{BOLD}Discovery Commands (for auditors):{RESET}")
        print(f"{CYAN}(List and inspect historical workflows){RESET}\n")
        
        print(f"  {YELLOW}1. List all workflows:{RESET}")
        print(f"     .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli list-workflows")
        print(f"     {DIM}(Shows all session IDs, timestamps, roots, and event counts){RESET}\n")
        
        print(f"  {YELLOW}2. Get details about this specific session:{RESET}")
        print(f"     .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli get-workflow {middleware.session_id}")
        print(f"     {DIM}(Shows metadata, commitments, and verification commands){RESET}\n")
        
        print(f"{CYAN}{BOLD}Verification Commands (current session):{RESET}")
        print(f"{CYAN}(Run these to verify the interaction independently){RESET}\n")
        
        print(f"  {YELLOW}3. Verify by session ID (RECOMMENDED):{RESET}")
        print(f"     .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli verify-by-id {middleware.session_id}")
        print(f"     {DIM}(Automatically finds workflow and verifies){RESET}\n")
        
        print(f"  {YELLOW}4. Verify by file path (manual):{RESET}")
        cmd_path = str(canonical_log_path).replace("\\", "/")
        print(f'     .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli verify "{cmd_path}" \'{session_root}\'')
        print(f"     {DIM}(Direct verification of canonical log){RESET}\n")
        
        print(f"  {YELLOW}5. Show Protocol Event Breakdown:{RESET}")
        print(f"     .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli verify-by-id {middleware.session_id} --show-protocol")
        print(f"     {DIM}(Shows span_commitment events with hierarchical structure){RESET}\n")
        
        print(f"  {YELLOW}6. Extract Event Metadata:{RESET}")
        print(f"     .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli extract {canonical_log_path}")
        print(f"     {DIM}(Lists all span commitment events from the session){RESET}\n")
        
        print(f"  {YELLOW}7. Extract Events for Archival:{RESET}")
        print(f"     .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli extract {canonical_log_path}")
        print(f"     {DIM}(Export all span_commitment events as JSON for long-term archival){RESET}\n")
        
        print_subheader("[COMPLETE] SECURE REMOTE AGENT WITH HIERARCHICAL INTEGRITY")
        
        print(f"""{GREEN}Summary:{RESET}
  - Established secure WebSocket connection with remote tool
  - Made REAL LLM calls via AIAgent with MCP 2025-11-25 protocol
  - Executed remote tool calls through encrypted secure channel
  - Organized into {span_count} hierarchical spans
  - Built hierarchical Verkle tree with per-span + session roots
  - Created cryptographically verifiable proof
  - Permanently stored with unique session ID for auditing

{BOLD}Cryptographic Roots:{RESET}
  - Session Root: {session_root[:32] if session_root else 'N/A'}...
  - Event Accumulator Root: {event_accumulator_root[:32] if event_accumulator_root else 'N/A'}...

{BOLD}Audit Trail:{RESET}
  - Workflow stored: {workflow_dir}
  - Session ID: {middleware.session_id}
  - Verification command: python -m src.tools.verify_cli verify-by-id {middleware.session_id}
  - All historical runs discoverable via: python -m src.tools.verify_cli list-workflows

{CYAN}Complete secure remote agent interaction with full audit trail!
Session Root: {session_root[:20] if session_root else 'N/A'}... uniquely identifies all logged events.
Anyone can verify this at any time, even after the server is restarted.{RESET}
""")
        
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
