"""
Agent Demo with Multiple Tools (MCP 2026-02)
Efficient agent demo with 5 tool definitions and 5 predefined prompts for easy testing.

Tools:
- Weather (OpenWeatherMap API)
- Currency Exchange (exchangerate-api)
- Math Calculator (local eval)
- Wikipedia Search (wikipedia API)
- Datetime Info (local)

Usage:
- Change PROMPT_INDEX to select which prompt/tool to test.
- Run: python examples/agent_multi_tool_demo.py
& "./venv/Scripts/python.exe" examples/agent_multi_tool_demo.py
"""


import os
import sys
import asyncio
import ast
import operator
from typing import Any
from datetime import datetime, timedelta, timezone
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent import MCPServer, AIAgent, MCPHost, ToolDefinition
from src.integrity import HierarchicalVerkleMiddleware

# --- Tool Definitions ---

async def weather_tool(city=None, **kwargs) -> str:
    """Get current weather for a city using OpenWeatherMap API. Accepts 'city' or 'q' as input."""
    import requests
    from src.config import get_settings
    if city is None:
        city = kwargs.get('q')
    if not city:
        return "Error: No city provided."
    settings = get_settings()
    api_key = settings.openweather.api_key
    base_url = settings.openweather.base_url
    if not api_key:
        return "Error: OPENWEATHER_API_KEY not set."
    url = f"{base_url}/weather?q={city}&appid={api_key}&units=metric"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if resp.status_code != 200:
            return f"Error: {data.get('message', 'API error')}"
        temp = data['main']['temp']
        desc = data['weather'][0]['description']
        return f"Weather in {city}: {temp}°C, {desc}"
    except Exception as e:
        return f"Error: {str(e)}"

async def currency_tool(from_currency: str, to_currency: str) -> str:
    """Get exchange rate from one currency to another using exchangerate-api."""
    import requests
    url = f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if resp.status_code != 200:
            return f"Error: {data.get('error', 'API error')}"
        rate = data['rates'].get(to_currency.upper())
        if rate is None:
            return f"Error: Currency {to_currency} not found."
        return f"1 {from_currency.upper()} = {rate} {to_currency.upper()}"
    except Exception as e:
        return f"Error: {str(e)}"

async def math_tool(expression: str = None, **kwargs) -> str:
    """Evaluate a mathematical expression locally. Accepts 'expression' or any argument starting with 'expr'."""
    # Accept 'expression' or any argument starting with 'expr'
    if expression is None:
        for k, v in kwargs.items():
            if k.startswith('expr'):
                expression = v
                break
    if not expression:
        return "Error: No expression provided."
    
    # Allowed operators: +, -, *, /, //, %, **
    ALLOWED_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }
    
    # Allowed functions: abs, min, max, sum, pow, round
    ALLOWED_FUNCS = {
        'abs': abs, 'min': min, 'max': max, 'sum': sum, 'pow': pow, 'round': round,
    }
    
    def safe_eval_node(node):
        """Safely evaluate an AST node (no eval, no builtins, no attribute access)."""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Older Python versions
            return node.n
        elif isinstance(node, ast.BinOp):
            left = safe_eval_node(node.left)
            right = safe_eval_node(node.right)
            op = ALLOWED_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Operation not allowed")
            return op(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = safe_eval_node(node.operand)
            op = ALLOWED_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Operation not allowed")
            return op(operand)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Complex function calls not allowed")
            func_name = node.func.id
            if func_name not in ALLOWED_FUNCS:
                raise ValueError(f"Function '{func_name}' not allowed")
            args = [safe_eval_node(arg) for arg in node.args]
            return ALLOWED_FUNCS[func_name](*args)
        else:
            raise ValueError(f"Expression type not allowed")
    
    try:
        tree = ast.parse(expression, mode='eval')
        result = safe_eval_node(tree.body)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"

async def wikipedia_tool(query: str) -> str:
    """Search Wikipedia for a summary."""
    import requests
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '%20')}"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MCPAgent/1.0; +https://example.com/)"}
        resp = requests.get(url, timeout=5, headers=headers)
        if resp.status_code != 200:
            # Try to parse error detail if possible
            try:
                data = resp.json()
                return f"Error: {data.get('detail', data.get('message', 'API error'))} (HTTP {resp.status_code})"
            except Exception:
                return f"Error: Wikipedia API returned HTTP {resp.status_code} with no JSON body."
        if not resp.content or not resp.text.strip():
            return "Error: Wikipedia API returned empty response."
        try:
            data = resp.json()
        except Exception as e:
            return f"Error: Wikipedia API response was not valid JSON: {str(e)}"
        return data.get('extract', 'No summary found.')
    except Exception as e:
        return f"Error: Wikipedia request failed: {str(e)}"

async def datetime_tool(format: str = "%Y-%m-%d %H:%M:%S", utc_offset: int = 0, **kwargs) -> str:
    """Return current datetime. By default returns local system time. Provide utc_offset to see UTC with conversion to that timezone."""
    try:
        # Check if any parameter contains "offset" in its name
        offset_param_found = None
        if utc_offset == 0:  # Only look in kwargs if utc_offset wasn't explicitly set
            for key in kwargs.keys():
                if 'offset' in key.lower():
                    offset_param_found = key
                    try:
                        utc_offset = int(kwargs[key])
                    except (ValueError, TypeError):
                        pass
                    break
        
        # Prepare list of ignored parameters (excluding the offset parameter if found)
        ignored_params = [k for k in kwargs.keys() if k != offset_param_found]
        has_extra_params = len(ignored_params) > 0
        extra_params_note = f" (Note: I only accept 'format' and 'utc_offset' parameters, ignoring: {', '.join(ignored_params)})" if has_extra_params else ""
        
        if utc_offset != 0:
            # User provided offset: show UTC and converted local time
            now = datetime.now(timezone.utc)
            utc_time = now.strftime(format)
            local_time = (now + timedelta(hours=utc_offset)).strftime(format)
            return f"Current UTC time: {utc_time}. Local time (UTC{utc_offset:+d}): {local_time}.{extra_params_note}"
        else:
            # Default: show system local time
            local_time = datetime.now().strftime(format)
            return f"The current date and time is {local_time}.{extra_params_note}"
    except Exception as e:
        return f"Error: {str(e)}"

# --- MCP Server Setup ---
mcp_server = MCPServer(session_id="multi-tool-demo-" + datetime.now().strftime("%Y%m%d-%H%M%S"))

mcp_server.register_tool(ToolDefinition(
    name="weather",
    description="Get current weather for a city (OpenWeatherMap API).",
    input_schema={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"}
        },
        "required": ["city"]
    },
    handler=weather_tool
))
mcp_server.register_tool(ToolDefinition(
    name="currency",
    description="Get exchange rate between two currencies (exchangerate-api).",
    input_schema={
        "type": "object",
        "properties": {
            "from_currency": {"type": "string", "description": "Source currency code"},
            "to_currency": {"type": "string", "description": "Target currency code"}
        },
        "required": ["from_currency", "to_currency"]
    },
    handler=currency_tool
))
mcp_server.register_tool(ToolDefinition(
    name="math",
    description="Evaluate a mathematical expression locally.",
    input_schema={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Math expression"}
        },
        "required": ["expression"]
    },
    handler=math_tool
))
mcp_server.register_tool(ToolDefinition(
    name="wikipedia",
    description="Search Wikipedia for a summary.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term"}
        },
        "required": ["query"]
    },
    handler=wikipedia_tool
))
mcp_server.register_tool(ToolDefinition(
    name="datetime",
    description="Get current date and time. Returns local system time by default (no parameters needed). To get UTC with conversion to other timezones, provide 'utc_offset' (hours from UTC, e.g., -5 for Miami/EST, +1 for CET).",
    input_schema={
        "type": "object",
        "properties": {
            "format": {"type": "string", "description": "Datetime format (e.g., '%Y-%m-%d %H:%M:%S'). Default shows full datetime.", "default": "%Y-%m-%d %H:%M:%S"},
            "utc_offset": {"type": "integer", "description": "Optional: UTC offset in hours (e.g., -5 for Miami/EST, +1 for CET). Only provide if you want UTC time with timezone conversion. Omit for local system time.", "default": 0}
        },
        "required": []
    },
    handler=datetime_tool
))

# --- Predefined Prompts ---
PROMPTS = [
    "Use the 'weather' tool to get the weather in London. Pass the city as 'London'. State the temperature and description.",
    "Use the 'currency' tool to get the exchange rate from USD to EUR. Pass 'USD' as from_currency and 'EUR' as to_currency. State the rate.",
    "Use the 'math' tool to calculate 2048 + 512 - 256. Pass the expression as '2048 + 512 - 256'. State the result.",
    "Use the 'wikipedia' tool to get a summary about 'Quantum computing'. Pass the query as 'Quantum computing'. State the summary.",
    "Use the 'datetime' tool to get the current datetime. State the result."
]

PROMPT_INDEX = int(os.getenv("PROMPT_INDEX", 4))  # Change this to test different tools

async def main():
    middleware = HierarchicalVerkleMiddleware(session_id=mcp_server.session_id)
    try:
        llm_client = AIAgent.create_llm_client()
    except Exception as e:
        print(f"Error initializing LLM client: {e}")
        return
    class DummySecurityMiddleware:
        def validate_tool_invocation(self, session_id: str, tool_name: str) -> bool:
            return True

    mcp_host = MCPHost(
        integrity_middleware=middleware,
        security_middleware=DummySecurityMiddleware(),
        mcp_server=mcp_server,
    )

    agent = AIAgent(
        mcp_host=mcp_host,
        llm_client=llm_client
    )
    prompt = PROMPTS[PROMPT_INDEX]
    print(f"\nPrompt ({PROMPT_INDEX}): {prompt}\n")
    result = await agent.run_async(prompt=prompt, max_turns=6)
    print(f"Agent Output:\n{result['output']}\n")
    print(f"Session Root: {result['integrity'].get('session_root', 'N/A')}")
    print(f"Event Accumulator Root: {result['integrity'].get('event_accumulator_root', 'N/A')}\n")
    workflow_dir = Path("workflows") / f"workflow_{middleware.session_id}"
    middleware.save_to_local_storage(workflow_dir)
    print(f"Workflow saved to: {workflow_dir}\n")

if __name__ == "__main__":
    asyncio.run(main())
