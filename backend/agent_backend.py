"""
Backend MCP Agent Server (MCP 2026-02)

This script defines the same tools and MCP server setup as agent_multi_tool_demo.py, but exposes an async function to answer prompts from the frontend via FastAPI.
"""

import os
import sys
import asyncio
import requests
import re
from typing import Any, List
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
from src.security import SecurityMiddleware
from src.config import get_settings

# --- Safe Math Expression Evaluator ---

class SafeMathEvaluator:
    """
    Secure mathematical expression parser and evaluator.
    No external dependencies. Pure Python implementation.
    
    Allowed operations:
    - Arithmetic: +, -, *, /, //, **, %
    - Parentheses for grouping
    - Functions: abs(), round(), min(), max(), sum()
    - Numbers: integers and floats (e.g., 3.14, -5, 0.5)
    
    NOT allowed:
    - Variables or assignments
    - Function definitions
    - Imports, attribute access, or method calls
    - Loops, conditionals, or any control flow
    - Any Python code beyond safe math expressions
    
    Examples:
    - "2 + 3 * 4" => 14.0
    - "(5 - 2) ** 2" => 9.0
    - "abs(-10)" => 10.0
    - "min(3, 1, 5)" => 1.0
    - "sum(1, 2, 3)" => 6.0
    """
    
    def __init__(self):
        pass
    
    def evaluate(self, expression: str) -> float:
        """Parse and safely evaluate the expression. Returns float result."""
        # Reject expressions with disallowed characters
        allowed_chars = set('0123456789+-*/%() .,abs()round()min()max()sum()')
        if not all(c in allowed_chars for c in expression):
            raise ValueError("Expression contains disallowed characters")
        
        # Tokenize
        tokens = self._tokenize(expression.strip())
        
        if not tokens:
            raise ValueError("Empty expression")
        
        # Parse and evaluate
        result, pos = self._parse_expression(tokens, 0)
        
        # Ensure all tokens were consumed
        if pos < len(tokens):
            raise ValueError(f"Unexpected token at position {pos}: {tokens[pos]}")
        
        return float(result)
    
    def _tokenize(self, expr: str) -> List[str]:
        """Tokenize expression into a list of tokens"""
        tokens = []
        i = 0
        
        while i < len(expr):
            # Skip whitespace
            if expr[i].isspace():
                i += 1
                continue
            
            # Numbers (int or float)
            if expr[i].isdigit() or (expr[i] == '.' and i + 1 < len(expr) and expr[i + 1].isdigit()):
                j = i
                has_dot = False
                while j < len(expr) and (expr[j].isdigit() or (expr[j] == '.' and not has_dot)):
                    if expr[j] == '.':
                        has_dot = True
                    j += 1
                tokens.append(expr[i:j])
                i = j
            # Function names
            elif expr[i:i+5] == 'round' and (i + 5 >= len(expr) or not expr[i + 5].isalnum()):
                tokens.append('round')
                i += 5
            elif expr[i:i+3] == 'abs' and (i + 3 >= len(expr) or not expr[i + 3].isalnum()):
                tokens.append('abs')
                i += 3
            elif expr[i:i+3] == 'min' and (i + 3 >= len(expr) or not expr[i + 3].isalnum()):
                tokens.append('min')
                i += 3
            elif expr[i:i+3] == 'max' and (i + 3 >= len(expr) or not expr[i + 3].isalnum()):
                tokens.append('max')
                i += 3
            elif expr[i:i+3] == 'sum' and (i + 3 >= len(expr) or not expr[i + 3].isalnum()):
                tokens.append('sum')
                i += 3
            # Operators and parentheses
            elif expr[i:i+2] == '//':
                tokens.append('//')
                i += 2
            elif expr[i:i+2] == '**':
                tokens.append('**')
                i += 2
            elif expr[i] in '+-*/%(),':
                tokens.append(expr[i])
                i += 1
            else:
                raise ValueError(f"Unexpected character: '{expr[i]}'")
        
        return tokens
    
    def _parse_expression(self, tokens: List[str], pos: int) -> tuple:
        """Parse addition/subtraction (lowest precedence)"""
        left, pos = self._parse_term(tokens, pos)
        
        while pos < len(tokens) and tokens[pos] in ('+', '-'):
            op = tokens[pos]
            pos += 1
            right, pos = self._parse_term(tokens, pos)
            left = left + right if op == '+' else left - right
        
        return left, pos
    
    def _parse_term(self, tokens: List[str], pos: int) -> tuple:
        """Parse multiplication/division/modulo (medium precedence)"""
        left, pos = self._parse_power(tokens, pos)
        
        while pos < len(tokens) and tokens[pos] in ('*', '/', '//', '%'):
            op = tokens[pos]
            pos += 1
            right, pos = self._parse_power(tokens, pos)
            
            if op == '*':
                left = left * right
            elif op == '/':
                if right == 0:
                    raise ValueError("Division by zero")
                left = left / right
            elif op == '//':
                if right == 0:
                    raise ValueError("Division by zero")
                left = int(left // right)
            else:  # %
                if right == 0:
                    raise ValueError("Modulo by zero")
                left = left % right
        
        return left, pos
    
    def _parse_power(self, tokens: List[str], pos: int) -> tuple:
        """Parse exponentiation (right-associative)"""
        left, pos = self._parse_unary(tokens, pos)
        
        if pos < len(tokens) and tokens[pos] == '**':
            pos += 1
            right, pos = self._parse_power(tokens, pos)
            left = left ** right
        
        return left, pos
    
    def _parse_unary(self, tokens: List[str], pos: int) -> tuple:
        """Parse unary +/- and function calls"""
        # Unary operators
        if pos < len(tokens) and tokens[pos] in ('+', '-'):
            op = tokens[pos]
            pos += 1
            val, pos = self._parse_unary(tokens, pos)
            return (-val if op == '-' else val), pos
        
        # Function calls
        if pos < len(tokens) and tokens[pos] in ('abs', 'round', 'min', 'max', 'sum'):
            func_name = tokens[pos]
            pos += 1
            
            if pos >= len(tokens) or tokens[pos] != '(':
                raise ValueError(f"Expected '(' after {func_name}")
            pos += 1
            
            # Parse arguments
            args = []
            if pos < len(tokens) and tokens[pos] != ')':
                while True:
                    val, pos = self._parse_expression(tokens, pos)
                    args.append(val)
                    
                    if pos >= len(tokens):
                        raise ValueError(f"Unexpected end of expression in {func_name}() call")
                    
                    if tokens[pos] == ')':
                        break
                    elif tokens[pos] == ',':
                        pos += 1
                    else:
                        raise ValueError(f"Expected ',' or ')' in {func_name}() call, got '{tokens[pos]}'")
            
            if pos >= len(tokens) or tokens[pos] != ')':
                raise ValueError(f"Expected ')' after {func_name}() arguments")
            pos += 1
            
            # Apply function
            if func_name == 'abs':
                if len(args) != 1:
                    raise ValueError(f"abs() takes exactly 1 argument, got {len(args)}")
                return abs(args[0]), pos
            elif func_name == 'round':
                if len(args) < 1 or len(args) > 2:
                    raise ValueError(f"round() takes 1 or 2 arguments, got {len(args)}")
                ndigits = int(args[1]) if len(args) == 2 else 0
                return round(args[0], ndigits), pos
            elif func_name == 'min':
                if len(args) < 1:
                    raise ValueError("min() requires at least 1 argument")
                return min(args), pos
            elif func_name == 'max':
                if len(args) < 1:
                    raise ValueError("max() requires at least 1 argument")
                return max(args), pos
            elif func_name == 'sum':
                if len(args) < 1:
                    raise ValueError("sum() requires at least 1 argument")
                return sum(args), pos
        
        return self._parse_primary(tokens, pos)
    
    def _parse_primary(self, tokens: List[str], pos: int) -> tuple:
        """Parse primary values: numbers and parenthesized expressions"""
        if pos >= len(tokens):
            raise ValueError("Unexpected end of expression")
        
        token = tokens[pos]
        
        # Number literal
        try:
            return float(token), pos + 1
        except ValueError:
            pass
        
        # Parenthesized expression
        if token == '(':
            pos += 1
            val, pos = self._parse_expression(tokens, pos)
            if pos >= len(tokens) or tokens[pos] != ')':
                raise ValueError("Expected ')'")
            return val, pos + 1
        
        raise ValueError(f"Expected number or '(', got '{token}'")


# --- Tool Definitions ---

async def weather_tool(city=None, **kwargs) -> str:
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

async def currency_tool(from_currency: str = None, to_currency: str = None, **kwargs) -> str:
    # Handle alternative parameter names the agent might use
    if from_currency is None:
        from_currency = kwargs.get('from') or kwargs.get('base') or kwargs.get('from_currency')
    if to_currency is None:
        to_currency = kwargs.get('to') or kwargs.get('symbols') or kwargs.get('to_currency')
    
    amount = kwargs.get('amount', 1)  # Optional amount for conversion, default 1
    
    if not from_currency or not to_currency:
        return "Error: from_currency and to_currency are required."
    
    url = f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if resp.status_code != 200:
            return f"Error: {data.get('error', 'API error')}"
        rate = data['rates'].get(to_currency.upper())
        if rate is None:
            return f"Error: Currency {to_currency} not found."
        result = rate * amount
        if amount == 1:
            return f"1 {from_currency.upper()} = {rate} {to_currency.upper()}"
        else:
            return f"{amount} {from_currency.upper()} = {result} {to_currency.upper()}"
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
        evaluator = SafeMathEvaluator()
        result = evaluator.evaluate(expression)
        return f"{expression} = {result}"
    except ValueError as e:
        return f"Error: Invalid expression: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

async def wikipedia_tool(query: str) -> str:
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

def clean_latex_notation(text: str) -> str:
    """Remove LaTeX math delimiters while preserving the actual content."""
    # Remove inline math: $...$
    text = re.sub(r'\$([^$]*)\$', r'\1', text)
    # Remove \boxed{...}
    text = re.sub(r'\\boxed\{([^}]*)\}', r'\1', text)
    # Remove other common LaTeX commands
    text = re.sub(r'\\text\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\frac\{([^}]*)\}\{([^}]*)\}', r'\1/\2', text)
    return text

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
    description="Get exchange rate between two currencies (exchangerate-api). Accepts from_currency and to_currency, with optional amount (default 1).",
    input_schema={
        "type": "object",
        "properties": {
            "from_currency": {"type": "string", "description": "Source currency code (e.g., USD)"},
            "to_currency": {"type": "string", "description": "Target currency code (e.g., EUR)"},
            "amount": {"type": "number", "description": "Amount to convert (default: 1)"}
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

# --- Security Middleware Setup ---
security_middleware = SecurityMiddleware()
security_middleware.register_from_mcp_server(mcp_server)

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
    agent = AIAgent(
        integrity_middleware=middleware,
        security_middleware=security_middleware,
        mcp_server=mcp_server,
        llm_client=llm_client
    )
    try:
        result = await agent.run_async(prompt=prompt, max_turns=6)
        return clean_latex_notation(result['output'])
    except Exception as e:
        return f"Error running agent: {e}"
