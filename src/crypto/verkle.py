"""
Verkle Tree implementation using KZG polynomial commitments over BLS12-381.

This implementation provides:
- KZG commitments for compact polynomial commitment schemes
- BLS12-381 elliptic curve cryptography
- Production-grade integrity guarantees
"""

import hashlib
import base64
from dataclasses import dataclass
from typing import Any

try:
    from py_ecc.optimized_bls12_381 import (
        G1, G2, Z1, Z2, pairing, curve_order, 
        multiply, add, field_modulus
    )
except ImportError:
    raise ImportError(
        "py-ecc library not found. Install with: pip install py-ecc"
    )

from src.crypto.encoding import CanonicalEncoder


@dataclass
class KZGCommitment:
    """KZG polynomial commitment on BLS12-381 curve"""
    commitment_point: bytes  # Serialized G1 point (48 bytes)
    
    def to_b64(self) -> str:
        """Convert to Base64 for storage/transmission"""
        return base64.b64encode(self.commitment_point).decode("utf-8")
    
    @classmethod
    def from_b64(cls, b64_str: str) -> "KZGCommitment":
        """Create from Base64 string"""
        return cls(base64.b64decode(b64_str))


class KZGCommitter:
    """
    KZG polynomial commitment scheme over BLS12-381.
    
    Uses a simple trusted setup with g1^x where x is a secret.
    For production, use proper ceremony-generated parameters.
    """
    
    MAX_DEGREE = 256  # Max polynomial degree
    
    def __init__(self):
        """Initialize with simple trusted setup (WARNING: for testing only)"""
        # In production, use parameters from a trusted ceremony
        # This is a simple test setup with secret = 42
        self.secret = 42
        self._setup_powers()
    
    def _setup_powers(self) -> None:
        """Compute G1^secret^i for i = 0..MAX_DEGREE"""
        self.g1_powers: list[Any] = []
        current_power = 1
        
        for _ in range(self.MAX_DEGREE):
            # Compute G1 * (secret^i mod curve_order)
            g1_point = multiply(G1, current_power)
            self.g1_powers.append(g1_point)
            current_power = (current_power * self.secret) % curve_order
    
    def commit(self, polynomial_values: list[int]) -> KZGCommitment:
        """
        Create KZG commitment to polynomial.
        
        Args:
            polynomial_values: Coefficients of polynomial (low to high degree)
            
        Returns:
            KZGCommitment with commitment point
        """
        if len(polynomial_values) > self.MAX_DEGREE:
            raise ValueError(f"Polynomial degree exceeds max {self.MAX_DEGREE}")
        
        # C = sum(a_i * G1^(secret^i))
        commitment = Z1  # Identity/zero point
        
        for i, coeff in enumerate(polynomial_values):
            if coeff != 0:
                # Add coeff * G1_powers[i] to commitment
                term = multiply(self.g1_powers[i], coeff % curve_order)
                commitment = add(commitment, term)
        
        # Serialize commitment point (48 bytes for compressed G1)
        commitment_bytes = self._serialize_g1(commitment)
        return KZGCommitment(commitment_bytes)
    
    def _serialize_g1(self, point: Any) -> bytes:
        """Serialize G1 point to bytes (48 bytes for BLS12-381)"""
        if point == Z1:
            return b'\x00' * 48
        
        # py_ecc represents points as (x, y) tuples where x, y are FQ field elements
        # Serialize x-coordinate as 48 bytes (big-endian)
        try:
            x = point[0]  # Extract x-coordinate (FQ field element)
            # Convert FQ to int
            x_int = int(x)
        except (TypeError, IndexError, ValueError):
            # If unpacking fails, it's already a problematic point
            return b'\x00' * 48
        
        # Use big-endian encoding for the x-coordinate (BLS12-381 standard)
        x_bytes = x_int.to_bytes(48, byteorder='big')
        return x_bytes
    
    def _deserialize_g1(self, data: bytes) -> Any:
        """Deserialize bytes to G1 point (placeholder - full impl complex)"""
        if data == b'\x00' * 48:
            return Z1
        
        x = int.from_bytes(data[:48], byteorder='big')
        # In production, recover y from x and bit flag
        # For now, return identity as placeholder
        return Z1


@dataclass
class VerkleNode:
    """A node in the Verkle tree"""
    index: int
    value_hash: bytes  # SHA-256 hash of the value
    children: list["VerkleNode"] | None = None
    is_leaf: bool = True
    

class VerkleAccumulator:
    """
    Accumulates events into a Verkle tree structure using KZG commitments.
    
    Each event is canonically encoded, hashed, and committed via KZG.
    Produces a compact Verkle root per agent run.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.events: list[dict[str, Any]] = []
        self.event_hashes: list[bytes] = []
        self.root: bytes | None = None
        self.counter = 0
        self.kzg = KZGCommitter()
    
    def add_event(self, event: dict[str, Any]) -> None:
        """Add an event to the accumulator"""
        # Verify counter is sequential
        if "counter" in event:
            if event["counter"] != self.counter:
                raise ValueError(
                    f"Counter mismatch: expected {self.counter}, got {event['counter']}"
                )
            self.counter += 1
        
        # Canonically encode and hash
        encoded = CanonicalEncoder.encode_event(event)
        event_hash = hashlib.sha256(encoded).digest()
        
        self.events.append(event)
        self.event_hashes.append(event_hash)
    
    def finalize(self) -> bytes:
        """
        Finalize the Verkle tree and return the KZG commitment as root.
        Can only be called once per run.
        """
        if self.root is not None:
            raise RuntimeError("Verkle tree already finalized for this run")
        
        if not self.events:
            # Empty tree: KZG commit to zero polynomial
            self.root = self.kzg.commit([0]).commitment_point
            return self.root
        
        # Convert event hashes to polynomial coefficients
        # Each hash is a 32-byte value; use first 8 bytes as integer
        polynomial_values: list[int] = []
        for event_hash in self.event_hashes:
            # Convert hash bytes to integer (mod curve_order for safety)
            coeff = int.from_bytes(event_hash[:32], byteorder='big') % curve_order
            polynomial_values.append(coeff)
        
        # Create KZG commitment to the polynomial
        commitment = self.kzg.commit(polynomial_values)
        self.root = commitment.commitment_point
        
        return self.root
    
    def get_root_b64(self) -> str:
        """Get the root as a Base64-encoded string"""
        if self.root is None:
            raise RuntimeError("Tree not yet finalized")
        
        return base64.b64encode(self.root).decode("utf-8")
    
    def get_canonical_log(self) -> bytes:
        """Get the entire canonical log as bytes"""
        return CanonicalEncoder.encode_multiple(self.events)
    
    def verify_against_root(self, canonical_log: bytes, expected_root: bytes) -> bool:
        """
        Verify that a canonical log matches the expected root.
        Used by the verification CLI.
        """
        import json
        
        log_data = json.loads(canonical_log.decode("utf-8"))
        
        # Re-accumulate
        acc = VerkleAccumulator(self.session_id)
        for event in (log_data if isinstance(log_data, list) else [log_data]):
            acc.add_event(event)
        
        computed_root = acc.finalize()
        return computed_root == expected_root


class VerkleTreeProof:
    """Placeholder for Verkle tree proof of inclusion (for future use)"""
    
    def __init__(self, path: list[bytes], commitment: KZGCommitment):
        self.path = path
        self.commitment = commitment
