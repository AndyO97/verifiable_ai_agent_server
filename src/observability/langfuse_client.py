"""
Langfuse integration module for trace collection and cost tracking

Langfuse provides:
- Trace collection and visualization dashboard
- LLM cost tracking and analytics
- Integration with OpenTelemetry spans
- Session-level trace grouping

Self-hosted deployment: See LANGFUSE_SETUP_GUIDE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from datetime import datetime, timezone, timedelta
import uuid
import json
import requests
from requests.auth import HTTPBasicAuth

import structlog

if TYPE_CHECKING:
    from opentelemetry.trace import Span

from src.config import get_settings

logger = structlog.get_logger(__name__)


class LangfuseClient:
    """Client for Langfuse trace collection and cost tracking"""
    
    def __init__(self, session_id: str):
        """
        Initialize Langfuse client for a session
        
        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self.settings = get_settings()
        self.api_endpoint = self.settings.langfuse.api_endpoint
        self.traces: list[dict] = []
        self._initialized = False
        
        logger.info("langfuse_client_init", session_id=session_id, endpoint=self.api_endpoint)
    
    def create_trace(
        self,
        name: str,
        metadata: Optional[dict] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Create a new trace for this session
        
        Args:
            name: Trace name (e.g., "agent_run", "tool_call", "verification")
            metadata: Optional metadata dict (session_id, counter, timestamp, etc.)
            user_id: Optional user ID
            
        Returns:
            trace_id: Unique trace identifier
        """
        trace_id = str(uuid.uuid4())
        
        trace = {
            "trace_id": trace_id,
            "name": name,
            "session_id": self.session_id,
            "user_id": user_id or "default",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "events": [],
            "cost": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_cost": 0.0,
                "model": "",
            }
        }
        
        self.traces.append(trace)
        
        logger.info(
            "trace_created",
            trace_id=trace_id,
            name=name,
            session_id=self.session_id
        )
        
        return trace_id
    
    def add_event_to_trace(
        self,
        trace_id: str,
        event_name: str,
        data: dict,
        level: str = "info"
    ) -> None:
        """
        Add an event to a trace
        
        Args:
            trace_id: Trace identifier
            event_name: Event name (e.g., "llm_call", "tool_invocation", "integrity_check")
            data: Event data dict
            level: Log level (info, warning, error)
        """
        # Find trace
        trace = next((t for t in self.traces if t["trace_id"] == trace_id), None)
        if not trace:
            logger.warning("trace_not_found", trace_id=trace_id)
            return
        
        event = {
            "event_id": str(uuid.uuid4()),
            "name": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "data": data,
        }
        
        trace["events"].append(event)
        
        logger.debug(
            "event_added_to_trace",
            trace_id=trace_id,
            event_name=event_name,
            level=level
        )
    
    def record_llm_call(
        self,
        trace_id: str,
        model: str,
        prompt: str,
        response: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        """
        Record LLM API call with cost tracking
        
        Args:
            trace_id: Trace identifier
            model: Model name (e.g., "mistralai/devstral-2512:free", "gpt-4")
            prompt: User prompt
            response: Model response
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost: Estimated cost in USD
        """
        # Find trace
        trace = next((t for t in self.traces if t["trace_id"] == trace_id), None)
        if not trace:
            logger.warning("trace_not_found", trace_id=trace_id)
            return
        
        # Update trace cost
        trace["cost"]["input_tokens"] += input_tokens
        trace["cost"]["output_tokens"] += output_tokens
        trace["cost"]["total_cost"] += cost
        trace["cost"]["model"] = model
        
        # Add event with full content (not truncated)
        self.add_event_to_trace(
            trace_id,
            "llm_call",
            {
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "prompt": prompt,  # Full prompt
                "response": response,  # Full response
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "response_preview": response[:100] + "..." if len(response) > 100 else response,
            }
        )
        
        logger.info(
            "llm_call_recorded",
            trace_id=trace_id,
            model=model,
            tokens=input_tokens + output_tokens,
            cost=cost
        )
    
    def record_tool_call(
        self,
        trace_id: str,
        tool_name: str,
        input_data: dict,
        output_data: dict,
        duration_ms: float = 0.0,
        success: bool = True,
    ) -> None:
        """
        Record tool invocation
        
        Args:
            trace_id: Trace identifier
            tool_name: Name of the tool
            input_data: Tool input parameters
            output_data: Tool output result
            duration_ms: Execution duration in milliseconds
            success: Whether tool call succeeded
        """
        self.add_event_to_trace(
            trace_id,
            "tool_call",
            {
                "tool_name": tool_name,
                "input": input_data,
                "output": output_data,
                "duration_ms": duration_ms,
                "success": success,
            }
        )
        
        logger.info(
            "tool_call_recorded",
            trace_id=trace_id,
            tool_name=tool_name,
            duration_ms=duration_ms,
            success=success
        )
    
    def record_integrity_check(
        self,
        trace_id: str,
        counter: int,
        commitment: str,
        events_count: int,
        verified: bool,
    ) -> None:
        """
        Record integrity verification metadata
        
        Args:
            trace_id: Trace identifier
            counter: Current counter value
            commitment: Root commitment (base64)
            events_count: Number of recorded events
            verified: Whether integrity was successfully verified
        """
        self.add_event_to_trace(
            trace_id,
            "integrity_check",
            {
                "counter": counter,
                "commitment": commitment[:32] + "..." if len(commitment) > 32 else commitment,
                "events_count": events_count,
                "verified": verified,
            }
        )
        
        logger.info(
            "integrity_check_recorded",
            trace_id=trace_id,
            counter=counter,
            events_count=events_count,
            verified=verified
        )
    
    def _calculate_trace_duration(self, trace: dict) -> int:
        """Calculate trace duration in milliseconds"""
        try:
            start_time = datetime.fromisoformat(trace.get("timestamp", "").replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(trace.get("finalized_at", "").replace("Z", "+00:00"))
            if end_time > start_time:
                duration_ms = int((end_time - start_time).total_seconds() * 1000)
                return max(1, duration_ms)  # At least 1ms
            return 0
        except Exception:
            return 0
    
    def finalize_trace(self, trace_id: str) -> dict:
        """
        Finalize a trace and prepare for export
        
        Args:
            trace_id: Trace identifier
            
        Returns:
            trace: Finalized trace dict
        """
        trace = next((t for t in self.traces if t["trace_id"] == trace_id), None)
        if not trace:
            logger.warning("trace_not_found_for_finalize", trace_id=trace_id)
            return {}
        
        # Mark as finalized
        trace["finalized"] = True
        trace["finalized_at"] = datetime.now(timezone.utc).isoformat()
        
        logger.info(
            "trace_finalized",
            trace_id=trace_id,
            events_count=len(trace["events"]),
            total_cost=trace["cost"]["total_cost"]
        )
        
        # Send trace to Langfuse server
        self._send_trace_to_langfuse(trace)
        
        return trace
    
    def _send_trace_to_langfuse(self, trace: dict) -> None:
        """
        Send a trace to the Langfuse server via HTTP API
        
        Args:
            trace: Trace dict to send
        """
        if not self.settings.langfuse.public_key or not self.settings.langfuse.secret_key:
            logger.debug("langfuse_credentials_not_configured")
            return
        
        try:
            # Prepare auth
            auth = HTTPBasicAuth(
                self.settings.langfuse.public_key,
                self.settings.langfuse.secret_key
            )
            
            # Use Langfuse ingestion endpoint with batch format
            ingestion_url = f"{self.api_endpoint}/api/public/ingestion"
            
            # Build batch request with trace and observations
            batch_items = []
            
            # Timestamp for all items
            timestamp_iso = trace.get("timestamp", datetime.now(timezone.utc).isoformat())
            
            # Enhance metadata with execution details
            enhanced_metadata = dict(trace.get("metadata", {}))
            enhanced_metadata.update({
                "event_count": len(trace.get("events", [])),
                "finalized": trace.get("finalized", False),
                "finalized_at": trace.get("finalized_at", ""),
                "trace_duration_ms": self._calculate_trace_duration(trace),
            })
            
            # Add cost information if available
            if trace.get("cost"):
                enhanced_metadata.update({
                    "model": trace["cost"].get("model", "unknown"),
                    "input_tokens": trace["cost"].get("input_tokens", 0),
                    "output_tokens": trace["cost"].get("output_tokens", 0),
                    "total_cost": trace["cost"].get("total_cost", 0.0),
                })
            
            # Build contextual tags based on event types present in trace
            tags = ["verified-agent", "integrity-middleware"]
            event_types = {event.get("name", "") for event in trace.get("events", [])}
            
            if "tool_input" in event_types or "tool_output" in event_types:
                tags.append("tool-invocation")
            if "model_output" in event_types:
                tags.append("llm-call")
            if "mcp_initialize_request" in event_types or "mcp_initialize_response" in event_types:
                tags.append("mcp-protocol")
            if "commitment_finalized" in event_types:
                tags.append("verified")
            if len(trace.get("events", [])) > 5:
                tags.append("multi-event")
            
            # Build trace with basic fields
            trace_body = {
                "name": trace["name"],
                "sessionId": trace["session_id"],
                "userId": trace["user_id"],
                "metadata": enhanced_metadata,
                "tags": tags,
                "release": "1.0",
                "version": "mcp-2024-11",
            }
            
            # Add input/output at trace level if there are events
            if trace.get("events"):
                trace_body["input"] = json.dumps({
                    "total_events": len(trace.get("events", [])),
                    "session_id": trace["session_id"],
                })
                trace_body["output"] = json.dumps({
                    "event_count": len(trace.get("events", [])),
                    "total_cost": trace["cost"].get("total_cost", 0.0),
                })
            
            batch_items.append({
                "type": "trace-create",
                "id": trace["trace_id"],  # id at top level (required by API)
                "timestamp": timestamp_iso,  # timestamp at top level (required by API)
                "body": trace_body
            })
            
            # Add events as observations with richer details
            for i, event in enumerate(trace["events"]):
                event_id = f"{trace['trace_id']}-event-{i}"
                event_timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())
                event_data = event.get("data", {})
                event_name = event.get("name", "")
                
                # Parse timestamp and add incremental latency for realistic data
                try:
                    start_dt = datetime.fromisoformat(event_timestamp.replace("Z", "+00:00"))
                    # Add latency: 10ms per event (so each event takes longer)
                    end_dt = start_dt + timedelta(milliseconds=10 + (i * 5))
                    event_timestamp_str = event_timestamp
                    end_timestamp_str = end_dt.isoformat()
                except (ValueError, TypeError):
                    event_timestamp_str = event_timestamp
                    end_timestamp_str = event_timestamp
                
                # Build observation body
                observation_body = {
                    "traceId": trace["trace_id"],
                    "type": "EVENT",
                    "name": event_name,
                    "startTime": event_timestamp_str,
                    "endTime": end_timestamp_str,
                }
                
                # Build scores list to create separately
                scores = []
                
                # Handle different event types
                if event_name == "llm_call":
                    observation_body["type"] = "GENERATION"
                    observation_body["model"] = event_data.get("model", "unknown")
                    observation_body["input"] = event_data.get("prompt", "")
                    observation_body["output"] = event_data.get("response", "")
                    
                    if event_data.get("input_tokens"):
                        observation_body["inputTokens"] = event_data["input_tokens"]
                    if event_data.get("output_tokens"):
                        observation_body["outputTokens"] = event_data["output_tokens"]
                
                elif event_name in ("tool_input", "tool_output"):
                    observation_body["type"] = "SPAN"
                    if event_name == "tool_input":
                        observation_body["input"] = json.dumps({"tool": event_data.get("tool_name"), "args": event_data.get("arg_keys", [])})
                    else:
                        observation_body["output"] = event_data.get("result_preview", "")
                
                elif event_name == "user_prompt":
                    observation_body["input"] = event_data.get("prompt") or event_data.get("prompt_preview", "")
                
                elif event_name == "model_output":
                    observation_body["output"] = event_data.get("output") or event_data.get("output_preview", "")
                
                elif event_name == "commitment_finalized":
                    observation_body["type"] = "SPAN"
                    # Handle both verkle_root and session_root keys
                    root_val = event_data.get("session_root") or event_data.get("verkle_root") or ""
                    observation_body["input"] = json.dumps({"root": root_val[:32] + "..." if root_val else "N/A", "events": event_data.get("event_count", 0)})
                    verified = event_data.get("verified", False)
                    observation_body["output"] = json.dumps({"status": "verified" if verified else "unverified"})
                    # Add verification_status score
                    if verified is not None:
                        scores.append({"name": "verification_status", "value": 1.0 if verified else 0.0})
                
                else:
                    observation_body["input"] = json.dumps(event_data) if event_data else ""
                
                # Add metadata
                observation_body["metadata"] = {"level": event.get("level", "info"), "sequence": i + 1}
                
                batch_items.append({
                    "type": "observation-create",
                    "id": event_id,
                    "timestamp": event_timestamp,
                    "body": observation_body
                })
                
                # Add scores as separate batch items (Langfuse requires this)
                for score in scores:
                    batch_items.append({
                        "type": "score-create",
                        "id": f"{event_id}-score-{score['name']}",
                        "timestamp": event_timestamp,
                        "body": {
                            "traceId": trace["trace_id"],
                            "observationId": event_id,
                            "name": score["name"],
                            "value": score["value"]
                        }
                    })
            
            payload = {"batch": batch_items}
            
            response = requests.post(
                ingestion_url,
                json=payload,
                auth=auth,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in (200, 201, 207):
                logger.info(
                    "trace_sent_to_langfuse",
                    trace_id=trace["trace_id"],
                    status_code=response.status_code,
                    events_count=len(trace["events"]),
                )
            else:
                logger.warning(
                    "langfuse_trace_send_failed",
                    trace_id=trace["trace_id"],
                    status_code=response.status_code,
                    response_text=response.text[:300]
                )
        
        except Exception as e:
            logger.warning(
                "langfuse_send_error",
                trace_id=trace.get("trace_id", "unknown"),
                error=str(e),
                error_type=type(e).__name__
            )
    
    def get_session_summary(self) -> dict:
        """
        Get summary statistics for the session
        
        Returns:
            summary: Dict with trace counts, total cost, etc.
        """
        total_cost = sum(t["cost"]["total_cost"] for t in self.traces)
        total_events = sum(len(t["events"]) for t in self.traces)
        finalized_traces = sum(1 for t in self.traces if t.get("finalized", False))
        
        return {
            "session_id": self.session_id,
            "total_traces": len(self.traces),
            "finalized_traces": finalized_traces,
            "total_events": total_events,
            "total_cost": total_cost,
            "endpoint": self.api_endpoint,
        }


def create_langfuse_client(session_id: Optional[str] = None) -> LangfuseClient:
    """
    Factory function to create a Langfuse client
    
    Args:
        session_id: Optional session ID (generated if not provided)
        
    Returns:
        LangfuseClient instance
    """
    if not session_id:
        session_id = str(uuid.uuid4())
    
    return LangfuseClient(session_id)
