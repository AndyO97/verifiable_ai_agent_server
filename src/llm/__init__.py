"""
LLM integration module - Ollama client and LLM abstractions
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

import requests
import structlog

if TYPE_CHECKING:
    from opentelemetry import trace

logger = structlog.get_logger(__name__)


class ToolCall:
    """Represents a single tool call from the LLM"""
    
    def __init__(self, tool_name: str, arguments: dict[str, Any]):
        self.tool_name = tool_name
        self.arguments = arguments
    
    def __repr__(self) -> str:
        return f"ToolCall(tool={self.tool_name}, args={self.arguments})"


class LLMResponse:
    """Structured LLM response with text and optional tool calls"""
    
    def __init__(
        self,
        text: str,
        tool_calls: Optional[list[ToolCall]] = None,
        stop_reason: str = "end_turn"
    ):
        self.text = text
        self.tool_calls = tool_calls or []
        self.stop_reason = stop_reason
    
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls"""
        return len(self.tool_calls) > 0


class OllamaClient:
    """
    Ollama LLM client wrapper
    
    Handles communication with local Ollama instance and tool calling.
    Requires Ollama running locally (default: http://localhost:11434)
    """
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama2"):
        self.base_url = base_url
        self.model = model
        self.endpoint = f"{base_url}/api/generate"
        
        logger.info("ollama_client_initialized", model=model, base_url=base_url)
    
    def health_check(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            is_healthy = response.status_code == 200
            if is_healthy:
                logger.info("ollama_health_check_passed")
            else:
                logger.warning("ollama_health_check_failed", status=response.status_code)
            return is_healthy
        except requests.RequestException as e:
            logger.warning("ollama_health_check_error", error=str(e))
            return False
    
    def call_llm(
        self,
        prompt: str,
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> LLMResponse:
        """
        Call Ollama LLM with prompt and optional tools
        
        Args:
            prompt: User prompt
            tools: List of tool definitions (schema)
            temperature: Model temperature (0-1)
            max_tokens: Maximum tokens in response
        
        Returns:
            LLMResponse with text and optional tool calls
        """
        
        # Build system message with tool definitions if provided
        system_msg = self._build_system_message(tools)
        
        # Prepare full prompt with system context
        full_prompt = f"{system_msg}\n\nUser: {prompt}"
        
        try:
            logger.info("ollama_call_start", model=self.model, prompt_len=len(prompt))
            
            # Call Ollama
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": full_prompt,
                    "temperature": temperature,
                    "stream": False
                },
                timeout=60
            )
            
            if response.status_code != 200:
                try:
                    error_detail = response.json().get("error", "")
                except:
                    error_detail = response.text[:200] if response.text else ""
                
                logger.error("ollama_call_failed", status=response.status_code, error=error_detail)
                
                # Provide helpful error message
                if "not found" in error_detail.lower():
                    msg = f"Ollama model '{self.model}' not found. Pull it with: ollama pull {self.model}"
                elif response.status_code == 404:
                    msg = f"Ollama endpoint not found (404). Is Ollama running at {self.endpoint}?"
                else:
                    msg = f"Ollama request failed: {response.status_code} - {error_detail}"
                
                raise RuntimeError(msg)
            
            response_text = response.json().get("response", "")
            
            logger.info("ollama_call_complete", response_len=len(response_text))
            
            # Parse tool calls if present (Ollama doesn't have native tool calling,
            # so we look for structured tool calls in the response)
            tool_calls = self._parse_tool_calls(response_text, tools)
            
            return LLMResponse(
                text=response_text,
                tool_calls=tool_calls,
                stop_reason="end_turn"
            )
        
        except Exception as e:
            logger.exception("ollama_call_error", error=str(e))
            raise
    
    def _build_system_message(self, tools: Optional[list[dict[str, Any]]]) -> str:
        """Build system message with tool context"""
        base_msg = (
            "You are a helpful AI agent. You have access to the following tools:\n"
        )
        
        if tools:
            tool_descriptions = []
            for tool in tools:
                tool_desc = f"- {tool['name']}: {tool['description']}"
                tool_descriptions.append(tool_desc)
            
            base_msg += "\n".join(tool_descriptions)
            base_msg += (
                "\n\nWhen you need to use a tool, respond with JSON like: "
                '{"tool": "tool_name", "args": {"arg1": value1}}'
            )
        
        return base_msg
    
    def _parse_tool_calls(
        self,
        response_text: str,
        tools: Optional[list[dict[str, Any]]]
    ) -> list[ToolCall]:
        """Extract tool calls from LLM response"""
        if not tools:
            return []
        
        tool_calls = []
        
        # Look for JSON tool call patterns
        # This is a simple pattern match for {"tool": "...", "args": {...}}
        import re
        
        pattern = r'\{"tool":\s*"([^"]+)",\s*"args":\s*({.*?})\}'
        matches = re.findall(pattern, response_text)
        
        for tool_name, args_str in matches:
            try:
                args = json.loads(args_str)
                tool_calls.append(ToolCall(tool_name, args))
                logger.info("tool_call_parsed", tool=tool_name, args=args)
            except json.JSONDecodeError as e:
                logger.warning("tool_call_parse_error", args_str=args_str, error=str(e))
        
        return tool_calls
