"""
AI Agent Server with MCP-compatible tool routing
Implements the core agent runtime with tool handling and LLM integration.

Supports LLM-integrated agent loops with OpenRouter and Ollama.
- Records all LLM interactions in integrity middleware
- Handles multi-turn tool calling
- Validates tools through security middleware
"""

from __future__ import annotations

import inspect
import json
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional, Union

import structlog
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError, create_model

if TYPE_CHECKING:
    from src.integrity import IntegrityMiddleware
    from src.llm import OllamaClient, OpenRouterClient
    from src.security import SecurityMiddleware

from src.llm import LLMResponse

# Re-export MCP transport components for architectural clarity
try:
    from src.transport.secure_mcp import SecureMCPClient, SecureMCPServer
except ImportError:
    SecureMCPClient = None  # type: ignore
    SecureMCPServer = None  # type: ignore

logger = structlog.get_logger(__name__)


class IntegrityMetadata(BaseModel):
    """MCP 2025-11-25 compliant integrity metadata"""
    model_config = ConfigDict(frozen=False)
    
    session_id: str                             # Session identifier
    session_root: str                           # Hierarchical commitment
    event_accumulator_root: str                 # Flat event structure root
    span_roots: dict[str, str]                  # Per-span roots
    canonical_log_hash: str                     # SHA-256 of canonical log
    event_count: int                            # Total events recorded
    timestamp: str                              # Finalization time (ISO 8601)


class AgentResponse(BaseModel):
    """
    MCP 2025-11-25 compliant agent response.
    
    Provides a structured contract for agent interactions with:
    - Text output (LLM response)
    - Integrity metadata (cryptographic verification)
    - Session metadata (turn count, etc)
    """
    model_config = ConfigDict(frozen=False)
    
    output: str                                 # LLM response text
    integrity: IntegrityMetadata               # Cryptographic commitments
    turns: int                                  # Number of interaction turns


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
        """Validate input against schema.
        
        Security: Enforces contract boundaries by validating type safety and structure,
        preventing injection attacks and ensuring auditability of tool invocations.
        """
        try:
            if isinstance(self.input_schema, type) and issubclass(self.input_schema, BaseModel):
                self.input_schema(**args)
                return True
            
            # If schema is a dict of types (like in tests), create dynamic model
            if isinstance(self.input_schema, dict):
                # Convert simplified schema to Pydantic field definitions
                fields = {
                    k: (v, ...) 
                    for k, v in self.input_schema.items() 
                    if isinstance(v, type)
                }
                if fields:
                    DynamicModel = create_model(f"{self.name}Input", **fields)
                    DynamicModel(**args)
                    return True
                
            return True
        except ValidationError as e:
            logger.warning("tool_input_validation_failed", tool=self.name, error=str(e))
            return False


class Resource:
    """Schema for a resource exposed by the server.
    
    Resources represent files, data sources, or other artifacts that tools
    may reference but do not directly execute.
    """
    
    def __init__(
        self,
        uri: str,
        name: str,
        description: str,
        mime_type: str = "text/plain"
    ):
        self.uri = uri
        self.name = name
        self.description = description
        self.mime_type = mime_type
    
    def read(self) -> str:
        """Read the resource content. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement read()")


class VerificationAuditLogResource(Resource):
    """Example resource: audit log of all verifications in session"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        super().__init__(
            uri=f"audit://verification-log/{session_id}",
            name="Verification Audit Log",
            description="Records of all cryptographic verifications performed in this session",
            mime_type="application/json"
        )
        self.entries: list[dict[str, Any]] = []
    
    def add_entry(self, proof_type: str, result: str, details: dict[str, Any]) -> None:
        """Log a verification entry"""
        self.entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "proof_type": proof_type,
            "result": result,
            "details": details
        })
    
    def read(self) -> str:
        """Return audit log as JSON"""
        return json.dumps({
            "session_id": self.session_id,
            "verifications": self.entries
        }, indent=2)


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


class VerificationExplanationPrompt(Prompt):
    """Example prompt: ask LLM to explain why a proof is valid"""
    
    def __init__(self):
        super().__init__(
            name="explain_verification",
            description="Generates a cryptographic explanation of why a proof is valid",
            template="""You are a cryptography expert. Explain why the {proof_type} proof is cryptographically sound.

Consider:
- The commitment scheme used
- Security assumptions required
- The verification algorithm steps

Proof Details:
{proof_details}

Provide a clear, technical explanation suitable for a security audit.""",
            arguments={
                "proof_type": "Type of proof (verkle, ibs, kzg, etc.",
                "proof_details": "Detailed information about the specific proof"
            }
        )


class AuditSummaryPrompt(Prompt):
    """Example prompt: summarize all audits from log"""
    
    def __init__(self):
        super().__init__(
            name="audit_summary",
            description="Generates a summary of all verifications in an audit log",
            template="""Based on the following verification audit log, provide a security summary:

{audit_log}

Include:
- Number of successful verifications
- Proof types used
- Any patterns or concerns
- Overall security posture assessment""",
            arguments={
                "audit_log": "JSON-formatted verification audit log"
            }
        )


class MCPServer:
    """
    Simplified MCP-compatible server for agent message routing.
    Manages tool definitions and coordinates with integrity middleware.
    
    Features:
    - Tool Registry: Manages local tool definitions and schemas.
    - Input Validation: Enforces Pydantic schemas for reliable execution.
    - Resource Management: Exposes files and data sources for tool reference.
    - Prompt Templates: Provides reusable LLM prompt templates.
    - Server Capabilities: Advertises MCP compliance and supported features.
    - Notification System: Sends events to connected clients.
    - Secure Transport Integration: Designed to work with `SecureMCPClient` 
      (src/transport/secure_mcp.py) for verifiable remote tool execution over WebSockets.

    NOTE: A custom transport layer is used instead of standard FastMCP to ensure
    byte-level canonicalization required for Verkle Tree commitments and 
    Identity-Based Signatures (IBS).
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.tools: dict[str, ToolDefinition] = {}
        self.resources: dict[str, Resource] = {}
        self.prompts: dict[str, Prompt] = {}
        self.notification_handlers: list[callable] = []
        
        # Register example resources and prompts
        audit_log_resource = VerificationAuditLogResource(session_id)
        self.register_resource(audit_log_resource)
        
        self.register_prompt(VerificationExplanationPrompt())
        self.register_prompt(AuditSummaryPrompt())
        
        logger.info("mcp_server_initialized", session_id=session_id)
    
    def get_capabilities(self) -> dict[str, Any]:
        """Advertise server capabilities per MCP specification.
        
        Returns compliance information for protocol version 2025-11-25.
        """
        return {
            "protocolVersion": "2025-11-25",
            "capabilities": {
                "tools": {
                    "enabled": True,
                    "count": len(self.tools)
                },
                "resources": {
                    "enabled": True,
                    "count": len(self.resources)
                },
                "prompts": {
                    "enabled": True,
                    "count": len(self.prompts)
                },
                "notifications": {
                    "enabled": True,
                    "supportedTypes": [
                        "tool_executed",
                        "resource_accessed",
                        "verification_complete"
                    ]
                },
                "sampling": False,  # Integrated LLM client, no sampling needed
            },
            "serverInfo": {
                "name": "Crypto Protocols MCP Server",
                "version": "1.0.0",
                "features": [
                    "byte-level-canonicalization",
                    "verkle-tree-commitments",
                    "identity-based-signatures"
                ]
            }
        }
    
    def verify_protocol_version(self, remote_version: str) -> bool:
        """
        Verify protocol version compatibility with remote peer.
        
        Ensures remote is using MCP 2025-11-25 or compatible patch version.
        Warns if mismatch detected.
        
        Args:
            remote_version: Version string from remote peer (e.g., "2025-11-25", "2025-12-xx")
        
        Returns:
            True if version is compatible (2025-xx), False otherwise
        """
        expected_version = "2025-11-25"
        
        if remote_version == expected_version:
            logger.info("protocol_version_verified", remote_version=remote_version)
            return True
        
        if remote_version.startswith("2025-"):
            # Accept 2025-xx patches for backward compatibility
            logger.warning(
                "protocol_version_mismatch_patch",
                expected=expected_version,
                remote=remote_version,
                note="Using different 2025-xx patch; JSON-RPC format should be compatible"
            )
            return True
        
        # Major version mismatch
        logger.error(
            "protocol_version_incompatible",
            expected=expected_version,
            remote=remote_version,
            note="Major version mismatch; cryptographic commitments may not be valid"
        )
        return False
    
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """
        Register a tool with the server.
        Enforces unique tool names to prevent identity collisions.
        """
        if tool.name in self.tools:
            raise ValueError(f"Tool name collision: '{tool.name}' is already registered. Identities must be unique.")
            
        self.tools[tool.name] = tool
        logger.info("tool_registered", tool_name=tool.name)
        self.send_notification("tool_registered", {"tool_name": tool.name})
    
    def register_resource(self, resource: Resource) -> None:
        """Register a resource with the server."""
        if resource.uri in self.resources:
            raise ValueError(f"Resource URI collision: '{resource.uri}' is already registered.")
        
        self.resources[resource.uri] = resource
        logger.info("resource_registered", resource_uri=resource.uri)
        self.send_notification("resource_registered", {"resource_uri": resource.uri})
    
    def register_prompt(self, prompt: Prompt) -> None:
        """Register a prompt template with the server."""
        if prompt.name in self.prompts:
            raise ValueError(f"Prompt name collision: '{prompt.name}' is already registered.")
        
        self.prompts[prompt.name] = prompt
        logger.info("prompt_registered", prompt_name=prompt.name)
        self.send_notification("prompt_registered", {"prompt_name": prompt.name})
    
    
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
    
    def list_resources(self) -> list[dict[str, Any]]:
        """List all available resources (MCP-compliant format)"""
        return [
            {
                "uri": resource.uri,
                "name": resource.name,
                "description": resource.description,
                "mimeType": resource.mime_type
            }
            for resource in self.resources.values()
        ]
    
    def read_resource(self, resource_uri: str) -> str:
        """Read a resource by URI"""
        if resource_uri not in self.resources:
            raise ValueError(f"Resource not found: {resource_uri}")
        
        resource = self.resources[resource_uri]
        content = resource.read()
        logger.info("resource_accessed", resource_uri=resource_uri)
        self.send_notification("resource_accessed", {"resource_uri": resource_uri})
        return content
    
    def list_prompts(self) -> list[dict[str, Any]]:
        """List all available prompt templates (MCP-compliant format)"""
        return [
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": prompt.arguments
            }
            for prompt in self.prompts.values()
        ]
    
    def call_prompt(self, prompt_name: str, arguments: dict[str, str]) -> str:
        """Evaluate a prompt template with provided arguments"""
        if prompt_name not in self.prompts:
            raise ValueError(f"Prompt not found: {prompt_name}")
        
        prompt = self.prompts[prompt_name]
        rendered = prompt.render(arguments)
        logger.info("prompt_called", prompt_name=prompt_name)
        self.send_notification("prompt_called", {"prompt_name": prompt_name})
        return rendered
    
    def send_notification(self, notification_type: str, data: dict[str, Any]) -> None:
        """Send a notification to all subscribed clients"""
        notification = {
            "type": notification_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sessionId": self.session_id,
            "data": data
        }
        logger.info("notification_sent", notification_type=notification_type)
        
        for handler in self.notification_handlers:
            try:
                handler(notification)
            except Exception as e:
                logger.exception("notification_handler_error", error=str(e))
    
    def subscribe_notifications(self, handler: callable) -> None:
        """Subscribe a handler to receive server notifications"""
        self.notification_handlers.append(handler)
        logger.info("notification_subscriber_registered")
    
    
    def invoke_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Invoke a tool by name with given arguments"""
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")
        
        tool = self.tools[tool_name]
        
        # Validate input
        if not tool.validate_input(args):
            raise ValueError(f"Invalid input for tool {tool_name}")
        
        # Execute handler
        result = tool.handler(**args)
        self.send_notification("tool_executed", {"tool_name": tool_name, "status": "success"})
        return result
    
    async def invoke_tool_async(self, tool_name: str, args: dict[str, Any]) -> Any:
        """
        Asynchronously invoke a tool by name with given arguments.
        
        Supports both synchronous and asynchronous tool handlers.
        Automatically detects handler type and awaits if needed.
        
        Cryptographic Integrity Note:
        =============================
        This method does NOT modify integrity recording behavior.
        All tool input/output recording is done by the caller (AIAgent.run_async)
        using synchronous integrity middleware methods, which preserves
        cryptographic commitments exactly as in the synchronous path.
        
        The async boundary is ONLY at tool invocation, not at recording.
        """
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")
        
        tool = self.tools[tool_name]
        
        # Validate input
        if not tool.validate_input(args):
            raise ValueError(f"Invalid input for tool {tool_name}")
        
        # Execute handler - check if it's async
        if inspect.iscoroutinefunction(tool.handler):
            result = await tool.handler(**args)
        else:
            result = tool.handler(**args)
        
        self.send_notification("tool_executed", {"tool_name": tool_name, "status": "success"})
        return result


class MCPHost:
    """
    MCP 2025-11-25 Host: Orchestrates the MCP server/client lifecycle and tool execution.
    
    This class stands at the architectural center of the MCP implementation:
    - Manages the MCPServer (local tool registry)
    - Manages SecureMCPClient connections to remote tools
    - Enforces security policies (tool authorization, input validation)
    - Records all tool interactions via integrity middleware
    - Supports both synchronous and asynchronous tool invocation
    
    The MCPHost delegates LLM loop logic to AIAgent and focuses exclusively on:
    1. Tool authorization (security middleware)
    2. Tool invocation (MCPServer)
    3. Integrity recording (integrity middleware)
    4. Remote tool communication (SecureMCPClient)
    
    Architecture:
        MCPHost (this class)
        ├── MCPServer: local tool management
        ├── SecurityMiddleware: authorization enforcement
        ├── IntegrityMiddleware: cryptographic recording
        └── SecureMCPClient instances: remote tool clients
        
        AIAgent delegates all tool concerns to MCPHost via invoke_tool/invoke_tool_async
    """
    
    def __init__(
        self,
        integrity_middleware: IntegrityMiddleware,
        security_middleware: SecurityMiddleware,
        mcp_server: MCPServer
    ):
        """
        Initialize the MCP Host.
        
        Args:
            integrity_middleware: Integrity tracking middleware for recording tool interactions
            security_middleware: Security validation middleware for authorization checks
            mcp_server: MCPServer instance managing local tool definitions
        """
        self.integrity = integrity_middleware
        self.security = security_middleware
        self.mcp = mcp_server
        self.remote_clients: dict[str, Any] = {}  # tool_name -> SecureMCPClient
        
        logger.info("mcp_host_initialized", session_id=self.integrity.session_id)
    
    def register_remote_tool(
        self,
        tool_name: str,
        host: str,
        port: int
    ) -> Any:  # Returns SecureMCPClient
        """
        Register a client connection to a remote tool via secure WebSocket.
        
        Args:
            tool_name: Identifier for the remote tool
            host: Hostname/IP of remote tool server
            port: WebSocket port of remote tool server
            
        Returns:
            The connected SecureMCPClient instance
            
        Raises:
            RuntimeError: If SecureMCPClient is not available (import failed)
        """
        if SecureMCPClient is None:
            raise RuntimeError(
                "SecureMCPClient not available. Ensure src/transport/secure_mcp.py is accessible."
            )
        
        client = SecureMCPClient(tool_name, host, port, self.integrity)
        self.remote_clients[tool_name] = client
        logger.info("remote_tool_registered", tool_name=tool_name, host=host, port=port)
        return client
    
    def invoke_tool(self, tool_call: Any) -> str:
        """
        Synchronously invoke a tool with authorization and integrity recording.
        
        Security flow:
        1. Check tool authorization via security middleware
        2. Record tool input to integrity log
        3. Execute tool locally via MCPServer
        4. Record tool output to integrity log
        5. Return result to agent
        
        Args:
            tool_call: Object with tool_name and arguments attributes
            
        Returns:
            Tool result as string
        """
        # Step 1: Authorization check
        if not self.security.validate_tool_invocation(
            self.integrity.session_id, tool_call.tool_name
        ):
            error_msg = f"Unauthorized tool: {tool_call.tool_name}"
            logger.warning("tool_call_blocked", tool=tool_call.tool_name)
            
            # Record the blocked attempt for audit purposes
            self.integrity.record_tool_input(tool_call.tool_name, tool_call.arguments)
            blocked_result = f"Error: {error_msg}"
            self.integrity.record_tool_output(tool_call.tool_name, blocked_result)
            return blocked_result
        
        # Step 2-5: Record input, execute, record output
        self.integrity.record_tool_input(tool_call.tool_name, tool_call.arguments)
        try:
            tool_result = self.mcp.invoke_tool(tool_call.tool_name, tool_call.arguments)
            logger.info("tool_executed", tool=tool_call.tool_name, result=str(tool_result)[:100])
        except Exception as e:
            tool_result = f"Error executing tool: {str(e)}"
            logger.exception("tool_execution_error", tool=tool_call.tool_name)
        
        self.integrity.record_tool_output(tool_call.tool_name, tool_result)
        return tool_result
    
    async def invoke_tool_async(self, tool_call: Any) -> str:
        """
        Asynchronously invoke a tool with authorization and integrity recording.
        
        Identical to invoke_tool but supports async tool handlers via MCPServer.invoke_tool_async.
        
        Cryptographic Integrity Note:
        =============================
        This method produces IDENTICAL cryptographic commitments to invoke_tool.
        All integrity recording is synchronous (unchanged).
        Only tool invocation is async (via MCPServer.invoke_tool_async).
        
        Args:
            tool_call: Object with tool_name and arguments attributes
            
        Returns:
            Tool result as string
        """
        # Step 1: Authorization check
        if not self.security.validate_tool_invocation(
            self.integrity.session_id, tool_call.tool_name
        ):
            error_msg = f"Unauthorized tool: {tool_call.tool_name}"
            logger.warning("tool_call_blocked", tool=tool_call.tool_name)
            
            # Record the blocked attempt for audit purposes
            self.integrity.record_tool_input(tool_call.tool_name, tool_call.arguments)
            blocked_result = f"Error: {error_msg}"
            self.integrity.record_tool_output(tool_call.tool_name, blocked_result)
            return blocked_result
        
        # Step 2-5: Record input, execute, record output
        self.integrity.record_tool_input(tool_call.tool_name, tool_call.arguments)
        try:
            tool_result = await self.mcp.invoke_tool_async(tool_call.tool_name, tool_call.arguments)
            logger.info("tool_executed", tool=tool_call.tool_name, result=str(tool_result)[:100])
        except Exception as e:
            tool_result = f"Error executing tool: {str(e)}"
            logger.exception("tool_execution_error", tool=tool_call.tool_name)
        
        self.integrity.record_tool_output(tool_call.tool_name, tool_result)
        return tool_result
    
    def list_tools(self) -> list[dict[str, Any]]:
        """
        List all available tools (from MCPServer).
        
        Returns:
            List of tool schemas with name, description, and input schema
        """
        return self.mcp.list_tools()
    
    def list_capabilities(self) -> dict[str, Any]:
        """
        Advertise MCP host capabilities.
        
        Returns:
            MCP 2025-11-25 compliant capabilities dictionary
        """
        return self.mcp.get_capabilities()


class AIAgent:
    """
    MCP 2025-11-25 Agent: Executes LLM reasoning with tool calling.
    
    This class focuses exclusively on the LLM loop:
    - Validating the LLM client configuration
    - Building conversation history
    - Calling the LLM with available tools
    - Parsing tool calls from LLM responses
    - Invoking tools via the MCPHost
    - Building and finalizing agent responses
    
    Tool invocation, authorization, and integrity recording are delegated to MCPHost.
    
    Supports both local and cloud-based LLM backends:
    - OllamaClient: Local Ollama instance (requires local setup)
    - OpenRouterClient: Cloud-based OpenRouter.ai API (requires API key)
    """
    
    def __init__(
        self,
        mcp_host: MCPHost,
        llm_client: Optional[Union["OllamaClient", "OpenRouterClient"]] = None
    ):
        """
        Initialize the AI Agent.
        
        Args:
            mcp_host: MCPHost instance for tool invocation and orchestration
            llm_client: Optional LLM client (OllamaClient or OpenRouterClient)
                       If None, raises RuntimeError on first run()
                       
        Examples:
            # Setup MCP Host with server and middleware
            mcp_server = MCPServer(session_id=session_id)
            mcp_host = MCPHost(integrity_middleware, security_middleware, mcp_server)
            
            # Create agent with LLM client
            from src.llm import OllamaClient
            ollama = OllamaClient(model="llama2")
            agent = AIAgent(mcp_host=mcp_host, llm_client=ollama)
            
            # Or create with factory LLM
            agent = AIAgent(mcp_host=mcp_host, llm_client=AIAgent.create_llm_client())
        """
        self.mcp_host = mcp_host
        self.llm_client = llm_client
        
        logger.info("ai_agent_initialized", session_id=self.mcp_host.integrity.session_id)
    
    @staticmethod
    def create_llm_client() -> Union["OllamaClient", "OpenRouterClient"]:
        """
        Factory method: create the appropriate LLM client based on LLM_PROVIDER env var.
        
        Providers:
            - "ollama"  (default): Local Ollama at OLLAMA_BASE_URL
            - "openrouter": Cloud-based OpenRouter.ai API
        
        Returns:
            Configured LLM client (OllamaClient or OpenRouterClient)
            
        Raises:
            ValueError: If provider is unknown or required config is missing
        """
        load_dotenv()
        
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        
        if provider == "ollama":
            from src.llm import OllamaClient
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            model = os.getenv("OLLAMA_MODEL", "llama3.1")
            client = OllamaClient(model=model, base_url=base_url)
            logger.info("llm_client_created", provider="ollama", model=model, base_url=base_url)
            return client
        
        elif provider == "openrouter":
            from src.llm import OpenRouterClient
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            model = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY not set. Get a free key at: https://openrouter.ai/keys"
                )
            client = OpenRouterClient(api_key=api_key, model=model)
            logger.info("llm_client_created", provider="openrouter", model=model)
            return client
        
        else:
            raise ValueError(
                f"Unknown LLM_PROVIDER: '{provider}'. Supported: 'ollama', 'openrouter'"
            )
    
    # ==================================================================================
    # Private helpers — shared logic used by both run() and run_async()
    # ==================================================================================

    def _validate_and_prepare(self, prompt: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Validate LLM client and prepare the execution context.
        
        Starts the top-level integrity span, records the initial prompt,
        and builds the tool schema list from MCPHost.
        
        Returns:
            Tuple of (model_name, tool_schemas, conversation_history)
            
        Raises:
            RuntimeError: If no LLM client is configured
        """
        if self.llm_client is None:
            raise RuntimeError(
                "No LLM client configured. Set LLM_PROVIDER in .env and ensure "
                "the provider is properly configured (see .env for OLLAMA_* or OPENROUTER_* settings). "
                "Use AIAgent.create_llm_client() to create one automatically."
            )
        
        self.mcp_host.integrity.start_span("agent_run")
        
        model_name = getattr(self.llm_client, 'model', 'unknown')
        self.mcp_host.integrity.record_prompt(prompt, metadata={"model": model_name})
        
        tool_schemas = self.mcp_host.list_tools()
        conversation_history: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        
        return model_name, tool_schemas, conversation_history

    def _call_llm_and_record(
        self,
        conversation_history: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        model_name: str,
        turn_count: int,
    ) -> tuple[Any, dict]:
        """
        Call the LLM and record the generation for observability.
        
        Returns:
            Tuple of (llm_response, usage_dict)
        """
        llm_response = self.llm_client.call_llm(
            messages=conversation_history,
            tools=tool_schemas
        )
        
        usage = getattr(llm_response, 'usage', {}) or {}
        
        self.mcp_host.integrity.record_llm_generation(
            prompt=conversation_history[-1]["content"],
            response=llm_response.text,
            model=model_name,
            name=f"llm_call_turn_{turn_count}",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            turn=turn_count,
        )
        
        return llm_response, usage

    
    def _append_tool_results_to_history(
        self,
        conversation_history: list[dict[str, Any]],
        llm_response: Any,
        tool_results_parts: list[str],
    ) -> None:
        """Append assistant response and tool results to conversation history for the next LLM turn."""
        conversation_history.append({
            "role": "assistant",
            "content": llm_response.text
        })
        if llm_response.tool_calls:
            results_msg = "\n".join(tool_results_parts)
            conversation_history.append({
                "role": "user",
                "content": f"Tool results:\n{results_msg}\n\nBased on these tool results, please provide your final answer."
            })

    def _build_response(
        self,
        final_output: str,
        model_name: str,
        last_usage: dict,
        turn_count: int,
    ) -> dict[str, Any]:
        """Record final output, finalize integrity commitments, and build the MCP response."""
        if final_output:
            output_metadata = {
                "model": model_name,
                "input_tokens": last_usage.get("input_tokens", 0),
                "output_tokens": last_usage.get("output_tokens", 0),
                "total_tokens": last_usage.get("total_tokens", 0),
            }
            self.mcp_host.integrity.record_model_output(final_output, metadata=output_metadata)
        
        # Finalize and commit (this finalizes the current span and creates session root)
        # NOTE: Do NOT create an empty agent_finalize span - only commit non-empty spans
        session_root, commitments, canonical_log_bytes = self.mcp_host.integrity.finalize()

        # Persist canonical log for future audit/verification.
        # The canonical_log_bytes are the raw bytes whose SHA-256 == canonical_log_hash.
        # Without persisting these, the hash in the response is unverifiable after session ends.
        if canonical_log_bytes:
            logger.info("canonical_log_generated",
                       size_bytes=len(canonical_log_bytes),
                       hash=commitments.canonical_log_hash)
        # TODO: Store canonical_log_bytes in a verifiable storage layer (e.g., IPFS, S3)
        #       and include reference in response for third-party verification.
        
        integrity_metadata = IntegrityMetadata(
            session_id=self.mcp_host.integrity.session_id,
            session_root=session_root,
            event_accumulator_root=commitments.event_accumulator_root,
            span_roots=commitments.span_roots,
            canonical_log_hash=commitments.canonical_log_hash,
            event_count=commitments.event_count,
            timestamp=commitments.timestamp
        )
        
        response = AgentResponse(
            output=final_output,
            integrity=integrity_metadata,
            turns=turn_count
        )
        
        logger.info("agent_run_completed", session_root=session_root, event_count=commitments.event_count)
        return response.model_dump()

    # ==================================================================================
    # Public entry points
    # ==================================================================================

    def run(self, prompt: str, max_turns: int = 10) -> dict[str, Any]:
        """
        Execute the agent with the given prompt (synchronous).
        
        Workflow:
        1. Record initial prompt via MCPHost
        2. Call LLM with available tool schemas from MCPHost
        3. Parse tool calls from response
        4. For each tool call:
           - Delegate to MCPHost.invoke_tool() (handles auth, security, record)
        5. Continue until LLM produces final output
        6. Finalize and generate Verkle root
        
        Args:
            prompt: Initial user prompt
            max_turns: Maximum turns to prevent infinite loops
        
        Returns:
            Final output with integrity metadata
        """
        model_name, tool_schemas, conversation_history = self._validate_and_prepare(prompt)
        
        final_output = None
        turn_count = 0
        last_usage: dict = {}
        
        try:
            while turn_count < max_turns:
                turn_count += 1
                logger.info("agent_turn_start", turn=turn_count, session_id=self.mcp_host.integrity.session_id)
                self.mcp_host.integrity.start_span(f"agent_turn_{turn_count}")
                
                try:
                    llm_response, last_usage = self._call_llm_and_record(
                        conversation_history, tool_schemas, model_name, turn_count
                    )
                    
                    if not llm_response.has_tool_calls():
                        final_output = llm_response.text
                        logger.info("agent_final_output", output_len=len(final_output))
                        break
                    
                    # Process each tool call — delegate to MCPHost for auth + execution
                    tool_results_parts = []
                    for tool_call in llm_response.tool_calls:
                        logger.info("tool_call_requested", tool=tool_call.tool_name, args=tool_call.arguments)
                        tool_result = self.mcp_host.invoke_tool(tool_call)
                        tool_results_parts.append(f"Tool '{tool_call.tool_name}' returned: {tool_result}")
                    
                    self._append_tool_results_to_history(
                        conversation_history, llm_response, tool_results_parts
                    )
                
                except Exception as e:
                    logger.exception("turn_error", turn=turn_count, error=str(e))
                    raise
            
            if final_output is None:
                final_output = "Agent reached maximum turns without final output"
                logger.warning("agent_max_turns_reached", max_turns=max_turns)
        
        except Exception as e:
            logger.exception("agent_error", error=str(e))
            final_output = f"Error during agent execution: {str(e)}"
        
        return self._build_response(final_output, model_name, last_usage, turn_count)
    
    async def run_async(self, prompt: str, max_turns: int = 10) -> dict[str, Any]:
        """
        Asynchronously execute the agent with the given prompt.
        
        Identical to run() but delegates async tool invocation to MCPHost.invoke_tool_async.
        
        Cryptographic Integrity Note:
        =============================
        This method produces IDENTICAL cryptographic commitments to run().
        All integrity recording is synchronous (unchanged).
        Only tool invocation is async (via MCPHost.invoke_tool_async).
        
        Args:
            prompt: Initial user prompt
            max_turns: Maximum turns to prevent infinite loops
        
        Returns:
            Final output with integrity metadata (same as run())
        """
        model_name, tool_schemas, conversation_history = self._validate_and_prepare(prompt)
        
        final_output = None
        turn_count = 0
        last_usage: dict = {}
        
        try:
            while turn_count < max_turns:
                turn_count += 1
                logger.info("agent_turn_start", turn=turn_count, session_id=self.mcp_host.integrity.session_id)
                self.mcp_host.integrity.start_span(f"agent_turn_{turn_count}")
                
                try:
                    llm_response, last_usage = self._call_llm_and_record(
                        conversation_history, tool_schemas, model_name, turn_count
                    )
                    
                    if not llm_response.has_tool_calls():
                        final_output = llm_response.text
                        logger.info("agent_final_output", output_len=len(final_output))
                        break
                    
                    # Process each tool call (async path) — delegate to MCPHost
                    tool_results_parts = []
                    for tool_call in llm_response.tool_calls:
                        logger.info("tool_call_requested", tool=tool_call.tool_name, args=tool_call.arguments)
                        tool_result = await self.mcp_host.invoke_tool_async(tool_call)
                        tool_results_parts.append(f"Tool '{tool_call.tool_name}' returned: {tool_result}")
                    
                    self._append_tool_results_to_history(
                        conversation_history, llm_response, tool_results_parts
                    )
                
                except Exception as e:
                    logger.exception("turn_error", turn=turn_count, error=str(e))
                    raise
            
            if final_output is None:
                final_output = "Agent reached maximum turns without final output"
                logger.warning("agent_max_turns_reached", max_turns=max_turns)
        
        except Exception as e:
            logger.exception("agent_error", error=str(e))
            final_output = f"Error during agent execution: {str(e)}"
        
        return self._build_response(final_output, model_name, last_usage, turn_count)
    

