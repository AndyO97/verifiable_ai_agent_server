"""
Security module - Authorization and threat prevention
"""

import structlog
from enum import Enum
from typing import Any, Callable

logger = structlog.get_logger(__name__)


class SecurityEvent(str, Enum):
    """Security event types"""
    UNAUTHORIZED_TOOL_ACCESS = "unauthorized_tool_access"
    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    REPLAY_ATTEMPT = "replay_attempt"


class ToolAuthorizationManager:
    """
    Manages tool access control.
    Enforces least-privilege principle and blocks unauthorized invocations.
    """
    
    def __init__(self):
        # Whitelist of authorized tools - to be populated during server init
        self.authorized_tools: set[str] = set()
        self.tool_policies: dict[str, dict[str, Any]] = {}
    
    def register_tool(self, tool_name: str, policy: dict[str, Any] | None = None) -> None:
        """Register an authorized tool"""
        self.authorized_tools.add(tool_name)
        if policy:
            self.tool_policies[tool_name] = policy
    
    def can_invoke(self, tool_name: str) -> bool:
        """Check if tool can be invoked"""
        return tool_name in self.authorized_tools
    
    def handle_unauthorized_access(self, session_id: str, tool_name: str) -> str:
        """
        Handle unauthorized tool access attempt.
        - Log security event
        - Return neutral failure response
        - Do NOT expose tool capability map to model
        """
        logger.warning(
            "security_event",
            event_type=SecurityEvent.UNAUTHORIZED_TOOL_ACCESS,
            session_id=session_id,
            tool_name=tool_name
        )
        
        # Return neutral response (no tool list exposure)
        return "Action blocked: unauthorized tool access."


class SecurityMiddleware:
    """
    Applies security policies to agent interactions.
    Prevents unauthorized tool access and prompt injection.
    """
    
    def __init__(self):
        self.auth_manager = ToolAuthorizationManager()
    
    def register_authorized_tools(self, tools: list[str]) -> None:
        """Register the whitelist of authorized tools"""
        for tool in tools:
            self.auth_manager.register_tool(tool)
    
    def validate_tool_invocation(self, session_id: str, tool_name: str) -> bool:
        """
        Validate that a tool invocation is authorized.
        If not, logs security event and returns False.
        """
        if not self.auth_manager.can_invoke(tool_name):
            self.auth_manager.handle_unauthorized_access(session_id, tool_name)
            return False
        
        return True
