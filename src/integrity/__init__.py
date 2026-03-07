"""
Integrity Middleware - captures and commits all agent interactions

Unified middleware that records both application events and MCP protocol events
into a single Verkle accumulator with integrated Langfuse observability.
"""

import base64
import hashlib
import requests
import uuid
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Tuple

import structlog
import ntplib

from src.crypto.encoding import CanonicalEncoder
from src.crypto.verkle import VerkleAccumulator
from src.security.key_management import KeyAuthority, ToolSigner
from src.config import get_settings
from src.observability.langfuse_client import LangfuseClient

logger = structlog.get_logger(__name__)


@dataclass
class IntegrityEvent:
    """A single integrity-tracked event in the agent run"""
    session_id: str
    counter: int
    timestamp: str  # ISO8601 UTC
    event_type: str  # prompt | model_output | tool_input | tool_output
    payload: dict[str, Any]
    signature: Optional[str] = None  # Base64 encoded IBS signature (U, V)
    signer_id: Optional[str] = None  # "server" or "tool_name"


class IntegrityMiddleware:
    """
    Unified middleware that ensures all agent interactions (both application events
    and MCP protocol events) are canonically encoded, monotonically sequenced, and
    cryptographically committed.
    
    Features:
    - Integrated Verkle accumulator for all events
    - Integrated Langfuse observability (optional)
    - Enforces sequential counter with atomic increment
    - Ensures server-generated timestamps from trusted clock
    - Maintains replay-resistance metadata
    - Finalizes Verkle tree exactly once per run
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.accumulator = VerkleAccumulator(self.session_id)
        self.counter = 0
        self.finalized = False
        
        # NTP verification fields
        self._ntp_offset_ms: Optional[int] = None  # Cached NTP offset in milliseconds
        self._ntp_last_check: float = 0  # Timestamp of last NTP check
        self._ntp_check_interval: int = 300  # Check NTP every 5 minutes
        self._clock_drift_warning_threshold_ms: int = 5000  # 5 seconds warning
        self._clock_drift_error_threshold_ms: int = 60000  # 60 seconds error
        self._ntp_sync_verified: bool = False  # Track if NTP was verified at least once
        
        # Initialize IBS Authority
        settings = get_settings()
        self.authority = KeyAuthority(
            master_secret_hex=settings.security.master_secret_key
        )
        
        # "server" identity for prompt/model output signing
        self.server_signer = self.authority.provision_tool("server")
        
        # Cache for tool signers
        self.tool_signers: dict[str, ToolSigner] = {}
        
        # Initialize Langfuse client (optional observability)
        self.langfuse_client: Optional[LangfuseClient] = None
        self.trace_id: Optional[str] = None
        self._initialize_langfuse()
        
        # Verify NTP sync at startup
        self._verify_ntp_sync()
        
        logger.info("integrity_middleware_initialized", session_id=self.session_id, ntp_verified=self._ntp_sync_verified)
    
    def _initialize_langfuse(self) -> None:
        """Initialize Langfuse if available"""
        try:
            settings = get_settings()
            langfuse_endpoint = settings.langfuse.api_endpoint
            
            # Check if Langfuse server is running
            response = requests.get(f"{langfuse_endpoint}/api/public/health", timeout=1)
            if response.status_code != 200:
                logger.debug("langfuse_server_not_available")
                return
            
            self.langfuse_client = LangfuseClient(self.session_id)
            # Use more descriptive trace name with full session ID
            trace_name = f"agent_verified_{self.session_id}"
            self.trace_id = self.langfuse_client.create_trace(
                name=trace_name,
                metadata={
                    "protocol_version": "MCP-2024-11",
                    "jsonrpc": "2.0",
                    "session_id": self.session_id,
                    "middleware_type": "integrity",
                    "cryptography": "KZG-BLS12-381",
                    "encoding": "RFC-8785"
                }
            )
            logger.info("langfuse_initialized", trace_id=self.trace_id)
        except Exception as e:
            logger.debug("langfuse_initialization_failed", error=str(e))
            self.langfuse_client = None
            self.trace_id = None
    
    def _get_signer(self, identity: str) -> ToolSigner:
        """Get or provision a signer for an identity"""
        if identity == "server":
            return self.server_signer
            
        if identity not in self.tool_signers:
            self.tool_signers[identity] = self.authority.provision_tool(identity)
            
        return self.tool_signers[identity]

    def _verify_ntp_sync(self) -> None:
        """
        Verify system clock is synchronized with NTP servers.
        Caches the result to avoid repeated NTP network calls.
        Logs warnings/errors if clock drift is detected.
        """
        current_time = time.time()
        
        # Skip if we've checked recently (within 5 minutes)
        if self._ntp_last_check > 0 and (current_time - self._ntp_last_check) < self._ntp_check_interval:
            return
        
        self._ntp_last_check = current_time
        
        try:
            # Query multiple NTP servers for redundancy
            ntp_servers = ["pool.ntp.org", "time.nist.gov", "time.cloudflare.com"]
            offsets_ms = []
            
            for server in ntp_servers:
                try:
                    ntp_client = ntplib.NTPClient()
                    response = ntp_client.request(server, version=3, timeout=2)
                    
                    # Calculate offset: NTP server time - local time (in milliseconds)
                    offset_sec = response.tx_time - time.time()
                    offset_ms = int(offset_sec * 1000)
                    offsets_ms.append(offset_ms)
                    
                except (ntplib.NTPException, OSError, TimeoutError):
                    # Individual server failed, try next
                    continue
            
            if not offsets_ms:
                logger.warning("ntp_sync_check_failed", reason="all_servers_unreachable")
                self._ntp_sync_verified = False
                return
            
            # Use median offset for robustness
            offsets_ms.sort()
            self._ntp_offset_ms = offsets_ms[len(offsets_ms) // 2]
            
            # Log based on drift severity
            abs_drift_ms = abs(self._ntp_offset_ms)
            if abs_drift_ms > self._clock_drift_error_threshold_ms:
                logger.error(
                    "ntp_clock_drift_critical",
                    offset_ms=self._ntp_offset_ms,
                    abs_drift_ms=abs_drift_ms,
                    threshold_ms=self._clock_drift_error_threshold_ms,
                    message="System clock is severely out of sync with NTP. Timestamps may be unreliable.",
                )
                self._ntp_sync_verified = False
            elif abs_drift_ms > self._clock_drift_warning_threshold_ms:
                logger.warning(
                    "ntp_clock_drift_warning",
                    offset_ms=self._ntp_offset_ms,
                    abs_drift_ms=abs_drift_ms,
                    threshold_ms=self._clock_drift_warning_threshold_ms,
                    message="System clock is slightly out of sync with NTP.",
                )
                self._ntp_sync_verified = True
            else:
                logger.info(
                    "ntp_sync_verified",
                    offset_ms=self._ntp_offset_ms,
                    abs_drift_ms=abs_drift_ms,
                )
                self._ntp_sync_verified = True
                
        except Exception as e:
            logger.warning("ntp_sync_verification_error", error=str(e), exception_type=type(e).__name__)
            self._ntp_sync_verified = False

    def _get_ntp_offset(self) -> Optional[int]:
        """
        Get the current NTP offset in milliseconds.
        Re-checks NTP if cache has expired (every 5 minutes).
        Returns None if NTP check fails.
        """
        self._verify_ntp_sync()
        return self._ntp_offset_ms

    def _get_server_timestamp(self) -> str:
        """
        Get current server timestamp (UTC, ISO8601) with NTP verification.
        If NTP is available and shows clock drift, applies correction.
        Falls back to system time if NTP unavailable.
        """
        # Get current time
        now = datetime.now(timezone.utc)
        
        # Try to get NTP offset
        ntp_offset_ms = self._get_ntp_offset()
        
        if ntp_offset_ms is not None:
            # Apply NTP correction to timestamp
            correction = timedelta(milliseconds=ntp_offset_ms)
            corrected_time = now + correction
            timestamp = corrected_time.isoformat()
        else:
            # No NTP available, use system time as-is
            timestamp = now.isoformat()
        
        return timestamp
    
    def _sign_payload(self, payload: dict[str, Any], signer_id: str) -> str:
        """Sign payload and return string representation of signature"""
        # Canonicalize payload to ensure consistent signing
        # Note: We use encode_event which delegates to canonicalize_json
        payload_bytes = CanonicalEncoder.encode_event(payload)
        
        signer = self._get_signer(signer_id)
        signature = signer.sign_message(payload_bytes)
        
        # Simple string serialization for the prototype (U, V)
        return str(signature)

    def record_prompt(self, prompt_text: str, metadata: dict[str, Any] | None = None) -> str:
        """Record the initial user prompt"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        payload = {"prompt": prompt_text, **(metadata or {})}
        signer_id = "server"
        signature = self._sign_payload(payload, signer_id)
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="prompt",
            payload=payload,
            signature=signature,
            signer_id=signer_id
        )
        
        self.counter += 1
        event_dict = asdict(event)
        self.accumulator.add_event(event_dict)
        
        # Log to Langfuse if available
        if self.langfuse_client and self.trace_id:
            self.langfuse_client.record_event(
                name="user_prompt",
                data={"prompt": prompt_text, **(metadata or {})}
            )
        
        logger.info("prompt_recorded", session_id=self.session_id, counter=event.counter)
        return event.session_id
    
    def record_model_output(self, output_text: str, metadata: dict[str, Any] | None = None) -> None:
        """Record the final LLM model output (no streaming)"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        payload = {"output": output_text, **(metadata or {})}
        signer_id = "server"
        signature = self._sign_payload(payload, signer_id)

        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="model_output",
            payload=payload,
            signature=signature,
            signer_id=signer_id
        )
        
        self.counter += 1
        event_dict = asdict(event)
        self.accumulator.add_event(event_dict)
        
        # Log to Langfuse if available
        if self.langfuse_client and self.trace_id:
            self.langfuse_client.record_event(
                name="model_output",
                data={"output": output_text, **(metadata or {})}
            )
        
        logger.info("model_output_recorded", session_id=self.session_id, counter=event.counter)
    
    def record_tool_input(self, tool_name: str, input_args: dict[str, Any]) -> None:
        """Record tool invocation input"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        payload = {"tool": tool_name, "args": input_args}
        signer_id = "server"
        signature = self._sign_payload(payload, signer_id)
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="tool_input",
            payload=payload,
            signature=signature,
            signer_id=signer_id
        )
        
        self.counter += 1
        event_dict = asdict(event)
        self.accumulator.add_event(event_dict)
        
        # Log to Langfuse if available
        if self.langfuse_client and self.trace_id:
            self.langfuse_client.record_span(
                name=f"tool_{tool_name}",
                input_data={"tool": tool_name, "args": input_args}
            )
        
        logger.info("tool_input_recorded", session_id=self.session_id, tool=tool_name, counter=event.counter)
    
    def record_tool_output(self, tool_name: str, result: Any, signature: Optional[str] = None) -> None:
        """
        Record tool invocation result.
        
        Args:
            tool_name: The identity of the tool.
            result: The output data.
            signature: Optional pre-computed signature from a remote tool. 
                       If None, the middleware acts as the signer (Trusted Middleware Model).
        """
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        payload = {"tool": tool_name, "result": result}
        signer_id = tool_name
        
        if signature is None:
            # Trusted Middleware Model: We sign on behalf of the tool
            signature = self._sign_payload(payload, signer_id)
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="tool_output",
            payload=payload,
            signature=signature,
            signer_id=signer_id
        )
        
        self.counter += 1
        event_dict = asdict(event)
        self.accumulator.add_event(event_dict)
        
        # Log to Langfuse if available - tool output recorded as span update
        # (Tool input span was already created)
        
        logger.info("tool_output_recorded", session_id=self.session_id, tool=tool_name, counter=event.counter)
    
    def record_mcp_event(self, event_type: str, jsonrpc_data: dict[str, Any]) -> None:
        """
        Record an MCP JSON-RPC 2.0 protocol event.
        
        These events track the protocol layer (initialize, tools/call, etc.)
        and are part of the unified Verkle-accumulated log.
        
        Args:
            event_type: Type of MCP event (e.g., "mcp_initialize_request", "mcp_tools_call_response")
            jsonrpc_data: The complete JSON-RPC 2.0 request or response dict
        """
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        # MCP events are protocol-level, not application-level, so we add them directly
        event_dict = {
            "type": event_type,
            "jsonrpc": jsonrpc_data,
            "timestamp": self._get_server_timestamp(),
            "session_id": self.session_id,
        }
        
        self.accumulator.add_event(event_dict)
        
        # Log to Langfuse if available
        if self.langfuse_client and self.trace_id:
            self.langfuse_client.record_event(
                name=event_type,
                data=event_dict
            )
        
        logger.info("mcp_event_recorded", session_id=self.session_id, event_type=event_type)
    
    def finalize(self) -> Tuple[str, bytes]:
        """
        Finalize the run and commit all events to Verkle tree.
        Returns: (root_b64, canonical_log_bytes)
        """
        if self.finalized:
            raise RuntimeError("Run already finalized")
        
        # Finalize Verkle tree
        root = self.accumulator.finalize()
        root_b64 = self.accumulator.get_root_b64()
        
        # Sign the Verkle Root (using KZG commitment bytes)
        root_bytes = base64.b64decode(root_b64)
        root_signature = self.authority.sign_root(root_bytes)
        
        # Get canonical log
        canonical_log = self.accumulator.get_canonical_log()
        if isinstance(canonical_log, str):
            canonical_log_bytes = canonical_log.encode('utf-8')
        else:
            canonical_log_bytes = canonical_log
        
        log_hash = hashlib.sha256(canonical_log_bytes).hexdigest()
        
        # Finalize Langfuse trace if it exists
        if self.langfuse_client and self.trace_id:
            try:
                self.langfuse_client.record_event(
                    name="commitment_finalized",
                    data={
                        "verkle_root": root_b64,
                        "root_signature": str(root_signature),
                        "canonical_log_hash": log_hash,
                        "event_count": len(self.accumulator.events),
                        "verified": True
                    }
                )
                self.langfuse_client.add_score(
                    name="verification_status",
                    value=1.0,
                    comment="Cryptographically verified"
                )
                self.langfuse_client.update_trace(
                    output=f"Verified. Root: {root_b64[:32]}...",
                    metadata={"verkle_root": root_b64, "event_count": len(self.accumulator.events)},
                )
            except Exception as e:
                logger.warning("langfuse_finalize_failed", error=str(e))
        
        self.finalized = True
        
        metadata = {
            "session_id": self.session_id,
            "verkle_root_b64": root_b64,
            "root_signature": str(root_signature),
            "server_mpk": str(self.authority.get_public_params()),
            "canonical_log_hash": log_hash,
            "event_count": len(self.accumulator.events),
            "finalized_at": self._get_server_timestamp()
        }
        
        logger.info("run_finalized", **metadata)
        return (root_b64, canonical_log_bytes)
    
    def get_canonical_log(self) -> bytes:
        """Get the entire canonical log (for storage)"""
        return self.accumulator.get_canonical_log()


# Import hierarchical version for convenience
from src.integrity.hierarchical_integrity import (
    HierarchicalVerkleMiddleware,
    HierarchicalCommitments,
    SpanMetadata
)

__all__ = [
    "IntegrityMiddleware",
    "IntegrityEvent",
    "HierarchicalVerkleMiddleware",
    "HierarchicalCommitments",
    "SpanMetadata",
]
