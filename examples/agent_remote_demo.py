"""
Agent Server with Remote Tool Integration.
Demonstrates the "Zero Trust" architecture where tools are remote and self-signing.

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

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.integrity import IntegrityMiddleware
from src.observability.langfuse_client import LangfuseClient 
from src.crypto.verkle import VerkleAccumulator
from src.config import get_settings
from src.transport.secure_mcp import SecureMCPClient

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

def check_langfuse_running():
    try:
        import requests
        response = requests.get("http://localhost:3000/api/public/health", timeout=1)
        return response.status_code == 200
    except:
        return False

async def main():
    print(f"{BOLD}Starting Secure Remote Tool Agent Demo (Async WebSocket)...{RESET}")
    
    # 1. Initialize Integrity & Observability
    middleware = IntegrityMiddleware()
    
    langfuse = None
    trace_id = None
    
    if check_langfuse_running():
        try:
            langfuse = LangfuseClient(middleware.session_id)
            trace_id = langfuse.create_trace(
                name="secure_remote_agent_demo",
                metadata={
                    "demo_type": "remote_tool_execution",
                    "transport": "ECDH-AES256",
                    "signature_scheme": "IBS-BLS12-381", 
                    "simulated_llm": True,
                    "tool": TOOL_NAME
                }
            )
            print(f"[Stats] Langfuse Trace created: {trace_id}")
        except Exception as e:
            print(f"{YELLOW}[Warn] Langfuse initialization failed: {e}{RESET}")
    else:
        print(f"{YELLOW}[Info] Langfuse not detected (running without observability){RESET}")
    
    print(f"Session ID: {middleware.session_id}")
    
    # 2. Connect to Remote Tool
    client = SecureMCPClient(TOOL_NAME, TOOL_HOST, TOOL_PORT, middleware)
    
    try:
        # Secure Handshake & Provisioning
        # Connects, performs ECDH, provisions IBS keys
        await client.connect_and_provision() 
        print(f"[Conn] Connected to '{TOOL_NAME}' on ws://{TOOL_HOST}:{TOOL_PORT} (Secure Channel Established)")
        
        # 3. Agent Workflow
        prompt = "Calculate 100 * 5"
        print(f"\n[Agent] Prompt: '{prompt}'")
        
        # Record Prompt
        middleware.record_prompt(prompt)
        if langfuse and trace_id:
            langfuse.add_event_to_trace(trace_id, "user_prompt", {"content": prompt})
        
        # 4. Call Remote Tool
        input_args = {"op": "mul", "a": 100, "b": 5}
        req_id = str(uuid.uuid4())
        
        print(f"[Agent] Calling tool '{TOOL_NAME}' with args {input_args}")
        
        # Record Tool Input
        middleware.record_tool_input(TOOL_NAME, input_args)
        if langfuse and trace_id:
            langfuse.add_event_to_trace(trace_id, "tool_start", {
                "tool": TOOL_NAME, 
                "input": input_args,
                "request_id": req_id
            })
        
        # Execute Remote Call (Encrypted + Signed)
        start_time = time.time()
        response = await client.call_tool(input_args, req_id)
        duration = time.time() - start_time
        
        result = response["result"]
        signature = response["signature"]
        
        print(f"{GREEN}✅ Valid Signature received from '{TOOL_NAME}'{RESET}")
        print(f"   Result: {result}")
        
        # Record Tool Output
        middleware.record_tool_output(TOOL_NAME, result, signature=signature)
        if langfuse and trace_id:
            langfuse.add_event_to_trace(trace_id, "tool_result", {
                "tool": TOOL_NAME, 
                "output": result, 
                "signature": signature,
                "duration": duration,
                "verified": True
            })
        
        # 5. Finalize
        final_answer = f"The result is {result}"
        middleware.record_model_output(final_answer)
        if langfuse and trace_id:
            langfuse.add_event_to_trace(trace_id, "model_response", {"content": final_answer})
        
        proof = middleware.finalize()
        root_b64 = proof['verkle_root_b64']
        
        print(f"\n{BOLD}Commitment Finalized:{RESET} {YELLOW}{root_b64}{RESET}")
        
        # Save Log to Disk (Missing functionality restored)
        canonical_log = middleware.get_canonical_log()
        with open(LOG_FILE, "wb") as f:
            f.write(canonical_log)
        print(f"[Disk] Saved canonical log to: {LOG_FILE}")

        # In-Process Verification (Missing functionality restored)
        print(f"\n{CYAN}Verifying Integrity locally...{RESET}")
        log_text = canonical_log.decode('utf-8')
        all_events = json.loads(log_text.strip())
        
        verifier = VerkleAccumulator(session_id="verify_session")
        for event in all_events:
            verifier.add_event(event)
        verifier.finalize()
        verified_root = verifier.get_root_b64()
        
        if verified_root == root_b64:
            print(f"{GREEN}✅ VERIFICATION SUCCESSFUL: Log matches Commitment{RESET}")
        else:
            print(f"{RED}❌ VERIFICATION FAILED{RESET}")

        # Record Commitment in Langfuse
        if langfuse and trace_id:
            langfuse.add_event_to_trace(trace_id, "commitment_finalized", {
                "verkle_root": root_b64,
                "event_count": middleware.counter,
                "verified_locally": (verified_root == root_b64)
            })
        
        print(f"\n{BOLD}To verify independently:{RESET}")
        print(f"python -m src.tools.verify_cli verify {LOG_FILE} '{root_b64}'")
        
    except Exception as e:
        print(f"\n{RED}❌ Error: {e}{RESET}")
        if langfuse and trace_id:
            langfuse.add_event_to_trace(trace_id, "error", {"error": str(e)})
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        # Ensure trace is finalized if the client supports it
        if langfuse and trace_id and hasattr(langfuse, 'finalize_trace'):
             langfuse.finalize_trace(trace_id)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
