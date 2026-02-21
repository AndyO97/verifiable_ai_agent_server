"""
Remote Tool Simulator with MCP 2024-11 Compliance.
This script mimics a tool running in a SEPARATE environment (e.g., different server/container).
It holds its own Identity Key ($SK_{ID}$) and signs its own outputs with full JSON-RPC response binding.

Architecture:
- Tool runs as SecureMCPServer (asyncio WebSocket + encryption)
- Each tool response is wrapped in JSON-RPC 2.0 format
- IBS (Identity-Based Signatures) authenticate full JSON-RPC response object
- Signature binding includes request ID (prevents replay attacks)
- All communication encrypted with ECDH-AES256-GCM

Signature Binding Strategy (Option B - Recommended):
- Sign the full JSON-RPC response object (not just the result value)
- Bind signature to request ID (in JSON-RPC object)
- This ensures: tool output authenticity + request-response correlation
- Example:
  Canonical JSON of full response:
  {"jsonrpc":"2.0","result":{"output":500},"id":"uuid-123"}
  Signed with IBS: signature = tool.sign_ibs(canonical_json(full_response))

Usage:
1. Run with this command in PowerShell:
    & "./venv/Scripts/python.exe" examples/remote_tool.py
2. Enter the Tool Name (e.g., "remote_calc")
3. Paste the Private Key provided by the Key Authority (from the other script)
4. Use it to process requests and generate signed JSON-RPC responses.


"""

import sys
import os
import asyncio
import json
from typing import Any, Dict

# Add path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.transport.secure_mcp import SecureMCPServer

TOOL_NAME = "remote_calc"

def calculator_logic(args):
    """
    The actual business logic of the tool.
    
    NOTE: This function returns the raw result. The SecureMCPServer will:
    1. Wrap result in JSON-RPC 2.0 response format
    2. Create canonical JSON of full response (including request ID)
    3. Sign full response using IBS (Option B - Recommended)
    4. Return signed JSON-RPC response to agent
    
    This ensures signature is bound to request ID, preventing replay attacks
    while maintaining full JSON-RPC protocol compliance.
    """
    op = args.get("op")
    a = args.get("a", 0)
    b = args.get("b", 0)
    
    if op == "add":
        return a + b
    elif op == "sub":
        return a - b
    elif op == "mul":
        return a * b
    else:
        return f"Unknown Operation: {op}"

if __name__ == "__main__":
    async def main():
        # Start the Secure Server (Modularized)
        server = SecureMCPServer(TOOL_NAME, port=5555)
        
        print("=" * 65)
        print("[STARTING] Secure Remote Tool Server")
        print("=" * 65)
        print(f"Tool Name: {TOOL_NAME}")
        print(f"Port: 5555")
        print(f"Encryption: ECDH-AES256-GCM")
        print(f"Signatures: IBS-BLS12-381")
        print(f"\n[WAITING] Listening for agent connections...")
        print("=" * 65 + "\n")
        
        # Note: server.start is an async generator or loop manager
        await server.start(calculator_logic)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOPPED] Tool stopped.")
