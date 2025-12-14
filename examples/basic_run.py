"""
Example: Basic agent run with integrity tracking

This demonstrates the complete Phase 1 workflow of the verifiable AI agent server:

1. Initialize integrity middleware (event capture + Verkle accumulation)
2. Register tools with MCP server and security layer
3. Execute agent workflow:
   - Record initial prompt (counter 0)
   - Call tool 1: add(15, 27) → 42 (counters 1-2)
   - Call tool 2: multiply(42, 2) → 84 (counters 3-4)
   - Record final output (counter 5)
4. Finalize and generate Verkle root commitment

Output: Deterministic Verkle root + canonical log hash, enabling third-party verification
that all events were captured exactly once in order, with no tampering or replay.
"""

from src.integrity import IntegrityMiddleware
from src.agent import AIAgent, MCPServer, ToolDefinition
from src.security import SecurityMiddleware


def calculator_add(a: float, b: float) -> float:
    """Simple addition tool"""
    return a + b


def calculator_multiply(a: float, b: float) -> float:
    """Simple multiplication tool"""
    return a * b


def main():
    """Run a basic example agent"""
    
    # Initialize components
    session_id = "example-run-001"
    
    integrity = IntegrityMiddleware(session_id)
    security = SecurityMiddleware()
    mcp = MCPServer(session_id)
    
    # Register tools with server
    add_tool = ToolDefinition(
        name="add",
        description="Add two numbers",
        input_schema={"a": float, "b": float},
        handler=calculator_add
    )
    mcp.register_tool(add_tool)
    
    multiply_tool = ToolDefinition(
        name="multiply",
        description="Multiply two numbers",
        input_schema={"a": float, "b": float},
        handler=calculator_multiply
    )
    mcp.register_tool(multiply_tool)
    
    # Register authorized tools with security
    security.register_authorized_tools(["add", "multiply"])
    
    # Create agent
    agent = AIAgent(integrity, security, mcp)
    
    # Example: Run agent with a prompt
    prompt = "Please calculate 15 + 27 and then multiply the result by 2"
    print(f"Prompt: {prompt}")
    
    # Record initial prompt
    integrity.record_prompt(prompt)
    
    # Simulate tool execution
    # Tool 1: Add
    integrity.record_tool_input("add", {"a": 15, "b": 27})
    result1 = calculator_add(15, 27)
    integrity.record_tool_output("add", result1)
    print(f"Tool result (add): {result1}")
    
    # Tool 2: Multiply
    integrity.record_tool_input("multiply", {"a": result1, "b": 2})
    result2 = calculator_multiply(result1, 2)
    integrity.record_tool_output("multiply", result2)
    print(f"Tool result (multiply): {result2}")
    
    # Record final output
    final_output = f"The answer is {result2}"
    integrity.record_model_output(final_output)
    print(f"Final output: {final_output}")
    
    # Finalize and commit
    integrity_result = integrity.finalize()
    
    # Display results
    print("\n" + "="*60)
    print("RUN COMPLETED - INTEGRITY METADATA")
    print("="*60)
    print(f"Session ID:        {integrity_result['session_id']}")
    print(f"Event Count:       {integrity_result['event_count']}")
    print(f"Verkle Root (B64): {integrity_result['verkle_root_b64']}")
    print(f"Log Hash (SHA256): {integrity_result['canonical_log_hash']}")
    print(f"Finalized At:      {integrity_result['finalized_at']}")
    print("="*60)
    
    # Get canonical log
    canonical_log = integrity.get_canonical_log()
    print(f"\nCanonical log size: {len(canonical_log)} bytes")
    
    # In a real scenario, this would be:
    # 1. Stored in S3/Blob storage
    # 2. Hash stored in database
    # 3. Verkle root stored in OTel span and Langfuse
    # 4. Available for third-party verification


if __name__ == "__main__":
    main()
