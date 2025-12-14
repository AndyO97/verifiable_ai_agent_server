"""
AI Agent Server with MCP-compatible tool routing
Implements the core agent runtime with tool handling and LLM integration.

Phase 2: LLM-integrated agent loop with Ollama support.
- Records all LLM interactions in integrity middleware
- Handles multi-turn tool calling
- Validates tools through security middleware
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from src.integrity import IntegrityMiddleware
    from src.llm import OllamaClient
    from src.security import SecurityMiddleware

logger = structlog.get_logger(__name__)


class ToolDefinition:
    """Schema for a single tool available to the agent"""
    
    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        handler: callable
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema  # Pydantic schema
        self.handler = handler
    
    def validate_input(self, args: dict[str, Any]) -> bool:
        """Validate input against schema"""
        # TODO: Use Pydantic validation
        return True


class MCPServer:
    """
    Simplified MCP-compatible server for agent message routing.
    Manages tool definitions and coordinates with integrity middleware.
    
    TODO (Phase 2): Integrate with actual FastMCP library for full HTTP/WebSocket support.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.tools: dict[str, ToolDefinition] = {}
        
        logger.info("mcp_server_initialized", session_id=session_id)
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a tool with the server"""
        self.tools[tool.name] = tool
        logger.info("tool_registered", tool_name=tool.name)
    
    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools (schema only, no capabilities exposed)"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in self.tools.values()
        ]
    
    def invoke_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Invoke a tool by name with given arguments"""
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")
        
        tool = self.tools[tool_name]
        
        # Validate input
        if not tool.validate_input(args):
            raise ValueError(f"Invalid input for tool {tool_name}")
        
        # Execute handler
        return tool.handler(**args)


class AIAgent:
    """
    Main agent class coordinating LLM, tools, and integrity tracking.
    This is the primary interface for running verifiable agent tasks.
    
    Phase 2: Full LLM integration with tool calling and integrity tracking.
    """
    
    def __init__(
        self,
        integrity_middleware: IntegrityMiddleware,
        security_middleware: SecurityMiddleware,
        mcp_server: MCPServer,
        llm_client: Optional[OllamaClient] = None
    ):
        self.integrity = integrity_middleware
        self.security = security_middleware
        self.mcp = mcp_server
        self.llm_client = llm_client
        
        logger.info("ai_agent_initialized", session_id=self.integrity.session_id)
    
    def run(self, prompt: str, max_turns: int = 10) -> dict[str, Any]:
        """
        Execute the agent with the given prompt.
        
        Workflow:
        1. Record initial prompt
        2. Call LLM with available tools
        3. Parse tool calls from response
        4. For each tool call:
           - Validate authorization
           - Record tool input
           - Execute tool
           - Record tool output
        5. Continue until LLM produces final output
        6. Finalize and generate Verkle root
        
        Args:
            prompt: Initial user prompt
            max_turns: Maximum turns to prevent infinite loops
        
        Returns:
            Final output with integrity metadata
        """
        # Record initial prompt
        self.integrity.record_prompt(prompt)
        
        # Build tool schemas for LLM
        tool_schemas = self.mcp.list_tools()
        
        conversation_history = [
            {"role": "user", "content": prompt}
        ]
        
        final_output = None
        turn_count = 0
        
        try:
            while turn_count < max_turns:
                turn_count += 1
                logger.info("agent_turn_start", turn=turn_count, session_id=self.integrity.session_id)
                
                # Call LLM
                if self.llm_client is None:
                    # Fallback: dummy implementation for testing without Ollama
                    llm_response = self._dummy_llm_call(prompt)
                else:
                    llm_response = self.llm_client.call_llm(
                        prompt=conversation_history[-1]["content"],
                        tools=tool_schemas
                    )
                
                # Check if LLM wants to call tools
                if not llm_response.has_tool_calls():
                    # No more tool calls - this is the final output
                    final_output = llm_response.text
                    logger.info("agent_final_output", output_len=len(final_output))
                    break
                
                # Process each tool call
                for tool_call in llm_response.tool_calls:
                    logger.info("tool_call_requested", tool=tool_call.tool_name, args=tool_call.arguments)
                    
                    # Check authorization
                    if not self.security.validate_tool_invocation(self.integrity.session_id, tool_call.tool_name):
                        error_msg = f"Unauthorized tool: {tool_call.tool_name}"
                        logger.warning("tool_call_blocked", tool=tool_call.tool_name)
                        # Record as blocked tool attempt
                        self.integrity.record_tool_input(tool_call.tool_name, tool_call.arguments)
                        tool_result = f"Error: {error_msg}"
                        self.integrity.record_tool_output(tool_call.tool_name, tool_result)
                    else:
                        # Record tool input
                        self.integrity.record_tool_input(tool_call.tool_name, tool_call.arguments)
                        
                        # Execute tool
                        try:
                            tool_result = self.mcp.invoke_tool(
                                tool_call.tool_name,
                                tool_call.arguments
                            )
                            logger.info("tool_executed", tool=tool_call.tool_name, result=str(tool_result)[:100])
                        except Exception as e:
                            tool_result = f"Error executing tool: {str(e)}"
                            logger.exception("tool_execution_error", tool=tool_call.tool_name)
                        
                        # Record tool output
                        self.integrity.record_tool_output(tool_call.tool_name, tool_result)
                
                # Add tool results to conversation and loop
                conversation_history.append({
                    "role": "assistant",
                    "content": llm_response.text
                })
            
            # Fallback if we hit max turns
            if final_output is None:
                final_output = "Agent reached maximum turns without final output"
                logger.warning("agent_max_turns_reached", max_turns=max_turns)
        
        except Exception as e:
            logger.exception("agent_error", error=str(e))
            final_output = f"Error during agent execution: {str(e)}"
        
        # Record final output
        if final_output:
            self.integrity.record_model_output(final_output)
        
        # Finalize and commit
        integrity_result = self.integrity.finalize()
        
        logger.info("agent_run_completed", **integrity_result)
        
        return {
            "output": final_output,
            "integrity": integrity_result,
            "turns": turn_count
        }
    
    def _dummy_llm_call(self, prompt: str) -> Any:
        """
        Dummy LLM response for testing without Ollama running.
        Returns a simple response without tool calls.
        """
        from src.llm import LLMResponse
        
        logger.info("using_dummy_llm_response")
        return LLMResponse(
            text=f"Dummy response to: {prompt[:50]}...",
            tool_calls=[],
            stop_reason="end_turn"
        )
