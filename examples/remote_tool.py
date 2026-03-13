"""
Remote Tool Simulator with MCP 2025-11-25 Compliance.
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
    Remote calculator business logic.
    
    Accepts two input modes:
      1. Expression string:  {"expression": "2048 + 512 - 256"}
      2. Structured operation: {"op": "add", "a": 10, "b": 5}
    
    Returns a dict with the input echo and computed result,
    or {"error": "..."} on failure.
    
    NOTE: The SecureMCPServer wraps the return value in a signed
    JSON-RPC 2.0 response (IBS over the full response object).
    """
    # --- Mode 1: expression string (preferred by LLMs) ---
    expression = args.get("expression")
    if expression is not None:
        expr_str = str(expression).strip()
        # Allow only digits, basic math operators, parentheses, spaces, and dots
        allowed = set("0123456789+-*/.() ")
        if not all(ch in allowed for ch in expr_str):
            return {"error": f"Invalid characters in expression: {expr_str}"}
        try:
            result = eval(expr_str, {"__builtins__": {}}, {})
            return {"expression": expr_str, "result": result}
        except Exception as e:
            return {"error": f"Failed to evaluate '{expr_str}': {e}"}

    # --- Mode 2: structured operation ---
    op = args.get("op")
    a = args.get("a", 0)
    b = args.get("b", 0)

    try:
        a = float(a)
        b = float(b)
    except (TypeError, ValueError):
        return {"error": f"Arguments a={a!r}, b={b!r} must be numbers"}

    operations = {
        "add": lambda: a + b,
        "sub": lambda: a - b,
        "mul": lambda: a * b,
        "div": lambda: a / b if b != 0 else (_ for _ in ()).throw(ZeroDivisionError("Division by zero")),
    }

    if op not in operations:
        return {"error": f"Unknown operation '{op}'. Supported: add, sub, mul, div"}

    try:
        result = operations[op]()
        # Return int when the result is a whole number
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return {"op": op, "a": a, "b": b, "result": result}
    except Exception as e:
        return {"error": str(e)}

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
