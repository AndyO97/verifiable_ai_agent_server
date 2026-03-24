"""
Tests for integrity middleware
"""

import pytest
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_ntp_sync_median_offset_within_threshold(self, session_id):
        """NTP verification should accept low drift and cache median offset."""
        with patch.object(IntegrityMiddleware, "_initialize_langfuse", lambda self: None):
            middleware = IntegrityMiddleware(session_id)

        middleware._ntp_last_check = 0

        # Simulate three NTP servers with offsets: +100ms, +200ms, +300ms.
        responses = [
            SimpleNamespace(tx_time=1000.100),
            SimpleNamespace(tx_time=1000.200),
            SimpleNamespace(tx_time=1000.300),
        ]

        with patch("src.integrity.time.time", return_value=1000.0):
            with patch("src.integrity.ntplib.NTPClient.request", side_effect=responses):
                middleware._verify_ntp_sync()

        assert middleware._ntp_sync_verified is True
        # Median of [100, 200, 300]
        assert middleware._ntp_offset_ms == 200

    def test_ntp_sync_critical_drift_marks_unverified(self, session_id):
        """Critical drift should mark clock sync as unverified."""
        with patch.object(IntegrityMiddleware, "_initialize_langfuse", lambda self: None):
            middleware = IntegrityMiddleware(session_id)

        middleware._ntp_last_check = 0

        # 120s drift is above 60s error threshold.
        critical = SimpleNamespace(tx_time=1120.0)

        with patch("src.integrity.time.time", return_value=1000.0):
            with patch("src.integrity.ntplib.NTPClient.request", side_effect=[critical, critical, critical]):
                middleware._verify_ntp_sync()

        assert middleware._ntp_sync_verified is False
        assert middleware._ntp_offset_ms == 120000

    def test_ntp_sync_all_servers_unreachable(self, session_id):
        """If all NTP servers fail, verification should fail closed."""
        with patch.object(IntegrityMiddleware, "_initialize_langfuse", lambda self: None):
            middleware = IntegrityMiddleware(session_id)

        middleware._ntp_last_check = 0
        middleware._ntp_offset_ms = None

        with patch("src.integrity.ntplib.NTPClient.request", side_effect=OSError("network unreachable")):
            middleware._verify_ntp_sync()

        assert middleware._ntp_sync_verified is False
        assert middleware._ntp_offset_ms is None
