"""
Key Management System for Attribute-Based Signing.
Manages the Master Secret and issues Derived Keys to Tools.
"""

import ast
from typing import Tuple, Any
from py_ecc.optimized_bls12_381 import FQ, FQ2
from src.crypto.signatures import IBSScheme, PointG1, PointG2, Scalar

class ToolSigner:
    """
    Represents a tool's cryptographic identity.
    Holds the tool's private key (derived from its name).
    """
    def __init__(self, tool_name: str, private_key: PointG1):
        self.tool_name = tool_name
        self._private_key = private_key  # Secret

    def sign_message(self, message: bytes) -> Tuple[PointG1, PointG1]:
        """Sign a message (e.g., tool output) using the IBS key"""
        return IBSScheme.sign(self._private_key, self.tool_name, message)
    
    def export_private_key(self) -> str:
        """Export private key as a string for remote provisioning"""
        # G1 is (x, y, z) tuple of FQ objects.
        # casting them to int gives the underlying integer.
        pk = self._private_key
        return str((int(pk[0]), int(pk[1]), int(pk[2])))

    @classmethod
    def import_from_string(cls, tool_name: str, key_str: str) -> 'ToolSigner':
        """Reconstruct a ToolSigner from an exported string"""
        # Parse tuple (x, y, z)
        try:
            vals = ast.literal_eval(key_str)
            if not isinstance(vals, tuple) or len(vals) != 3:
                raise ValueError("Invalid key format")
                
            x = FQ(vals[0])
            y = FQ(vals[1])
            z = FQ(vals[2])
            
            point = (x, y, z)
            return cls(tool_name, point)
        except Exception as e:
            raise ValueError(f"Failed to import key: {e}")

class KeyAuthority:
    """
    The Central Authority (Server).
    Holds the Master Secret Key.
    """
    def __init__(self, master_secret_hex: str | None = None):
        secret_int = None
        if master_secret_hex:
            try:
                secret_int = int(master_secret_hex, 16)
            except ValueError:
                # Fallback or error? For now, fallback to random is dangerous if user expects persistence.
                # raising error is better.
                raise ValueError("Invalid hex string for master_secret_key")

        self._msk, self.mpk = IBSScheme.setup(secret_int)

    def get_public_params(self) -> PointG2:
        """Return Master Public Key"""
        return self.mpk

    def provision_tool(self, tool_name: str) -> ToolSigner:
        """
        Derive a private key for a tool based *only* on its name.
        Returns a ToolSigner instance loaded with that key.
        """
        tool_sk = IBSScheme.extract(self._msk, tool_name)
        return ToolSigner(tool_name, tool_sk)

    def sign_root(self, root_hash: bytes) -> PointG1:
        """Sign the final Verkle Root using the Master Key"""
        return IBSScheme.sign_root_bls(self._msk, root_hash)

    def export_mpk(self) -> dict:
        """
        Export Master Public Key as a JSON-serializable dict.
        
        MPK is a G2 point on BLS12-381 with FQ2 coordinates.
        Each FQ2 has two integer coefficients.
        
        Returns:
            dict with curve, group, and x/y/z coordinate pairs
        """
        mpk = self.mpk
        return {
            "curve": "BLS12-381",
            "group": "G2",
            "x": [int(mpk[0].coeffs[0]), int(mpk[0].coeffs[1])],
            "y": [int(mpk[1].coeffs[0]), int(mpk[1].coeffs[1])],
            "z": [int(mpk[2].coeffs[0]), int(mpk[2].coeffs[1])],
        }

    @staticmethod
    def import_mpk(data: dict) -> PointG2:
        """
        Reconstruct Master Public Key from exported dict.
        
        Args:
            data: dict with x, y, z keys (each a [coeff0, coeff1] list)
        
        Returns:
            G2 point suitable for IBSScheme.verify()
        """
        x = FQ2(data["x"])
        y = FQ2(data["y"])
        z = FQ2(data["z"])
        return (x, y, z)

    @staticmethod
    def parse_ibs_signature(sig_str: str) -> Tuple[PointG1, PointG1]:
        """
        Parse an IBS signature string back into (U, V) G1 point tuple.
        
        The signature is stored in canonical events as str((U, V)) where
        U and V are G1 points in projective coordinates (FQ(x), FQ(y), FQ(z)).
        
        Args:
            sig_str: String representation like "((x1, y1, z1), (x2, y2, z2))"
        
        Returns:
            Tuple of two G1 points (U, V)
        
        Raises:
            ValueError: If the string cannot be parsed as a valid signature
        """
        from py_ecc.optimized_bls12_381 import FQ
        
        try:
            parsed = ast.literal_eval(sig_str)
            if not isinstance(parsed, tuple) or len(parsed) != 2:
                raise ValueError("Signature must be a tuple of two points")
            
            u_raw, v_raw = parsed
            if not isinstance(u_raw, tuple) or len(u_raw) != 3:
                raise ValueError("U point must be a tuple of 3 coordinates")
            if not isinstance(v_raw, tuple) or len(v_raw) != 3:
                raise ValueError("V point must be a tuple of 3 coordinates")
            
            U = (FQ(u_raw[0]), FQ(u_raw[1]), FQ(u_raw[2]))
            V = (FQ(v_raw[0]), FQ(v_raw[1]), FQ(v_raw[2]))
            
            return (U, V)
        except (SyntaxError, TypeError) as e:
            raise ValueError(f"Failed to parse IBS signature: {e}")


class Verifier:
    """
    Public Verifier.
    Only needs MPK to verify any tool signature.
    """
    def __init__(self, mpk: PointG2):
        self.mpk = mpk

    def verify_tool_signature(self, tool_name: str, message: bytes, signature: Tuple[PointG1, PointG1]) -> bool:
        return IBSScheme.verify(self.mpk, tool_name, message, signature)

    def verify_root_signature(self, root_hash: bytes, signature: PointG1) -> bool:
        return IBSScheme.verify_root_bls(self.mpk, root_hash, signature)
