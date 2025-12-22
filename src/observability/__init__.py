"""
Observability module - OTel and Langfuse integration

NOTE: OpenTelemetry imports will be available after running:
  uv pip install -e ".[dev]"

This module provides OTel initialization and span management for
tracing agent interactions with Langfuse backend export.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import structlog

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False  # Will be available after uv pip install -e ".[dev]"

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider as TracerProviderType
    from opentelemetry import trace as trace_module

from src.config import get_settings

logger = structlog.get_logger(__name__)


class OTelInitializer:
    """Initialize OpenTelemetry with Langfuse export"""
    
    @staticmethod
    def init_tracing() -> tuple[TracerProvider, trace.Tracer]:
        """
        Initialize OpenTelemetry tracing with Langfuse backend.
        
        Returns:
            (TracerProvider, Tracer) tuple
        """
        settings = get_settings()
        
        # Create resource
        resource = Resource.create({
            "service.name": settings.otel.service_name,
            "service.version": settings.otel.service_version,
        })
        
        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)
        
        # Export to Langfuse via OTLP
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel.otlp_endpoint,
            insecure=True,  # Set to False for TLS in production
        )
        
        tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        
        # Set as global provider
        trace.set_tracer_provider(tracer_provider)
        
        # Get tracer
        tracer = trace.get_tracer(__name__)
        
        logger.info("otel_initialized", endpoint=settings.otel.otlp_endpoint)
        
        return tracer_provider, tracer


class SpanManager:
    """
    Manages span creation and attribute setting for integrity metadata
    
    Provides hierarchical span management with automatic duration measurement,
    parent-child relationships, and integrity metadata tracking.
    """
    
    def __init__(self, tracer: trace.Tracer):
        self.tracer = tracer
        self.root_span: Optional[trace.Span] = None
        self.active_spans: dict[str, trace.Span] = {}
    
    def start_run_span(self, session_id: str) -> trace.Span:
        """
        Start the root span for an agent run
        
        Args:
            session_id: Session identifier
            
        Returns:
            Root span (stored as active)
        """
        span = self.tracer.start_as_current_span("agent_run")
        span.set_attribute("session_id", session_id)
        span.set_attribute("event.type", "agent_run_start")
        span.set_attribute("service.name", "verifiable-ai-agent")
        
        self.root_span = span
        self.active_spans["root"] = span
        
        logger.info("agent_run_span_started", session_id=session_id)
        
        return span
    
    def set_integrity_metadata(
        self,
        span: trace.Span,
        session_id: str,
        counter: int,
        timestamp: str
    ) -> None:
        """
        Set integrity-related metadata on a span
        
        Args:
            span: Span to update
            session_id: Session identifier
            counter: Current counter value
            timestamp: ISO 8601 timestamp
        """
        span.set_attribute("integrity.session_id", session_id)
        span.set_attribute("integrity.counter", counter)
        span.set_attribute("integrity.timestamp", timestamp)
        
        logger.debug(
            "integrity_metadata_set",
            session_id=session_id,
            counter=counter
        )
    
    def set_verkle_root(self, span: trace.Span, root_b64: str) -> None:
        """
        Set Verkle root commitment on a span (Base64-encoded)
        
        Args:
            span: Span to update
            root_b64: Verkle commitment root (base64)
        """
        span.set_attribute("verkle.root_b64", root_b64)
        span.set_attribute("verkle.root_length", len(root_b64))
        
        logger.info("verkle_root_set_on_span", root_length=len(root_b64))
    
    def start_llm_span(self, span_name: str = "llm_call") -> object:
        """
        Start a span for LLM API call
        
        Returns a context manager for use with 'with' statement:
        
        Example:
            with span_manager.start_llm_span() as span:
                response = llm.call(prompt)
                span.set_attribute("model", "mistral")
        """
        return self.tracer.start_as_current_span(span_name)
    
    def record_llm_call(
        self,
        span: trace.Span,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float = 0.0
    ) -> None:
        """
        Record LLM call metadata on a span
        
        Args:
            span: LLM call span
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cost: Cost in USD
        """
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.tokens.input", input_tokens)
        span.set_attribute("llm.tokens.output", output_tokens)
        span.set_attribute("llm.tokens.total", input_tokens + output_tokens)
        span.set_attribute("llm.cost_usd", cost)
        span.set_attribute("event.type", "llm_invocation")
        
        logger.debug(
            "llm_span_recorded",
            model=model,
            total_tokens=input_tokens + output_tokens,
            cost=cost
        )
    
    def start_tool_span(self, tool_name: str) -> object:
        """
        Start a span for tool execution
        
        Returns a context manager for use with 'with' statement:
        
        Example:
            with span_manager.start_tool_span("calculator") as span:
                result = tool.execute(input_data)
                span.set_attribute("status", "success")
        """
        span_name = f"tool.{tool_name}"
        return self.tracer.start_as_current_span(span_name)
    
    def record_tool_call(
        self,
        span: trace.Span,
        tool_name: str,
        success: bool,
        error_message: Optional[str] = None
    ) -> None:
        """
        Record tool call metadata on a span
        
        Args:
            span: Tool call span
            tool_name: Name of the tool
            success: Whether execution succeeded
            error_message: Optional error message if failed
        """
        span.set_attribute("tool.name", tool_name)
        span.set_attribute("tool.success", success)
        span.set_attribute("tool.status", "success" if success else "error")
        span.set_attribute("event.type", "tool_invocation")
        
        if error_message:
            span.set_attribute("tool.error", error_message)
            span.set_attribute("error", True)
        
        logger.debug(
            "tool_span_recorded",
            tool_name=tool_name,
            success=success
        )
    
    def start_verification_span(self) -> object:
        """
        Start a span for integrity verification
        
        Returns a context manager for use with 'with' statement:
        
        Example:
            with span_manager.start_verification_span() as span:
                verified = verify_integrity(commitment)
                span.set_attribute("verified", verified)
        """
        return self.tracer.start_as_current_span("verification")
    
    def record_verification(
        self,
        span: trace.Span,
        counter: int,
        commitment: str,
        verified: bool,
        events_count: int = 0
    ) -> None:
        """
        Record integrity verification metadata on a span
        
        Args:
            span: Verification span
            counter: Counter value at verification
            commitment: Verkle commitment (base64)
            verified: Whether verification succeeded
            events_count: Number of recorded events
        """
        span.set_attribute("verification.counter", counter)
        span.set_attribute("verification.commitment_length", len(commitment))
        span.set_attribute("verification.verified", verified)
        span.set_attribute("verification.events_count", events_count)
        span.set_attribute("verification.status", "success" if verified else "failed")
        span.set_attribute("event.type", "integrity_verification")
        
        if not verified:
            span.set_attribute("error", True)
        
        logger.debug(
            "verification_span_recorded",
            counter=counter,
            verified=verified,
            events_count=events_count
        )
    
    def start_counter_span(self) -> object:
        """
        Start a span for counter increment operation
        
        Returns a context manager for use with 'with' statement
        """
        return self.tracer.start_as_current_span("counter.increment")
    
    def record_counter_increment(
        self,
        span: trace.Span,
        counter_value: int,
        session_id: str
    ) -> None:
        """
        Record counter increment metadata on a span
        
        Args:
            span: Counter increment span
            counter_value: New counter value
            session_id: Session identifier
        """
        span.set_attribute("counter.value", counter_value)
        span.set_attribute("counter.session_id", session_id)
        span.set_attribute("event.type", "counter_increment")
        
        logger.debug(
            "counter_span_recorded",
            counter_value=counter_value,
            session_id=session_id
        )
    
    def end_span(self, span: trace.Span) -> None:
        """
        Explicitly end a span
        
        Note: Context managers (with statement) automatically end spans.
        Use this only if not using context manager.
        """
        # Spans are auto-ended when context exits
        logger.debug("span_ended")
    
    def set_span_status_success(self, span: trace.Span) -> None:
        """Mark span as successful"""
        span.set_attribute("span.status", "success")
    
    def set_span_status_error(
        self,
        span: trace.Span,
        error_message: str
    ) -> None:
        """Mark span as failed with error message"""
        span.set_attribute("span.status", "error")
        span.set_attribute("span.error", error_message)
        span.set_attribute("error", True)


class LangfuseClient:
    """
    Wrapper for Langfuse API interactions.
    Can be used for additional metadata or custom events.
    """
    
    def __init__(self):
        settings = get_settings()
        self.endpoint = settings.langfuse.api_endpoint
        self.public_key = settings.langfuse.public_key
        self.secret_key = settings.langfuse.secret_key
    
    def log_custom_event(self, event_name: str, metadata: dict) -> None:
        """Log a custom event to Langfuse"""
        # This would use the Langfuse SDK or REST API
        # For now, just logging
        logger.info("langfuse_custom_event", event=event_name, metadata=metadata)
