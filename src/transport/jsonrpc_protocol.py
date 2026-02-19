"""
JSON-RPC 2.0 Protocol Implementation for MCP
Implements the MCP specification with proper protocol versioning, initialization,
error handling, and request/response correlation.

Reference: https://www.jsonrpc.org/specification (JSON-RPC 2.0)
          https://spec.modelcontextprotocol.io/ (MCP Specification 2024-11)
"""

import json
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass, asdict
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# JSON-RPC 2.0 Error Codes (per spec)
# ============================================================================

class JSONRPCErrorCode(Enum):
    """Standard JSON-RPC 2.0 error codes"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    SERVER_ERROR_START = -32099
    SERVER_ERROR_END = -32000
    
    # MCP-specific error codes (within server error range)
    TOOL_EXECUTE_ERROR = -32050
    RESOURCE_NOT_FOUND = -32051
    PROMPT_NOT_FOUND = -32052
    UNAUTHORIZED = -32053


class MCPErrorCode(Enum):
    """MCP-specific error codes"""
    INVALID_REQUEST = "INVALID_REQUEST"
    METHOD_NOT_FOUND = "METHOD_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TIMEOUT = "TIMEOUT"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    PROMPT_NOT_FOUND = "PROMPT_NOT_FOUND"
    TOOL_EXECUTE_ERROR = "TOOL_EXECUTE_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"


# ============================================================================
# JSON-RPC 2.0 Message Structures
# ============================================================================

@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 Request Object"""
    jsonrpc: str = "2.0"
    method: str = ""
    params: Optional[Union[Dict, List]] = None
    id: Optional[Union[str, int]] = None
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict"""
        d = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            d["params"] = self.params
        if self.id is not None:
            d["id"] = self.id
        return d
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict())


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 Response Object"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict"""
        d = {"jsonrpc": self.jsonrpc}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        if self.id is not None:
            d["id"] = self.id
        return d
    
    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict())
    
    @staticmethod
    def from_dict(data: dict) -> "JSONRPCResponse":
        """Parse from dict"""
        return JSONRPCResponse(
            jsonrpc=data.get("jsonrpc", "2.0"),
            result=data.get("result"),
            error=data.get("error"),
            id=data.get("id")
        )


@dataclass
class JSONRPCError:
    """JSON-RPC 2.0 Error Object"""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict"""
        d = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


# ============================================================================
# MCP Protocol Implementation
# ============================================================================

class MCPProtocolHandler:
    """
    Handles JSON-RPC 2.0 protocol for MCP.
    
    Responsibilities:
    - Protocol version management
    - Request/response correlation with request IDs
    - Initialization handshake
    - Standard error handling
    - Method routing
    """
    
    PROTOCOL_VERSION = "2024-11"
    SUPPORTED_METHODS = {
        "initialize": "Initialize client-server connection",
        "tools/list": "List available tools",
        "tools/call": "Execute a tool",
        "resources/list": "List available resources",
        "resources/read": "Read a resource",
        "prompts/list": "List available prompts",
        "prompts/call": "Evaluate a prompt",
        "ping": "Health check",
    }
    
    def __init__(self, server_name: str = "MCP Server"):
        self.server_name = server_name
        self.initialized = False
        self.request_handlers: Dict[str, Callable] = {}
        self.pending_requests: Dict[Union[str, int], JSONRPCRequest] = {}
        
        logger.info("mcp_protocol_initialized", server_name=server_name, version=self.PROTOCOL_VERSION)
    
    def register_method(self, method_name: str, handler: Callable) -> None:
        """Register a method handler"""
        if method_name not in self.SUPPORTED_METHODS:
            logger.warning("registering_custom_method", method=method_name)
        
        self.request_handlers[method_name] = handler
        logger.info("method_registered", method=method_name)
    
    def create_request(
        self,
        method: str,
        params: Optional[Union[Dict, List]] = None,
        request_id: Optional[Union[str, int]] = None
    ) -> JSONRPCRequest:
        """Create a properly formatted JSON-RPC 2.0 request"""
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        request = JSONRPCRequest(
            jsonrpc="2.0",
            method=method,
            params=params,
            id=request_id
        )
        
        self.pending_requests[request_id] = request
        logger.info("request_created", method=method, request_id=request_id)
        
        return request
    
    def handle_request(self, request_data: Union[str, dict]) -> JSONRPCResponse:
        """
        Handle incoming JSON-RPC 2.0 request.
        
        Args:
            request_data: JSON string or dict
        
        Returns:
            JSON-RPC 2.0 Response
        """
        request_id = None
        
        try:
            # Parse request
            if isinstance(request_data, str):
                request_dict = json.loads(request_data)
            else:
                request_dict = request_data
            
            # Validate request
            if not isinstance(request_dict, dict):
                return self._error_response(
                    JSONRPCErrorCode.INVALID_REQUEST,
                    "Request must be an object",
                    request_id
                )
            
            # Extract fields
            request_id = request_dict.get("id")
            jsonrpc_version = request_dict.get("jsonrpc")
            method = request_dict.get("method")
            params = request_dict.get("params")
            
            # Validate protocol version
            if jsonrpc_version != "2.0":
                return self._error_response(
                    JSONRPCErrorCode.INVALID_REQUEST,
                    f"Invalid jsonrpc version: {jsonrpc_version}",
                    request_id
                )
            
            # Validate method
            if not method or not isinstance(method, str):
                return self._error_response(
                    JSONRPCErrorCode.INVALID_REQUEST,
                    "Method must be a non-empty string",
                    request_id
                )
            
            # Special handling for initialize
            if method == "initialize":
                return self._handle_initialize(params, request_id)
            
            # Check initialization before other methods
            if not self.initialized:
                return self._error_response(
                    MCPErrorCode.UNAUTHORIZED,
                    "Server not initialized. Call initialize first.",
                    request_id
                )
            
            # Route to handler
            if method not in self.request_handlers:
                return self._error_response(
                    JSONRPCErrorCode.METHOD_NOT_FOUND,
                    f"Method not found: {method}",
                    request_id
                )
            
            handler = self.request_handlers[method]
            
            try:
                # Execute handler
                result = handler(params or {})
                
                logger.info("request_handled", method=method, request_id=request_id)
                
                # Only send response if request has an ID
                if request_id is not None:
                    return JSONRPCResponse(
                        jsonrpc="2.0",
                        result=result,
                        id=request_id
                    )
                
            except TypeError as e:
                return self._error_response(
                    JSONRPCErrorCode.INVALID_PARAMS,
                    f"Invalid parameters: {str(e)}",
                    request_id
                )
            except ValueError as e:
                return self._error_response(
                    MCPErrorCode.TOOL_EXECUTE_ERROR,
                    f"Tool execution error: {str(e)}",
                    request_id
                )
            except Exception as e:
                logger.exception("handler_error", method=method, error=str(e))
                return self._error_response(
                    JSONRPCErrorCode.INTERNAL_ERROR,
                    f"Internal server error: {str(e)}",
                    request_id
                )
        
        except json.JSONDecodeError as e:
            return self._error_response(
                JSONRPCErrorCode.PARSE_ERROR,
                f"JSON parse error: {str(e)}",
                request_id
            )
        except Exception as e:
            logger.exception("unexpected_error", error=str(e))
            return self._error_response(
                JSONRPCErrorCode.INTERNAL_ERROR,
                f"Unexpected error: {str(e)}",
                request_id
            )
    
    def _handle_initialize(self, params: Optional[dict], request_id: Optional[Union[str, int]]) -> JSONRPCResponse:
        """
        Handle initialize method (MCP handshake).
        
        Client sends client info, server responds with capabilities.
        """
        params = params or {}
        
        logger.info("initialize_request", client_info=params.get("clientInfo"))
        
        # Server capabilities response
        capabilities = {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"enabled": True},
                "resources": {"enabled": True},
                "prompts": {"enabled": True},
                "notifications": {
                    "enabled": True,
                    "supportedTypes": [
                        "tool_executed",
                        "resource_accessed",
                        "verification_complete"
                    ]
                },
                "sampling": False,
            },
            "serverInfo": {
                "name": self.server_name,
                "version": "1.0.0",
            }
        }
        
        self.initialized = True
        logger.info("server_initialized", capabilities=capabilities)
        
        return JSONRPCResponse(
            jsonrpc="2.0",
            result=capabilities,
            id=request_id
        )
    
    def _error_response(
        self,
        error_code: Union[JSONRPCErrorCode, MCPErrorCode],
        message: str,
        request_id: Optional[Union[str, int]] = None
    ) -> JSONRPCResponse:
        """Create a JSON-RPC 2.0 error response"""
        if isinstance(error_code, JSONRPCErrorCode):
            code = error_code.value
        else:
            code = error_code.value  # For MCP codes, use string
        
        error_obj = JSONRPCError(
            code=code,
            message=message
        )
        
        return JSONRPCResponse(
            jsonrpc="2.0",
            error=error_obj.to_dict(),
            id=request_id
        )
    
    def correlate_response(
        self,
        response_data: Union[str, dict]
    ) -> tuple[Optional[JSONRPCRequest], JSONRPCResponse]:
        """
        Correlate a response with its original request using request ID.
        
        Returns:
            (original_request, response) or (None, response) if no matching request
        """
        try:
            if isinstance(response_data, str):
                response_dict = json.loads(response_data)
            else:
                response_dict = response_data
            
            response = JSONRPCResponse.from_dict(response_dict)
            
            # Look up original request
            original_request = None
            if response.id in self.pending_requests:
                original_request = self.pending_requests.pop(response.id)
            
            logger.info("response_correlated", request_id=response.id, has_request=original_request is not None)
            
            return original_request, response
        
        except Exception as e:
            logger.exception("correlation_error", error=str(e))
            return None, JSONRPCResponse(error={"code": -32603, "message": str(e)})
    
    def validate_response(self, response: JSONRPCResponse, expected_request_id: Optional[Union[str, int]] = None) -> bool:
        """
        Validate response integrity.
        
        Args:
            response: Response to validate
            expected_request_id: Expected request ID (for correlation check)
        
        Returns:
            True if valid, False otherwise
        """
        # Check protocol version
        if response.jsonrpc != "2.0":
            logger.warning("invalid_response_version", version=response.jsonrpc)
            return False
        
        # Check either result or error is present (not both)
        if response.result is not None and response.error is not None:
            logger.warning("response_has_both_result_and_error")
            return False
        
        # Check request ID correlation
        if expected_request_id is not None and response.id != expected_request_id:
            logger.warning("request_id_mismatch", expected=expected_request_id, got=response.id)
            return False
        
        return True


# ============================================================================
# Batch Request Support (Optional JSON-RPC 2.0 feature)
# ============================================================================

class JSONRPCBatchRequest:
    """Handle batch requests (array of requests)"""
    
    def __init__(self, requests: List[JSONRPCRequest]):
        self.requests = requests
    
    def to_json(self) -> str:
        """Serialize batch to JSON"""
        return json.dumps([req.to_dict() for req in self.requests])


def parse_batch_response(response_data: str) -> List[JSONRPCResponse]:
    """Parse batch response (array of responses)"""
    try:
        responses_data = json.loads(response_data)
        if not isinstance(responses_data, list):
            raise ValueError("Batch response must be an array")
        
        return [JSONRPCResponse.from_dict(resp) for resp in responses_data]
    except Exception as e:
        logger.exception("batch_response_parse_error", error=str(e))
        return []
