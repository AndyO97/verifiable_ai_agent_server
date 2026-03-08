"""
W3C Trace Context propagation (https://www.w3.org/TR/trace-context/)

Implements traceparent and tracestate header parsing, generation, and propagation
for distributed trace correlation with external OTel-instrumented services.

Header formats:
  traceparent: {version}-{trace-id}-{parent-id}-{trace-flags}
    Example: 00-4bf92f3577b6a27ff6a3dc12e9d2c07e-00f067aa0ba902b7-01
  tracestate: vendor-specific key=value pairs, comma-separated
    Example: langfuse=abc123,verifiable=session-xyz
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# W3C Trace Context format validation
# version: 2 hex chars, trace-id: 32 hex chars, parent-id: 16 hex chars, flags: 2 hex chars
TRACEPARENT_PATTERN = re.compile(
    r'^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$'
)

# tracestate key: [a-z][a-z0-9_\-*/]{0,255} or tenant@vendor format
# tracestate value: printable ASCII (0x20-0x7E) except ',' and '='
TRACESTATE_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_\-*/]{0,255}$')

# Version we generate
TRACE_CONTEXT_VERSION = "00"

# All-zero IDs are invalid per spec
INVALID_TRACE_ID = "0" * 32
INVALID_PARENT_ID = "0" * 16


@dataclass
class TraceContext:
    """
    Represents a W3C Trace Context with traceparent and tracestate.

    The traceparent header contains:
    - version: Always "00" for current spec
    - trace_id: 16-byte hex string identifying the entire distributed trace
    - parent_id: 8-byte hex string identifying the parent span
    - trace_flags: 1-byte hex, bit 0 = sampled
    """
    version: str = TRACE_CONTEXT_VERSION
    trace_id: str = ""
    parent_id: str = ""
    trace_flags: str = "01"  # sampled by default
    tracestate: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_headers(cls, traceparent: Optional[str], tracestate: Optional[str] = None) -> Optional[TraceContext]:
        """
        Parse W3C Trace Context from HTTP headers.

        Returns None if traceparent is missing or invalid.
        """
        if not traceparent:
            return None

        match = TRACEPARENT_PATTERN.match(traceparent.strip().lower())
        if not match:
            logger.warning("invalid_traceparent", traceparent=traceparent)
            return None

        version, trace_id, parent_id, flags = match.groups()

        # All-zero trace-id or parent-id are invalid
        if trace_id == INVALID_TRACE_ID or parent_id == INVALID_PARENT_ID:
            logger.warning("invalid_traceparent_zero_ids", trace_id=trace_id, parent_id=parent_id)
            return None

        ctx = cls(
            version=version,
            trace_id=trace_id,
            parent_id=parent_id,
            trace_flags=flags,
        )

        # Parse tracestate if provided
        if tracestate:
            ctx.tracestate = cls._parse_tracestate(tracestate)

        return ctx

    @classmethod
    def generate(cls, tracestate: Optional[dict[str, str]] = None) -> TraceContext:
        """
        Generate a new root trace context with random trace-id and parent-id.
        """
        trace_id = os.urandom(16).hex()
        parent_id = os.urandom(8).hex()
        return cls(
            version=TRACE_CONTEXT_VERSION,
            trace_id=trace_id,
            parent_id=parent_id,
            trace_flags="01",
            tracestate=tracestate or {},
        )

    def create_child(self) -> TraceContext:
        """
        Create a child context: same trace-id, new parent-id, same flags.
        Used when this service creates a downstream span.
        """
        return TraceContext(
            version=self.version,
            trace_id=self.trace_id,
            parent_id=os.urandom(8).hex(),
            trace_flags=self.trace_flags,
            tracestate=dict(self.tracestate),
        )

    @property
    def traceparent(self) -> str:
        """Format as W3C traceparent header value."""
        return f"{self.version}-{self.trace_id}-{self.parent_id}-{self.trace_flags}"

    @property
    def tracestate_header(self) -> str:
        """Format as W3C tracestate header value."""
        if not self.tracestate:
            return ""
        return ",".join(f"{k}={v}" for k, v in self.tracestate.items())

    @property
    def is_sampled(self) -> bool:
        """Check if trace-flags has the sampled bit set."""
        return (int(self.trace_flags, 16) & 0x01) == 1

    def inject_headers(self, headers: dict) -> dict:
        """
        Inject traceparent and tracestate into an outgoing headers dict.
        Returns the modified headers dict.
        """
        headers["traceparent"] = self.traceparent
        ts = self.tracestate_header
        if ts:
            headers["tracestate"] = ts
        return headers

    def to_metadata(self) -> dict:
        """
        Export trace context as a metadata dict for inclusion in
        Langfuse traces, integrity events, etc.
        """
        meta = {
            "w3c_trace_id": self.trace_id,
            "w3c_parent_id": self.parent_id,
            "w3c_trace_flags": self.trace_flags,
            "w3c_traceparent": self.traceparent,
        }
        if self.tracestate:
            meta["w3c_tracestate"] = self.tracestate_header
        return meta

    @staticmethod
    def _parse_tracestate(header: str) -> dict[str, str]:
        """Parse tracestate header into key-value dict."""
        result = {}
        for pair in header.split(","):
            pair = pair.strip()
            if "=" in pair:
                key, _, value = pair.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value:
                    result[key] = value
        return result

    def __repr__(self) -> str:
        return f"TraceContext(traceparent={self.traceparent})"
