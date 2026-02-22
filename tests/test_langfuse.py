"""
Unit tests for Langfuse client integration

Tests the new Langfuse client API:
- Session-based client initialization
- Trace creation for user interactions
- Generation recording for LLM calls
- Span recording for tool calls
- Event recording for general events
- Score recording for metrics
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import requests

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
        assert client.current_trace_id is None
        assert client.api_endpoint is not None
    
    def test_client_has_settings_reference(self):
        """Test client has access to Langfuse settings"""
        client = LangfuseClient("test-session")
        
        assert client.settings is not None
        assert hasattr(client, 'api_endpoint')
        assert client.api_endpoint.startswith("http")
    
    def test_client_sets_auth_when_credentials_available(self):
        """Test client sets auth when credentials are configured"""
        client = LangfuseClient("test-session")
        
        # Auth will be set if credentials are available in settings
        # The test just checks the attribute exists
        assert hasattr(client, '_auth')


class TestTraceCreation:
    """Test trace creation"""
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_create_trace_returns_trace_id(self, mock_send):
        """Test creating a trace returns a UUID"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        
        trace_id = client.create_trace("user_interaction")
        
        assert trace_id is not None
        assert len(trace_id) == 36  # UUID format
        assert client.current_trace_id == trace_id
        # create_trace no longer sends immediately - data is stored for later flush
        assert mock_send.call_count == 0
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_create_trace_with_metadata(self, mock_send):
        """Test creating trace with metadata stores it locally"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        
        metadata = {"key": "value", "counter": 1}
        trace_id = client.create_trace("agent_run", metadata=metadata)
        
        # Data is stored locally, not sent yet
        assert client._current_trace_data["metadata"] == metadata
        assert mock_send.call_count == 0
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_create_trace_with_user_id(self, mock_send):
        """Test creating trace with user_id stores it locally"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        
        trace_id = client.create_trace("agent_run", user_id="user-123")
        
        # Data is stored locally, not sent yet
        assert client._current_trace_data["userId"] == "user-123"
        assert mock_send.call_count == 0
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_create_trace_with_tags(self, mock_send):
        """Test creating trace with tags stores them locally"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        
        tags = ["production", "verified"]
        trace_id = client.create_trace("agent_run", tags=tags)
        
        # Data is stored locally, not sent yet
        assert client._current_trace_data["tags"] == tags
        assert mock_send.call_count == 0
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_create_trace_sends_session_id(self, mock_send):
        """Test trace includes session_id for grouping"""
        mock_send.return_value = True
        client = LangfuseClient("my-session-123")
        
        trace_id = client.create_trace("agent_run")
        
        # Data is stored locally with session_id
        assert client._current_trace_data["sessionId"] == "my-session-123"
        assert mock_send.call_count == 0


class TestGenerationRecording:
    """Test generation recording for LLM calls"""
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_record_generation(self, mock_send):
        """Test recording an LLM generation"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        
        gen_id = client.record_generation(
            name="llm_call",
            model="gpt-4",
            prompt="Hello",
            response="Hi there!"
        )
        
        assert gen_id is not None
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["type"] == "generation-create"
        assert call_args[0]["body"]["model"] == "gpt-4"
        assert call_args[0]["body"]["input"] == "Hello"
        assert call_args[0]["body"]["output"] == "Hi there!"
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_record_generation_with_tokens(self, mock_send):
        """Test recording generation with token counts"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        
        gen_id = client.record_generation(
            name="llm_call",
            model="gpt-4",
            prompt="Hello",
            response="Hi!",
            input_tokens=5,
            output_tokens=3
        )
        
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["body"]["usageDetails"]["input"] == 5
        assert call_args[0]["body"]["usageDetails"]["output"] == 3
        assert call_args[0]["body"]["usageDetails"]["total"] == 8
    
    def test_record_generation_without_trace_returns_empty(self):
        """Test recording generation without trace returns empty string"""
        client = LangfuseClient("test-session")
        # No trace created
        
        gen_id = client.record_generation(
            name="llm_call",
            model="gpt-4",
            prompt="Hello",
            response="Hi!"
        )
        
        assert gen_id == ""


class TestSpanRecording:
    """Test span recording for tool calls"""
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_record_span(self, mock_send):
        """Test recording a span"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        
        span_id = client.record_span(
            name="tool_calculator",
            input_data={"expression": "2+2"},
            output_data={"result": 4}
        )
        
        assert span_id is not None
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["type"] == "span-create"
        assert call_args[0]["body"]["name"] == "tool_calculator"
    
    def test_record_span_without_trace_returns_empty(self):
        """Test recording span without trace returns empty string"""
        client = LangfuseClient("test-session")
        
        span_id = client.record_span(
            name="tool_calculator",
            input_data={"expression": "2+2"}
        )
        
        assert span_id == ""


class TestEventRecording:
    """Test event recording"""
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_record_event(self, mock_send):
        """Test recording a simple event"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        
        event_id = client.record_event(
            name="user_prompt",
            data={"prompt": "Hello world"}
        )
        
        assert event_id is not None
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["type"] == "event-create"
        assert call_args[0]["body"]["name"] == "user_prompt"
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_record_event_with_level(self, mock_send):
        """Test recording event with level"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        
        event_id = client.record_event(
            name="error",
            data={"message": "Something failed"},
            level="ERROR"
        )
        
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["body"]["level"] == "ERROR"


class TestTraceUpdate:
    """Test trace update functionality"""
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_update_trace_with_output(self, mock_send):
        """Test updating trace with final output"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        client._current_trace_data = {"name": "test", "sessionId": "test-session"}
        
        # Without flush, data is accumulated but not sent
        client.update_trace(output="Final result: success")
        assert client._current_trace_data["output"] == "Final result: success"
        assert mock_send.call_count == 0
        
        # With flush, data is sent
        client.update_trace(flush=True)
        assert mock_send.call_count == 1
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["body"]["output"] == "Final result: success"
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_update_trace_with_metadata(self, mock_send):
        """Test updating trace with metadata"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        client._current_trace_data = {"name": "test", "sessionId": "test-session", "metadata": {}}
        
        # Accumulate metadata
        client.update_trace(metadata={"verified": True})
        assert client._current_trace_data["metadata"] == {"verified": True}
        
        # Flush sends it
        client.update_trace(flush=True)
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["body"]["metadata"] == {"verified": True}
    
    def test_update_trace_without_trace_does_nothing(self):
        """Test updating without trace does nothing"""
        client = LangfuseClient("test-session")
        # No trace, should not raise
        client.update_trace(output="test")


class TestScoreRecording:
    """Test score recording"""
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_add_score(self, mock_send):
        """Test adding a score to trace"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        
        score_id = client.add_score(
            name="verification_status",
            value=1.0
        )
        
        assert score_id is not None
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["type"] == "score-create"
        assert call_args[0]["body"]["name"] == "verification_status"
        assert call_args[0]["body"]["value"] == 1.0
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_add_score_with_comment(self, mock_send):
        """Test adding score with comment"""
        mock_send.return_value = True
        client = LangfuseClient("test-session")
        client.current_trace_id = "trace-123"
        
        score_id = client.add_score(
            name="quality",
            value=0.8,
            comment="Good response"
        )
        
        call_args = mock_send.call_args[0][0]
        assert call_args[0]["body"]["comment"] == "Good response"


class TestBatchSending:
    """Test batch sending to Langfuse API"""
    
    @patch('requests.post')
    def test_send_batch_success(self, mock_post):
        """Test successful batch send"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        client = LangfuseClient("test-session")
        client._auth = MagicMock()  # Mock auth
        
        result = client._send_batch([{"type": "test"}])
        
        assert result is True
    
    @patch('requests.post')
    def test_send_batch_failure(self, mock_post):
        """Test batch send failure"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_post.return_value = mock_response
        
        client = LangfuseClient("test-session")
        client._auth = MagicMock()
        
        result = client._send_batch([{"type": "test"}])
        
        assert result is False
    
    def test_send_batch_without_auth_returns_false(self):
        """Test batch send without auth returns false"""
        client = LangfuseClient("test-session")
        client._auth = None
        
        result = client._send_batch([{"type": "test"}])
        
        assert result is False


class TestFactoryFunction:
    """Test the create_langfuse_client factory function"""
    
    def test_create_with_session_id(self):
        """Test creating client with session_id"""
        client = create_langfuse_client("custom-session")
        
        assert client.session_id == "custom-session"
    
    def test_create_without_session_id_generates_uuid(self):
        """Test creating client without session_id generates UUID"""
        client = create_langfuse_client()
        
        assert client.session_id is not None
        assert len(client.session_id) == 36  # UUID format


class TestIntegrationScenario:
    """Test a typical integration scenario"""
    
    @patch.object(LangfuseClient, '_send_batch')
    def test_complete_agent_workflow(self, mock_send):
        """Test complete agent workflow: trace -> generation -> score -> flush"""
        mock_send.return_value = True
        
        # Create client with session
        client = LangfuseClient("integration-test-001")
        
        # Create trace for user interaction (does NOT send - stores locally)
        trace_id = client.create_trace(
            name="agent_run",
            metadata={"protocol": "MCP-2024-11"}
        )
        assert trace_id is not None
        assert mock_send.call_count == 0  # No send yet
        
        # Record LLM generation (sends immediately)
        gen_id = client.record_generation(
            name="explain_verkle",
            model="gpt-4",
            prompt="Explain Verkle trees",
            response="Verkle trees are..."
        )
        assert gen_id is not None
        assert mock_send.call_count == 1  # generation sent
        
        # Record verification event (sends immediately)
        event_id = client.record_event(
            name="verification_complete",
            data={"verified": True, "root": "abc123"}
        )
        assert event_id is not None
        assert mock_send.call_count == 2  # event sent
        
        # Add verification score (sends immediately)
        score_id = client.add_score(
            name="verification_status",
            value=1.0,
            comment="Cryptographically verified"
        )
        assert score_id is not None
        assert mock_send.call_count == 3  # score sent
        
        # Update trace with final output (accumulates, does not send)
        client.update_trace(
            output="Agent run complete",
            tags=["verified", "production"]
        )
        assert mock_send.call_count == 3  # No send yet
        
        # Flush to send the trace with all accumulated data
        client.update_trace(flush=True)
        assert mock_send.call_count == 4  # trace sent
