"""
JSON-RPC 2.0 Error Response Handler

Implements standard JSON-RPC 2.0 error format with proper error codes per spec:
https://www.jsonrpc.org/specification#error_objects

Standard Error Codes:
  - -32700: Parse error
  - -32600: Invalid Request
  - -32601: Method not found
  - -32602: Invalid params
  - -32603: Internal error
  - -32000 to -32099: Server error (reserved for implementation-defined)
"""

from typing import Optional, Any, Dict


class JSONRPCError:
    """JSON-RPC 2.0 error response builder."""

    # Standard error codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # Custom server error codes (in -32000 to -32099 range)
    CONVERSATION_NOT_FOUND = -32001
    INVALID_CONVERSATION_ID = -32002
    CONVERSATION_FINALIZED = -32003
    ACCESS_DENIED = -32004
    INVALID_SESSION = -32005
    PROMPT_TOO_LONG = -32006
    AGENT_ERROR = -32007
    TOKEN_RATE_LIMIT_EXCEEDED = -32008
    VERIFICATION_FAILED = -32009
    INVALID_STATE = -32010
    DATABASE_ERROR = -32011

    # Error messages
    ERROR_MESSAGES = {
        PARSE_ERROR: "Parse error",
        INVALID_REQUEST: "Invalid Request",
        METHOD_NOT_FOUND: "Method not found",
        INVALID_PARAMS: "Invalid params",
        INTERNAL_ERROR: "Internal error",
        CONVERSATION_NOT_FOUND: "Conversation not found",
        INVALID_CONVERSATION_ID: "Invalid conversation ID format",
        CONVERSATION_FINALIZED: "Conversation is finalized (read-only)",
        ACCESS_DENIED: "Access denied",
        INVALID_SESSION: "Invalid or expired session",
        PROMPT_TOO_LONG: "Prompt exceeds maximum length",
        AGENT_ERROR: "Agent execution error",
        TOKEN_RATE_LIMIT_EXCEEDED: "LLM token budget exceeded",
        VERIFICATION_FAILED: "Verification failed",
        INVALID_STATE: "Invalid state",
        DATABASE_ERROR: "Database error",
    }

    @staticmethod
    def error_response(
        code: int,
        message: Optional[str] = None,
        data: Optional[Any] = None,
        request_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a JSON-RPC 2.0 error response.

        Args:
            code: Error code (from standard or custom codes)
            message: Error message (defaults to standard message for code)
            data: Additional error data (optional)
            request_id: Request ID from the request (if available)

        Returns:
            dict in JSON-RPC 2.0 error format: {"jsonrpc": "2.0", "error": {...}, "id": ...}
        """
        if message is None:
            message = JSONRPCError.ERROR_MESSAGES.get(
                code, "Unknown error"
            )

        error_obj = {
            "code": code,
            "message": message,
        }

        if data is not None:
            error_obj["data"] = data

        response = {
            "jsonrpc": "2.0",
            "error": error_obj,
        }

        if request_id is not None:
            response["id"] = request_id

        return response

    @staticmethod
    def parse_error(data: Optional[str] = None) -> Dict[str, Any]:
        """Parse error response."""
        return JSONRPCError.error_response(
            JSONRPCError.PARSE_ERROR, data=data
        )

    @staticmethod
    def invalid_request(data: Optional[str] = None) -> Dict[str, Any]:
        """Invalid Request response."""
        return JSONRPCError.error_response(
            JSONRPCError.INVALID_REQUEST, data=data
        )

    @staticmethod
    def method_not_found(data: Optional[str] = None) -> Dict[str, Any]:
        """Method not found response."""
        return JSONRPCError.error_response(
            JSONRPCError.METHOD_NOT_FOUND, data=data
        )

    @staticmethod
    def invalid_params(
        details: Optional[str] = None, data: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Invalid params response."""
        message = "Invalid params"
        if details:
            message = f"{message}: {details}"
        return JSONRPCError.error_response(
            JSONRPCError.INVALID_PARAMS, message=message, data=data
        )

    @staticmethod
    def internal_error(details: Optional[str] = None) -> Dict[str, Any]:
        """Internal error response."""
        message = "Internal error"
        if details:
            message = f"{message}: {details}"
        return JSONRPCError.error_response(
            JSONRPCError.INTERNAL_ERROR, message=message
        )

    @staticmethod
    def conversation_not_found(
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Conversation not found response."""
        return JSONRPCError.error_response(
            JSONRPCError.CONVERSATION_NOT_FOUND,
            message=f"Conversation '{conversation_id}' not found",
            data={"conversation_id": conversation_id},
        )

    @staticmethod
    def invalid_conversation_id(
        conversation_id: str, reason: str
    ) -> Dict[str, Any]:
        """Invalid conversation ID response."""
        return JSONRPCError.error_response(
            JSONRPCError.INVALID_CONVERSATION_ID,
            message=f"Invalid conversation ID: {reason}",
            data={"conversation_id": conversation_id, "reason": reason},
        )

    @staticmethod
    def conversation_finalized(
        conversation_id: str,
    ) -> Dict[str, Any]:
        """Conversation is finalized response."""
        return JSONRPCError.error_response(
            JSONRPCError.CONVERSATION_FINALIZED,
            message=f"Conversation '{conversation_id}' is finalized (read-only)",
            data={"conversation_id": conversation_id},
        )

    @staticmethod
    def access_denied(reason: Optional[str] = None) -> Dict[str, Any]:
        """Access denied response."""
        message = "Access denied"
        if reason:
            message = f"{message}: {reason}"
        return JSONRPCError.error_response(
            JSONRPCError.ACCESS_DENIED, message=message
        )

    @staticmethod
    def invalid_session(reason: Optional[str] = None) -> Dict[str, Any]:
        """Invalid or expired session response."""
        message = "Invalid or expired session"
        if reason:
            message = f"{message}: {reason}"
        return JSONRPCError.error_response(
            JSONRPCError.INVALID_SESSION, message=message
        )

    @staticmethod
    def prompt_too_long(
        max_length: int, current_length: int
    ) -> Dict[str, Any]:
        """Prompt exceeds maximum length response."""
        return JSONRPCError.error_response(
            JSONRPCError.PROMPT_TOO_LONG,
            message=f"Prompt exceeds maximum length of {max_length} characters (current: {current_length})",
            data={"max_length": max_length, "current_length": current_length},
        )

    @staticmethod
    def prompt_too_large_bytes(
        max_bytes: int, current_bytes: int
    ) -> Dict[str, Any]:
        """Prompt exceeds maximum UTF-8 byte-size response."""
        return JSONRPCError.error_response(
            JSONRPCError.PROMPT_TOO_LONG,
            message=f"Prompt exceeds maximum size of {max_bytes} bytes (current: {current_bytes})",
            data={"max_bytes": max_bytes, "current_bytes": current_bytes},
        )

    @staticmethod
    def token_rate_limit_exceeded(
        details: str, limit: int, window_sec: int
    ) -> Dict[str, Any]:
        """LLM token rate limit exceeded response."""
        return JSONRPCError.error_response(
            JSONRPCError.TOKEN_RATE_LIMIT_EXCEEDED,
            message="LLM token budget exceeded for this time window",
            data={
                "details": details,
                "limit": limit,
                "window_sec": window_sec,
            },
        )

    @staticmethod
    def agent_error(details: str) -> Dict[str, Any]:
        """Agent execution error response."""
        return JSONRPCError.error_response(
            JSONRPCError.AGENT_ERROR,
            message=f"Agent execution error: {details}",
            data={"details": details},
        )

    @staticmethod
    def database_error(details: str) -> Dict[str, Any]:
        """Database error response."""
        return JSONRPCError.error_response(
            JSONRPCError.DATABASE_ERROR,
            message=f"Database error: {details}",
            data={"details": details},
        )

    @staticmethod
    def verification_failed(reason: str) -> Dict[str, Any]:
        """Verification failed response."""
        return JSONRPCError.error_response(
            JSONRPCError.VERIFICATION_FAILED,
            message=f"Verification failed: {reason}",
            data={"reason": reason},
        )

    @staticmethod
    def invalid_state(reason: str) -> Dict[str, Any]:
        """Invalid state response."""
        return JSONRPCError.error_response(
            JSONRPCError.INVALID_STATE,
            message=f"Invalid state: {reason}",
            data={"reason": reason},
        )
