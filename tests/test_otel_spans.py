"""
Unit tests for OTel span integration and SpanManager

Tests cover:
- Span creation and context management
- Attribute setting (LLM, tool, verification, counter)
- Span hierarchy management
- Error handling in spans
- Integration with integrity metadata

NOTE: These tests use mock spans since OTel is conditionally imported.
The SpanManager will work with real OTel spans in production.
"""

import pytest
from datetime import datetime

from src.observability import SpanManager


class MockSpan:
    """Mock span for testing without OTel imports"""
    
    def __init__(self, name: str):
        self.name = name
        self.attributes = {}
        self.ended = False
    
    def set_attribute(self, key: str, value) -> None:
        self.attributes[key] = value
    
    def end(self) -> None:
        self.ended = True
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end()


class MockTracer:
    """Mock tracer for testing"""
    
    def __init__(self):
        self.spans = []
        self.current_span = None
    
    def start_as_current_span(self, name: str):
        """Create and return a mock span context manager"""
        span = MockSpan(name)
        self.spans.append(span)
        self.current_span = span
        return span


class TestSpanManagerInitialization:
    """Test SpanManager initialization"""
    
    def test_span_manager_initialization(self):
        """Test SpanManager initializes with tracer"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        assert span_manager.tracer == mock_tracer
        assert span_manager.root_span is None
        assert span_manager.active_spans == {}
    
    def test_start_run_span(self):
        """Test starting agent run root span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = span_manager.start_run_span("session-001")
        
        assert span is not None
        assert span.attributes["session_id"] == "session-001"
        assert span.attributes["event.type"] == "agent_run_start"
        assert span.attributes["service.name"] == "verifiable-ai-agent"
        assert span_manager.root_span == span
        assert span_manager.active_spans["root"] == span


class TestIntegrityMetadata:
    """Test integrity metadata setting"""
    
    def test_set_integrity_metadata(self):
        """Test setting integrity metadata on span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("test")
        span_manager.set_integrity_metadata(
            span,
            session_id="session-001",
            counter=5,
            timestamp="2025-12-22T10:00:00Z"
        )
        
        assert span.attributes["integrity.session_id"] == "session-001"
        assert span.attributes["integrity.counter"] == 5
        assert span.attributes["integrity.timestamp"] == "2025-12-22T10:00:00Z"
    
    def test_set_verkle_root(self):
        """Test setting Verkle root commitment on span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("test")
        root_b64 = "A18sig5Q+rV8sf3y8/nnWKPgFfCZPFZLsRcW062Sii0="
        span_manager.set_verkle_root(span, root_b64)
        
        assert span.attributes["verkle.root_b64"] == root_b64
        assert span.attributes["verkle.root_length"] == len(root_b64)


class TestLLMSpans:
    """Test LLM call span management"""
    
    def test_start_llm_span(self):
        """Test starting LLM call span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span_context = span_manager.start_llm_span()
        
        assert span_context is not None
        assert callable(getattr(span_context, '__enter__', None))
    
    def test_record_llm_call(self):
        """Test recording LLM call metadata"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("llm_call")
        span_manager.record_llm_call(
            span,
            model="mistral-7b",
            input_tokens=100,
            output_tokens=50,
            cost=0.00050
        )
        
        assert span.attributes["llm.model"] == "mistral-7b"
        assert span.attributes["llm.tokens.input"] == 100
        assert span.attributes["llm.tokens.output"] == 50
        assert span.attributes["llm.tokens.total"] == 150
        assert span.attributes["llm.cost_usd"] == 0.00050
        assert span.attributes["event.type"] == "llm_invocation"
    
    def test_llm_span_with_context_manager(self):
        """Test using LLM span with context manager"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        with span_manager.start_llm_span() as span:
            span.set_attribute("model", "gpt-4")
            assert span.attributes["model"] == "gpt-4"
        
        # Span should be ended after context exit
        assert span.ended


class TestToolSpans:
    """Test tool call span management"""
    
    def test_start_tool_span(self):
        """Test starting tool call span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span_context = span_manager.start_tool_span("calculator")
        
        assert span_context is not None
        assert callable(getattr(span_context, '__enter__', None))
    
    def test_record_tool_call_success(self):
        """Test recording successful tool call"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("tool.calculator")
        span_manager.record_tool_call(
            span,
            tool_name="calculator",
            success=True
        )
        
        assert span.attributes["tool.name"] == "calculator"
        assert span.attributes["tool.success"] is True
        assert span.attributes["tool.status"] == "success"
        assert span.attributes["event.type"] == "tool_invocation"
        assert "tool.error" not in span.attributes
    
    def test_record_tool_call_failure(self):
        """Test recording failed tool call"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("tool.invalid")
        span_manager.record_tool_call(
            span,
            tool_name="invalid_tool",
            success=False,
            error_message="Tool not found"
        )
        
        assert span.attributes["tool.success"] is False
        assert span.attributes["tool.status"] == "error"
        assert span.attributes["tool.error"] == "Tool not found"
        assert span.attributes["error"] is True
    
    def test_tool_span_with_context_manager(self):
        """Test using tool span with context manager"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        with span_manager.start_tool_span("test_tool") as span:
            assert not span.ended
            span_manager.record_tool_call(span, "test_tool", True)
        
        # Span should be ended
        assert span.ended
        assert span.attributes["tool.success"] is True


class TestVerificationSpans:
    """Test integrity verification span management"""
    
    def test_start_verification_span(self):
        """Test starting verification span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span_context = span_manager.start_verification_span()
        
        assert span_context is not None
        assert callable(getattr(span_context, '__enter__', None))
    
    def test_record_verification_success(self):
        """Test recording successful verification"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("verification")
        span_manager.record_verification(
            span,
            counter=5,
            commitment="A18sig5Q+rV8sf3y8/nnWKPgFfCZPFZLsRcW062Sii0=",
            verified=True,
            events_count=6
        )
        
        assert span.attributes["verification.counter"] == 5
        assert span.attributes["verification.commitment_length"] == 44
        assert span.attributes["verification.verified"] is True
        assert span.attributes["verification.status"] == "success"
        assert span.attributes["verification.events_count"] == 6
        assert "error" not in span.attributes
    
    def test_record_verification_failure(self):
        """Test recording failed verification"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("verification")
        span_manager.record_verification(
            span,
            counter=3,
            commitment="BadCommitment",
            verified=False,
            events_count=2
        )
        
        assert span.attributes["verification.verified"] is False
        assert span.attributes["verification.status"] == "failed"
        assert span.attributes["error"] is True


class TestCounterSpans:
    """Test counter increment span management"""
    
    def test_start_counter_span(self):
        """Test starting counter increment span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span_context = span_manager.start_counter_span()
        
        assert span_context is not None
        assert callable(getattr(span_context, '__enter__', None))
    
    def test_record_counter_increment(self):
        """Test recording counter increment"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("counter.increment")
        span_manager.record_counter_increment(
            span,
            counter_value=5,
            session_id="session-001"
        )
        
        assert span.attributes["counter.value"] == 5
        assert span.attributes["counter.session_id"] == "session-001"
        assert span.attributes["event.type"] == "counter_increment"


class TestSpanStatusManagement:
    """Test span status management"""
    
    def test_set_span_status_success(self):
        """Test setting span status to success"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("test")
        span_manager.set_span_status_success(span)
        
        assert span.attributes["span.status"] == "success"
    
    def test_set_span_status_error(self):
        """Test setting span status to error"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span = MockSpan("test")
        span_manager.set_span_status_error(span, "Test error message")
        
        assert span.attributes["span.status"] == "error"
        assert span.attributes["span.error"] == "Test error message"
        assert span.attributes["error"] is True


class TestIntegrationScenario:
    """Integration test for complete OTel span workflow"""
    
    def test_complete_agent_run_spans(self):
        """Test complete agent run with all span types"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        # Root span
        root_span = span_manager.start_run_span("session-001")
        span_manager.set_integrity_metadata(
            root_span,
            session_id="session-001",
            counter=0,
            timestamp="2025-12-22T10:00:00Z"
        )
        
        # Simulate LLM call
        with span_manager.start_llm_span() as llm_span:
            span_manager.record_llm_call(
                llm_span,
                model="mistral-7b",
                input_tokens=100,
                output_tokens=50,
                cost=0.00050
            )
        
        # Simulate tool call
        with span_manager.start_tool_span("calculator") as tool_span:
            span_manager.record_tool_call(
                tool_span,
                tool_name="calculator",
                success=True
            )
        
        # Simulate counter increment
        with span_manager.start_counter_span() as counter_span:
            span_manager.record_counter_increment(
                counter_span,
                counter_value=2,
                session_id="session-001"
            )
        
        # Simulate verification
        with span_manager.start_verification_span() as verify_span:
            span_manager.record_verification(
                verify_span,
                counter=2,
                commitment="A18sig5Q+rV8sf3y8/nnWKPgFfCZPFZLsRcW062Sii0=",
                verified=True,
                events_count=3
            )
        
        # End root span
        root_span.end()
        
        # Verify root span has all metadata
        assert root_span.attributes["session_id"] == "session-001"
        assert root_span.attributes["integrity.counter"] == 0
        
        # Verify all spans are created
        assert len(mock_tracer.spans) >= 4
        
        # All spans should be ended
        for span in mock_tracer.spans:
            assert span.ended


class TestContextManagerBehavior:
    """Test context manager behavior for automatic span ending"""
    
    def test_context_manager_ends_span(self):
        """Test that context manager properly ends span"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span_returned = None
        with span_manager.start_llm_span() as span:
            span_returned = span
            assert not span.ended
        
        # After context exit, span should be ended
        assert span_returned.ended
    
    def test_context_manager_with_exception(self):
        """Test context manager properly ends span even with exception"""
        mock_tracer = MockTracer()
        span_manager = SpanManager(mock_tracer)
        
        span_returned = None
        try:
            with span_manager.start_tool_span("failing_tool") as span:
                span_returned = span
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # Span should still be ended despite exception
        assert span_returned.ended
