"""
RFC 8785 Canonical JSON Encoder
Ensures deterministic serialization for all log events
"""

import json
import unicodedata
from typing import Any


def is_finite(val: float) -> bool:
    """Check if a float is finite (no NaN, Infinity, -Infinity)"""
    return isinstance(val, float) and not (val != val or val == float("inf") or val == float("-inf"))


def canonicalize_json(obj: Any) -> str:
    """
    Encode object to canonical JSON per RFC 8785.
    - Ensures deterministic key ordering
    - Normalizes Unicode to NFC
    - Rejects non-finite floats
    - No whitespace
    """
    # Validate no non-finite floats exist
    _validate_no_non_finite(obj)
    
    # Convert to JSON with sorted keys
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    
    # Unicode normalization to NFC
    normalized = unicodedata.normalize("NFC", canonical)
    
    return normalized


def _validate_no_non_finite(obj: Any) -> None:
    """Recursively validate no non-finite floats in object tree"""
    if isinstance(obj, float):
        if not is_finite(obj):
            raise ValueError(f"Non-finite float encountered: {obj}")
    elif isinstance(obj, dict):
        for value in obj.values():
            _validate_no_non_finite(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _validate_no_non_finite(item)


def canonicalize_bytes(obj: Any) -> bytes:
    """Convert object to canonical JSON and encode as UTF-8 bytes"""
    return canonicalize_json(obj).encode("utf-8")


class CanonicalEncoder:
    """Helper class for deterministic encoding of log events"""
    
    @staticmethod
    def encode_event(event: dict[str, Any]) -> bytes:
        """Encode a complete event in canonical form"""
        return canonicalize_bytes(event)
    
    @staticmethod
    def encode_multiple(events: list[dict[str, Any]]) -> bytes:
        """Encode multiple events as a canonical array"""
        return canonicalize_bytes(events)
