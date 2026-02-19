"""
Tests for integrity middleware
"""

import pytest

from src.integrity import IntegrityMiddleware


class TestIntegrityMiddleware:
    """Tests for the integrity middleware"""
    
    def test_middleware_creation(self, session_id):
        """Test middleware initialization"""
        middleware = IntegrityMiddleware(session_id)
        
        assert middleware.session_id == session_id
        assert middleware.counter == 0
        assert not middleware.finalized
    
    def test_record_prompt(self, session_id):
        """Test recording a prompt"""
        middleware = IntegrityMiddleware(session_id)
        
        ret_session = middleware.record_prompt("Test prompt")
        
        assert ret_session == session_id
        assert len(middleware.accumulator.events) == 1
        assert middleware.counter == 1
    
    def test_record_model_output(self, session_id):
        """Test recording model output"""
        middleware = IntegrityMiddleware(session_id)
        
        middleware.record_prompt("Test")
        middleware.record_model_output("Response")
        
        assert len(middleware.accumulator.events) == 2
        assert middleware.counter == 2
    
    def test_record_tool_invocations(self, session_id):
        """Test recording tool input/output"""
        middleware = IntegrityMiddleware(session_id)
        
        middleware.record_prompt("Use the calculator")
        middleware.record_tool_input("calculator", {"operation": "add", "a": 1, "b": 2})
        middleware.record_tool_output("calculator", 3)
        middleware.record_model_output("The result is 3")
        
        assert len(middleware.accumulator.events) == 4
        assert middleware.counter == 4
    
    def test_finalization(self, session_id):
        """Test run finalization"""
        middleware = IntegrityMiddleware(session_id)
        
        middleware.record_prompt("Test")
        middleware.record_model_output("Done")
        
        root_b64, canonical_log = middleware.finalize()
        
        assert isinstance(root_b64, str)
        assert isinstance(canonical_log, bytes)
        assert len(middleware.accumulator.events) == 2
        assert middleware.finalized
    
    def test_no_events_after_finalization(self, session_id):
        """Test that events can't be added after finalization"""
        middleware = IntegrityMiddleware(session_id)
        
        middleware.record_prompt("Test")
        middleware.finalize()
        
        with pytest.raises(RuntimeError, match="after finalization"):
            middleware.record_model_output("Should fail")
