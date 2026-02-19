"""
Remote Tool Simulator.
This script mimics a tool running in a SEPARATE environment (e.g., different server/container).
It holds its own Identity Key ($SK_{ID}$) and signs its own outputs.

Usage:
1. Run with this command in PowerShell:
    & "./venv/Scripts/python.exe" examples/remote_tool.py
2. Enter the Tool Name (e.g., "remote_calc")
3. Paste the Private Key provided by the Key Authority (from the other script)
4. Use it to process requests and generate signed responses.


"""

import sys
import os
import asyncio

# Add path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.transport.secure_mcp import SecureMCPServer

TOOL_NAME = "remote_calc"

def calculator_logic(args):
    """The actual business logic of the tool"""
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
        # Note: server.start is an async generator or loop manager
        await server.start(calculator_logic)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopping...")
