"""
Backend MCP Agent Server (MCP 2026-02)

This script defines the same tools and MCP server setup as agent_multi_tool_demo.py, but exposes an async function to answer prompts from the frontend via FastAPI.
"""

import os
import sys
import asyncio
from typing import Any
from datetime import datetime
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent import MCPServer, AIAgent, ToolDefinition
from src.integrity import HierarchicalVerkleMiddleware

# --- Tool Definitions ---

async def weather_tool(city=None, **kwargs) -> str:
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
    if expression is None:
        for k, v in kwargs.items():
            if k.startswith('expr'):
                expression = v
                break
    if not expression:
        return "Error: No expression provided."
    try:
        result = eval(expression, {"__builtins__": {}})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"

async def wikipedia_tool(query: str) -> str:
    import requests
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ', '%20')}"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MCPAgent/1.0; +https://example.com/)"}
        resp = requests.get(url, timeout=5, headers=headers)
        if resp.status_code != 200:
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

async def datetime_tool(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    try:
        now = datetime.now().strftime(format)
        return f"Current datetime: {now}"
    except Exception as e:
        return f"Error: {str(e)}"

# --- MCP Server Setup ---
mcp_server = MCPServer(session_id="backend-mcp-agent-" + datetime.now().strftime("%Y%m%d-%H%M%S"))

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
    description="Return current datetime in specified format.",
    input_schema={
        "type": "object",
        "properties": {
            "format": {"type": "string", "description": "Datetime format", "default": "%Y-%m-%d %H:%M:%S"}
        },
        "required": []
    },
    handler=datetime_tool
))

# --- Agent Setup ---
async def answer_prompt(prompt: str) -> str:
    """
    Run the agent on the given prompt and return the output string.
    """
    middleware = HierarchicalVerkleMiddleware(session_id=mcp_server.session_id)
    try:
        llm_client = AIAgent.create_llm_client()
    except Exception as e:
        return f"Error initializing LLM client: {e}"
    class DummySecurityMiddleware:
        def validate_tool_invocation(self, session_id: str, tool_name: str) -> bool:
            return True
    agent = AIAgent(
        integrity_middleware=middleware,
        security_middleware=DummySecurityMiddleware(),
        mcp_server=mcp_server,
        llm_client=llm_client
    )
    try:
        result = await agent.run_async(prompt=prompt, max_turns=6)
        return result['output']
    except Exception as e:
        return f"Error running agent: {e}"
