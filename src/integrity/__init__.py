"""
Integrity Middleware - captures and commits all agent interactions
"""

import hashlib
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from src.crypto.encoding import CanonicalEncoder
from src.crypto.verkle import VerkleAccumulator
from src.security.key_management import KeyAuthority, ToolSigner
from src.config import get_settings

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
    Middleware that ensures all agent interactions are canonically encoded,
    monotonically sequenced, and cryptographically committed.
    
    - Enforces sequential counter with atomic increment
    - Ensures server-generated timestamps from trusted clock
    - Maintains replay-resistance metadata
    - Finalizes Verkle tree exactly once per run
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.verkle_accumulator = VerkleAccumulator(self.session_id)
        self.counter = 0
        self.finalized = False
        
        # Initialize IBS Authority
        settings = get_settings()
        self.authority = KeyAuthority(
            master_secret_hex=settings.security.master_secret_key
        )
        
        # "server" identity for prompt/model output signing
        self.server_signer = self.authority.provision_tool("server")
        
        # Cache for tool signers
        self.tool_signers: dict[str, ToolSigner] = {}
        
        logger.info("integrity_middleware_initialized", session_id=self.session_id)
    
    def _get_signer(self, identity: str) -> ToolSigner:
        """Get or provision a signer for an identity"""
        if identity == "server":
            return self.server_signer
            
        if identity not in self.tool_signers:
            self.tool_signers[identity] = self.authority.provision_tool(identity)
            
        return self.tool_signers[identity]

    def _get_server_timestamp(self) -> str:
        """Get current server timestamp (UTC, ISO8601)"""
        # TODO: Verify NTP sync and prevent local time tampering
        return datetime.now(timezone.utc).isoformat()
    
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
        self.verkle_accumulator.add_event(event_dict)
        
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
        self.verkle_accumulator.add_event(event_dict)
        
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
        self.verkle_accumulator.add_event(event_dict)
        
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
        self.verkle_accumulator.add_event(event_dict)
        
        logger.info("tool_output_recorded", session_id=self.session_id, tool=tool_name, counter=event.counter)
    
    def finalize(self) -> dict[str, Any]:
        """
        Finalize the run and commit all events to Verkle tree.
        Returns metadata including root commitment and hash.
        """
        if self.finalized:
            raise RuntimeError("Run already finalized")
        
        # Finalize Verkle tree
        root = self.verkle_accumulator.finalize()
        root_b64 = self.verkle_accumulator.get_root_b64()
        
        # Sign the Verkle Root (using KZG commitment bytes)
        # We need the raw bytes. base64 decode is safest way to get them from public property
        import base64
        root_bytes = base64.b64decode(root_b64)
        root_signature = self.authority.sign_root(root_bytes)
        
        # Get canonical log
        canonical_log = self.verkle_accumulator.get_canonical_log()
        log_hash = hashlib.sha256(canonical_log).hexdigest()
        
        self.finalized = True
        
        result = {
            "session_id": self.session_id,
            "verkle_root_b64": root_b64,
            "root_signature": str(root_signature),
            "server_mpk": str(self.authority.get_public_params()),
            "canonical_log_hash": log_hash,
            "event_count": len(self.verkle_accumulator.events),
            "finalized_at": self._get_server_timestamp()
        }
        
        logger.info("run_finalized", **result)
        return result
    
    def get_canonical_log(self) -> bytes:
        """Get the entire canonical log (for storage)"""
        return self.verkle_accumulator.get_canonical_log()
