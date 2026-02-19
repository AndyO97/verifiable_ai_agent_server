"""
MCP Protocol Adapter
Integrates MCPServer with JSON-RPC 2.0 protocol and secure transport layer.
Provides complete MCP 2024-11 compliance.
"""

from typing import Any, Dict, Optional
import structlog
import json

from src.agent import MCPServer
from src.transport.jsonrpc_protocol import (
    MCPProtocolHandler,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCErrorCode,
)

logger = structlog.get_logger(__name__)


class MCPProtocolAdapter:
    """
    Adapter that bridges MCPServer with JSON-RPC 2.0 protocol layer.
    
    Responsibilities:
    - Wrap MCPServer methods in JSON-RPC handlers
    - Ensure MCP specification compliance
    - Handle protocol-level concerns (versioning, initialization, error codes)
    - Maintain request/response correlation
    """
    
    def __init__(self, mcp_server: MCPServer):
        self.mcp_server = mcp_server
        self.protocol = MCPProtocolHandler(server_name="Crypto Protocols MCP Server")
        
        # Register all MCPServer methods as JSON-RPC handlers
        self._register_handlers()
        
        logger.info("mcp_protocol_adapter_initialized", session_id=mcp_server.session_id)
    
    def _register_handlers(self):
        """Register MCPServer methods as JSON-RPC handlers"""
        
        # Tool methods
        self.protocol.register_method("tools/list", self._handle_tools_list)
        self.protocol.register_method("tools/call", self._handle_tools_call)
        
        # Resource methods
        self.protocol.register_method("resources/list", self._handle_resources_list)
        self.protocol.register_method("resources/read", self._handle_resources_read)
        
        # Prompt methods
        self.protocol.register_method("prompts/list", self._handle_prompts_list)
        self.protocol.register_method("prompts/call", self._handle_prompts_call)
        
        # Health check
        self.protocol.register_method("ping", self._handle_ping)
        
        logger.info("protocol_handlers_registered")
    
    # Tool handlers
    def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list JSON-RPC method"""
        tools = self.mcp_server.list_tools()
        # Convert type objects in input_schema to JSON-serializable format
        json_tools = []
        for tool in tools:
            tool_dict = dict(tool)
            # Convert input_schema types to string representations
            if isinstance(tool_dict.get("input_schema"), dict):
                tool_dict["input_schema"] = {
                    k: v.__name__ if isinstance(v, type) else str(v)
                    for k, v in tool_dict["input_schema"].items()
                }
            json_tools.append(tool_dict)
        
        return {
            "tools": json_tools,
            "count": len(json_tools)
        }
    
    def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call JSON-RPC method"""
        if not isinstance(params, dict):
            raise TypeError("Parameters must be an object")
        
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise ValueError("Missing required parameter: name")
        
        try:
            result = self.mcp_server.invoke_tool(tool_name, arguments)
            return {
                "result": result,
                "tool": tool_name,
                "status": "success"
            }
        except ValueError as e:
            logger.error("tool_invocation_failed", tool=tool_name, error=str(e))
            raise
    
    # Resource handlers
    def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/list JSON-RPC method"""
        resources = self.mcp_server.list_resources()
        return {
            "resources": resources,
            "count": len(resources)
        }
    
    def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read JSON-RPC method"""
        if not isinstance(params, dict):
            raise TypeError("Parameters must be an object")
        
        uri = params.get("uri")
        if not uri:
            raise ValueError("Missing required parameter: uri")
        
        try:
            content = self.mcp_server.read_resource(uri)
            return {
                "contents": content,
                "uri": uri,
                "mimeType": "application/json" if uri.startswith("audit://") else "text/plain"
            }
        except ValueError as e:
            logger.error("resource_read_failed", uri=uri, error=str(e))
            raise
    
    # Prompt handlers
    def _handle_prompts_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/list JSON-RPC method"""
        prompts = self.mcp_server.list_prompts()
        return {
            "prompts": prompts,
            "count": len(prompts)
        }
    
    def _handle_prompts_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/call JSON-RPC method"""
        if not isinstance(params, dict):
            raise TypeError("Parameters must be an object")
        
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not prompt_name:
            raise ValueError("Missing required parameter: name")
        
        try:
            rendered = self.mcp_server.call_prompt(prompt_name, arguments)
            return {
                "result": rendered,
                "prompt": prompt_name,
                "status": "success"
            }
        except ValueError as e:
            logger.error("prompt_evaluation_failed", prompt=prompt_name, error=str(e))
            raise
    
    # Health check
    def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping method for health checks"""
        return {
            "status": "ok",
            "server": "Crypto Protocols MCP Server",
            "protocol_version": self.protocol.PROTOCOL_VERSION
        }
    
    # Top-level interface
    def handle_jsonrpc_request(self, request_data: str) -> str:
        """
        Handle incoming JSON-RPC 2.0 request string.
        
        Args:
            request_data: JSON string containing JSON-RPC 2.0 request
        
        Returns:
            JSON string containing JSON-RPC 2.0 response
        """
        response = self.protocol.handle_request(request_data)
        return response.to_json()
    
    def handle_dict_request(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle incoming JSON-RPC 2.0 request dict.
        
        Args:
            request_dict: Dict containing JSON-RPC 2.0 request
        
        Returns:
            Dict containing JSON-RPC 2.0 response
        """
        response = self.protocol.handle_request(request_dict)
        return response.to_dict()
    
    def create_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> JSONRPCRequest:
        """Create a JSON-RPC 2.0 request"""
        return self.protocol.create_request(method, params)
    
    def initialize(self) -> Dict[str, Any]:
        """
        Perform MCP initialization handshake.
        
        Returns MCP protocol capabilities.
        """
        response = self.protocol.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "MCP Client",
                    "version": "1.0.0"
                }
            },
            "id": "init-1"
        })
        
        if response.error:
            raise RuntimeError(f"Initialization failed: {response.error}")
        
        logger.info("mcp_initialized", capabilities=response.result)
        return response.result
