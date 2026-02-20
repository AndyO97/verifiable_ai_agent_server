"""
Hierarchical Verkle Integrity Middleware with OpenTelemetry Support

Extends IntegrityMiddleware to support:
- Span-based event organization
- Per-span Verkle roots
- Session-level Verkle root (combining span roots)
- OpenTelemetry format export (OTel-compatible)
- Dual storage (local canonical log + OTel export)
- Multi-level verification strategy
"""

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple, Dict

import structlog

from src.integrity import IntegrityMiddleware, IntegrityEvent
from src.crypto.verkle import VerkleAccumulator
from src.crypto.encoding import CanonicalEncoder

logger = structlog.get_logger(__name__)


@dataclass
class SpanMetadata:
    """Metadata for a span (corresponds to OpenTelemetry span)"""
    span_id: str
    name: str  # e.g., "mcp_initialize", "user_interaction", "tool_execution"
    start_time: str  # ISO8601 UTC
    end_time: Optional[str] = None
    start_index: int = 0  # Index of first event in this span
    end_index: int = 0    # Index of last event in this span
    event_count: int = 0
    verkle_root: Optional[str] = None  # Per-span Verkle root (base64)
    duration_ms: int = 0


@dataclass
class HierarchicalCommitments:
    """Complete commitment structure for verification"""
    session_root: str  # Verkle root of all span roots
    event_accumulator_root: str  # Verkle root of all raw events (flat structure)
    span_roots: Dict[str, str]  # span_id -> root (string)
    canonical_log_hash: str  # SHA-256 of canonical log
    event_count: int
    timestamp: str  # When finalized
    otel_compliant: bool = True


class HierarchicalVerkleMiddleware(IntegrityMiddleware):
    """
    Extended middleware with hierarchical Verkle support and OpenTelemetry export.
    
    Architecture:
    - Each span gets its own Verkle accumulator and root
    - Session root is Verkle of all span roots
    - Events are associated with their span
    - Verification possible at span level or session level
    """
    
    def __init__(self, session_id: Optional[str] = None):
        """Initialize hierarchical middleware"""
        super().__init__(session_id)
        
        # Span management
        self.spans: Dict[str, SpanMetadata] = {}
        self.current_span_id: Optional[str] = None
        self.current_span_accumulator: Optional[VerkleAccumulator] = None
        self.current_span_counter: int = 0  # Per-span counter (resets per span)
        self.span_roots: Dict[str, str] = {}
        
        # Session-level accumulator (accumulates span roots)
        self.session_accumulator = VerkleAccumulator(f"{self.session_id}_session")
        self.session_accumulator_counter = 0  # Separate counter for session events
        
        # Track events by span
        self.events_by_span: Dict[str, list] = {}
        
        logger.info("hierarchical_verkle_middleware_initialized", session_id=self.session_id)
    
    def start_span(self, span_name: str) -> str:
        """
        Start a new span.
        
        Args:
            span_name: Name of the span (e.g., "mcp_initialize", "user_interaction")
            
        Returns:
            span_id: Unique identifier for this span
        """
        # Finalize current span if any
        if self.current_span_id:
            self._finalize_current_span()
        
        # Create new span
        self.current_span_id = f"{span_name}-{uuid.uuid4().hex[:8]}"
        span = SpanMetadata(
            span_id=self.current_span_id,
            name=span_name,
            start_time=self._get_server_timestamp(),
            start_index=self.counter,
        )
        self.spans[self.current_span_id] = span
        self.events_by_span[self.current_span_id] = []
        
        # Create span-level accumulator
        self.current_span_accumulator = VerkleAccumulator(
            f"{self.session_id}_{self.current_span_id}"
        )
        self.current_span_counter = 0  # Reset counter for new span
        
        logger.info("span_started", span_id=self.current_span_id, span_name=span_name)
        return self.current_span_id
    
    def record_event_in_span(
        self,
        event_type: str,
        payload: dict[str, Any],
        signer_id: str = "server"
    ) -> str:
        """
        Record an event within the current span.
        
        Args:
            event_type: Type of event (prompt, model_output, tool_input, tool_output, etc.)
            payload: Event payload
            signer_id: Who signed this (server or tool name)
            
        Returns:
            event_counter: The counter for this event
        """
        if not self.current_span_id:
            raise RuntimeError("No active span. Call start_span() first.")
        
        if self.finalized:
            raise RuntimeError("Cannot record events after finalization")
        
        # Sign payload
        signature = self._sign_payload(payload, signer_id)
        
        # Create event
        event = IntegrityEvent(
            session_id=self.session_id,
            counter=self.counter,
            timestamp=self._get_server_timestamp(),
            event_type=event_type,
            payload=payload,
            signature=signature,
            signer_id=signer_id
        )
        
        event_dict = asdict(event)
        event_dict["span_id"] = self.current_span_id
        
        # Add to session accumulator with global counter
        self.accumulator.add_event(event_dict)  # Session-level (redundancy)
        
        # Create span version with local counter for per-span root
        span_event_dict = asdict(event)
        span_event_dict["span_id"] = self.current_span_id
        span_event_dict["counter"] = self.current_span_counter  # Use span's local counter
        self.current_span_accumulator.add_event(span_event_dict)  # Span-level (for per-span root)
        
        # Track in span
        self.events_by_span[self.current_span_id].append(event_dict)
        
        self.counter += 1
        self.current_span_counter += 1  # Increment span-local counter
        
        return str(self.counter - 1)
    
    def _finalize_current_span(self) -> str:
        """
        Finalize the current span and compute its Verkle root.
        
        Returns:
            span_root: The Verkle root for this span (base64)
        """
        if not self.current_span_id:
            return None
        
        span = self.spans[self.current_span_id]
        
        # Finalize span accumulator
        self.current_span_accumulator.finalize()
        span_root = self.current_span_accumulator.get_root_b64()
        
        # Store span root
        span.end_time = self._get_server_timestamp()
        span.end_index = self.counter - 1
        span.event_count = len(self.events_by_span[self.current_span_id])
        span.verkle_root = span_root
        span.duration_ms = int(
            (datetime.fromisoformat(span.end_time) -
             datetime.fromisoformat(span.start_time)).total_seconds() * 1000
        )
        
        # Add span root to session accumulator as a synthetic event
        # This ensures session root is a function of all span roots
        span_commitment_event = {
            "session_id": self.session_id,
            "counter": self.session_accumulator_counter,  # Session accumulator counter
            "timestamp": span.end_time,
            "event_type": "span_commitment",
            "span_id": self.current_span_id,
            "span_name": span.name,
            "span_root": span_root,
            "event_count": span.event_count,
        }
        self.session_accumulator.add_event(span_commitment_event)
        self.session_accumulator_counter += 1  # Increment session counter
        self.span_roots[self.current_span_id] = span_root
        
        logger.info(
            "span_finalized",
            span_id=self.current_span_id,
            span_root=span_root,
            event_count=span.event_count
        )
        
        return span_root
    
    def finalize(self) -> Tuple[str, HierarchicalCommitments, bytes]:
        """
        Finalize entire session with hierarchical Verkle roots.
        
        Returns:
            (session_root, commitments, canonical_log_bytes)
        """
        if self.finalized:
            raise RuntimeError("Run already finalized")
        
        # Finalize last span
        if self.current_span_id:
            self._finalize_current_span()
        
        # Finalize event accumulator (all raw events)
        self.accumulator.finalize()
        event_accumulator_root = self.accumulator.get_root_b64()
        
        # Finalize session-level (all span roots)
        self.session_accumulator.finalize()
        session_root = self.session_accumulator.get_root_b64()
        
        # Get canonical log
        canonical_log = self.accumulator.get_canonical_log()
        if isinstance(canonical_log, str):
            canonical_log_bytes = canonical_log.encode('utf-8')
        else:
            canonical_log_bytes = canonical_log
        
        log_hash = hashlib.sha256(canonical_log_bytes).hexdigest()
        
        # Build commitments structure
        commitments = HierarchicalCommitments(
            session_root=session_root,
            event_accumulator_root=event_accumulator_root,
            span_roots=self.span_roots,
            canonical_log_hash=log_hash,
            event_count=self.counter,
            timestamp=self._get_server_timestamp(),
            otel_compliant=True
        )
        
        # Finalize Langfuse if available
        if self.langfuse_client and self.trace_id:
            try:
                self.langfuse_client.add_event_to_trace(
                    self.trace_id,
                    "commitment_finalized",
                    {
                        "session_root": session_root,
                        "span_count": len(self.spans),
                        "span_roots": self.span_roots,
                        "canonical_log_hash": log_hash,
                        "event_count": self.counter,
                        "verification_ready": True
                    }
                )
                self.langfuse_client.finalize_trace(self.trace_id)
            except Exception as e:
                logger.warning("langfuse_finalize_failed", error=str(e))
        
        self.finalized = True
        
        logger.info(
            "hierarchical_run_finalized",
            session_id=self.session_id,
            session_root=session_root,
            span_count=len(self.spans),
            event_count=self.counter
        )
        
        return (session_root, commitments, canonical_log_bytes)
    
    def export_to_otel_format(self) -> dict:
        """
        Export spans to OpenTelemetry format.
        
        Returns:
            dict: OpenTelemetry-compatible trace structure
        """
        trace_id = self.trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        
        otel_spans = []
        for span_id, span_meta in self.spans.items():
            # Convert ISO timestamps to milliseconds since epoch
            start_ms = int(
                datetime.fromisoformat(span_meta.start_time).timestamp() * 1000
            )
            end_ms = int(
                datetime.fromisoformat(span_meta.end_time).timestamp() * 1000
            ) if span_meta.end_time else start_ms
            
            otel_span = {
                "traceId": trace_id,
                "spanId": span_id,
                "parentSpanId": None,  # All spans are top-level for now
                "name": span_meta.name,
                "startTime": start_ms * 1_000_000,  # Convert to nanoseconds
                "endTime": end_ms * 1_000_000,
                "durationMillis": span_meta.duration_ms,
                "status": {
                    "code": "OK",
                    "description": ""
                },
                "attributes": {
                    "local_verkle_root": span_meta.verkle_root,
                    "event_indices": f"{span_meta.start_index}-{span_meta.end_index}",
                    "event_count": span_meta.event_count,
                    "session_id": self.session_id,
                    "span_index": list(self.spans.keys()).index(span_id),
                }
            }
            otel_spans.append(otel_span)
        
        return {
            "traceId": trace_id,
            "name": "verifiable_ai_workflow",
            "startTime": int(
                datetime.fromisoformat(self.spans[list(self.spans.keys())[0]].start_time).timestamp() * 1000 * 1_000_000
            ) if self.spans else 0,
            "endTime": int(
                datetime.fromisoformat(self.spans[list(self.spans.keys())[-1]].end_time).timestamp() * 1000 * 1_000_000
            ) if self.spans else 0,
            "spans": otel_spans,
            "metadata": {
                "integrity": {
                    "session_root_commitment": self.session_accumulator.get_root_b64() if not self.finalized else None,
                    "span_roots": self.span_roots,
                    "canonical_log_hash": hashlib.sha256(self.accumulator.get_canonical_log()).hexdigest(),
                    "event_count": self.counter,
                    "verification_ready": True,
                    "otel_compliant": True,
                    "session_id": self.session_id,
                }
            }
        }
    
    def save_to_local_storage(self, base_dir: Path) -> dict:
        """
        Save all data to local storage with hierarchical structure.
        
        Args:
            base_dir: Base directory for storage (e.g., Path("workflow_abc123"))
            
        Returns:
            dict: Summary of saved files and metadata
        """
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Save canonical log
        canonical_log = self.accumulator.get_canonical_log()
        log_path = base_dir / "canonical_log.jsonl"
        if isinstance(canonical_log, bytes):
            log_path.write_bytes(canonical_log)
        else:
            log_path.write_text(canonical_log)
        
        # 2. Save spans structure
        spans_data = {}
        for span_id, span_meta in self.spans.items():
            spans_data[span_id] = asdict(span_meta)
        
        spans_path = base_dir / "spans_structure.json"
        spans_path.write_text(json.dumps(spans_data, indent=2))
        
        # 3. Save commitments
        commitments_path = base_dir / "commitments.json"
        commitments_data = {
            "session_root": self.session_accumulator.get_root_b64() if self.finalized else None,
            "span_roots": self.span_roots,
        }
        commitments_path.write_text(json.dumps(commitments_data, indent=2))
        
        # 4. Save metadata
        metadata_path = base_dir / "metadata.json"
        metadata = {
            "session_id": self.session_id,
            "timestamp": self._get_server_timestamp(),
            "event_count": self.counter,
            "span_count": len(self.spans),
            "log_hash": hashlib.sha256(
                self.accumulator.get_canonical_log()
                if isinstance(self.accumulator.get_canonical_log(), bytes)
                else self.accumulator.get_canonical_log().encode('utf-8')
            ).hexdigest(),
            "canonical_log_file": "canonical_log.jsonl",
            "spans_file": "spans_structure.json",
            "commitments_file": "commitments.json",
            "otel_export_file": "otel_export.json",
        }
        metadata_path.write_text(json.dumps(metadata, indent=2))
        
        # 5. Save OTel export
        otel_export = self.export_to_otel_format()
        otel_path = base_dir / "otel_export.json"
        otel_path.write_text(json.dumps(otel_export, indent=2))
        
        # 6. Save recovery instructions
        recovery_path = base_dir / "RECOVERY.md"
        recovery_path.write_text(self._generate_recovery_instructions(base_dir))
        
        result = {
            "base_dir": str(base_dir),
            "canonical_log": str(log_path),
            "spans_structure": str(spans_path),
            "commitments": str(commitments_path),
            "metadata": str(metadata_path),
            "otel_export": str(otel_path),
            "recovery_instructions": str(recovery_path),
            "session_root": self.session_accumulator.get_root_b64() if not self.finalized else None,
        }
        
        logger.info("local_storage_saved", **result)
        return result
    
    def _generate_recovery_instructions(self, base_dir: Path) -> str:
        """Generate recovery instructions for accessing local proof"""
        session_root = self.session_accumulator.get_root_b64()
        
        return f"""# Recovery Instructions

## Overview
This directory contains cryptographically verifiable proof of an AI agent workflow.

## Files
- `canonical_log.jsonl`: All raw events (source of truth)
- `spans_structure.json`: OpenTelemetry span layout
- `commitments.json`: Verkle roots for verification
- `metadata.json`: Session metadata
- `otel_export.json`: OpenTelemetry format (for any OTel UI)

## Verification Levels

### Level 1: Quick Check (Instant)
```bash
python verify_cli check metadata {base_dir}/metadata.json
```

### Level 2: Local Verification (Complete)
```bash
python verify_cli verify local {base_dir} '{session_root}'
```

### Level 3: Deep Verification (Reconstructs Merkle)
```bash
python verify_cli verify --deep local {base_dir} '{session_root}'
```

### Level 4: Cross-Verify with OTel UI (If Langfuse exists)
```bash
python verify_cli verify --compare-otel local {base_dir} langfuse:trace-xxx
```

## Recovery from Data Loss

If Langfuse is deleted or unavailable:
1. You still have all events in `canonical_log.jsonl`
2. You have all span structure in `spans_structure.json`
3. You have cryptographic commitments in `commitments.json`
4. Run Level 3 verification to prove everything matches

## Support
For questions about verification, see:
- README.md in the project root
- verify_cli --help
- src/tools/verify_cli.py

Generated: {datetime.now(timezone.utc).isoformat()}
Session ID: {self.session_id}
Session Root: {session_root}
"""
