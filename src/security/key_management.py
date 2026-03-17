"""
Key Management System for Attribute-Based Signing.
Manages the Master Secret and issues Derived Keys to Tools.
"""

import ast
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from py_ecc.optimized_bls12_381 import FQ, FQ2
from src.crypto.signatures import IBSScheme, PointG1, PointG2, Scalar


def _is_valid_master_secret_hex(secret_hex: str) -> bool:
    """Validate a 32-byte master secret represented as 64 hex chars."""
    if len(secret_hex) != 64:
        return False
    try:
        int(secret_hex, 16)
    except ValueError:
        return False
    return True


class MasterKeyRing:
    """
    Encrypted-at-rest keyring with epoch-based master secret rotation.

    Encryption:
    - KEK derived via HKDF-SHA256 from bootstrap secret in SECURITY_MASTER_SECRET_KEY
    - Data encrypted with AES-256-GCM (nonce: 96-bit random)
    """

    def __init__(
        self,
        bootstrap_secret_hex: str,
        keyring_path: Optional[Path] = None,
    ):
        if not _is_valid_master_secret_hex(bootstrap_secret_hex):
            raise ValueError("SECURITY_MASTER_SECRET_KEY must be 64 hex chars (32 bytes)")

        self._bootstrap_secret_hex = bootstrap_secret_hex
        self._bootstrap_secret_bytes = bytes.fromhex(bootstrap_secret_hex)
        self._path = keyring_path or Path("./artifacts/security/master_keyring.enc.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)

        if not self._path.exists():
            self._initialize_keyring()

    def _initialize_keyring(self) -> None:
        """Create first keyring entry using the bootstrap secret as epoch 1."""
        salt = os.urandom(16)
        envelope = {
            "version": 1,
            "kdf": {
                "name": "HKDF-SHA256",
                "salt": base64.b64encode(salt).decode("ascii"),
                "info": "verifiable-ai-agent/master-keyring/v1",
            },
            "active_epoch": 1,
            "keys": [],
        }

        entry = self._encrypt_epoch_secret(
            epoch=1,
            secret_hex=self._bootstrap_secret_hex,
            salt=salt,
        )
        envelope["keys"].append(entry)
        self._write_envelope(envelope)

    def _derive_kek(self, salt: bytes) -> bytes:
        """Derive a 256-bit key-encryption-key from bootstrap secret."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"verifiable-ai-agent/master-keyring/v1",
        )
        return hkdf.derive(self._bootstrap_secret_bytes)

    def _read_envelope(self) -> dict:
        with open(self._path, "r", encoding="utf-8") as f:
            envelope = json.load(f)
        if envelope.get("version") != 1:
            raise ValueError("Unsupported keyring version")
        return envelope

    def _write_envelope(self, envelope: dict) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
        os.replace(tmp_path, self._path)

    def _encrypt_epoch_secret(self, epoch: int, secret_hex: str, salt: bytes) -> dict:
        if not _is_valid_master_secret_hex(secret_hex):
            raise ValueError("Invalid master secret format")

        plaintext = secret_hex.encode("ascii")
        nonce = os.urandom(12)
        aad = f"epoch:{epoch}".encode("ascii")
        kek = self._derive_kek(salt)
        ciphertext = AESGCM(kek).encrypt(nonce, plaintext, aad)

        return {
            "epoch": epoch,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        }

    def _decrypt_epoch_secret(self, entry: dict, salt: bytes) -> str:
        epoch = int(entry["epoch"])
        nonce = base64.b64decode(entry["nonce"])
        ciphertext = base64.b64decode(entry["ciphertext"])
        aad = f"epoch:{epoch}".encode("ascii")
        kek = self._derive_kek(salt)
        plaintext = AESGCM(kek).decrypt(nonce, ciphertext, aad)
        secret_hex = plaintext.decode("ascii")
        if not _is_valid_master_secret_hex(secret_hex):
            raise ValueError("Decrypted invalid master secret")
        return secret_hex

    def get_active_epoch(self) -> int:
        envelope = self._read_envelope()
        return int(envelope["active_epoch"])

    def get_active_secret_hex(self) -> str:
        envelope = self._read_envelope()
        salt = base64.b64decode(envelope["kdf"]["salt"])
        active_epoch = int(envelope["active_epoch"])

        for entry in envelope.get("keys", []):
            if int(entry["epoch"]) == active_epoch:
                return self._decrypt_epoch_secret(entry, salt)

        raise ValueError(f"Active epoch {active_epoch} not found in keyring")

    def rotate(self, new_secret_hex: Optional[str] = None) -> dict:
        """
        Rotate to a new active master secret.

        Returns metadata with previous and new epochs.
        """
        envelope = self._read_envelope()
        salt = base64.b64decode(envelope["kdf"]["salt"])
        current_epoch = int(envelope["active_epoch"])
        new_epoch = current_epoch + 1
        next_secret = new_secret_hex or os.urandom(32).hex()

        if not _is_valid_master_secret_hex(next_secret):
            raise ValueError("Rotated secret must be 64 hex chars (32 bytes)")

        entry = self._encrypt_epoch_secret(new_epoch, next_secret, salt)
        envelope.setdefault("keys", []).append(entry)
        envelope["active_epoch"] = new_epoch
        self._write_envelope(envelope)

        return {
            "previous_epoch": current_epoch,
            "new_epoch": new_epoch,
            "keyring_path": str(self._path),
        }

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
    def __init__(self, master_secret_hex: str | None = None, keyring_path: Optional[Path] = None):
        self._keyring: Optional[MasterKeyRing] = None
        self.active_epoch: Optional[int] = None

        secret_int = None
        if master_secret_hex:
            self._keyring = MasterKeyRing(master_secret_hex, keyring_path=keyring_path)
            active_secret_hex = self._keyring.get_active_secret_hex()
            self.active_epoch = self._keyring.get_active_epoch()

            try:
                secret_int = int(active_secret_hex, 16)
            except ValueError:
                raise ValueError("Invalid active master secret in keyring")

        self._msk, self.mpk = IBSScheme.setup(secret_int)

    def rotate_master_secret(self, new_secret_hex: str | None = None) -> dict:
        """
        Rotate to a new master secret epoch and reinitialize authority keys.

        Rotation is only available when initialized with SECURITY_MASTER_SECRET_KEY.
        """
        if self._keyring is None:
            raise ValueError("Key rotation requires SECURITY_MASTER_SECRET_KEY to be configured")

        result = self._keyring.rotate(new_secret_hex)
        active_secret_hex = self._keyring.get_active_secret_hex()
        self.active_epoch = self._keyring.get_active_epoch()
        self._msk, self.mpk = IBSScheme.setup(int(active_secret_hex, 16))
        return result

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
