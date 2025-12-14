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
    """Manages span creation and attribute setting for integrity metadata"""
    
    def __init__(self, tracer: trace.Tracer):
        self.tracer = tracer
    
    def start_run_span(self, session_id: str) -> trace.Span:
        """Start the root span for an agent run"""
        with self.tracer.start_as_current_span("agent_run") as span:
            span.set_attribute("session_id", session_id)
            span.set_attribute("event.type", "agent_run_start")
            return span
    
    def set_integrity_metadata(
        self,
        span: trace.Span,
        session_id: str,
        counter: int,
        timestamp: str
    ) -> None:
        """Set integrity-related metadata on a span"""
        span.set_attribute("integrity.session_id", session_id)
        span.set_attribute("integrity.counter", counter)
        span.set_attribute("integrity.timestamp", timestamp)
    
    def set_verkle_root(self, span: trace.Span, root_b64: str) -> None:
        """Set Verkle root commitment on the root span (Base64-encoded)"""
        span.set_attribute("verkle.root_b64", root_b64)
        logger.info("verkle_root_set_on_span", root=root_b64)
    
    def start_tool_span(self, parent_span: trace.Span, tool_name: str) -> trace.Span:
        """Start a span for tool execution"""
        with self.tracer.start_as_current_span(f"tool.{tool_name}") as span:
            span.set_attribute("tool.name", tool_name)
            return span
    
    def start_model_span(self, parent_span: trace.Span) -> trace.Span:
        """Start a span for model invocation"""
        with self.tracer.start_as_current_span("model.invoke") as span:
            span.set_attribute("event.type", "model_invocation")
            return span


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
