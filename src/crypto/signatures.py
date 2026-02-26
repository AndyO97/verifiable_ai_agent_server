"""
Identity-Based Signature (IBS) Scheme over BLS12-381.
Implements a Cha-Cheon style IBS scheme for "Tool Name as Public Key" architecture.
"""

import hashlib
import os
from typing import Tuple, Optional, Any

try:
    from py_ecc.optimized_bls12_381 import (
        G2, multiply, add, pairing, curve_order, field_modulus, FQ
    )
except ImportError:
    raise ImportError("py-ecc library required")

# Type definitions
PointG1 = tuple[FQ, FQ, FQ]  # Optimized BLS12-381 points are projective
PointG2 = tuple[Any, Any, Any]
Scalar = int


def hash_to_field(data: bytes) -> int:
    """Hash bytes to element in Field Fp"""
    digest = hashlib.sha256(data).digest()
    return int.from_bytes(digest, "big") % field_modulus


def hash_to_scalar(data: bytes) -> int:
    """Hash bytes to scalar field Fr (curve order)"""
    digest = hashlib.sha256(data).digest()
    return int.from_bytes(digest, "big") % curve_order


def hash_to_G1(data: bytes) -> PointG1:
    """
    Map arbitrary data to a point on G1 using Try-and-Increment.
    Secure enough for this demo, ensures H(ID) has no discrete log relation to Generator.
    """
    counter = 0
    while True:
        # H(data || counter)
        t_bytes = data + counter.to_bytes(4, "big")
        # Map to X coordinate in Fp
        x_int = int.from_bytes(hashlib.sha256(t_bytes).digest(), "big") % field_modulus
        
        # Check if y^2 = x^3 + 4 has a solution (BLS12-381 equation)
        # y^2 = x^3 + b
        x_fq = FQ(x_int)
        rhs = x_fq ** 3 + FQ(4)
        
        # Euler's criterion: a^((p-1)/2) == 1 mod p if square
        # BLS12-381 prime is 3 mod 4, so we can use y = a^((p+1)/4)
        y = rhs ** ((field_modulus + 1) // 4)
        
        if y * y == rhs:
             return (x_fq, y, FQ(1))
        
        counter += 1
        if counter > 1000:
             raise RuntimeError("Failed to find point on curve")


class IBSScheme:
    """
    Identity-Based Signature Scheme (Cha-Cheon style over BLS12-381).
    """

    @staticmethod
    def setup(secret: Optional[int] = None) -> Tuple[Scalar, PointG2]:
        """
        Generate Master Secret Key (MSK) and Master Public Key (MPK).
        Returns: (s, P_pub)
        """
        if secret is not None:
             s = secret % curve_order
        else:
             s = int.from_bytes(os.urandom(32), "big") % curve_order
        
        P_pub = multiply(G2, s)
        return s, P_pub

    @staticmethod
    def extract(master_sk: Scalar, identity: str) -> PointG1:
        """
        Extract private key for an identity.
        D_ID = s * H_G1(ID)
        """
        Q_id = hash_to_G1(identity.encode("utf-8"))
        D_id = multiply(Q_id, master_sk)
        return D_id

    @staticmethod
    def sign(tool_sk: PointG1, identity: str, message: bytes) -> Tuple[PointG1, PointG1]:
        """
        Sign a message using the Tool's Private Key.
        Signature = (U, V)
        """
        Q_id = hash_to_G1(identity.encode("utf-8"))
        
        # Random r
        r = int.from_bytes(os.urandom(32), "big") % curve_order
        
        # U = r * Q_ID
        U = multiply(Q_id, r)
        
        # h = H(m || U_bytes)
        # We need to serialize U deterministically for the hash.
        # Simple repr() is fragile but deterministic within the same library version.
        # Ideally serialize x, y coords.
        U_bytes = str(U).encode("utf-8") 
        h_input = message + U_bytes
        h = hash_to_scalar(h_input)
        
        # V = (r + h) * D_ID
        scalar = (r + h) % curve_order
        V = multiply(tool_sk, scalar)
        
        return (U, V)

    @staticmethod
    def verify(mpk: PointG2, identity: str, message: bytes, signature: Tuple[PointG1, PointG1]) -> bool:
        """
        Verify signature (U, V) against Master Public Key and Identity.
        Check: e(MPK, U + h*Q_ID) == e(G2, V)
        """
        U, V = signature
        Q_id = hash_to_G1(identity.encode("utf-8"))
        
        # Reconstruct h
        U_bytes = str(U).encode("utf-8")
        h_input = message + U_bytes
        h = hash_to_scalar(h_input)
        
        # LHS_point = U + h * Q_ID
        h_Q_id = multiply(Q_id, h)
        LHS_point = add(U, h_Q_id)
        
        # Pairings
        lhs_pairing = pairing(mpk, LHS_point)
        rhs_pairing = pairing(G2, V)
        
        return lhs_pairing == rhs_pairing

    @staticmethod
    def sign_root_bls(master_sk: Scalar, root_hash: bytes) -> PointG1:
        """
        Standard BLS signature for the Verkle Root.
        Sig = s * H(root)
        """
        H_point = hash_to_G1(root_hash)
        return multiply(H_point, master_sk)

    @staticmethod
    def verify_root_bls(mpk: PointG2, root_hash: bytes, signature: PointG1) -> bool:
        """
        Verify BLS signature.
        e(MPK, H(root)) == e(G2, Sig)
        """
        H_point = hash_to_G1(root_hash)
        
        lhs = pairing(mpk, H_point)
        rhs = pairing(G2, signature)
        
        return lhs == rhs
