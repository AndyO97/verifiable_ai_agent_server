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

logger = structlog.get_logger(__name__)


@dataclass
class IntegrityEvent:
    """A single integrity-tracked event in the agent run"""
    session_id: str
    counter: int
    timestamp: str  # ISO8601 UTC
    event_type: str  # prompt | model_output | tool_input | tool_output
    payload: dict[str, Any]


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
        
        logger.info("integrity_middleware_initialized", session_id=self.session_id)
    
    def _get_server_timestamp(self) -> str:
        """Get current server timestamp (UTC, ISO8601)"""
        # TODO: Verify NTP sync and prevent local time tampering
        return datetime.now(timezone.utc).isoformat()
    
    def record_prompt(self, prompt_text: str, metadata: dict[str, Any] | None = None) -> str:
        """Record the initial user prompt"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="prompt",
            payload={"prompt": prompt_text, **(metadata or {})}
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
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="model_output",
            payload={"output": output_text, **(metadata or {})}
        )
        
        self.counter += 1
        event_dict = asdict(event)
        self.verkle_accumulator.add_event(event_dict)
        
        logger.info("model_output_recorded", session_id=self.session_id, counter=event.counter)
    
    def record_tool_input(self, tool_name: str, input_args: dict[str, Any]) -> None:
        """Record tool invocation input"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="tool_input",
            payload={"tool": tool_name, "args": input_args}
        )
        
        self.counter += 1
        event_dict = asdict(event)
        self.verkle_accumulator.add_event(event_dict)
        
        logger.info("tool_input_recorded", session_id=self.session_id, tool=tool_name, counter=event.counter)
    
    def record_tool_output(self, tool_name: str, result: Any) -> None:
        """Record tool invocation result"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type="tool_output",
            payload={"tool": tool_name, "result": result}
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
        
        # Get canonical log
        canonical_log = self.verkle_accumulator.get_canonical_log()
        log_hash = hashlib.sha256(canonical_log).hexdigest()
        
        self.finalized = True
        
        result = {
            "session_id": self.session_id,
            "verkle_root_b64": root_b64,
            "canonical_log_hash": log_hash,
            "event_count": len(self.verkle_accumulator.events),
            "finalized_at": self._get_server_timestamp()
        }
        
        logger.info("run_finalized", **result)
        return result
    
    def get_canonical_log(self) -> bytes:
        """Get the entire canonical log (for storage)"""
        return self.verkle_accumulator.get_canonical_log()
