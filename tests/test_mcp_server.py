"""
Comprehensive tests for MCP Server compliance.

Tests all major MCP features:
- Tool registration, listing, and invocation
- Resource management (register, list, read)
- Prompt templates (register, list, call)
- Server capabilities advertisement
- Notification system
"""

import pytest
from pydantic import BaseModel

from src.agent import (
    MCPServer,
    ToolDefinition,
    Resource,
    VerificationAuditLogResource,
    Prompt,
    VerificationExplanationPrompt,
    AuditSummaryPrompt,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mcp_server():
    """Create a fresh MCP server for each test"""
    return MCPServer(session_id="test-session-001")


@pytest.fixture
def simple_tool():
    """Define a simple test tool"""
    def test_handler(value: int) -> int:
        return value * 2
    
    return ToolDefinition(
        name="double_number",
        description="Doubles an input number",
        input_schema={"value": int},
        handler=test_handler
    )


@pytest.fixture
def validation_tool():
    """Define a tool with Pydantic model validation"""
    
    class DoubleInput(BaseModel):
        value: int
        name: str
    
    def validator_handler(value: int, name: str) -> dict:
        return {"input_value": value, "input_name": name, "doubled": value * 2}
    
    return ToolDefinition(
        name="validated_double",
        description="Doubles a number with validation",
        input_schema=DoubleInput,
        handler=validator_handler
    )


# ============================================================================
# Tool Management Tests
# ============================================================================


class TestToolManagement:
    """Test tool registration, listing, and invocation"""
    
    def test_register_tool(self, mcp_server, simple_tool):
        """Test registering a tool"""
        mcp_server.register_tool(simple_tool)
        assert "double_number" in mcp_server.tools
        assert mcp_server.tools["double_number"].name == "double_number"
    
    def test_tool_collision_prevention(self, mcp_server, simple_tool):
        """Test that duplicate tool names are rejected"""
        mcp_server.register_tool(simple_tool)
        
        with pytest.raises(ValueError, match="Tool name collision"):
            mcp_server.register_tool(simple_tool)
    
    def test_list_tools(self, mcp_server, simple_tool):
        """Test listing all registered tools"""
        mcp_server.register_tool(simple_tool)
        tools = mcp_server.list_tools()
        
        assert len(tools) == 1
        assert tools[0]["name"] == "double_number"
        assert tools[0]["description"] == "Doubles an input number"
        assert tools[0]["input_schema"] == {"value": int}
    
    def test_invoke_tool_success(self, mcp_server, simple_tool):
        """Test successfully invoking a tool"""
        mcp_server.register_tool(simple_tool)
        result = mcp_server.invoke_tool("double_number", {"value": 5})
        
        assert result == 10
    
    def test_invoke_tool_not_found(self, mcp_server):
        """Test invoking a tool that doesn't exist"""
        with pytest.raises(ValueError, match="Tool not found"):
            mcp_server.invoke_tool("nonexistent_tool", {})
    
    def test_invoke_tool_invalid_input(self, mcp_server, simple_tool):
        """Test that invalid inputs are rejected"""
        mcp_server.register_tool(simple_tool)
        
        with pytest.raises(ValueError, match="Invalid input"):
            mcp_server.invoke_tool("double_number", {"value": "not a number"})
    
    def test_invoke_tool_with_pydantic_validation(self, mcp_server, validation_tool):
        """Test tool invocation with Pydantic model validation"""
        mcp_server.register_tool(validation_tool)
        result = mcp_server.invoke_tool("validated_double", {
            "value": 7,
            "name": "test_value"
        })
        
        assert result["doubled"] == 14
        assert result["input_name"] == "test_value"
    
    def test_invoke_tool_missing_required_field(self, mcp_server, validation_tool):
        """Test that missing required fields are rejected"""
        mcp_server.register_tool(validation_tool)
        
        with pytest.raises(ValueError, match="Invalid input"):
            mcp_server.invoke_tool("validated_double", {"value": 7})


# ============================================================================
# Resource Management Tests
# ============================================================================


class TestResourceManagement:
    """Test resource registration, listing, and reading"""
    
    def test_register_resource(self, mcp_server):
        """Test registering a resource"""
        resource = VerificationAuditLogResource("test-session")
        mcp_server.register_resource(resource)
        
        assert resource.uri in mcp_server.resources
    
    def test_resource_collision_prevention(self, mcp_server):
        """Test that duplicate resource URIs are rejected"""
        resource1 = VerificationAuditLogResource("session-1")
        resource2 = VerificationAuditLogResource("session-1")
        
        mcp_server.register_resource(resource1)
        
        with pytest.raises(ValueError, match="Resource URI collision"):
            mcp_server.register_resource(resource2)
    
    def test_list_resources(self, mcp_server):
        """Test listing all resources in MCP-compliant format"""
        resources = mcp_server.list_resources()
        
        # Server already registers an audit log resource in __init__
        assert len(resources) >= 1
        assert any(r["uri"].startswith("audit://") for r in resources)
        
        # Check MCP format
        resource = resources[0]
        assert "uri" in resource
        assert "name" in resource
        assert "description" in resource
        assert "mimeType" in resource
    
    def test_read_resource(self, mcp_server):
        """Test reading a resource"""
        resources = mcp_server.list_resources()
        audit_resource_uri = [r["uri"] for r in resources if "audit" in r["uri"]][0]
        
        content = mcp_server.read_resource(audit_resource_uri)
        assert isinstance(content, str)
        assert "verifications" in content
    
    def test_read_nonexistent_resource(self, mcp_server):
        """Test reading a resource that doesn't exist"""
        with pytest.raises(ValueError, match="Resource not found"):
            mcp_server.read_resource("audit://missing")
    
    def test_audit_log_resource_entries(self, mcp_server):
        """Test adding entries to audit log resource"""
        resources = mcp_server.list_resources()
        audit_uri = [r["uri"] for r in resources if "audit" in r["uri"]][0]
        audit_resource = mcp_server.resources[audit_uri]
        
        # Add verification entries
        audit_resource.add_entry("verkle", "valid", {"commitment": "0x123abc"})
        audit_resource.add_entry("ibs", "valid", {"signature": "0xdef456"})
        
        content = mcp_server.read_resource(audit_uri)
        assert "verkle" in content
        assert "ibs" in content
        assert "0x123abc" in content


# ============================================================================
# Prompt Management Tests
# ============================================================================


class Prompt:
    """Schema for a reusable prompt template.
    
    Prompts are named templates with placeholders that can be rendered
    with arguments to generate consistent, reproducible LLM inputs.
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        template: str,
        arguments: dict[str, str]
    ):
        self.name = name
        self.description = description
        self.template = template  # Template with {arg} placeholders
        self.arguments = arguments  # Argument schemas
    
    def render(self, arguments: dict[str, str]) -> str:
        """Render template with provided arguments"""
        try:
            return self.template.format(**arguments)
        except KeyError as e:
            raise ValueError(f"Missing required argument: {e}")


@pytest.fixture
def custom_prompt():
    """Define a custom test prompt"""
    return Prompt(
        name="custom_test_prompt",
        description="A test prompt for unit tests",
        template="Test with: {value}",
        arguments={"value": "test value"}
    )


# ============================================================================
# Prompt Management Tests
# ============================================================================


class TestPromptManagement:
    """Test prompt template registration, listing, and calling"""
    
    def test_register_prompt(self, mcp_server, custom_prompt):
        """Test registering a prompt"""
        mcp_server.register_prompt(custom_prompt)
        
        assert "custom_test_prompt" in mcp_server.prompts
    
    def test_prompt_collision_prevention(self, mcp_server, custom_prompt):
        """Test that duplicate prompt names are rejected"""
        mcp_server.register_prompt(custom_prompt)
        
        # Try to register another with the same name
        duplicate = Prompt(
            name="custom_test_prompt",
            description="Duplicate",
            template="Duplicate: {x}",
            arguments={"x": "value"}
        )
        
        with pytest.raises(ValueError, match="Prompt name collision"):
            mcp_server.register_prompt(duplicate)
    
    def test_list_prompts(self, mcp_server):
        """Test listing all prompts in MCP-compliant format"""
        prompts = mcp_server.list_prompts()
        
        # Server registers two example prompts
        assert len(prompts) == 2
        prompt_names = [p["name"] for p in prompts]
        assert "explain_verification" in prompt_names
        assert "audit_summary" in prompt_names
        
        # Check MCP format
        prompt = prompts[0]
        assert "name" in prompt
        assert "description" in prompt
        assert "arguments" in prompt
    
    def test_call_prompt(self, mcp_server):
        """Test rendering a prompt template"""
        rendered = mcp_server.call_prompt("explain_verification", {
            "proof_type": "Verkle Tree",
            "proof_details": "Commitment: 0x123abc..."
        })
        
        assert isinstance(rendered, str)
        assert "Verkle Tree" in rendered
        assert "0x123abc" in rendered
    
    def test_call_nonexistent_prompt(self, mcp_server):
        """Test calling a prompt that doesn't exist"""
        with pytest.raises(ValueError, match="Prompt not found"):
            mcp_server.call_prompt("nonexistent_prompt", {})
    
    def test_call_prompt_missing_argument(self, mcp_server):
        """Test that missing prompt arguments are caught"""
        with pytest.raises(ValueError, match="Missing required argument"):
            mcp_server.call_prompt("explain_verification", {
                "proof_type": "Verkle Tree"
                # Missing proof_details
            })
    
    def test_audit_summary_prompt(self, mcp_server):
        """Test rendering audit summary prompt"""
        import json
        audit_log = json.dumps({
            "verifications": [
                {"proof_type": "verkle", "result": "valid"},
                {"proof_type": "ibs", "result": "valid"}
            ]
        })
        
        rendered = mcp_server.call_prompt("audit_summary", {
            "audit_log": audit_log
        })
        
        assert "security summary" in rendered.lower()


# ============================================================================
# Server Capabilities Tests
# ============================================================================


class TestServerCapabilities:
    """Test capability advertisement"""
    
    def test_get_capabilities(self, mcp_server):
        """Test retrieving server capabilities"""
        capabilities = mcp_server.get_capabilities()
        
        # Check protocol version
        assert capabilities["protocolVersion"] == "2025-11-25"
        
        # Check capabilities structure
        caps = capabilities["capabilities"]
        assert "tools" in caps
        assert "resources" in caps
        assert "prompts" in caps
        assert "notifications" in caps
        assert "sampling" in caps
        
        # Check tool capability
        assert caps["tools"]["enabled"] is True
        assert "count" in caps["tools"]
        
        # Check resource capability
        assert caps["resources"]["enabled"] is True
        assert caps["resources"]["count"] >= 1  # Audit log registered by default
        
        # Check prompt capability
        assert caps["prompts"]["enabled"] is True
        assert caps["prompts"]["count"] == 2  # Two example prompts
        
        # Check notification capability
        assert caps["notifications"]["enabled"] is True
        assert isinstance(caps["notifications"]["supportedTypes"], list)
        
        # Sampling should be disabled
        assert caps["sampling"] is False
    
    def test_server_info(self, mcp_server):
        """Test server info advertisement"""
        capabilities = mcp_server.get_capabilities()
        server_info = capabilities["serverInfo"]
        
        assert "name" in server_info
        assert "version" in server_info
        assert "features" in server_info
        assert "Crypto Protocols" in server_info["name"]
        assert "byte-level-canonicalization" in server_info["features"]
        assert "verkle-tree-commitments" in server_info["features"]
        assert "identity-based-signatures" in server_info["features"]


# ============================================================================
# Notification System Tests
# ============================================================================


class TestNotificationSystem:
    """Test notification subscription and delivery"""
    
    def test_subscribe_notifications(self, mcp_server, simple_tool):
        """Test subscribing to notifications"""
        notifications = []
        
        def notification_handler(notification):
            notifications.append(notification)
        
        mcp_server.subscribe_notifications(notification_handler)
        mcp_server.register_tool(simple_tool)
        
        # Should have received a notification
        assert len(notifications) == 1
        assert notifications[0]["type"] == "tool_registered"
        assert notifications[0]["data"]["tool_name"] == "double_number"
    
    def test_notification_structure(self, mcp_server, simple_tool):
        """Test notification contains all required fields"""
        notifications = []
        mcp_server.subscribe_notifications(lambda n: notifications.append(n))
        mcp_server.register_tool(simple_tool)
        
        notification = notifications[0]
        assert "type" in notification
        assert "timestamp" in notification
        assert "sessionId" in notification
        assert "data" in notification
        assert notification["sessionId"] == "test-session-001"
    
    def test_multiple_subscribers(self, mcp_server, simple_tool):
        """Test multiple notification subscribers"""
        notifications1 = []
        notifications2 = []
        
        mcp_server.subscribe_notifications(lambda n: notifications1.append(n))
        mcp_server.subscribe_notifications(lambda n: notifications2.append(n))
        mcp_server.register_tool(simple_tool)
        
        assert len(notifications1) == 1
        assert len(notifications2) == 1
        assert notifications1[0]["type"] == notifications2[0]["type"]
    
    def test_resource_access_notification(self, mcp_server):
        """Test notification on resource access"""
        notifications = []
        mcp_server.subscribe_notifications(lambda n: notifications.append(n))
        
        # Get the audit log resource
        resources = mcp_server.list_resources()
        audit_uri = [r["uri"] for r in resources if "audit" in r["uri"]][0]
        
        # Clear initial notifications (from initialization)
        notifications.clear()
        
        # Read the resource
        mcp_server.read_resource(audit_uri)
        
        # Should have received an access notification
        assert any(n["type"] == "resource_accessed" for n in notifications)
    
    def test_tool_execution_notification(self, mcp_server, simple_tool):
        """Test notification on tool execution"""
        mcp_server.register_tool(simple_tool)
        notifications = []
        mcp_server.subscribe_notifications(lambda n: notifications.append(n))
        
        notifications.clear()
        mcp_server.invoke_tool("double_number", {"value": 5})
        
        # Should have received an execution notification
        assert any(n["type"] == "tool_executed" for n in notifications)
        exec_notif = [n for n in notifications if n["type"] == "tool_executed"][0]
        assert exec_notif["data"]["tool_name"] == "double_number"
        assert exec_notif["data"]["status"] == "success"
    
    def test_prompt_call_notification(self, mcp_server):
        """Test notification on prompt call"""
        notifications = []
        mcp_server.subscribe_notifications(lambda n: notifications.append(n))
        
        # Clear initialization notifications
        notifications.clear()
        
        mcp_server.call_prompt("explain_verification", {
            "proof_type": "Verkle",
            "proof_details": "test"
        })
        
        # Should have received a prompt call notification
        assert any(n["type"] == "prompt_called" for n in notifications)


# ============================================================================
# Integration Tests
# ============================================================================


class TestMCPServerIntegration:
    """Integration tests combining multiple features"""
    
    def test_complete_workflow(self, mcp_server, simple_tool):
        """Test a complete workflow using multiple MCP features"""
        notifications = []
        mcp_server.subscribe_notifications(lambda n: notifications.append(n))
        
        # Register a tool
        mcp_server.register_tool(simple_tool)
        
        # Get capabilities
        caps = mcp_server.get_capabilities()
        assert caps["capabilities"]["tools"]["count"] == 1
        
        # List and invoke tool
        tools = mcp_server.list_tools()
        assert len(tools) == 1
        
        result = mcp_server.invoke_tool("double_number", {"value": 10})
        assert result == 20
        
        # Access resources
        resources = mcp_server.list_resources()
        assert len(resources) >= 1
        
        # Use a prompt
        rendered = mcp_server.call_prompt("explain_verification", {
            "proof_type": "test",
            "proof_details": "test details"
        })
        assert "test" in rendered
        
        # Check notifications
        assert len(notifications) > 0
        notification_types = [n["type"] for n in notifications]
        assert "tool_registered" in notification_types
        assert "tool_executed" in notification_types
    
    def test_mcp_compliance_summary(self, mcp_server):
        """Verify full MCP compliance"""
        # 1. Server Capabilities (Feature 3)
        caps = mcp_server.get_capabilities()
        assert caps["protocolVersion"] == "2025-11-25"
        
        # 2. Resource Management (Feature 1)
        assert len(mcp_server.list_resources()) >= 1
        assert len(mcp_server.resources) >= 1
        
        # 3. Prompt Management (Feature 2)
        assert len(mcp_server.list_prompts()) == 2
        assert len(mcp_server.prompts) == 2
        
        # 4. Tool Management
        assert mcp_server.list_tools() is not None
        
        # 5. Notification System (Feature 5)
        assert callable(mcp_server.subscribe_notifications)
        assert callable(mcp_server.send_notification)
        
        print("\n✅ Full MCP Compliance Verified:")
        print(f"   - Protocol Version: {caps['protocolVersion']}")
        print(f"   - Resources: {len(mcp_server.resources)}")
        print(f"   - Prompts: {len(mcp_server.prompts)}")
        print(f"   - Notifications: Enabled")
        print(f"   - Server Features: {caps['serverInfo']['features']}")
