"""
Tests for KZG polynomial commitments and Verkle tree integration (Phase 3).
"""

import hashlib
import pytest

from src.crypto.verkle import KZGCommitter, KZGCommitment, VerkleAccumulator


class TestKZGCommitter:
    """Test KZG commitment scheme"""
    
    def test_kzg_init(self):
        """Test KZG committer initialization"""
        committer = KZGCommitter()
        assert committer.secret == 42
        assert len(committer.g1_powers) == committer.MAX_DEGREE
    
    def test_kzg_commit_simple(self):
        """Test committing to a simple polynomial"""
        committer = KZGCommitter()
        
        # Commit to polynomial: p(x) = 1 + 2x + 3x^2
        poly = [1, 2, 3]
        commitment = committer.commit(poly)
        
        assert isinstance(commitment, KZGCommitment)
        assert len(commitment.commitment_point) == 48  # Serialized G1 point
    
    def test_kzg_commit_zero_polynomial(self):
        """Test committing to zero polynomial"""
        committer = KZGCommitter()
        
        # Commit to zero polynomial
        poly = [0]
        commitment = committer.commit(poly)
        
        assert isinstance(commitment, KZGCommitment)
        assert commitment.commitment_point == b'\x00' * 48
    
    def test_kzg_commit_large_coefficients(self):
        """Test polynomial with large coefficients (should wrap mod curve_order)"""
        committer = KZGCommitter()
        
        # Use large coefficients
        poly = [2**100, 2**101, 2**102]
        commitment = committer.commit(poly)
        
        assert isinstance(commitment, KZGCommitment)
        assert len(commitment.commitment_point) == 48
    
    def test_kzg_commit_max_degree(self):
        """Test committing to max degree polynomial"""
        committer = KZGCommitter()
        
        # Create polynomial at max degree
        poly = [i % 100 for i in range(committer.MAX_DEGREE)]
        commitment = committer.commit(poly)
        
        assert isinstance(commitment, KZGCommitment)
        assert len(commitment.commitment_point) == 48
    
    def test_kzg_commit_exceeds_max_degree(self):
        """Test that exceeding max degree raises error"""
        committer = KZGCommitter()
        
        # Try to commit polynomial exceeding max degree
        poly = [1] * (committer.MAX_DEGREE + 1)
        
        with pytest.raises(ValueError, match="exceeds max"):
            committer.commit(poly)
    
    def test_kzg_commitment_to_b64(self):
        """Test converting commitment to Base64"""
        committer = KZGCommitter()
        poly = [42]
        commitment = committer.commit(poly)
        
        b64_str = commitment.to_b64()
        assert isinstance(b64_str, str)
        assert len(b64_str) > 0
        
        # Should be valid Base64
        import base64
        decoded = base64.b64decode(b64_str)
        assert decoded == commitment.commitment_point
    
    def test_kzg_commitment_from_b64(self):
        """Test creating commitment from Base64"""
        committer = KZGCommitter()
        poly = [42]
        original = committer.commit(poly)
        
        b64_str = original.to_b64()
        restored = KZGCommitment.from_b64(b64_str)
        
        assert restored.commitment_point == original.commitment_point


class TestVerkleAccumulatorWithKZG:
    """Test Verkle accumulator with KZG commitments (Phase 3)"""
    
    def test_verkle_init(self):
        """Test VerkleAccumulator initialization"""
        acc = VerkleAccumulator("test-session")
        
        assert acc.session_id == "test-session"
        assert acc.events == []
        assert acc.event_hashes == []
        assert acc.root is None
        assert acc.counter == 0
        assert isinstance(acc.kzg, KZGCommitter)
    
    def test_verkle_add_single_event(self):
        """Test adding a single event"""
        acc = VerkleAccumulator("test-session")
        
        event = {
            "type": "test",
            "counter": 0,
            "data": "hello"
        }
        
        acc.add_event(event)
        
        assert len(acc.events) == 1
        assert len(acc.event_hashes) == 1
        assert acc.counter == 1
    
    def test_verkle_add_multiple_events(self):
        """Test adding multiple events"""
        acc = VerkleAccumulator("test-session")
        
        for i in range(5):
            event = {
                "type": "test",
                "counter": i,
                "data": f"event-{i}"
            }
            acc.add_event(event)
        
        assert len(acc.events) == 5
        assert len(acc.event_hashes) == 5
        assert acc.counter == 5
    
    def test_verkle_counter_mismatch(self):
        """Test that counter mismatch raises error"""
        acc = VerkleAccumulator("test-session")
        
        event1 = {"type": "test", "counter": 0}
        event2 = {"type": "test", "counter": 2}  # Should be 1
        
        acc.add_event(event1)
        
        with pytest.raises(ValueError, match="Counter mismatch"):
            acc.add_event(event2)
    
    def test_verkle_finalize_empty(self):
        """Test finalizing empty accumulator"""
        acc = VerkleAccumulator("test-session")
        
        root = acc.finalize()
        
        assert root is not None
        assert len(root) == 48  # Serialized G1 point
        assert acc.root == root
    
    def test_verkle_finalize_with_events(self):
        """Test finalizing accumulator with events"""
        acc = VerkleAccumulator("test-session")
        
        for i in range(3):
            event = {
                "type": "test",
                "counter": i,
                "data": f"event-{i}"
            }
            acc.add_event(event)
        
        root = acc.finalize()
        
        assert root is not None
        assert len(root) == 48
        assert acc.root == root
    
    def test_verkle_finalize_once(self):
        """Test that finalize can only be called once"""
        acc = VerkleAccumulator("test-session")
        
        event = {"type": "test", "counter": 0}
        acc.add_event(event)
        
        root1 = acc.finalize()
        
        with pytest.raises(RuntimeError, match="already finalized"):
            acc.finalize()
    
    def test_verkle_get_root_b64(self):
        """Test getting root as Base64"""
        acc = VerkleAccumulator("test-session")
        
        event = {"type": "test", "counter": 0}
        acc.add_event(event)
        acc.finalize()
        
        root_b64 = acc.get_root_b64()
        
        assert isinstance(root_b64, str)
        assert len(root_b64) > 0
        
        # Should be valid Base64
        import base64
        decoded = base64.b64decode(root_b64)
        assert decoded == acc.root
    
    def test_verkle_get_root_b64_before_finalize(self):
        """Test that getting root before finalize raises error"""
        acc = VerkleAccumulator("test-session")
        
        with pytest.raises(RuntimeError, match="not yet finalized"):
            acc.get_root_b64()
    
    def test_verkle_get_canonical_log(self):
        """Test getting canonical log"""
        acc = VerkleAccumulator("test-session")
        
        for i in range(3):
            event = {"type": "test", "counter": i, "data": f"event-{i}"}
            acc.add_event(event)
        
        log = acc.get_canonical_log()
        
        assert isinstance(log, bytes)
        assert len(log) > 0
    
    def test_verkle_determinism(self):
        """Test that same events produce same root (determinism)"""
        events = [
            {"type": "test", "counter": i, "data": f"event-{i}"}
            for i in range(3)
        ]
        
        # Run 1
        acc1 = VerkleAccumulator("session-1")
        for event in events:
            acc1.add_event(event)
        root1 = acc1.finalize()
        
        # Run 2
        acc2 = VerkleAccumulator("session-2")
        for event in events:
            acc2.add_event(event)
        root2 = acc2.finalize()
        
        # Roots should be identical
        assert root1 == root2
    
    def test_verkle_different_events_different_root(self):
        """Test that different events produce different roots"""
        acc1 = VerkleAccumulator("session-1")
        acc1.add_event({"type": "test", "counter": 0, "data": "event-a"})
        root1 = acc1.finalize()
        
        acc2 = VerkleAccumulator("session-2")
        acc2.add_event({"type": "test", "counter": 0, "data": "event-b"})
        root2 = acc2.finalize()
        
        # Different events should produce different roots
        assert root1 != root2
    
    def test_verkle_verify_against_root(self):
        """Test verifying canonical log against root"""
        acc = VerkleAccumulator("test-session")
        
        for i in range(3):
            event = {"type": "test", "counter": i, "data": f"event-{i}"}
            acc.add_event(event)
        
        root = acc.finalize()
        log = acc.get_canonical_log()
        
        # Verification should pass
        assert acc.verify_against_root(log, root)


class TestVerkleBackwardCompatibility:
    """Test backward compatibility of Verkle API"""
    
    def test_verkle_api_unchanged(self):
        """Test that public API is unchanged from Phase 2"""
        acc = VerkleAccumulator("test-session")
        
        # Old API should still work
        event = {"type": "test", "counter": 0}
        acc.add_event(event)
        
        root = acc.finalize()
        root_b64 = acc.get_root_b64()
        log = acc.get_canonical_log()
        
        # All should work without errors
        assert root is not None
        assert isinstance(root_b64, str)
        assert isinstance(log, bytes)
    
    def test_verkle_root_format_still_base64(self):
        """Test that root can still be Base64 encoded"""
        acc = VerkleAccumulator("test-session")
        acc.add_event({"type": "test", "counter": 0})
        acc.finalize()
        
        root_b64 = acc.get_root_b64()
        
        # Should be valid Base64 string
        import base64
        decoded = base64.b64decode(root_b64)
        assert len(decoded) == 48  # G1 point size
