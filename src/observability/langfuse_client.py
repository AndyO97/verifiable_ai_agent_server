"""
Langfuse integration module for trace collection and LLM observability

Langfuse Hierarchy (correct model):
- Session: Groups multiple traces together (e.g., a chat session)
- Trace: A single user request/interaction
- Generation: An LLM API call (prompt -> response) within a trace
- Span: A tool call or other operation within a trace

This module provides:
- Trace collection and visualization dashboard
- LLM cost tracking and analytics
- Generation tracking for LLM calls
- Session-level trace grouping

Self-hosted deployment: See LANGFUSE_SETUP_GUIDE.md
"""

from __future__ import annotations

from typing import Optional, Any
from datetime import datetime, timezone
import uuid
import json
import requests
from requests.auth import HTTPBasicAuth

import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)


class LangfuseClient:
    """
    Client for Langfuse trace collection and LLM observability.
    
    Correct Langfuse Hierarchy:
    - Session: Groups multiple traces (set via session_id)
    - Trace: One per user request/interaction
    - Generation: LLM API calls within a trace
    - Span: Tool calls or other operations
    
    PREVIOUS ISSUE (SEEMS FIXED): The Langfuse dashboard was showing duplicate
    traces. This was fixed by ensuring the 'id' field is included in the trace
    body (not just the batch item). With proper 'id' in body, Langfuse correctly
    merges trace updates. Needs further testing to confirm fully resolved.
    
    MULTI-TRACE SUPPORT: This client supports multiple traces per session. Each
    create_trace() + flush_trace() cycle creates a separate trace. Complex workflows
    (e.g., multi-turn agents) may create multiple traces within one session.
    """
    
    def __init__(self, session_id: str):
        """
        Initialize Langfuse client for a session.
        
        Args:
            session_id: Unique session identifier (groups traces together)
        """
        self.session_id = session_id
        self.settings = get_settings()
        self.api_endpoint = self.settings.langfuse.api_endpoint
        self.current_trace_id: Optional[str] = None
        self._current_trace_data: Optional[dict] = None  # Store trace data for updates
        self._trace_flushed: bool = False  # Track whether current trace has been sent to Langfuse
        self._has_pending_updates: bool = False  # Track if there are updates since last flush
        self._pending_traces: list[tuple[str, dict]] = []  # (trace_id, trace_data) for multi-trace support
        self._auth: Optional[HTTPBasicAuth] = None
        
        # Initialize auth if credentials available
        if self.settings.langfuse.public_key and self.settings.langfuse.secret_key:
            self._auth = HTTPBasicAuth(
                self.settings.langfuse.public_key,
                self.settings.langfuse.secret_key
            )
        
        logger.info("langfuse_client_init", session_id=session_id, endpoint=self.api_endpoint)
    
    def create_trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        tags: Optional[list[str]] = None,
        input_data: Optional[str] = None,
    ) -> str:
        """
        Create a new trace for a user interaction.
        
        In Langfuse, a Trace represents a single user request or interaction.
        Multiple traces can belong to the same session (grouped by session_id).
        
        NOTE: This does NOT send to Langfuse immediately. The trace is only
        sent when update_trace(flush=True) is called, ensuring only one
        trace entry appears in Langfuse.
        
        Args:
            name: Trace name (e.g., "user_request", "explain_verkle_trees")
            user_id: Optional user ID
            metadata: Optional metadata dict
            tags: Optional list of tags
            input_data: Optional input text (e.g., user prompt)
            
        Returns:
            trace_id: Unique trace identifier
        """
        trace_id = str(uuid.uuid4())
        self.current_trace_id = trace_id
        self._trace_flushed = False  # New trace, not yet sent
        self._has_pending_updates = True  # New trace data needs to be sent
        
        # Build trace payload - store locally, don't send yet
        self._current_trace_data = {
            "id": trace_id,  # Required for Langfuse to identify the trace
            "name": name,
            "sessionId": self.session_id,  # Links trace to session
            "userId": user_id or "default",
            "metadata": metadata or {},
            "tags": tags or ["verified-agent"],
            "release": "1.0",
            "version": "mcp-2024-11",
        }
        
        if input_data:
            self._current_trace_data["input"] = input_data
        
        # Don't send yet - will be sent on update_trace(flush=True) or flush_trace()
        logger.info("langfuse_trace_created", trace_id=trace_id, name=name, session_id=self.session_id)
        return trace_id
    
    def flush_trace(self, reset: bool = True) -> None:
        """
        Flush the current trace to Langfuse immediately.
        
        Use this for multi-trace workflows where you need to send a trace
        and start a new one within the same session. After flushing with reset=True,
        you can call create_trace() again to start a new trace.
        
        Args:
            reset: If True, reset trace state for next trace. If False, keep state
                   (used internally by update_trace to allow continued updates).
        """
        if not self.current_trace_id or not self._current_trace_data:
            logger.warning("no_trace_to_flush")
            return
        
        # Skip if already flushed and no new updates (minimize duplicates)
        if self._trace_flushed and not self._has_pending_updates:
            logger.debug("langfuse_trace_skip_flush_no_updates", trace_id=self.current_trace_id)
            if reset:
                self.current_trace_id = None
                self._current_trace_data = None
                self._trace_flushed = False
                self._has_pending_updates = False
            return
        
        self._send_batch([{
            "type": "trace-create",
            "id": self.current_trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "body": self._current_trace_data
        }])
        
        logger.debug("langfuse_trace_flushed", trace_id=self.current_trace_id)
        
        self._trace_flushed = True  # Mark as sent
        self._has_pending_updates = False  # Updates sent
        
        # Reset for next trace if requested (but keep session_id)
        if reset:
            self.current_trace_id = None
            self._current_trace_data = None
            self._trace_flushed = False
            self._has_pending_updates = False
    
    def record_generation(
        self,
        name: str,
        model: str,
        prompt: str,
        response: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        input_cost: float = 0.0,
        output_cost: float = 0.0,
        total_cost: float = 0.0,
        trace_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Record an LLM generation (API call) within a trace.
        
        This creates a GENERATION observation in Langfuse, which is specifically
        designed for LLM calls and shows prompt/response, tokens, and cost.
        
        Session/trace costs and tokens are automatically aggregated from generations.
        
        Args:
            name: Generation name (e.g., "llm_call", "explain_verkle_trees")
            model: Model name (e.g., "gpt-4", "arcee-ai/trinity-large-preview:free")
            prompt: The input prompt sent to the LLM
            response: The output response from the LLM
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            input_cost: Input cost in USD
            output_cost: Output cost in USD
            total_cost: Total cost in USD (if 0, calculated from input+output)
            trace_id: Optional trace ID (uses current trace if not provided)
            metadata: Optional additional metadata
            
        Returns:
            generation_id: Unique generation identifier
        """
        trace_id = trace_id or self.current_trace_id
        if not trace_id:
            logger.warning("no_trace_for_generation", name=name)
            return ""
        
        # Ensure trace is sent to Langfuse before adding generations
        # (Langfuse needs the trace to exist before it can attach generations)
        if not self._trace_flushed and self._current_trace_data:
            self.flush_trace(reset=False)  # Send trace but keep state for updates
        
        generation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Build generation payload (Langfuse GENERATION type)
        generation_body = {
            "id": generation_id,  # Required for Langfuse to create the generation
            "traceId": trace_id,
            "type": "GENERATION",
            "name": name,
            "model": model,
            "input": prompt,
            "output": response,
            "startTime": now.isoformat(),
            "endTime": now.isoformat(),
            "metadata": metadata or {},
        }
        
        # Add usageDetails (new format, replaces deprecated 'usage')
        total_tokens = input_tokens + output_tokens
        if input_tokens > 0 or output_tokens > 0:
            generation_body["usageDetails"] = {
                "input": input_tokens,
                "output": output_tokens,
                "total": total_tokens,
            }
        
        # Add costDetails in USD (enables session/trace cost aggregation)
        calculated_total = total_cost if total_cost > 0 else (input_cost + output_cost)
        if input_cost > 0 or output_cost > 0 or calculated_total > 0:
            generation_body["costDetails"] = {
                "input": input_cost,
                "output": output_cost,
                "total": calculated_total,
            }
        
        # Send to Langfuse
        self._send_batch([{
            "type": "generation-create",
            "id": generation_id,
            "timestamp": now.isoformat(),
            "body": generation_body
        }])
        
        logger.info(
            "langfuse_generation_recorded",
            generation_id=generation_id,
            trace_id=trace_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        
        return generation_id
    
    def record_span(
        self,
        name: str,
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
        trace_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Record a span (tool call or other operation) within a trace.
        
        Args:
            name: Span name (e.g., "tool_calculator", "mcp_initialize")
            input_data: Input data for the operation
            output_data: Output data from the operation
            trace_id: Optional trace ID (uses current trace if not provided)
            metadata: Optional additional metadata
            
        Returns:
            span_id: Unique span identifier
        """
        trace_id = trace_id or self.current_trace_id
        if not trace_id:
            logger.warning("no_trace_for_span", name=name)
            return ""
        
        span_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Build span payload
        span_body = {
            "traceId": trace_id,
            "type": "SPAN",
            "name": name,
            "startTime": now.isoformat(),
            "endTime": now.isoformat(),
            "metadata": metadata or {},
        }
        
        if input_data is not None:
            span_body["input"] = json.dumps(input_data) if isinstance(input_data, dict) else str(input_data)
        if output_data is not None:
            span_body["output"] = json.dumps(output_data) if isinstance(output_data, dict) else str(output_data)
        
        # Send to Langfuse
        self._send_batch([{
            "type": "span-create",
            "id": span_id,
            "timestamp": now.isoformat(),
            "body": span_body
        }])
        
        logger.debug("langfuse_span_recorded", span_id=span_id, trace_id=trace_id, name=name)
        return span_id
    
    def record_event(
        self,
        name: str,
        data: Optional[dict] = None,
        trace_id: Optional[str] = None,
        level: str = "DEFAULT",
    ) -> str:
        """
        Record a simple event within a trace.
        
        Args:
            name: Event name
            data: Event data
            trace_id: Optional trace ID (uses current trace if not provided)
            level: Event level (DEFAULT, DEBUG, WARNING, ERROR)
            
        Returns:
            event_id: Unique event identifier
        """
        trace_id = trace_id or self.current_trace_id
        if not trace_id:
            logger.warning("no_trace_for_event", name=name)
            return ""
        
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Build event payload
        event_body = {
            "traceId": trace_id,
            "type": "EVENT",
            "name": name,
            "startTime": now.isoformat(),
            "level": level,
        }
        
        if data:
            event_body["input"] = json.dumps(data) if isinstance(data, dict) else str(data)
        
        # Send to Langfuse
        self._send_batch([{
            "type": "event-create",
            "id": event_id,
            "timestamp": now.isoformat(),
            "body": event_body
        }])
        
        logger.debug("langfuse_event_recorded", event_id=event_id, trace_id=trace_id, name=name)
        return event_id
    
    def update_trace(
        self,
        trace_id: Optional[str] = None,
        input_data: Optional[str] = None,
        output: Optional[str] = None,
        metadata: Optional[dict] = None,
        tags: Optional[list[str]] = None,
        flush: bool = False,
    ) -> None:
        """
        Update a trace with input, output and metadata.
        
        Updates are accumulated locally and only sent when flush=True.
        
        Args:
            trace_id: Trace ID to update (uses current if not provided)
            input_data: Input text (e.g., user prompt)
            output: Final output/result of the trace
            metadata: Additional metadata to merge
            tags: Additional tags to add
            flush: If True, send accumulated updates to Langfuse immediately
        """
        trace_id = trace_id or self.current_trace_id
        if not trace_id:
            logger.warning("no_trace_to_update")
            return
        
        # Initialize trace data if not exists
        if self._current_trace_data is None:
            self._current_trace_data = {
                "id": trace_id,  # Required for Langfuse to identify the trace
                "name": "trace",
                "sessionId": self.session_id,
                "userId": "default",
                "release": "1.0",
                "version": "mcp-2024-11",
            }
        
        # Ensure id is always in body (for updates)
        if "id" not in self._current_trace_data:
            self._current_trace_data["id"] = trace_id
        
        # Accumulate updates (don't send yet)
        has_updates = False
        if input_data:
            self._current_trace_data["input"] = input_data
            has_updates = True
        if output:
            self._current_trace_data["output"] = output
            has_updates = True
        if metadata:
            # Merge metadata with existing
            existing_metadata = self._current_trace_data.get("metadata", {})
            self._current_trace_data["metadata"] = {**existing_metadata, **metadata}
            has_updates = True
        if tags:
            # Extend tags with new ones
            existing_tags = self._current_trace_data.get("tags", [])
            self._current_trace_data["tags"] = list(set(existing_tags + tags))
            has_updates = True
        
        if has_updates:
            self._has_pending_updates = True
        
        # Only send if flush requested (don't reset - keep trace data for reference)
        if flush:
            self.flush_trace(reset=False)
            logger.debug("langfuse_trace_updated", trace_id=trace_id)
    
    def add_score(
        self,
        name: str,
        value: float,
        trace_id: Optional[str] = None,
        observation_id: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> str:
        """
        Add a score to a trace or observation.
        
        Args:
            name: Score name (e.g., "verification_status", "quality")
            value: Score value (typically 0.0-1.0)
            trace_id: Trace ID (uses current if not provided)
            observation_id: Optional specific observation to score
            comment: Optional comment explaining the score
            
        Returns:
            score_id: Unique score identifier
        """
        trace_id = trace_id or self.current_trace_id
        if not trace_id:
            logger.warning("no_trace_for_score", name=name)
            return ""
        
        score_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        score_body = {
            "traceId": trace_id,
            "name": name,
            "value": value,
        }
        
        if observation_id:
            score_body["observationId"] = observation_id
        if comment:
            score_body["comment"] = comment
        
        self._send_batch([{
            "type": "score-create",
            "id": score_id,
            "timestamp": now.isoformat(),
            "body": score_body
        }])
        
        logger.debug("langfuse_score_added", score_id=score_id, trace_id=trace_id, name=name, value=value)
        return score_id
    
    def _send_batch(self, items: list[dict]) -> bool:
        """
        Send a batch of items to Langfuse API.
        
        Args:
            items: List of batch items to send
            
        Returns:
            bool: Whether the request was successful
        """
        if not self._auth:
            logger.debug("langfuse_no_credentials")
            return False
        
        try:
            ingestion_url = f"{self.api_endpoint}/api/public/ingestion"
            
            response = requests.post(
                ingestion_url,
                json={"batch": items},
                auth=self._auth,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in (200, 201, 207):
                logger.debug("langfuse_batch_sent", item_count=len(items))
                return True
            else:
                logger.warning(
                    "langfuse_batch_failed",
                    status_code=response.status_code,
                    response_text=response.text[:200] if response.text else "empty"
                )
                return False
                
        except Exception as e:
            logger.warning("langfuse_batch_error", error=str(e), error_type=type(e).__name__)
            return False
    
    def get_current_trace_id(self) -> Optional[str]:
        """Get the current trace ID."""
        return self.current_trace_id


def create_langfuse_client(session_id: Optional[str] = None) -> LangfuseClient:
    """
    Factory function to create a Langfuse client.
    
    Args:
        session_id: Optional session ID (generated if not provided)
        
    Returns:
        LangfuseClient instance
    """
    if not session_id:
        session_id = str(uuid.uuid4())
    
    return LangfuseClient(session_id)
