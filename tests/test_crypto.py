"""
Tests for canonical encoding and Verkle tree
"""

import pytest

from src.crypto.encoding import CanonicalEncoder, canonicalize_json
from src.crypto.verkle import VerkleAccumulator


class TestCanonicalEncoding:
    """Tests for RFC 8785 canonical encoding"""
    
    def test_canonical_json_simple(self):
        """Test basic canonical JSON encoding"""
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonicalize_json(obj)
        
        # Keys should be sorted
        assert result == '{"a":2,"m":3,"z":1}'
    
    def test_canonical_json_unicode_normalization(self):
        """Test Unicode NFC normalization"""
        # é can be represented two ways
        obj = {"key": "café"}  # Precomposed
        result = canonicalize_json(obj)
        
        # Should be deterministic
        obj2 = {"key": "café"}  # Decomposed (different bytes, same visual)
        result2 = canonicalize_json(obj2)
        
        # Both should result in the same output
        assert result == result2
    
    def test_canonical_json_rejects_non_finite(self):
        """Test that non-finite floats are rejected"""
        with pytest.raises(ValueError):
            canonicalize_json({"value": float("nan")})
        
        with pytest.raises(ValueError):
            canonicalize_json({"value": float("inf")})
        
        with pytest.raises(ValueError):
            canonicalize_json({"value": float("-inf")})
    
    def test_canonical_encoder_encode_event(self):
        """Test canonical encoding of a single event"""
        event = {
            "session_id": "test-123",
            "counter": 0,
            "timestamp": "2025-12-08T10:00:00Z",
            "event_type": "prompt",
            "payload": {"prompt": "Hello"}
        }
        
        encoded = CanonicalEncoder.encode_event(event)
        assert isinstance(encoded, bytes)
        assert b"session_id" in encoded


class TestVerkleAccumulator:
    """Tests for Verkle tree accumulation"""
    
    def test_verkle_single_event(self, session_id):
        """Test accumulating a single event"""
        acc = VerkleAccumulator(session_id)
        
        event = {
            "session_id": session_id,
            "counter": 0,
            "timestamp": "2025-12-08T10:00:00Z",
            "event_type": "prompt",
            "payload": {"prompt": "Test"}
        }
        
        acc.add_event(event)
        assert len(acc.events) == 1
        
        root = acc.finalize()
        assert root is not None
        assert len(root) == 32  # SHA-256 output
    
    def test_verkle_multiple_events(self, session_id):
        """Test accumulating multiple events"""
        acc = VerkleAccumulator(session_id)
        
        for i in range(3):
            event = {
                "session_id": session_id,
                "counter": i,
                "timestamp": f"2025-12-08T10:00:{i}0Z",
                "event_type": "test",
                "payload": {"index": i}
            }
            acc.add_event(event)
        
        assert len(acc.events) == 3
        root = acc.finalize()
        assert root is not None
    
    def test_verkle_root_b64(self, session_id):
        """Test Verkle root as Base64"""
        acc = VerkleAccumulator(session_id)
        
        event = {
            "session_id": session_id,
            "counter": 0,
            "timestamp": "2025-12-08T10:00:00Z",
            "event_type": "test",
            "payload": {}
        }
        
        acc.add_event(event)
        acc.finalize()
        
        root_b64 = acc.get_root_b64()
        assert isinstance(root_b64, str)
        
        # Should be valid Base64
        import base64
        decoded = base64.b64decode(root_b64)
        assert len(decoded) == 32
    
    def test_verkle_counter_validation(self, session_id):
        """Test that counter mismatches are caught"""
        acc = VerkleAccumulator(session_id)
        
        event1 = {
            "session_id": session_id,
            "counter": 0,
            "timestamp": "2025-12-08T10:00:00Z",
            "event_type": "test",
            "payload": {}
        }
        acc.add_event(event1)
        
        # Wrong counter
        event2 = {
            "session_id": session_id,
            "counter": 5,
            "timestamp": "2025-12-08T10:00:01Z",
            "event_type": "test",
            "payload": {}
        }
        
        with pytest.raises(ValueError, match="Counter mismatch"):
            acc.add_event(event2)
    
    def test_verkle_double_finalize(self, session_id):
        """Test that finalizing twice raises error"""
        acc = VerkleAccumulator(session_id)
        
        event = {
            "session_id": session_id,
            "counter": 0,
            "timestamp": "2025-12-08T10:00:00Z",
            "event_type": "test",
            "payload": {}
        }
        acc.add_event(event)
        
        acc.finalize()
        
        with pytest.raises(RuntimeError, match="already finalized"):
            acc.finalize()
