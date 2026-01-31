"""
Unit tests for Langfuse client integration

Tests cover:
- Trace creation and event recording
- LLM call tracking with cost calculation
- Tool call recording
- Integrity check metadata
- Session summary generation
- Factory function
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.observability.langfuse_client import (
    LangfuseClient,
    create_langfuse_client,
)


class TestLangfuseClientInitialization:
    """Test LangfuseClient initialization"""
    
    def test_client_initialization_with_session_id(self):
        """Test creating client with explicit session_id"""
        session_id = "test-session-001"
        client = LangfuseClient(session_id)
        
        assert client.session_id == session_id
        assert client.traces == []
        assert client.api_endpoint is not None
        assert client._initialized is False
    
    def test_client_has_settings_reference(self):
        """Test client has access to Langfuse settings"""
        client = LangfuseClient("test-session")
        
        assert client.settings is not None
        assert hasattr(client, 'api_endpoint')
        # Endpoint should be http://localhost:3000 by default
        assert client.api_endpoint.startswith("http")


class TestTraceCreation:
    """Test trace creation and management"""
    
    def test_create_simple_trace(self):
        """Test creating a simple trace"""
        client = LangfuseClient("test-session")
        
        trace_id = client.create_trace("agent_run")
        
        assert trace_id is not None
        assert len(client.traces) == 1
        assert client.traces[0]["name"] == "agent_run"
        assert client.traces[0]["session_id"] == "test-session"
    
    def test_create_trace_with_metadata(self):
        """Test creating trace with metadata"""
        client = LangfuseClient("test-session")
        metadata = {
            "counter": 0,
            "timestamp": "2025-12-22T10:00:00Z",
        }
        
        trace_id = client.create_trace(
            "agent_run",
            metadata=metadata
        )
        
        trace = client.traces[0]
        assert trace["metadata"] == metadata
    
    def test_create_trace_with_user_id(self):
        """Test creating trace with user_id"""
        client = LangfuseClient("test-session")
        
        trace_id = client.create_trace(
            "agent_run",
            user_id="user-123"
        )
        
        trace = client.traces[0]
        assert trace["user_id"] == "user-123"
    
    def test_trace_has_cost_tracking(self):
        """Test trace includes cost tracking structure"""
        client = LangfuseClient("test-session")
        
        trace_id = client.create_trace("agent_run")
        trace = client.traces[0]
        
        assert "cost" in trace
        assert trace["cost"]["input_tokens"] == 0
        assert trace["cost"]["output_tokens"] == 0
        assert trace["cost"]["total_cost"] == 0.0
        assert trace["cost"]["model"] == ""
    
    def test_multiple_traces_in_session(self):
        """Test creating multiple traces in same session"""
        client = LangfuseClient("test-session")
        
        trace_id_1 = client.create_trace("agent_run")
        trace_id_2 = client.create_trace("verification")
        
        assert len(client.traces) == 2
        assert trace_id_1 != trace_id_2
        assert client.traces[0]["name"] == "agent_run"
        assert client.traces[1]["name"] == "verification"


class TestEventRecording:
    """Test event recording within traces"""
    
    def test_add_event_to_trace(self):
        """Test adding event to a trace"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.add_event_to_trace(
            trace_id,
            "step_completed",
            {"step": "initialization"}
        )
        
        trace = client.traces[0]
        assert len(trace["events"]) == 1
        assert trace["events"][0]["name"] == "step_completed"
        assert trace["events"][0]["data"]["step"] == "initialization"
    
    def test_add_multiple_events(self):
        """Test adding multiple events to trace"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        for i in range(3):
            client.add_event_to_trace(
                trace_id,
                f"event_{i}",
                {"index": i}
            )
        
        trace = client.traces[0]
        assert len(trace["events"]) == 3
    
    def test_event_has_timestamp(self):
        """Test event includes timestamp"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        before = datetime.now(timezone.utc).isoformat()
        client.add_event_to_trace(trace_id, "test", {})
        after = datetime.now(timezone.utc).isoformat()
        
        event = client.traces[0]["events"][0]
        assert "timestamp" in event
        assert before <= event["timestamp"] <= after
    
    def test_event_with_different_levels(self):
        """Test events with different log levels"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.add_event_to_trace(trace_id, "info_event", {}, level="info")
        client.add_event_to_trace(trace_id, "warn_event", {}, level="warning")
        client.add_event_to_trace(trace_id, "error_event", {}, level="error")
        
        trace = client.traces[0]
        assert trace["events"][0]["level"] == "info"
        assert trace["events"][1]["level"] == "warning"
        assert trace["events"][2]["level"] == "error"
    
    def test_add_event_to_nonexistent_trace(self):
        """Test adding event to non-existent trace (should not crash)"""
        client = LangfuseClient("test-session")
        
        # Should not raise, just log warning
        client.add_event_to_trace("nonexistent-trace", "event", {})
        
        # No traces created
        assert len(client.traces) == 0


class TestLLMCallTracking:
    """Test LLM call recording with cost tracking"""
    
    def test_record_llm_call(self):
        """Test recording LLM API call"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_llm_call(
            trace_id,
            model="mistral-7b",
            prompt="What is 2 + 2?",
            response="2 + 2 = 4",
            input_tokens=15,
            output_tokens=8,
            cost=0.00015
        )
        
        trace = client.traces[0]
        assert len(trace["events"]) == 1
        assert trace["events"][0]["name"] == "llm_call"
    
    def test_llm_call_updates_trace_cost(self):
        """Test LLM call updates trace cost totals"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_llm_call(
            trace_id,
            model="gpt-4",
            prompt="test",
            response="test",
            input_tokens=100,
            output_tokens=50,
            cost=0.005
        )
        
        trace = client.traces[0]
        assert trace["cost"]["input_tokens"] == 100
        assert trace["cost"]["output_tokens"] == 50
        assert trace["cost"]["total_cost"] == 0.005
        assert trace["cost"]["model"] == "gpt-4"
    
    def test_multiple_llm_calls_accumulate_cost(self):
        """Test multiple LLM calls accumulate costs"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        # First call
        client.record_llm_call(
            trace_id, "mistral", "q1", "a1",
            input_tokens=10, output_tokens=5, cost=0.001
        )
        
        # Second call
        client.record_llm_call(
            trace_id, "mistral", "q2", "a2",
            input_tokens=15, output_tokens=8, cost=0.002
        )
        
        trace = client.traces[0]
        assert trace["cost"]["input_tokens"] == 25
        assert trace["cost"]["output_tokens"] == 13
        assert abs(trace["cost"]["total_cost"] - 0.003) < 0.0001
        assert len(trace["events"]) == 2
    
    def test_llm_call_event_data_structure(self):
        """Test LLM call event has correct structure"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_llm_call(
            trace_id,
            model="mistral",
            prompt="What is AI?",
            response="AI is...",
            input_tokens=4,
            output_tokens=10,
            cost=0.00001
        )
        
        event = client.traces[0]["events"][0]
        assert event["data"]["model"] == "mistral"
        assert event["data"]["input_tokens"] == 4
        assert event["data"]["output_tokens"] == 10
        assert event["data"]["cost"] == 0.00001
        # Long prompts should be truncated
        assert "prompt_preview" in event["data"]
        assert "response_preview" in event["data"]


class TestToolCallTracking:
    """Test tool invocation recording"""
    
    def test_record_tool_call(self):
        """Test recording tool invocation"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_tool_call(
            trace_id,
            tool_name="calculator",
            input_data={"operation": "add", "a": 2, "b": 2},
            output_data={"result": 4},
            duration_ms=45.2,
            success=True
        )
        
        event = client.traces[0]["events"][0]
        assert event["name"] == "tool_call"
        assert event["data"]["tool_name"] == "calculator"
        assert event["data"]["success"] is True
    
    def test_tool_call_with_failure(self):
        """Test recording failed tool call"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_tool_call(
            trace_id,
            tool_name="invalid_tool",
            input_data={"param": "value"},
            output_data={"error": "Tool not found"},
            duration_ms=10.5,
            success=False
        )
        
        event = client.traces[0]["events"][0]
        assert event["data"]["success"] is False
        assert "error" in event["data"]["output"]
    
    def test_tool_call_duration_tracking(self):
        """Test tool call duration is recorded"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_tool_call(
            trace_id,
            tool_name="slow_tool",
            input_data={},
            output_data={},
            duration_ms=1234.5
        )
        
        event = client.traces[0]["events"][0]
        assert event["data"]["duration_ms"] == 1234.5


class TestIntegrityCheckRecording:
    """Test integrity verification metadata recording"""
    
    def test_record_integrity_check(self):
        """Test recording integrity check"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_integrity_check(
            trace_id,
            counter=5,
            commitment="A18sig5Q+rV8sf3y8/nnWKPgFfCZPFZLsRcW062Sii0=",
            events_count=6,
            verified=True
        )
        
        event = client.traces[0]["events"][0]
        assert event["name"] == "integrity_check"
        assert event["data"]["counter"] == 5
        assert event["data"]["events_count"] == 6
        assert event["data"]["verified"] is True
    
    def test_integrity_check_failed_verification(self):
        """Test recording failed integrity verification"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        client.record_integrity_check(
            trace_id,
            counter=3,
            commitment="BadCommitment",
            events_count=2,
            verified=False
        )
        
        event = client.traces[0]["events"][0]
        assert event["data"]["verified"] is False
    
    def test_commitment_truncation(self):
        """Test long commitments are truncated in event data"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        long_commitment = "A18sig5Q+rV8sf3y8/nnWKPgFfCZPFZLsRcW062Sii0=" * 10
        
        client.record_integrity_check(
            trace_id,
            counter=1,
            commitment=long_commitment,
            events_count=1,
            verified=True
        )
        
        event = client.traces[0]["events"][0]
        commitment_preview = event["data"]["commitment"]
        # Should be truncated with "..."
        assert len(commitment_preview) < len(long_commitment)
        assert commitment_preview.endswith("...")


class TestTraceFinalization:
    """Test trace finalization"""
    
    def test_finalize_trace(self):
        """Test finalizing a trace"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        # Add some events
        client.add_event_to_trace(trace_id, "event1", {})
        client.add_event_to_trace(trace_id, "event2", {})
        
        result = client.finalize_trace(trace_id)
        
        assert result["finalized"] is True
        assert "finalized_at" in result
        assert len(result["events"]) == 2
    
    def test_finalize_nonexistent_trace(self):
        """Test finalizing non-existent trace"""
        client = LangfuseClient("test-session")
        
        result = client.finalize_trace("nonexistent-trace")
        
        # Should return empty dict without crashing
        assert result == {}
    
    def test_finalized_at_timestamp(self):
        """Test finalized_at timestamp is set"""
        client = LangfuseClient("test-session")
        trace_id = client.create_trace("agent_run")
        
        before = datetime.now(timezone.utc).isoformat()
        client.finalize_trace(trace_id)
        after = datetime.now(timezone.utc).isoformat()
        
        trace = client.traces[0]
        assert before <= trace["finalized_at"] <= after


class TestSessionSummary:
    """Test session summary generation"""
    
    def test_empty_session_summary(self):
        """Test summary for session with no traces"""
        client = LangfuseClient("test-session")
        
        summary = client.get_session_summary()
        
        assert summary["session_id"] == "test-session"
        assert summary["total_traces"] == 0
        assert summary["finalized_traces"] == 0
        assert summary["total_events"] == 0
        assert summary["total_cost"] == 0.0
    
    def test_session_summary_with_traces(self):
        """Test summary with multiple traces"""
        client = LangfuseClient("test-session")
        
        # Create traces with events and costs
        trace_id_1 = client.create_trace("agent_run")
        client.add_event_to_trace(trace_id_1, "event1", {})
        client.record_llm_call(
            trace_id_1, "mistral", "q", "a",
            input_tokens=10, output_tokens=5, cost=0.001
        )
        
        trace_id_2 = client.create_trace("verification")
        client.add_event_to_trace(trace_id_2, "verify_event", {})
        client.record_llm_call(
            trace_id_2, "mistral", "q", "a",
            input_tokens=5, output_tokens=3, cost=0.0005
        )
        
        # Finalize one
        client.finalize_trace(trace_id_1)
        
        summary = client.get_session_summary()
        
        assert summary["total_traces"] == 2
        assert summary["finalized_traces"] == 1
        assert summary["total_events"] == 4  # 2 events per trace
        assert abs(summary["total_cost"] - 0.0015) < 0.00001
    
    def test_summary_includes_endpoint(self):
        """Test summary includes Langfuse endpoint"""
        client = LangfuseClient("test-session")
        
        summary = client.get_session_summary()
        
        assert "endpoint" in summary
        assert summary["endpoint"] == client.api_endpoint


class TestFactoryFunction:
    """Test factory function for creating clients"""
    
    def test_create_client_with_explicit_session_id(self):
        """Test factory function with explicit session ID"""
        session_id = "factory-test-001"
        client = create_langfuse_client(session_id)
        
        assert isinstance(client, LangfuseClient)
        assert client.session_id == session_id
    
    def test_create_client_generates_session_id(self):
        """Test factory function generates session ID if not provided"""
        client = create_langfuse_client()
        
        assert isinstance(client, LangfuseClient)
        assert client.session_id is not None
        assert len(client.session_id) > 0
    
    def test_multiple_clients_have_different_ids(self):
        """Test multiple clients created with factory have different IDs"""
        client1 = create_langfuse_client()
        client2 = create_langfuse_client()
        
        assert client1.session_id != client2.session_id


class TestIntegrationScenario:
    """Integration test for complete workflow"""
    
    def test_complete_agent_workflow(self):
        """Test complete agent workflow with all event types"""
        # Setup
        session_id = "integration-test-001"
        client = create_langfuse_client(session_id)
        
        # Create trace
        trace_id = client.create_trace(
            "agent_run",
            metadata={
                "session_id": session_id,
                "counter": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
        
        # Record LLM call
        client.record_llm_call(
            trace_id,
            model="mistral-7b",
            prompt="What is 2 + 2?",
            response="2 + 2 = 4",
            input_tokens=15,
            output_tokens=8,
            cost=0.00015
        )
        
        # Record tool call
        client.record_tool_call(
            trace_id,
            tool_name="calculator",
            input_data={"operation": "add", "a": 2, "b": 2},
            output_data={"result": 4},
            duration_ms=45.2,
            success=True
        )
        
        # Record integrity check
        client.record_integrity_check(
            trace_id,
            counter=2,
            commitment="A18sig5Q+rV8sf3y8/nnWKPgFfCZPFZLsRcW062Sii0=",
            events_count=2,
            verified=True
        )
        
        # Finalize
        client.finalize_trace(trace_id)
        
        # Verify summary
        summary = client.get_session_summary()
        
        assert summary["session_id"] == session_id
        assert summary["total_traces"] == 1
        assert summary["finalized_traces"] == 1
        assert summary["total_events"] == 3  # llm_call, tool_call, integrity_check
        assert summary["total_cost"] > 0
