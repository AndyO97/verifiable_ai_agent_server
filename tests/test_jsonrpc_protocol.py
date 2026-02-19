"""
Tests for JSON-RPC 2.0 Protocol and MCP Protocol Adapter.

Tests:
- Protocol versioning (2024-11)
- Initialization handshake
- Standard error codes
- Request/response correlation
- Request ID management
- MCP specification compliance
"""

import pytest
import json
from pydantic import BaseModel

from src.agent import MCPServer, ToolDefinition
from src.transport.jsonrpc_protocol import (
    MCPProtocolHandler,
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    JSONRPCErrorCode,
    MCPErrorCode,
)
from src.transport.mcp_protocol_adapter import MCPProtocolAdapter


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def protocol_handler():
    """Create a protocol handler"""
    return MCPProtocolHandler(server_name="Test MCP Server")


@pytest.fixture
def mcp_server():
    """Create an MCP server"""
    server = MCPServer(session_id="test-protocol-001")
    
    # Register a test tool
    def double_handler(value: int) -> int:
        return value * 2
    
    tool = ToolDefinition(
        name="double",
        description="Doubles a number",
        input_schema={"value": int},
        handler=double_handler
    )
    server.register_tool(tool)
    
    return server


@pytest.fixture
def protocol_adapter(mcp_server):
    """Create a protocol adapter"""
    return MCPProtocolAdapter(mcp_server)


# ============================================================================
# JSON-RPC 2.0 Protocol Tests
# ============================================================================


class TestJSONRPC2Protocol:
    """Test basic JSON-RPC 2.0 protocol compliance"""
    
    def test_jsonrpc_request_creation(self, protocol_handler):
        """Test creating a JSON-RPC request"""
        request = protocol_handler.create_request(
            "test/method",
            params={"key": "value"}
        )
        
        assert request.jsonrpc == "2.0"
        assert request.method == "test/method"
        assert request.params == {"key": "value"}
        assert request.id is not None
    
    def test_jsonrpc_request_serialization(self):
        """Test JSON-RPC request serialization"""
        request = JSONRPCRequest(
            method="ping",
            params={"message": "hello"},
            id="req-1"
        )
        
        json_str = request.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "ping"
        assert parsed["params"]["message"] == "hello"
        assert parsed["id"] == "req-1"
    
    def test_jsonrpc_response_serialization(self):
        """Test JSON-RPC response serialization"""
        response = JSONRPCResponse(
            result={"status": "ok"},
            id="req-1"
        )
        
        json_str = response.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["result"]["status"] == "ok"
        assert parsed["id"] == "req-1"
        assert "error" not in parsed
    
    def test_jsonrpc_error_response(self):
        """Test JSON-RPC error response"""
        error = JSONRPCError(
            code=-32600,
            message="Invalid Request",
            data={"details": "Missing method"}
        )
        
        error_dict = error.to_dict()
        assert error_dict["code"] == -32600
        assert error_dict["message"] == "Invalid Request"
        assert error_dict["data"]["details"] == "Missing method"


# ============================================================================
# Protocol Versioning Tests
# ============================================================================


class TestProtocolVersioning:
    """Test protocol version management"""
    
    def test_protocol_version_constant(self, protocol_handler):
        """Test protocol version is 2024-11"""
        assert protocol_handler.PROTOCOL_VERSION == "2024-11"
    
    def test_initialize_returns_protocol_version(self, protocol_handler):
        """Test initialize method returns protocol version"""
        response = protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1"
        })
        
        assert response.result["protocolVersion"] == "2024-11"
    
    def test_invalid_protocol_version_rejected(self, protocol_handler):
        """Test that invalid protocol versions are rejected"""
        response = protocol_handler.handle_request({
            "jsonrpc": "1.0",  # Invalid
            "method": "ping",
            "id": "req-1"
        })
        
        assert response.error is not None
        assert response.error["code"] == JSONRPCErrorCode.INVALID_REQUEST.value


# ============================================================================
# Initialization Handshake Tests
# ============================================================================


class TestInitializationHandshake:
    """Test MCP initialization protocol"""
    
    def test_initialize_sets_initialized_flag(self, protocol_handler):
        """Test that initialize sets the initialized flag"""
        assert protocol_handler.initialized is False
        
        protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1"
        })
        
        assert protocol_handler.initialized is True
    
    def test_initialize_response_structure(self, protocol_handler):
        """Test initialize response has proper structure"""
        response = protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "Test Client",
                    "version": "1.0.0"
                }
            },
            "id": "init-1"
        })
        
        assert response.result is not None
        assert "protocolVersion" in response.result
        assert "capabilities" in response.result
        assert "serverInfo" in response.result
        assert response.id == "init-1"
    
    def test_initialize_advertises_capabilities(self, protocol_handler):
        """Test initialize advertises all capabilities"""
        response = protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1"
        })
        
        caps = response.result["capabilities"]
        assert "tools" in caps
        assert "resources" in caps
        assert "prompts" in caps
        assert "notifications" in caps
        assert caps["tools"]["enabled"] is True
        assert caps["resources"]["enabled"] is True
        assert caps["prompts"]["enabled"] is True
        assert caps["notifications"]["enabled"] is True
    
    def test_methods_blocked_before_initialization(self, protocol_handler):
        """Test that methods are blocked until initialized"""
        response = protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "ping",
            "id": "req-1"
        })
        
        # Should return error before initialization
        assert response.error is not None


# ============================================================================
# Error Code Tests
# ============================================================================


class TestErrorCodes:
    """Test standard JSON-RPC 2.0 error codes"""
    
    def test_parse_error_handling(self, protocol_handler):
        """Test PARSE_ERROR (-32700)"""
        response = protocol_handler.handle_request("{invalid json")
        
        assert response.error is not None
        assert response.error["code"] == JSONRPCErrorCode.PARSE_ERROR.value
    
    def test_invalid_request_error(self, protocol_handler):
        """Test INVALID_REQUEST (-32600)"""
        # Initialize first
        protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1"
        })
        
        # Send invalid request (not an object)
        response = protocol_handler.handle_request(["array", "not", "object"])
        
        assert response.error is not None
        assert response.error["code"] == JSONRPCErrorCode.INVALID_REQUEST.value
    
    def test_method_not_found_error(self, protocol_handler):
        """Test METHOD_NOT_FOUND (-32601)"""
        # Initialize first
        protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1"
        })
        
        response = protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "nonexistent/method",
            "id": "req-1"
        })
        
        assert response.error is not None
        assert response.error["code"] == JSONRPCErrorCode.METHOD_NOT_FOUND.value
    
    def test_invalid_params_error(self, protocol_handler):
        """Test INVALID_PARAMS (-32602)"""
        # Initialize first
        protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1"
        })
        
        # Register a handler that expects specific params
        def strict_handler(params):
            if not isinstance(params, dict) or "required" not in params:
                raise TypeError("Missing required parameter")
            return {"ok": True}
        
        protocol_handler.register_method("test/strict", strict_handler)
        
        response = protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "test/strict",
            "params": {"wrong": "param"},
            "id": "req-1"
        })
        
        assert response.error is not None
        assert response.error["code"] == JSONRPCErrorCode.INVALID_PARAMS.value


# ============================================================================
# Request/Response Correlation Tests
# ============================================================================


class TestRequestResponseCorrelation:
    """Test request ID correlation and matching"""
    
    def test_request_id_generation(self, protocol_handler):
        """Test automatic request ID generation"""
        request = protocol_handler.create_request("test/method")
        
        assert request.id is not None
        assert isinstance(request.id, str)
    
    def test_request_id_in_response(self, protocol_handler):
        """Test request ID is echoed in response"""
        # Initialize
        protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "custom-id-123"
        })
        
        # Make request with custom ID
        response = protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "ping",
            "id": "custom-id-456"
        })
        
        assert response.id == "custom-id-456"
    
    def test_response_correlation(self, protocol_handler):
        """Test correlating response to original request"""
        # Initialize
        protocol_handler.handle_request({
            "jsonrpc": "2.0",
            "method": "initialize",
            "id": "init-1"
        })
        
        # Create and send request
        request = protocol_handler.create_request("ping")
        request_json = request.to_json()
        
        # Handle and get response
        response = protocol_handler.handle_request(request_json)
        
        # Correlate
        original, correlated_response = protocol_handler.correlate_response(response.to_dict())
        
        assert original is not None
        assert original.method == "ping"
        assert correlated_response.id == response.id
    
    def test_response_validation(self, protocol_handler):
        """Test response validation"""
        # Create a valid response
        response = JSONRPCResponse(
            jsonrpc="2.0",
            result={"status": "ok"},
            id="req-1"
        )
        
        assert protocol_handler.validate_response(response) is True
    
    def test_response_validation_with_wrong_id(self, protocol_handler):
        """Test response validation detects ID mismatch"""
        response = JSONRPCResponse(
            jsonrpc="2.0",
            result={"status": "ok"},
            id="req-1"
        )
        
        assert protocol_handler.validate_response(response, expected_request_id="req-2") is False


# ============================================================================
# MCP Protocol Adapter Tests
# ============================================================================


class TestMCPProtocolAdapter:
    """Test protocol adapter integration"""
    
    def test_adapter_initialization(self, protocol_adapter):
        """Test protocol adapter initialization"""
        assert protocol_adapter.mcp_server is not None
        assert protocol_adapter.protocol is not None
    
    def test_adapter_initialize(self, protocol_adapter):
        """Test adapter initialization"""
        result = protocol_adapter.initialize()
        
        assert result["protocolVersion"] == "2024-11"
        assert "capabilities" in result
        assert "serverInfo" in result
    
    def test_adapter_handles_tools_list(self, protocol_adapter):
        """Test adapter handles tools/list"""
        protocol_adapter.initialize()
        
        response = protocol_adapter.handle_jsonrpc_request(
            json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": "req-1"
            })
        )
        
        result = json.loads(response)
        assert result["result"]["count"] >= 1
        assert "tools" in result["result"]
    
    def test_adapter_handles_tools_call(self, protocol_adapter):
        """Test adapter handles tools/call"""
        protocol_adapter.initialize()
        
        response = protocol_adapter.handle_jsonrpc_request(
            json.dumps({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "double",
                    "arguments": {"value": 5}
                },
                "id": "req-1"
            })
        )
        
        result = json.loads(response)
        assert result["result"]["result"] == 10
        assert result["result"]["tool"] == "double"
        assert result["result"]["status"] == "success"
    
    def test_adapter_handles_resources_list(self, protocol_adapter):
        """Test adapter handles resources/list"""
        protocol_adapter.initialize()
        
        response = protocol_adapter.handle_jsonrpc_request(
            json.dumps({
                "jsonrpc": "2.0",
                "method": "resources/list",
                "id": "req-1"
            })
        )
        
        result = json.loads(response)
        assert result["result"]["count"] >= 1
        assert "resources" in result["result"]
    
    def test_adapter_handles_prompts_list(self, protocol_adapter):
        """Test adapter handles prompts/list"""
        protocol_adapter.initialize()
        
        response = protocol_adapter.handle_jsonrpc_request(
            json.dumps({
                "jsonrpc": "2.0",
                "method": "prompts/list",
                "id": "req-1"
            })
        )
        
        result = json.loads(response)
        assert result["result"]["count"] == 2
        assert "prompts" in result["result"]
    
    def test_adapter_handles_ping(self, protocol_adapter):
        """Test adapter handles ping health check"""
        protocol_adapter.initialize()
        
        response = protocol_adapter.handle_jsonrpc_request(
            json.dumps({
                "jsonrpc": "2.0",
                "method": "ping",
                "id": "req-1"
            })
        )
        
        result = json.loads(response)
        assert result["result"]["status"] == "ok"
        assert result["result"]["protocol_version"] == "2024-11"


# ============================================================================
# MCP Compliance Tests
# ============================================================================


class TestMCPCompliance:
    """Test full MCP 2024-11 specification compliance"""
    
    def test_full_protocol_flow(self, protocol_adapter):
        """Test complete MCP protocol flow"""
        # 1. Initialize
        init_response = json.loads(
            protocol_adapter.handle_jsonrpc_request(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {"clientInfo": {"name": "Test", "version": "1.0"}},
                    "id": "init-1"
                })
            )
        )
        
        assert init_response["result"]["protocolVersion"] == "2024-11"
        
        # 2. List tools
        tools_response = json.loads(
            protocol_adapter.handle_jsonrpc_request(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": "req-1"
                })
            )
        )
        
        assert tools_response["result"]["count"] >= 1
        
        # 3. Call tool
        call_response = json.loads(
            protocol_adapter.handle_jsonrpc_request(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "double",
                        "arguments": {"value": 7}
                    },
                    "id": "req-2"
                })
            )
        )
        
        assert call_response["result"]["result"] == 14
        
        # 4. List resources
        resources_response = json.loads(
            protocol_adapter.handle_jsonrpc_request(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "resources/list",
                    "id": "req-3"
                })
            )
        )
        
        assert resources_response["result"]["count"] >= 1
        
        # 5. Health check
        ping_response = json.loads(
            protocol_adapter.handle_jsonrpc_request(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "ping",
                    "id": "req-4"
                })
            )
        )
        
        assert ping_response["result"]["status"] == "ok"
    
    def test_error_messages_follow_mcp_spec(self, protocol_adapter):
        """Test error messages follow MCP spec"""
        response = json.loads(
            protocol_adapter.handle_jsonrpc_request(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": "init-1"
                })
            )
        )
        
        # Initialize to allow other methods
        response = json.loads(
            protocol_adapter.handle_jsonrpc_request(
                json.dumps({
                    "jsonrpc": "2.0",
                    "method": "invalid/method",
                    "id": "req-1"
                })
            )
        )
        
        assert response["error"] is not None
        assert "code" in response["error"]
        assert "message" in response["error"]
        assert response["id"] == "req-1"
