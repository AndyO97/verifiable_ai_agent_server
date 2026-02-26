"""
Hierarchical Verkle Integrity Middleware with Langfuse Observability

Extends IntegrityMiddleware to support:
- Span-based event organization
- Per-span Verkle roots
- Session-level Verkle root (combining span roots)
- Integrated Langfuse observability (traces, generations, spans)
- Dual storage (local canonical log + Langfuse observability)
- Multi-level verification strategy

Langfuse Hierarchy (handled internally):
- Session: The overall workflow session (groups traces)
- Trace: A single user request/interaction
- Generation: An LLM API call (prompt -> response)
- Span: A tool call or other operation
"""

import hashlib
import json
import requests
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple, Dict

import structlog

from src.config import get_settings
from src.integrity import IntegrityMiddleware, IntegrityEvent
from src.crypto.verkle import VerkleAccumulator
from src.observability.langfuse_client import LangfuseClient

logger = structlog.get_logger(__name__)


@dataclass
class SpanMetadata:
    """Metadata for a span (corresponds to OpenTelemetry span)"""
    span_id: str
    name: str  # e.g., "mcp_initialize", "user_interaction", "tool_execution"
    start_time: str  # ISO8601 UTC
    end_time: Optional[str] = None
    start_index: int = 0  # Index of first event in this span
    end_index: int = 0    # Index of last event in this span
    event_count: int = 0
    verkle_root: Optional[str] = None  # Per-span Verkle root (base64)
    duration_ms: int = 0


@dataclass
class HierarchicalCommitments:
    """Complete commitment structure for verification"""
    session_root: str  # Verkle root of all span roots
    event_accumulator_root: str  # Verkle root of all raw events (flat structure)
    span_roots: Dict[str, str]  # span_id -> root (string)
    canonical_log_hash: str  # SHA-256 of canonical log
    event_count: int
    timestamp: str  # When finalized
    otel_compliant: bool = True


class HierarchicalVerkleMiddleware(IntegrityMiddleware):
    """
    Extended middleware with hierarchical Verkle support and Langfuse observability.
    
    Architecture:
    - Each span gets its own Verkle accumulator and root
    - Session root is Verkle of all span roots
    - Events are associated with their span
    - Verification possible at span level or session level
    
    Langfuse Integration (handled internally):
    - Creates traces for user interactions automatically
    - Records generations for LLM calls
    - Records spans for tool calls
    - Callers don't need to interact with Langfuse directly
    """
    
    def __init__(self, session_id: Optional[str] = None):
        """Initialize hierarchical middleware with Langfuse observability"""
        super().__init__(session_id)
        
        # Span management
        self.spans: Dict[str, SpanMetadata] = {}
        self.current_span_id: Optional[str] = None
        self.current_span_accumulator: Optional[VerkleAccumulator] = None
        self.current_span_counter: int = 0  # Per-span counter (resets per span)
        self.span_counter: int = 0  # Global counter for deterministic span IDs
        self.span_roots: Dict[str, str] = {}
        
        # Session-level accumulator (accumulates span roots)
        self.session_accumulator = VerkleAccumulator(f"{self.session_id}_session")
        self.session_accumulator_counter = 0  # Separate counter for session events
        
        # Track events by span
        self.events_by_span: Dict[str, list] = {}
        
        # Canonical events list (for JSONL export with full event data + span commitments)
        # Each event includes: timestamp, span_id, attributes (for OTel compliance)
        self.canonical_events: list[dict[str, Any]] = []
        
        # Track current LLM context for generation recording
        self._current_prompt: Optional[str] = None
        self._current_model: Optional[str] = None
        
        # Initialize Langfuse client (handles session -> trace -> generation hierarchy)
        self._initialize_langfuse_client()
        
        logger.info(
            "hierarchical_verkle_middleware_initialized",
            session_id=self.session_id,
            langfuse_enabled=self.langfuse_client is not None
        )
    
    def _initialize_langfuse(self) -> None:
        """Override parent's Langfuse init - we handle it ourselves in _initialize_langfuse_client"""
        # Skip parent's Langfuse initialization - hierarchical middleware manages its own
        pass
    
    def _initialize_langfuse_client(self) -> None:
        """Initialize Langfuse client for observability"""
        try:
            settings = get_settings()
            langfuse_endpoint = settings.langfuse.api_endpoint
            response = requests.get(f"{langfuse_endpoint}/api/public/health", timeout=1)
            if response.status_code != 200:
                logger.debug("langfuse_server_not_available")
                self.langfuse_client = None
                self.trace_id = None
                return
            
            # Create Langfuse client with session_id (groups all traces together)
            self.langfuse_client = LangfuseClient(self.session_id)
            self.trace_id = None  # Will be created when first interaction starts
            
            logger.info("langfuse_client_initialized", session_id=self.session_id)
        except Exception as e:
            logger.debug("langfuse_initialization_failed", error=str(e))
            self.langfuse_client = None
            self.trace_id = None
    
    def _ensure_trace_exists(self, trace_name: str = "user_interaction", input_data: Optional[str] = None) -> Optional[str]:
        """Ensure a Langfuse trace exists, creating one if needed"""
        if not self.langfuse_client:
            return None
        
        if not self.trace_id:
            self.trace_id = self.langfuse_client.create_trace(
                name=trace_name,
                metadata={
                    "protocol_version": "MCP-2024-11",
                    "session_id": self.session_id,
                    "middleware_type": "hierarchical_verkle",
                    "cryptography": "KZG-BLS12-381",
                },
                input_data=input_data,
            )
        
        return self.trace_id
    
    def _create_canonical_event(
        self,
        event_type: str,
        attributes: dict[str, Any],
        timestamp: str,
        signature: str = "",
        signer_id: str = "server"
    ) -> dict[str, Any]:
        """
        Create an OTel-compliant event for the canonical log.
        
        OTel Structure (OpenTelemetry compliant - RFC 3339 timestamps):
        {
            "counter": global session counter (0, 1, 2, ... for ordering),
            "timestamp": ISO8601 UTC (OTel standard),
            "event_type": type of event,
            "span_id": which span this belongs to,
            "span_name": human-readable span name (OTel attribute),
            "attributes": event-specific data (OTel standard field for event data),
            "signature": cryptographic signature,
            "signer_id": who created this event,
            "session_id": session identifier
        }
        
        NOTE: 
        - Only ONE field for event data: 'attributes' (OTel standard)
        - span_counter is NOT stored (redundant) - computed during verification as position within span
        - Verification reconstruction uses 'attributes' as the payload for Verkle computation
        - timestamp parameter must be passed in (from IntegrityEvent) to ensure consistency
        """
        return {
            "counter": self.counter,
            "timestamp": timestamp,
            "event_type": event_type,
            "span_id": self.current_span_id,
            "span_name": self.spans[self.current_span_id].name if self.current_span_id in self.spans else None,
            "attributes": attributes,  # OTel standard field - single source of truth for event data
            "signature": signature,
            "signer_id": signer_id,
            "session_id": self.session_id,
        }
    
    def start_span(self, span_name: str) -> str:
        """
        Start a new span.
        
        Args:
            span_name: Name of the span (e.g., "mcp_initialize", "user_interaction")
            
        Returns:
            span_id: Unique identifier for this span (deterministic and globally unique)
        """
        # Finalize current span if any
        if self.current_span_id:
            self._finalize_current_span()
        
        # Create span ID that is:
        # 1. Deterministic within a session (uses counter, not UUID)
        # 2. Globally unique across sessions and server restarts (includes session_id)
        self.current_span_id = f"{self.session_id}_{span_name}_{self.span_counter}"
        self.span_counter += 1
        
        span = SpanMetadata(
            span_id=self.current_span_id,
            name=span_name,
            start_time=self._get_server_timestamp(),
            start_index=self.counter,
        )
        self.spans[self.current_span_id] = span
        self.events_by_span[self.current_span_id] = []
        
        # Create span-level accumulator
        self.current_span_accumulator = VerkleAccumulator(
            f"{self.session_id}_{self.current_span_id}"
        )
        self.current_span_counter = 0  # Reset counter for new span
        
        # Record span in Langfuse (only if trace exists - trace will be created in record_prompt)
        if self.langfuse_client and self.trace_id:
            self.langfuse_client.record_span(
                name=f"span_{span_name}",
                input_data={"span_id": self.current_span_id, "index": self.span_counter - 1}
            )
        
        logger.info("span_started", span_id=self.current_span_id, span_name=span_name)
        return self.current_span_id
    
    def end_span(self, span_id: Optional[str] = None) -> str:
        """
        Finalize the current span (or specified span).
        
        Returns:
            span_root: The Verkle root for the span (base64)
        """
        if span_id is not None and span_id != self.current_span_id:
            logger.warning("end_span_mismatch", expected=self.current_span_id, requested=span_id)
        return self._finalize_current_span()
    
    def record_prompt(self, prompt_text: str, metadata: dict[str, Any] | None = None) -> str:
        """
        Record the initial user prompt.
        
        This stores the prompt for later pairing with the model output to create
        a complete Langfuse generation.
        """
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        # Store prompt for generation recording
        self._current_prompt = prompt_text
        self._current_model = (metadata or {}).get("model", "unknown")
        
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
        
        event_dict = asdict(event)
        
        # Add to flat accumulator (for flat root computation)
        self.accumulator.add_event(event_dict)
        
        # Add to span accumulator if span is active
        if self.current_span_id and self.current_span_accumulator:
            # Only include core event fields (not metadata like signature/signer_id)
            span_event_dict = {
                "session_id": event.session_id,
                "counter": self.current_span_counter,  # Per-span position
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "payload": event.payload,
                "span_id": self.current_span_id,
            }
            self.current_span_accumulator.add_event(span_event_dict)
            self.current_span_counter += 1
            self.events_by_span[self.current_span_id].append(event_dict)
        
        # Add to canonical events (OTel-compliant format for auditing)
        canonical_event = self._create_canonical_event(
            event_type="prompt",
            attributes=payload,
            timestamp=event.timestamp,
            signature=signature,
            signer_id=signer_id
        )
        self.canonical_events.append(canonical_event)
        
        self.counter += 1
        
        # Create or update trace in Langfuse with the prompt as input
        if self.langfuse_client:
            if not self.trace_id:
                # Create trace with clean name and prompt as input
                self._ensure_trace_exists("llm_request", input_data=prompt_text)
            else:
                # Update existing trace with prompt input
                self.langfuse_client.update_trace(input_data=prompt_text)
        
        logger.info("prompt_recorded", session_id=self.session_id, counter=event.counter)
        return event.session_id
    
    # Keys that are for Langfuse only (excluded from integrity payload to preserve commitments)
    _LANGFUSE_ONLY_KEYS = {"input_tokens", "output_tokens", "total_tokens", "input_cost", "output_cost", "total_cost"}
    
    def record_model_output(self, output_text: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Record the LLM model output.
        
        This pairs with the previous prompt to create a complete Langfuse generation.
        """
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        # Extract langfuse-only fields (excluded from integrity payload to preserve commitments)
        integrity_metadata = {k: v for k, v in (metadata or {}).items() if k not in self._LANGFUSE_ONLY_KEYS}
        payload = {"output": output_text, **integrity_metadata}
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
        
        event_dict = asdict(event)
        
        # Add to flat accumulator
        self.accumulator.add_event(event_dict)
        
        # Add to span accumulator if span is active
        if self.current_span_id and self.current_span_accumulator:
            # Only include core event fields (not metadata like signature/signer_id)
            span_event_dict = {
                "session_id": event.session_id,
                "counter": self.current_span_counter,  # Per-span position
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "payload": event.payload,
                "span_id": self.current_span_id,
            }
            self.current_span_accumulator.add_event(span_event_dict)
            self.current_span_counter += 1
            self.events_by_span[self.current_span_id].append(event_dict)
        
        # Add to canonical events (OTel-compliant format for auditing)
        canonical_event = self._create_canonical_event(
            event_type="model_output",
            attributes=payload,
            timestamp=event.timestamp,
            signature=signature,
            signer_id=signer_id
        )
        self.canonical_events.append(canonical_event)
        
        self.counter += 1
        
        # Record generation in Langfuse (combining prompt and response)
        if self.langfuse_client and self._current_prompt:
            model = (metadata or {}).get("model", self._current_model or "unknown")
            input_tokens = (metadata or {}).get("input_tokens", 0)
            output_tokens = (metadata or {}).get("output_tokens", 0)
            input_cost = (metadata or {}).get("input_cost", 0.0)
            output_cost = (metadata or {}).get("output_cost", 0.0)
            total_cost = (metadata or {}).get("total_cost", 0.0)
            
            self.langfuse_client.record_generation(
                name="llm_generation",
                model=model,
                prompt=self._current_prompt,
                response=output_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                input_cost=input_cost,
                output_cost=output_cost,
                total_cost=total_cost,
                metadata={
                    "session_id": self.session_id,
                    "span_id": self.current_span_id,
                    "counter": self.counter - 1,
                }
            )
            
            # Update trace output with the LLM response
            response_preview = output_text[:200] + "..." if len(output_text) > 200 else output_text
            self.langfuse_client.update_trace(output=response_preview)
            
            # Clear prompt after recording
            self._current_prompt = None
        
        logger.info("model_output_recorded", session_id=self.session_id, counter=event.counter)
    
    def record_llm_generation(
        self,
        prompt: str,
        response: str,
        model: str = "unknown",
        name: str = "llm_call",
        input_tokens: int = 0,
        output_tokens: int = 0,
        input_cost: float = 0.0,
        output_cost: float = 0.0,
        total_cost: float = 0.0,
        turn: int = 0,
    ) -> str:
        """
        Record an LLM generation for observability only (Langfuse).
        
        IMPORTANT: This method does NOT modify the integrity log or commitments.
        It only sends data to Langfuse for observability purposes.
        
        Use this for multi-turn agents where you want visibility into each LLM call
        without affecting cryptographic commitments.
        
        Args:
            prompt: The input prompt sent to the LLM
            response: The output response from the LLM
            model: Model name
            name: Generation name (e.g., "llm_call_turn_1")
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            input_cost: Input cost in USD
            output_cost: Output cost in USD
            total_cost: Total cost in USD
            turn: Turn number for metadata
            
        Returns:
            generation_id: Langfuse generation ID (empty string if Langfuse unavailable)
        """
        if not self.langfuse_client:
            return ""
        
        # Ensure trace exists before recording generation
        self._ensure_trace_exists(trace_name="agent_run", input_data=prompt[:200] if turn == 1 else None)
        
        generation_id = self.langfuse_client.record_generation(
            name=name,
            model=model,
            prompt=prompt,
            response=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            metadata={
                "session_id": self.session_id,
                "span_id": self.current_span_id,
                "turn": turn,
            }
        )
        
        logger.debug(
            "llm_generation_recorded",
            generation_id=generation_id,
            turn=turn,
            model=model
        )
        
        return generation_id
    
    def record_tool_input(self, tool_name: str, input_args: dict[str, Any]) -> None:
        """Record tool invocation input"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        payload = {"tool_name": tool_name, "input": input_args}
        signer_id = tool_name
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
        
        event_dict = asdict(event)
        self.accumulator.add_event(event_dict)
        
        if self.current_span_id and self.current_span_accumulator:
            # Only include core event fields (not metadata like signature/signer_id)
            span_event_dict = {
                "session_id": event.session_id,
                "counter": self.current_span_counter,  # Per-span position
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "payload": event.payload,
                "span_id": self.current_span_id,
            }
            self.current_span_accumulator.add_event(span_event_dict)
            self.current_span_counter += 1
            self.events_by_span[self.current_span_id].append(event_dict)
        
        # Add to canonical events (OTel-compliant format for auditing)
        canonical_event = self._create_canonical_event(
            event_type="tool_input",
            attributes=payload,
            timestamp=event.timestamp,
            signature=signature,
            signer_id=signer_id
        )
        self.canonical_events.append(canonical_event)
        
        self.counter += 1
        
        # Record in Langfuse (only if trace exists)
        if self.langfuse_client and self.trace_id:
            self.langfuse_client.record_span(
                name=f"tool_{tool_name}",
                input_data=input_args,
                metadata={"tool_name": tool_name}
            )
        
        logger.info("tool_input_recorded", session_id=self.session_id, counter=event.counter, tool=tool_name)
    
    def record_tool_output(self, tool_name: str, output: Any) -> None:
        """Record tool invocation output"""
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        payload = {"tool_name": tool_name, "output": output}
        signer_id = tool_name
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
        
        event_dict = asdict(event)
        self.accumulator.add_event(event_dict)
        
        if self.current_span_id and self.current_span_accumulator:
            # Only include core event fields (not metadata like signature/signer_id)
            span_event_dict = {
                "session_id": event.session_id,
                "counter": self.current_span_counter,  # Per-span position
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "payload": event.payload,
                "span_id": self.current_span_id,
            }
            self.current_span_accumulator.add_event(span_event_dict)
            self.current_span_counter += 1
            self.events_by_span[self.current_span_id].append(event_dict)
        
        # Add to canonical events (OTel-compliant format for auditing)
        canonical_event = self._create_canonical_event(
            event_type="tool_output",
            attributes=payload,
            timestamp=event.timestamp,
            signature=signature,
            signer_id=signer_id
        )
        self.canonical_events.append(canonical_event)
        
        self.counter += 1
        
        logger.info("tool_output_recorded", session_id=self.session_id, counter=event.counter, tool=tool_name)
    
    def record_event_in_span(
        self,
        event_type: str,
        payload: dict[str, Any],
        signer_id: str = "server"
    ) -> str:
        """Record an event within the current span"""
        if not self.current_span_id:
            raise RuntimeError("No active span. Call start_span() first.")
        
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        signature = self._sign_payload(payload, signer_id)
        
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type=event_type,
            payload=payload,
            signature=signature,
            signer_id=signer_id
        )
        
        event_dict = asdict(event)
        event_dict["span_id"] = self.current_span_id
        
        self.accumulator.add_event(event_dict)
        
        # Only include core event fields (not metadata like signature/signer_id)
        span_event_dict = {
            "session_id": self.session_id,
            "counter": self.current_span_counter,  # Per-span position
            "timestamp": event.timestamp,  # Use IntegrityEvent timestamp, not new one
            "event_type": event_type,
            "payload": payload,
            "span_id": self.current_span_id,
        }
        self.current_span_accumulator.add_event(span_event_dict)
        
        self.events_by_span[self.current_span_id].append(event_dict)
        
        # Add to canonical events (OTel-compliant format for auditing)
        # Use _create_canonical_event to ensure consistent structure with no duplicates
        canonical_event = self._create_canonical_event(
            event_type=event_type,
            attributes=payload,  # OTel standard: single field for event data
            timestamp=event.timestamp,  # Use IntegrityEvent timestamp
            signature=signature,
            signer_id=signer_id
        )
        self.canonical_events.append(canonical_event)
        
        self.current_span_counter += 1
        self.counter += 1
        
        return str(self.counter - 1)
    
    def _finalize_current_span(self) -> str:
        """Finalize the current span and compute its Verkle root"""
        if not self.current_span_id:
            return None
        
        span = self.spans[self.current_span_id]
        
        self.current_span_accumulator.finalize()
        span_root = self.current_span_accumulator.get_root_b64()
        
        span.end_time = self._get_server_timestamp()
        span.end_index = self.counter - 1
        span.event_count = len(self.events_by_span[self.current_span_id])
        span.verkle_root = span_root
        span.duration_ms = int(
            (datetime.fromisoformat(span.end_time) -
             datetime.fromisoformat(span.start_time)).total_seconds() * 1000
        )
        
        # Add span root to session accumulator (for session root computation)
        span_commitment_event = {
            "session_id": self.session_id,
            "counter": self.session_accumulator_counter,
            "event_type": "span_commitment",
            "span_id": self.current_span_id,
            "span_name": span.name,
            "span_root": span_root,
            "event_count": span.event_count,
        }
        self.session_accumulator.add_event(span_commitment_event)
        self.session_accumulator_counter += 1
        self.span_roots[self.current_span_id] = span_root
        
        logger.info(
            "span_finalized",
            span_id=self.current_span_id,
            span_root=span_root,
            event_count=span.event_count
        )
        
        return span_root
    
    def finalize(self) -> Tuple[str, HierarchicalCommitments, bytes]:
        """
        Finalize entire session with hierarchical Verkle roots.
        
        Returns:
            (session_root, commitments, canonical_log_bytes)
        """
        if self.finalized:
            raise RuntimeError("Run already finalized")
        
        # Finalize last span
        if self.current_span_id:
            self._finalize_current_span()
        
        # Finalize accumulators
        self.accumulator.finalize()
        event_accumulator_root = self.accumulator.get_root_b64()
        
        self.session_accumulator.finalize()
        session_root = self.session_accumulator.get_root_b64()
        
        # Get canonical log
        canonical_log = self.session_accumulator.get_canonical_log()
        if isinstance(canonical_log, str):
            canonical_log_bytes = canonical_log.encode('utf-8')
        else:
            canonical_log_bytes = canonical_log
        
        log_hash = hashlib.sha256(canonical_log_bytes).hexdigest()
        
        commitments = HierarchicalCommitments(
            session_root=session_root,
            event_accumulator_root=event_accumulator_root,
            span_roots=self.span_roots,
            canonical_log_hash=log_hash,
            event_count=self.counter,
            timestamp=self._get_server_timestamp(),
            otel_compliant=True
        )
        
        # Finalize Langfuse trace
        if self.langfuse_client and self.trace_id:
            try:
                # Record final verification event
                self.langfuse_client.record_event(
                    name="verification_complete",
                    data={
                        "session_root": session_root,
                        "span_count": len(self.spans),
                        "event_count": self.counter,
                        "verified": True
                    }
                )
                
                # Add verification score
                self.langfuse_client.add_score(
                    name="verification_status",
                    value=1.0,
                    comment="Cryptographically verified"
                )
                
                # Update trace with final output and FLUSH to Langfuse
                self.langfuse_client.update_trace(
                    output=f"Session verified. Root: {session_root[:32]}...",
                    metadata={
                        "session_root": session_root,
                        "span_count": len(self.spans),
                        "event_count": self.counter,
                        "canonical_log_hash": log_hash,
                    },
                    tags=["verified", "finalized"],
                    flush=True  # Send all accumulated trace data now
                )
            except Exception as e:
                logger.warning("langfuse_finalize_failed", error=str(e))
        
        self.finalized = True
        
        logger.info(
            "hierarchical_run_finalized",
            session_id=self.session_id,
            session_root=session_root,
            span_count=len(self.spans),
            event_count=self.counter
        )
        
        return (session_root, commitments, canonical_log_bytes)
    
    def export_to_otel_format(self) -> dict:
        """Export spans to OpenTelemetry format"""
        trace_id = self.trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        
        otel_spans = []
        for span_id, span_meta in self.spans.items():
            start_ms = int(datetime.fromisoformat(span_meta.start_time).timestamp() * 1000)
            end_ms = int(datetime.fromisoformat(span_meta.end_time).timestamp() * 1000) if span_meta.end_time else start_ms
            
            otel_span = {
                "traceId": trace_id,
                "spanId": span_id,
                "parentSpanId": None,
                "name": span_meta.name,
                "startTime": start_ms * 1_000_000,
                "endTime": end_ms * 1_000_000,
                "durationMillis": span_meta.duration_ms,
                "status": {"code": "OK", "description": ""},
                "attributes": {
                    "local_verkle_root": span_meta.verkle_root,
                    "event_indices": f"{span_meta.start_index}-{span_meta.end_index}",
                    "event_count": span_meta.event_count,
                    "session_id": self.session_id,
                }
            }
            otel_spans.append(otel_span)
        
        return {
            "traceId": trace_id,
            "name": "verifiable_ai_workflow",
            "startTime": int(datetime.fromisoformat(self.spans[list(self.spans.keys())[0]].start_time).timestamp() * 1000 * 1_000_000) if self.spans else 0,
            "endTime": int(datetime.fromisoformat(self.spans[list(self.spans.keys())[-1]].end_time).timestamp() * 1000 * 1_000_000) if self.spans else 0,
            "spans": otel_spans,
            "metadata": {
                "integrity": {
                    "session_root_commitment": self.session_accumulator.get_root_b64() if not self.finalized else None,
                    "span_roots": self.span_roots,
                    "canonical_log_hash": hashlib.sha256(self.accumulator.get_canonical_log()).hexdigest(),
                    "event_count": self.counter,
                    "verification_ready": True,
                    "session_id": self.session_id,
                }
            }
        }
    
    def save_to_local_storage(self, base_dir: Path) -> dict:
        """Save all data to local storage with hierarchical structure"""
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # Save canonical log as JSON array with full event data (for auditing)
        # Includes both actual events AND span_commitment events
        # Format: Standard JSON array (OTel-compliant), not JSONL
        log_path = base_dir / "canonical_log.json"
        with open(log_path, 'w') as f:
            f.write(json.dumps(self.canonical_events, indent=2))
        
        # Compute canonical log hash for verification
        # Use compact form for hash (no whitespace) for determinism
        canonical_log_text = json.dumps(self.canonical_events, separators=(',', ':'), sort_keys=True)
        canonical_log_bytes = canonical_log_text.encode('utf-8')
        canonical_log_hash = hashlib.sha256(canonical_log_bytes).hexdigest()
        
        # Save spans structure
        spans_data = {span_id: asdict(span_meta) for span_id, span_meta in self.spans.items()}
        spans_path = base_dir / "spans_structure.json"
        spans_path.write_text(json.dumps(spans_data, indent=2))
        
        # Save commitments
        commitments_path = base_dir / "commitments.json"
        commitments_data = {
            "session_root": self.session_accumulator.get_root_b64() if self.finalized else None,
            "event_accumulator_root": self.accumulator.get_root_b64() if self.finalized else None,
            "span_roots": self.span_roots,
            "canonical_log_hash": canonical_log_hash,
        }
        commitments_path.write_text(json.dumps(commitments_data, indent=2))
        
        # Save metadata
        metadata_path = base_dir / "metadata.json"
        metadata = {
            "session_id": self.session_id,
            "timestamp": self._get_server_timestamp(),
            "event_count": self.counter,
            "span_count": len(self.spans),
            "log_hash": canonical_log_hash,
            "otel_compliant": True,
            "format": "JSONL with OTel-style events",
        }
        metadata_path.write_text(json.dumps(metadata, indent=2))
        
        # Save OTel export
        otel_export = self.export_to_otel_format()
        otel_path = base_dir / "otel_export.json"
        otel_path.write_text(json.dumps(otel_export, indent=2))
        
        result = {
            "base_dir": str(base_dir),
            "canonical_log": str(log_path),
            "spans_structure": str(spans_path),
            "commitments": str(commitments_path),
            "metadata": str(metadata_path),
            "otel_export": str(otel_path),
        }
        
        logger.info("local_storage_saved", **result)
        return result
