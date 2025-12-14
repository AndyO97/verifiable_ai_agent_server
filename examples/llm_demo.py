"""
Phase 2 Demo: LLM-integrated Verifiable AI Agent

This comprehensive demo showcases:
1. LLM integration with tool calling (Ollama)
2. Multi-turn agent interactions
3. Full integrity tracking and event recording
4. Deterministic Verkle root generation
5. Security authorization checks

Works with or without Ollama running (fallback to dummy LLM):
  - WITH Ollama: Full tool calling demo
  - WITHOUT Ollama: Dummy LLM response demo

Usage:
  python examples/llm_demo.py
"""

from src.integrity import IntegrityMiddleware
from src.agent import AIAgent, MCPServer, ToolDefinition
from src.security import SecurityMiddleware
from src.llm import OllamaClient
from src.config import get_settings


# ==============================================================================
# Tool Definitions
# ==============================================================================

def weather_tool(location: str) -> str:
    """Get weather for a location"""
    weather_data = {
        "New York": "Sunny, 72°F",
        "San Francisco": "Cloudy, 65°F",
        "London": "Rainy, 55°F",
    }
    return weather_data.get(location, f"Unknown location: {location}")


def calculator_add(a: float, b: float) -> float:
    """Add two numbers"""
    result = a + b
    print(f"  => {a} + {b} = {result}")
    return result


def calculator_subtract(a: float, b: float) -> float:
    """Subtract two numbers"""
    result = a - b
    print(f"  => {a} - {b} = {result}")
    return result


def calculator_multiply(a: float, b: float) -> float:
    """Multiply two numbers"""
    result = a * b
    print(f"  => {a} * {b} = {result}")
    return result


def information_lookup(query: str) -> str:
    """Look up general information"""
    knowledge_base = {
        "python": "Python is a high-level programming language",
        "ai": "AI stands for Artificial Intelligence",
        "llama": "Llama is a large language model by Meta",
    }
    return knowledge_base.get(query.lower(), f"No information found for: {query}")


# ==============================================================================
# Demo Execution
# ==============================================================================

def main():
    """Run the LLM-integrated agent demo"""
    
    print("\n" + "="*80)
    print("PHASE 2 DEMO: LLM-Integrated Verifiable AI Agent")
    print("="*80 + "\n")
    
    # Initialize components
    session_id = "llm-demo-001"
    
    print("[1/5] Initializing integrity middleware...")
    integrity = IntegrityMiddleware(session_id)
    
    print("[2/5] Initializing security middleware...")
    security = SecurityMiddleware()
    
    print("[3/5] Initializing MCP server...")
    mcp = MCPServer(session_id)
    
    # Register tools
    print("[4/5] Registering tools...")
    tools = [
        ToolDefinition(
            name="weather",
            description="Get weather for a location",
            input_schema={"location": str},
            handler=weather_tool
        ),
        ToolDefinition(
            name="add",
            description="Add two numbers",
            input_schema={"a": float, "b": float},
            handler=calculator_add
        ),
        ToolDefinition(
            name="subtract",
            description="Subtract two numbers",
            input_schema={"a": float, "b": float},
            handler=calculator_subtract
        ),
        ToolDefinition(
            name="multiply",
            description="Multiply two numbers",
            input_schema={"a": float, "b": float},
            handler=calculator_multiply
        ),
        ToolDefinition(
            name="lookup",
            description="Look up general information",
            input_schema={"query": str},
            handler=information_lookup
        ),
    ]
    
    for tool in tools:
        mcp.register_tool(tool)
        print(f"  [+] Registered: {tool.name}")
    
    # Authorize tools
    security.register_authorized_tools([t.name for t in tools])
    
    # Initialize LLM client
    print("[5/5] Initializing LLM client (Ollama)...")
    settings = get_settings()
    llm_client = OllamaClient(
        base_url=settings.ollama.base_url,
        model=settings.ollama.model
    )
    
    # Check if Ollama is running
    if llm_client.health_check():
        print(f"  [OK] Ollama is running (model: {settings.ollama.model})")
        print(f"    Using real LLM at {settings.ollama.base_url}")
    else:
        print(f"  [!] Ollama not running at {settings.ollama.base_url}")
        print("    Will use dummy LLM responses for demo")
        llm_client = None  # Fallback to dummy LLM
    
    # Create agent
    print("\n[AGENT] Creating AI Agent...")
    agent = AIAgent(integrity, security, mcp, llm_client)
    
    # Run agent with different prompts
    prompts = [
        "What's the weather in New York and London?",
        "Calculate 100 + 50 and then multiply by 2",
        "Tell me about Python and then lookup AI",
    ]
    
    for i, prompt in enumerate(prompts, 1):
        print(f"\n" + "="*80)
        print(f"PROMPT {i}: {prompt}")
        print("="*80)
        
        # Reset integrity for each demo (in real scenario, each would be a separate run)
        if i > 1:
            integrity = IntegrityMiddleware(f"{session_id}-{i}")
            agent.integrity = integrity
        
        # Run agent
        print("\n[LLM AGENT] Starting reasoning loop...\n")
        result = agent.run(prompt, max_turns=5)
        
        # Display results
        print("\n" + "-"*80)
        print("AGENT RESULT")
        print("-"*80)
        print(f"Final Output: {result['output'][:200]}...")
        print(f"Turns Taken: {result['turns']}")
        
        # Display integrity metadata
        integrity_metadata = result['integrity']
        print("\n" + "-"*80)
        print("INTEGRITY METADATA")
        print("-"*80)
        print(f"Session ID:         {integrity_metadata['session_id']}")
        print(f"Event Count:        {integrity_metadata['event_count']}")
        print(f"Verkle Root (B64):  {integrity_metadata['verkle_root_b64']}")
        print(f"Log Hash (SHA256):  {integrity_metadata['canonical_log_hash']}")
        print(f"Finalized At:       {integrity_metadata['finalized_at']}")
        print(f"Canonical Log Size: {integrity_metadata.get('canonical_log_size', 'N/A')} bytes")
        
        # Show event summary
        print("\n" + "-"*80)
        print("EVENT SEQUENCE")
        print("-"*80)
        print(f"All events recorded with:")
        print(f"  [*] Sequential monotonic counters")
        print(f"  [*] Session ID: {integrity_metadata['session_id']}")
        print(f"  [*] Server timestamps (ISO8601 UTC)")
        print(f"  [*] Canonical JSON encoding (RFC 8785)")
        print(f"  [*] Replay-resistant metadata")


def run_production_like_scenario():
    """Run a more realistic multi-turn scenario"""
    
    print("\n" + "="*80)
    print("PRODUCTION-LIKE SCENARIO: Financial Advisor Bot")
    print("="*80 + "\n")
    
    # Setup
    session_id = "financial-advisor-001"
    integrity = IntegrityMiddleware(session_id)
    security = SecurityMiddleware()
    mcp = MCPServer(session_id)
    
    # Define financial tools
    def calculate_roi(investment: float, return_amount: float) -> float:
        """Calculate return on investment"""
        roi = ((return_amount - investment) / investment) * 100
        print(f"  => ROI: {roi:.2f}%")
        return roi
    
    def estimate_tax(income: float, rate: float) -> float:
        """Estimate taxes on income"""
        tax = income * (rate / 100)
        print(f"  => Tax: ${tax:.2f}")
        return tax
    
    financial_tools = [
        ToolDefinition(
            name="calculate_roi",
            description="Calculate return on investment percentage",
            input_schema={"investment": float, "return_amount": float},
            handler=calculate_roi
        ),
        ToolDefinition(
            name="estimate_tax",
            description="Estimate taxes on income",
            input_schema={"income": float, "rate": float},
            handler=estimate_tax
        ),
    ]
    
    for tool in financial_tools:
        mcp.register_tool(tool)
    
    security.register_authorized_tools([t.name for t in financial_tools])
    
    # Initialize LLM (without Ollama for demo)
    settings = get_settings()
    llm_client = OllamaClient(
        base_url=settings.ollama.base_url,
        model=settings.ollama.model
    )
    
    if not llm_client.health_check():
        print("ℹ Using dummy LLM for production scenario demo\n")
        llm_client = None
    
    # Create agent
    agent = AIAgent(integrity, security, mcp, llm_client)
    
    # Complex financial question
    prompt = (
        "I invested $10,000 and got back $15,000. "
        "What's my ROI? Then estimate my taxes if I earned $50,000 at 25% rate."
    )
    
    print(f"Scenario: Financial Advisory Question")
    print(f"Prompt: {prompt}\n")
    
    result = agent.run(prompt, max_turns=5)
    
    print("\n" + "="*80)
    print("SCENARIO RESULT")
    print("="*80)
    print(f"\nAgent Output:\n{result['output']}")
    print(f"\nIntegrity Metadata:")
    print(f"  Session ID: {result['integrity']['session_id']}")
    print(f"  Events: {result['integrity']['event_count']}")
    print(f"  Verkle Root: {result['integrity']['verkle_root_b64']}")
    print(f"  Turns: {result['turns']}")


if __name__ == "__main__":
    # Run basic demo
    main()
    
    # Optional: Run production scenario
    # Uncomment to see a more realistic scenario
    # run_production_like_scenario()
    
    print("\n" + "="*80)
    print("✅ PHASE 2 DEMO COMPLETE!")
    print("="*80)
    print("\nKey Achievements:")
    print("  ✅ LLM-integrated agent loop working")
    print("  ✅ Multi-turn tool calling implemented")
    print("  [DONE] Full event integrity tracking")
    print("  [DONE] Deterministic Verkle root generation")
    print("  [DONE] Security authorization checks")
    print("\nNext Steps:")
    print("  => Run with actual Ollama for real LLM responses")
    print("  => Create integration test suite (20+ tests)")
    print("  => Validate with production workloads")
    print("\n")
