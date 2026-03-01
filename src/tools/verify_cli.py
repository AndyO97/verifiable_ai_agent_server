"""
Public verification CLI
Enables third-party validation of agent run integrity.

Usage:
    verify <canonical_log_path> <expected_root_b64> [--hash <expected_hash>]
    extract <canonical_log_path>
    export-proof <canonical_log_path> <expected_root_b64> [--output <path>]
"""

import base64
import json
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
import typer

from src.crypto.verkle import VerkleAccumulator

logger = structlog.get_logger(__name__)

app = typer.Typer(
    help="Verify the integrity of a verifiable AI agent run",
    pretty_exceptions_enable=True
)


def categorize_events(events: list) -> tuple:
    """
    Separate application events from protocol events.
    
    Protocol events are those with type starting with 'mcp_', 'jsonrpc_', or 'commitment_'.
    All others are application events.
    
    Returns:
        tuple: (app_events, protocol_events)
    """
    app_events = []
    protocol_events = []
    
    for event in events:
        event_type = event.get("type") or event.get("event_type", "")
        
        # Check if it's a protocol event
        if event_type.startswith(("mcp_", "jsonrpc_", "commitment_")):
            protocol_events.append(event)
        else:
            app_events.append(event)
    
    return app_events, protocol_events


def get_event_summary(event_type: str) -> str:
    """
    Return human-readable description of event type.
    """
    descriptions = {
        # Application events
        "user_prompt": "User Question",
        "model_output": "LLM Response",
        "tool_input": "Tool Called",
        "tool_output": "Tool Result",
        "prompt": "User Input",
        
        # Protocol events
        "mcp_initialize_request": "MCP Handshake Started",
        "mcp_initialize_response": "MCP Handshake Complete",
        "mcp_tools_call_request": "Tool Invocation Request",
        "mcp_tools_call_response": "Tool Invocation Response",
    }
    return descriptions.get(event_type, event_type)


def print_event_breakdown(app_events: list, protocol_events: list) -> None:
    """
    Print a formatted breakdown of application and protocol events.
    """
    total = len(app_events) + len(protocol_events)
    typer.echo(f"\n📊 Event Breakdown")
    typer.echo(f"  Total Events: {total}")
    
    # Application events
    if app_events:
        typer.echo(f"  ├─ Application Events: {len(app_events)}")
        app_event_types = {}
        for event in app_events:
            et = event.get("type") or event.get("event_type", "unknown")
            app_event_types[et] = app_event_types.get(et, 0) + 1
        
        for i, (event_type, count) in enumerate(sorted(app_event_types.items())):
            is_last_app = (i == len(app_event_types) - 1) and not protocol_events
            prefix = "  └─" if is_last_app else "  │  ├─"
            summary = get_event_summary(event_type)
            if summary != event_type:
                typer.echo(f"{prefix} {summary} ({event_type}): {count}")
            else:
                typer.echo(f"{prefix} {event_type}: {count}")
    
    # Protocol events
    if protocol_events:
        typer.echo(f"  └─ Protocol Events: {len(protocol_events)}")
        protocol_event_types = {}
        for event in protocol_events:
            et = event.get("type") or event.get("event_type", "unknown")
            protocol_event_types[et] = protocol_event_types.get(et, 0) + 1
        
        for i, (event_type, count) in enumerate(sorted(protocol_event_types.items())):
            is_last = i == len(protocol_event_types) - 1
            prefix = "     └─" if is_last else "     ├─"
            summary = get_event_summary(event_type)
            if summary != event_type:
                typer.echo(f"{prefix} {summary} ({event_type}): {count}")
            else:
                typer.echo(f"{prefix} {event_type}: {count}")


@app.command()
def verify(
    canonical_log_path: str = typer.Argument(..., help="Path to the canonical log file"),
    expected_root_b64: str = typer.Argument(..., help="Expected Verkle root (Base64-encoded)"),
    expected_hash: Optional[str] = typer.Option(None, "--expected-hash", help="Expected SHA-256 hash of canonical log (optional)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed verification steps"),
    show_protocol: bool = typer.Option(False, "--show-protocol", help="Show protocol event breakdown")
) -> None:
    """
    Verify an agent run by reconstructing the Verkle tree.
    
    Steps:
    1. Load canonical log from file (JSON array format, OTel-compliant)
    2. Verify hash if provided
    3. Parse events from log
    4. Reconstruct Verkle tree (skipping span_commitment events)
    5. Verify reconstructed span roots match stored commitments
    6. Compare session root against provided commitment
    
    Returns exit code 0 on success, 1 on verification failure.
    
    Example:
        verify ./workflow_xxx/canonical_log.json "YWJjZGVmZ2hp..." --hash "abc123..."
    """
    
    try:
        # Load canonical log
        log_path = Path(canonical_log_path)
        if not log_path.exists():
            typer.echo(f"[ERROR] Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        with open(log_path, "r", encoding="utf-8") as f:
            canonical_log_text = f.read()
        
        typer.echo(f"[OK] Loaded canonical log ({len(canonical_log_text):,} bytes)")
        
        # Verify hash if provided
        if expected_hash:
            if verbose:
                typer.echo("Computing SHA-256 hash...")
            
            actual_hash = hashlib.sha256(canonical_log_text.encode("utf-8")).hexdigest()
            if actual_hash != expected_hash:
                typer.echo(f"[ERROR] Hash mismatch!", err=True)
                typer.echo(f"  Expected: {expected_hash}", err=True)
                typer.echo(f"  Actual:   {actual_hash}", err=True)
                raise typer.Exit(1)
            
            typer.echo(f"[OK] Canonical log hash verified")
            if verbose:
                typer.echo(f"  Hash: {actual_hash[:16]}...")
        
        # Decode expected root
        try:
            expected_root = base64.b64decode(expected_root_b64)
        except Exception as e:
            typer.echo(f"[ERROR] Error: Invalid Base64 root: {e}", err=True)
            raise typer.Exit(1)
        
        if verbose:
            typer.echo(f"Expected root: {expected_root_b64[:20]}...")
        
        # Parse canonical log (JSON array format, containing ONLY events, no metadata)
        if verbose:
            typer.echo("Parsing canonical log...")
        
        events = []
        
        try:
            # Parse as JSON array
            data = json.loads(canonical_log_text)
            if isinstance(data, list):
                events = data
            else:
                # Single event
                events = [data]
        except json.JSONDecodeError as e:
            typer.echo(f"[ERROR] Error: Invalid JSON in log file: {e}", err=True)
            raise typer.Exit(1)
        
        if not events:
            typer.echo(f"[ERROR] Error: No events found in log", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"[OK] Parsed {len(events)} events from canonical log")
        
        # Extract span_names from events
        span_names = {}
        for event in events:
            span_id = event.get("span_id")
            span_name = event.get("span_name")
            if span_id and span_name and span_id not in span_names:
                span_names[span_id] = span_name
        
        # Load commitments to get expected span roots
        log_dir = Path(canonical_log_path).parent
        commitments_path = log_dir / "commitments.json"
        
        span_commitments = {}
        if commitments_path.exists():
            try:
                with open(commitments_path, "r") as f:
                    commitments_data = json.load(f)
                    span_roots_data = commitments_data.get("span_roots", {})
                    # Transform to dict with span_root and span_name
                    for span_id, span_root_b64 in span_roots_data.items():
                        span_commitments[span_id] = {
                            "span_root": span_root_b64,
                            "span_name": span_names.get(span_id, span_id)
                        }
                    if verbose:
                        typer.echo(f"[OK] Loaded {len(span_commitments)} span commitments from commitments.json")
            except Exception as e:
                typer.echo(f"[WARNING] Could not load commitments.json: {e}", err=True)
        
        # Extract session_id from first event
        session_id = events[0].get("session_id", "unknown")
        if verbose:
            typer.echo(f"  Session ID: {session_id}")
            typer.echo(f"  First event: {events[0].get('event_type', 'unknown')}")
            typer.echo(f"  Last event: {events[-1].get('event_type', 'unknown')}")
        
        # Categorize events if requested
        if show_protocol:
            app_events, protocol_events = categorize_events(events)
            print_event_breakdown(app_events, protocol_events)
        
        # Group events by span_id and reconstruct per-span Verkle trees
        if verbose:
            typer.echo("\nGrouping events by span...")
        
        events_by_span = {}
        for event in events:
            span_id = event.get("span_id", "unknown")
            if span_id not in events_by_span:
                events_by_span[span_id] = []
            events_by_span[span_id].append(event)
        
        if verbose:
            typer.echo(f"  Found {len(events_by_span)} unique spans")
        
        # Reconstruct per-span Verkle trees
        if verbose:
            typer.echo("\nVerifying per-span Verkle roots...")
        
        span_roots = {}  # span_id -> computed root
        
        for span_id, span_events in events_by_span.items():
            if verbose:
                typer.echo(f"  Span: {span_id}")
            
            # Initialize accumulator with span_id 
            # Note: Using the full span_id for consistency with recording
            accumulator = VerkleAccumulator(f"{session_id}_{span_id}")
            
            try:
                for i, event in enumerate(span_events):
                    # Reconstruct verification event with ONLY core fields (not metadata)
                    # Use 0-indexed position within span as the counter
                    # Extract attributes from canonical_log (matches storage structure)
                    attributes = event.get("attributes")  # From canonical_log.json structure
                    
                    # Only include core event fields - NO signature/signer_id (they're not hashed)
                    verification_event = {
                        "session_id": event.get("session_id"),
                        "counter": i,  # Per-span counter: 0, 1, 2...
                        "timestamp": event.get("timestamp"),  # Use stored timestamp, not new one
                        "event_type": event.get("event_type"),
                        "payload": attributes,  # Merkle accumulator field (from canonical attributes)
                        "span_id": event.get("span_id"),
                    }
                    
                    accumulator.add_event(verification_event)
                    if verbose and (i + 1) % max(1, len(span_events) // 5) == 0:
                        typer.echo(f"    Processed {i + 1}/{len(span_events)} events...")
            except Exception as e:
                typer.echo(f"[ERROR] Error processing event {i} in span {span_id}: {e}", err=True)
                raise typer.Exit(1)
            
            # Finalize and get computed root
            try:
                span_root = accumulator.finalize()
                span_roots[span_id] = span_root
                
                if verbose:
                    span_root_b64 = base64.b64encode(span_root).decode()
                    typer.echo(f"    Computed root: {span_root_b64[:20]}...")
            except Exception as e:
                typer.echo(f"[ERROR] Error finalizing Verkle tree for span {span_id}: {e}", err=True)
                raise typer.Exit(1)
        
        # Verify span commitments
        if verbose:
            typer.echo("\nVerifying span commitments...")
        
        all_spans_valid = True
        for span_id, commitment in span_commitments.items():
            if span_id in span_roots:
                expected_span_root_b64 = commitment.get("span_root")
                if expected_span_root_b64:
                    try:
                        expected_span_root = base64.b64decode(expected_span_root_b64)
                        computed_span_root = span_roots[span_id]
                        
                        if computed_span_root == expected_span_root:
                            if verbose:
                                typer.echo(f"  [OK] Span {span_id}: root matches")
                        else:
                            typer.echo(f"[ERROR] Span {span_id}: root mismatch", err=True)
                            typer.echo(f"    Expected: {expected_span_root_b64[:30]}...", err=True)
                            typer.echo(f"    Computed: {base64.b64encode(computed_span_root).decode()[:30]}...", err=True)
                            all_spans_valid = False
                    except Exception as e:
                        typer.echo(f"[ERROR] Error verifying span {span_id}: {e}", err=True)
                        raise typer.Exit(1)
        
        if not all_spans_valid:
            typer.echo(f"\n[ERROR] Verification FAILED: span root mismatch [ERROR]", err=True)
            raise typer.Exit(1)
        
        # Reconstruct session root from span roots
        if verbose:
            typer.echo("\nReconstructing session root from span roots...")
        
        session_accumulator = VerkleAccumulator(session_id)
        
        # Add span roots to session accumulator in sorted order
        # Must match exactly how recording does it in _finalize_current_span
        session_counter = 0
        for span_id in sorted(span_roots.keys()):
            span_root = span_roots[span_id]
            
            # Reconstruct span commitment event exactly as recorded
            # event_count must match the actual number of events in the span
            span_event_count = len(events_by_span.get(span_id, []))
            span_event = {
                "session_id": session_id,
                "counter": session_counter,  # Session-level span commitment counter
                "event_type": "span_commitment",
                "span_id": span_id,
                "span_name": span_commitments.get(span_id, {}).get("span_name", span_id),
                "span_root": base64.b64encode(span_root).decode(),  # Direct field, not in attributes
                "event_count": span_event_count,
            }
            session_counter += 1
            try:
                session_accumulator.add_event(span_event)
            except Exception as e:
                typer.echo(f"[ERROR] Error adding span root for {span_id}: {e}", err=True)
                raise typer.Exit(1)
        
        try:
            computed_root = session_accumulator.finalize()
        except Exception as e:
            typer.echo(f"[ERROR] Error finalizing session Verkle tree: {e}", err=True)
            raise typer.Exit(1)
        
        # Compare roots
        if computed_root == expected_root:
            if show_protocol:
                typer.echo(f"\n[OK] Verification PASSED [OK] (MCP Compliant)")
            else:
                typer.echo(f"\n[OK] Verification PASSED [OK]")
            typer.echo(f"  Session root matches: {base64.b64encode(computed_root).decode()[:20]}...")
            typer.echo(f"  Spans verified: {len(span_roots)}")
            typer.echo(f"  Events verified: {len(events)}")
            raise typer.Exit(0)
        else:
            typer.echo(f"\n[ERROR] Verification FAILED [ERROR]", err=True)
            typer.echo(f"  Expected root: {expected_root_b64[:30]}...", err=True)
            typer.echo(f"  Computed root: {base64.b64encode(computed_root).decode()[:30]}...", err=True)
            raise typer.Exit(1)
        
    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("verification_failed", error=str(e))
        typer.echo(f"[ERROR] Error during verification: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def extract(
    canonical_log_path: str = typer.Argument(..., help="Path to the canonical log file")
) -> None:
    """
    Extract and display metadata from a canonical log without verification.
    
    Shows:
    - Session ID
    - Event count and breakdown by type
    - Span count
    - Log hash (SHA-256)
    - File size
    
    Supports JSON array format (OTel-compliant).
    
    Example:
        extract ./workflow_xxx/canonical_log.json
    """
    
    try:
        log_path = Path(canonical_log_path)
        if not log_path.exists():
            typer.echo(f"[ERROR] Error: Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        with open(log_path, "rb") as f:
            canonical_log_bytes = f.read()
        
        canonical_log_text = canonical_log_bytes.decode("utf-8")
        
        # Parse JSON array format
        try:
            data = json.loads(canonical_log_text)
            if isinstance(data, list):
                events = data
            else:
                events = [data]
        except json.JSONDecodeError as e:
            typer.echo(f"[ERROR] Error: Invalid JSON in log file: {e}", err=True)
            raise typer.Exit(1)
        
        # Categorize events
        event_types = {}
        spans = set()
        
        for event in events:
            event_type = event.get("event_type", "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1
            
            span_id = event.get("span_id")
            if span_id:
                spans.add(span_id)
        
        # Extract metadata
        session_id = events[0].get("session_id", "unknown") if events else "unknown"
        log_hash = hashlib.sha256(canonical_log_bytes).hexdigest()
        
        typer.echo(f"\n{'='*60}")
        typer.echo(f"{'Canonical Log Metadata':<30}")
        typer.echo(f"{'='*60}\n")
        
        if events:
            first_event = events[0]
            last_event = events[-1]
            
            typer.echo(f"Session ID:        {session_id}")
            typer.echo(f"Event Count:       {len(events)}")
            typer.echo(f"Span Count:        {len(spans)}")
            typer.echo(f"File Size:         {len(canonical_log_bytes):,} bytes")
            typer.echo(f"SHA-256 Hash:      {log_hash}")
            
            typer.echo(f"\nEvent Types:")
            for et, count in sorted(event_types.items()):
                typer.echo(f"  {et:.<40} {count:>5} events")
            
            # Timestamps if available
            if "timestamp" in first_event:
                typer.echo(f"\nFirst Timestamp:   {first_event.get('timestamp', 'N/A')}")
            if "timestamp" in last_event:
                typer.echo(f"Last Timestamp:    {last_event.get('timestamp', 'N/A')}")
            
            # Counter if available
            if "counter" in first_event or "counter" in last_event:
                first_counter = first_event.get("counter", "N/A")
                last_counter = last_event.get("counter", "N/A")
                typer.echo(f"\nCounter Range:     {first_counter} → {last_counter}")
        
        typer.echo(f"\n{'='*60}\n")
        
    except Exception as e:
        logger.exception("extract_metadata_failed", error=str(e))
        typer.echo(f"[ERROR] Error: {e}", err=True)
        raise typer.Exit(1)



@app.command()
def export_proof(
    canonical_log_path: str = typer.Argument(..., help="Path to the canonical log file"),
    expected_root_b64: str = typer.Argument(..., help="Expected root commitment (base64)"),
    output: Optional[str] = typer.Option(None, "--output", help="Output file path (default: proof.json)"),
    include_events: bool = typer.Option(False, "--include-events", help="Include full events in proof (verbose)"),
    include_log: bool = typer.Option(False, "--include-log", help="Include entire log in proof")
) -> None:
    """
    Export a verification proof for audit trail and archival.
    
    Generates a JSON proof containing:
    - Metadata (session, event count, timestamps)
    - Root hash commitment
    - Log hash (SHA-256)
    - Verification status
    - Optional: Full events and canonical log
    
    Example:
        export-proof ./run_log.json "YWJjZGVmZ2hp..." --output proof.json
    """
    
    try:
        log_path = Path(canonical_log_path)
        if not log_path.exists():
            typer.echo(f"[ERROR] Error: Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        with open(log_path, "rb") as f:
            canonical_log = f.read()
        
        # Parse JSON
        try:
            log_data = json.loads(canonical_log.decode("utf-8"))
        except json.JSONDecodeError as e:
            typer.echo(f"[ERROR] Error: Invalid JSON in log file: {e}", err=True)
            raise typer.Exit(1)
        
        events = log_data if isinstance(log_data, list) else [log_data]
        
        # Compute root
        session_id = events[0].get("session_id", "unknown") if events else "unknown"
        accumulator = VerkleAccumulator(session_id)
        
        for event in events:
            accumulator.add_event(event)
        
        computed_root = accumulator.finalize()
        computed_root_b64 = base64.b64encode(computed_root).decode()
        
        # Build proof object
        proof = {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "session_id": session_id,
                "event_count": len(events),
                "file_size_bytes": len(canonical_log),
                "first_event_type": events[0].get("type", "unknown") if events else None,
                "last_event_type": events[-1].get("type", "unknown") if events else None,
                "first_timestamp": events[0].get("timestamp", None) if events else None,
                "last_timestamp": events[-1].get("timestamp", None) if events else None,
            },
            "verification": {
                "log_hash_sha256": hashlib.sha256(canonical_log).hexdigest(),
                "computed_root_b64": computed_root_b64,
                "expected_root_b64": expected_root_b64,
                "verification_passed": computed_root_b64 == expected_root_b64,
                "verification_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }
        
        # Optional: include events summary
        if include_events:
            event_types = {}
            for event in events:
                et = event.get("event_type", "unknown")
                event_types[et] = event_types.get(et, 0) + 1
            
            proof["event_summary"] = event_types
            proof["sample_events"] = [
                events[0],
                events[len(events)//2] if len(events) > 1 else None,
                events[-1]
            ]
        
        # Optional: include full log
        if include_log:
            proof["canonical_log_b64"] = base64.b64encode(canonical_log).decode()
        
        # Write proof to file
        output_path = Path(output) if output else Path("proof.json")
        with open(output_path, "w") as f:
            json.dump(proof, f, indent=2)
        
        # Output verification status
        verification_status = "[OK] Proof exported" if proof["verification"]["verification_passed"] else "[FAILED] Proof exported (verification failed)"
        typer.echo(f"{verification_status} to {output_path}")
        typer.echo(f"  Root commitment: {computed_root_b64[:20]}...")
        typer.echo(f"  Events: {len(events)}")
        typer.echo(f"  Size: {output_path.stat().st_size:,} bytes")
        if not proof["verification"]["verification_passed"]:
            typer.echo(f"  [FAILED] Root mismatch - verification failed")
        
        
    except Exception as e:
        logger.exception("export_proof_failed", error=str(e))
        typer.echo(f"[ERROR] Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def list_workflows(
    workflows_dir: str = typer.Option("workflows", "--dir", "-d", help="Path to workflows directory")
) -> None:
    """
    List all available workflows with their metadata.
    
    Shows:
    - Session ID
    - Timestamp
    - Session Root
    - Event count
    - Status
    
    Example:
        list-workflows
        list-workflows --dir ./my_workflows
    """
    try:
        base_path = Path(workflows_dir)
        if not base_path.exists():
            typer.echo(f"[ERROR] Workflows directory not found: {workflows_dir}", err=True)
            raise typer.Exit(1)
        
        # Find all workflow directories
        workflow_dirs = sorted([d for d in base_path.iterdir() if d.is_dir() and d.name.startswith("workflow_")])
        
        if not workflow_dirs:
            typer.echo(f"No workflows found in {workflows_dir}")
            raise typer.Exit(0)
        
        typer.echo(f"\n[WORKFLOWS] Available Workflows ({len(workflow_dirs)} total)\n")
        typer.echo(f"{'Session ID':<50} {'Timestamp':<25} {'Root':<20} {'Events':<8}")
        typer.echo("-" * 120)
        
        for workflow_dir in workflow_dirs:
            # Extract session ID from directory name
            session_id = workflow_dir.name.replace("workflow_", "")
            
            # Load metadata
            metadata_path = workflow_dir / "metadata.json"
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text())
                    timestamp = metadata.get("timestamp", "N/A")[:19]
                    event_count = metadata.get("event_count", "?")
                except:
                    timestamp = "Error reading"
                    event_count = "?"
            else:
                timestamp = "Unknown"
                event_count = "?"
            
            # Load commitments for root
            commitments_path = workflow_dir / "commitments.json"
            if commitments_path.exists():
                try:
                    commitments = json.loads(commitments_path.read_text())
                    session_root = commitments.get("session_root", "N/A")[:16] + "..."
                except:
                    session_root = "Error reading"
            else:
                session_root = "N/A"
            
            typer.echo(f"{session_id:<50} {timestamp:<25} {session_root:<20} {event_count:<8}")
        
        typer.echo()
        typer.echo("[NOTE] To verify a specific workflow:")
        typer.echo("   verify-by-id <session-id>")
        typer.echo("   get-workflow <session-id>")
        
    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("list_workflows_failed", error=str(e))
        typer.echo(f"[ERROR] Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def get_workflow(
    session_id: str = typer.Argument(..., help="Session ID to retrieve"),
    workflows_dir: str = typer.Option("workflows", "--dir", "-d", help="Path to workflows directory")
) -> None:
    """
    Get detailed metadata for a specific workflow.
    
    Shows:
    - Session ID
    - Timestamp
    - Session Root (full)
    - Event Accumulator Root
    - Span roots
    - Event count
    - Span count
    
    Example:
        get-workflow real-prompt-mcp-20260221-200134
    """
    try:
        base_path = Path(workflows_dir)
        workflow_dir = base_path / f"workflow_{session_id}"
        
        if not workflow_dir.exists():
            typer.echo(f"[ERROR] Workflow not found: {session_id}", err=True)
            typer.echo(f"  Searched in: {workflow_dir}", err=True)
            raise typer.Exit(1)
        
        # Load metadata
        metadata_path = workflow_dir / "metadata.json"
        if not metadata_path.exists():
            typer.echo(f"[ERROR] Metadata not found for workflow: {session_id}", err=True)
            raise typer.Exit(1)
        
        metadata = json.loads(metadata_path.read_text())
        
        # Load commitments
        commitments_path = workflow_dir / "commitments.json"
        if commitments_path.exists():
            commitments = json.loads(commitments_path.read_text())
        else:
            commitments = {}
        
        typer.echo(f"\n[WORKFLOW] Details: {session_id}\n")
        
        typer.echo(f"{typer.style('Metadata:', bold=True)}")
        typer.echo(f"  Timestamp: {metadata.get('timestamp', 'N/A')}")
        typer.echo(f"  Event Count: {metadata.get('event_count', 'N/A')}")
        typer.echo(f"  Span Count: {metadata.get('span_count', 'N/A')}")
        
        typer.echo(f"\n{typer.style('Cryptographic Commitments:', bold=True)}")
        typer.echo(f"  Session Root: {commitments.get('session_root', 'N/A')}")
        
        if 'span_roots' in commitments:
            typer.echo(f"\n{typer.style('Span Roots:', bold=True)}")
            for span_id, root in commitments['span_roots'].items():
                root_display = root if len(root) < 40 else root[:37] + "..."
                typer.echo(f"  {span_id}: {root_display}")
        
        # Show file paths
        typer.echo(f"\n{typer.style('Files:', bold=True)}")
        typer.echo(f"  Canonical Log: {workflow_dir / 'canonical_log.json'}")
        typer.echo(f"  Metadata: {metadata_path}")
        typer.echo(f"  Commitments: {commitments_path}")
        
        # Verification command
        session_root = commitments.get('session_root', '')
        typer.echo(f"\n{typer.style('Verification Commands:', bold=True)}")
        typer.echo(f"\n  {typer.style('Recommended (by session ID):', dim=True)}")
        typer.echo(f"    .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli verify-by-id {session_id}")
        if session_root:
            typer.echo(f"\n  {typer.style('Alternative (by file path):', dim=True)}")
            canonical_log = workflow_dir / 'canonical_log.json'
            typer.echo(f'    .\\venv\\Scripts\\Activate.ps1; python -m src.tools.verify_cli verify "{canonical_log}" \'{session_root}\'')
        
        typer.echo()
        
    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("get_workflow_failed", error=str(e))
        typer.echo(f"[ERROR] Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def verify_by_id(
    session_id: str = typer.Argument(..., help="Session ID to verify"),
    workflows_dir: str = typer.Option("workflows", "--dir", "-d", help="Path to workflows directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed verification steps"),
    show_protocol: bool = typer.Option(False, "--show-protocol", help="Show protocol event breakdown")
) -> None:
    """
    Verify a workflow by session ID.
    
    Automatically finds the workflow directory and verifies the canonical log.
    Supports both single-session workflows and multi-prompt conversation workflows.
    
    Example:
        verify-by-id real-prompt-mcp-20260221-200134
        verify-by-id chat-20260301-150522-361806 --verbose
    """
    try:
        base_path = Path(workflows_dir)
        workflow_dir = base_path / f"workflow_{session_id}"
        
        if not workflow_dir.exists():
            typer.echo(f"[ERROR] Workflow not found: {session_id}", err=True)
            typer.echo(f"  Searched in: {workflow_dir}", err=True)
            # Try to help user find it
            if base_path.exists():
                typer.echo(f"\n  Available workflows:", err=True)
                for d in sorted(base_path.iterdir())[:5]:
                    if d.is_dir() and d.name.startswith("workflow_"):
                        typer.echo(f"    {d.name.replace('workflow_', '')}", err=True)
            raise typer.Exit(1)
        
        # Load commitments
        commitments_path = workflow_dir / "commitments.json"
        if not commitments_path.exists():
            typer.echo(f"[ERROR] Commitments not found for workflow: {session_id}", err=True)
            raise typer.Exit(1)
        
        commitments = json.loads(commitments_path.read_text())
        
        # Detect conversation workflow vs single-session
        is_conversation = commitments.get("is_conversation", False) or "prompt_details" in commitments
        
        # Get the root (support both field names)
        root_b64 = commitments.get("session_root") or commitments.get("conversation_root")
        if not root_b64:
            typer.echo(f"[ERROR] No session_root or conversation_root found in commitments for: {session_id}", err=True)
            raise typer.Exit(1)
        
        # Get canonical log path
        canonical_log_path = workflow_dir / "canonical_log.json"
        if not canonical_log_path.exists():
            typer.echo(f"[ERROR] Canonical log not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        if is_conversation:
            _verify_conversation_workflow(
                session_id, workflow_dir, commitments, root_b64,
                canonical_log_path, verbose, show_protocol
            )
        else:
            _verify_single_session_workflow(
                session_id, workflow_dir, commitments, root_b64,
                canonical_log_path, verbose, show_protocol
            )
        
    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("verify_by_id_failed", error=str(e))
        typer.echo(f"[ERROR] Error during verification: {e}", err=True)
        raise typer.Exit(1)


def _verify_session_events(
    session_id: str,
    events: list,
    span_commitments: dict,
    verbose: bool = False,
) -> tuple[bytes, dict, dict]:
    """
    Verify a single session's events by reconstructing per-span Verkle trees
    and combining them into a session root.

    This is the core logic shared between single-session and conversation workflows.

    Args:
        session_id: The session ID (used for VerkleAccumulator naming)
        events: List of canonical log events belonging to this session
        span_commitments: Dict of span_id -> {"span_root": b64, "span_name": str}
        verbose: Whether to print detailed output

    Returns:
        tuple of (computed_root_bytes, span_roots_dict, events_by_span_dict)
    """
    # Extract span names from events
    span_names = {}
    for event in events:
        span_id = event.get("span_id")
        span_name = event.get("span_name")
        if span_id and span_name and span_id not in span_names:
            span_names[span_id] = span_name

    # Group events by span
    events_by_span = {}
    for event in events:
        span_id = event.get("span_id", "unknown")
        if span_id not in events_by_span:
            events_by_span[span_id] = []
        events_by_span[span_id].append(event)

    if verbose:
        typer.echo(f"  Found {len(events_by_span)} unique spans")

    # Reconstruct per-span Verkle trees
    if verbose:
        typer.echo(f"  Verifying per-span Verkle roots...")

    span_roots = {}

    for span_id, span_events in events_by_span.items():
        if verbose:
            typer.echo(f"    Span: {span_id}")

        accumulator = VerkleAccumulator(f"{session_id}_{span_id}")

        try:
            for i, event in enumerate(span_events):
                attributes = event.get("attributes")
                verification_event = {
                    "session_id": event.get("session_id"),
                    "counter": i,
                    "timestamp": event.get("timestamp"),
                    "event_type": event.get("event_type"),
                    "payload": attributes,
                    "span_id": event.get("span_id"),
                }
                accumulator.add_event(verification_event)
        except Exception as e:
            typer.echo(f"[ERROR] Error processing events in span {span_id}: {e}", err=True)
            raise typer.Exit(1)

        try:
            span_root = accumulator.finalize()
            span_roots[span_id] = span_root
            if verbose:
                typer.echo(f"      Computed root: {base64.b64encode(span_root).decode()[:20]}...")
        except Exception as e:
            typer.echo(f"[ERROR] Error finalizing Verkle tree for span {span_id}: {e}", err=True)
            raise typer.Exit(1)

    # Verify span commitments if available
    all_spans_valid = True
    for span_id, commitment in span_commitments.items():
        if span_id in span_roots:
            expected_span_root_b64 = commitment.get("span_root")
            if expected_span_root_b64:
                try:
                    expected_span_root = base64.b64decode(expected_span_root_b64)
                    if span_roots[span_id] == expected_span_root:
                        if verbose:
                            typer.echo(f"  [OK] Span {span_id}: root matches")
                    else:
                        typer.echo(f"[ERROR] Span {span_id}: root mismatch", err=True)
                        all_spans_valid = False
                except Exception as e:
                    typer.echo(f"[ERROR] Error verifying span {span_id}: {e}", err=True)
                    raise typer.Exit(1)

    if not all_spans_valid:
        typer.echo(f"\n[ERROR] Verification FAILED: span root mismatch [ERROR]", err=True)
        raise typer.Exit(1)

    # Reconstruct session root from span roots
    if verbose:
        typer.echo(f"  Reconstructing session root from span roots...")

    session_accumulator = VerkleAccumulator(session_id)
    session_counter = 0
    for span_id in sorted(span_roots.keys()):
        span_root = span_roots[span_id]
        span_event_count = len(events_by_span.get(span_id, []))
        span_event = {
            "session_id": session_id,
            "counter": session_counter,
            "event_type": "span_commitment",
            "span_id": span_id,
            "span_name": span_commitments.get(span_id, {}).get("span_name", span_names.get(span_id, span_id)),
            "span_root": base64.b64encode(span_root).decode(),
            "event_count": span_event_count,
        }
        session_counter += 1
        try:
            session_accumulator.add_event(span_event)
        except Exception as e:
            typer.echo(f"[ERROR] Error adding span root for {span_id}: {e}", err=True)
            raise typer.Exit(1)

    try:
        computed_root = session_accumulator.finalize()
    except Exception as e:
        typer.echo(f"[ERROR] Error finalizing session Verkle tree: {e}", err=True)
        raise typer.Exit(1)

    return computed_root, span_roots, events_by_span


def _verify_single_session_workflow(
    session_id: str,
    workflow_dir: Path,
    commitments: dict,
    root_b64: str,
    canonical_log_path: Path,
    verbose: bool,
    show_protocol: bool,
) -> None:
    """Verify a single-session (non-conversation) workflow."""
    typer.echo(f"Verifying workflow: {session_id}")
    if verbose:
        typer.echo(f"  Canonical Log: {canonical_log_path}")
        typer.echo(f"  Session Root: {root_b64[:30]}...\n")

    expected_root = base64.b64decode(root_b64)

    with open(canonical_log_path, "r", encoding="utf-8") as f:
        canonical_log_text = f.read()

    typer.echo(f"[OK] Loaded canonical log ({len(canonical_log_text):,} bytes)")

    # Parse events
    try:
        data = json.loads(canonical_log_text)
        events = [e for e in (data if isinstance(data, list) else [data])
                  if e.get("event_type") != "span_commitment"]
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Error: Invalid JSON in log file: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"[OK] Parsed {len(events)} events from canonical log")

    if show_protocol:
        app_events, protocol_events = categorize_events(events)
        print_event_breakdown(app_events, protocol_events)

    # Load span commitments
    span_names = {}
    for event in events:
        sid = event.get("span_id")
        sname = event.get("span_name")
        if sid and sname and sid not in span_names:
            span_names[sid] = sname

    span_commitments = {}
    for span_id, span_root_b64 in commitments.get("span_roots", {}).items():
        span_commitments[span_id] = {
            "span_root": span_root_b64,
            "span_name": span_names.get(span_id, span_id),
        }

    # Verify
    computed_root, span_roots, events_by_span = _verify_session_events(
        session_id, events, span_commitments, verbose
    )

    if computed_root == expected_root:
        if show_protocol:
            typer.echo(f"\n[OK] Verification PASSED [OK] (MCP Compliant)")
        else:
            typer.echo(f"\n[OK] Verification PASSED [OK]")
        typer.echo(f"  Session ID: {session_id}")
        typer.echo(f"  Root matches: {root_b64[:30]}...")
        typer.echo(f"  Spans verified: {len(span_roots)}")
        typer.echo(f"  Events verified: {len(events)}")
        raise typer.Exit(0)
    else:
        typer.echo(f"\n[ERROR] Verification FAILED [ERROR]", err=True)
        typer.echo(f"  Expected root: {root_b64[:30]}...", err=True)
        typer.echo(f"  Computed root: {base64.b64encode(computed_root).decode()[:30]}...", err=True)
        raise typer.Exit(1)


def _verify_conversation_workflow(
    session_id: str,
    workflow_dir: Path,
    commitments: dict,
    conversation_root_b64: str,
    canonical_log_path: Path,
    verbose: bool,
    show_protocol: bool,
) -> None:
    """
    Verify a conversation workflow with multiple prompts.

    Each prompt has its own session (with its own spans and session root).
    The conversation root is a Verkle accumulator over all prompt session roots.
    """
    prompt_details = commitments.get("prompt_details", [])
    prompt_count = commitments.get("prompt_count", len(prompt_details))

    typer.echo(f"Verifying conversation: {session_id}")
    typer.echo(f"  Prompts: {prompt_count}")
    if verbose:
        typer.echo(f"  Canonical Log: {canonical_log_path}")
        typer.echo(f"  Conversation Root: {conversation_root_b64[:30]}...\n")

    expected_conversation_root = base64.b64decode(conversation_root_b64)

    # Load canonical log
    with open(canonical_log_path, "r", encoding="utf-8") as f:
        canonical_log_text = f.read()

    try:
        all_events = json.loads(canonical_log_text)
        if not isinstance(all_events, list):
            all_events = [all_events]
        all_events = [e for e in all_events if e.get("event_type") != "span_commitment"]
    except json.JSONDecodeError as e:
        typer.echo(f"[ERROR] Error: Invalid JSON in log file: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"[OK] Loaded canonical log ({len(canonical_log_text):,} bytes, {len(all_events)} events)")

    if show_protocol:
        app_events, protocol_events = categorize_events(all_events)
        print_event_breakdown(app_events, protocol_events)

    # Group events by prompt session_id
    events_by_prompt = {}
    for event in all_events:
        event_session_id = event.get("session_id", "unknown")
        if event_session_id not in events_by_prompt:
            events_by_prompt[event_session_id] = []
        events_by_prompt[event_session_id].append(event)

    if verbose:
        typer.echo(f"\n  Found {len(events_by_prompt)} prompt sessions in canonical log")

    # Verify each prompt session and collect prompt roots
    computed_prompt_roots = []
    total_spans_verified = 0

    for i, prompt_detail in enumerate(prompt_details):
        prompt_session_id = prompt_detail.get("prompt_session_id")
        expected_prompt_root_b64 = prompt_detail.get("prompt_root")

        if not prompt_session_id or not expected_prompt_root_b64:
            typer.echo(f"[ERROR] Missing prompt_session_id or prompt_root for prompt {i}", err=True)
            raise typer.Exit(1)

        expected_prompt_root = base64.b64decode(expected_prompt_root_b64)

        prompt_events = events_by_prompt.get(prompt_session_id, [])
        if not prompt_events:
            typer.echo(f"[ERROR] No events found for prompt session: {prompt_session_id}", err=True)
            raise typer.Exit(1)

        typer.echo(f"\n  Prompt {i}: {prompt_session_id} ({len(prompt_events)} events)")

        # Build span commitments for this prompt
        prompt_span_commitments = {}
        prompt_span_roots = prompt_detail.get("span_roots", {})
        for span_id, span_root_b64 in prompt_span_roots.items():
            # Get span name from events
            span_name = span_id
            for event in prompt_events:
                if event.get("span_id") == span_id and event.get("span_name"):
                    span_name = event["span_name"]
                    break
            prompt_span_commitments[span_id] = {
                "span_root": span_root_b64,
                "span_name": span_name,
            }

        # Verify this prompt's session
        computed_prompt_root, span_roots, _ = _verify_session_events(
            prompt_session_id, prompt_events, prompt_span_commitments, verbose
        )

        total_spans_verified += len(span_roots)

        # Check prompt root matches
        if computed_prompt_root == expected_prompt_root:
            typer.echo(f"  [OK] Prompt {i}: session root verified ({expected_prompt_root_b64[:20]}...)")
            computed_prompt_roots.append((prompt_session_id, expected_prompt_root_b64))
        else:
            typer.echo(f"[ERROR] Prompt {i}: session root mismatch", err=True)
            typer.echo(f"  Expected: {expected_prompt_root_b64[:30]}...", err=True)
            typer.echo(f"  Computed: {base64.b64encode(computed_prompt_root).decode()[:30]}...", err=True)
            raise typer.Exit(1)

    # Reconstruct conversation root from prompt roots
    # Must match conversation_manager.py: VerkleAccumulator with add_event for each prompt_root
    if verbose:
        typer.echo(f"\n  Reconstructing conversation root from {len(computed_prompt_roots)} prompt roots...")

    conversation_accumulator = VerkleAccumulator(f"{session_id}_conversation")
    for i, (prompt_session_id, prompt_root_b64) in enumerate(computed_prompt_roots):
        conversation_accumulator.add_event({
            "counter": i,
            "type": "prompt_root",
            "session_id": prompt_session_id,
            "prompt_root": prompt_root_b64,
        })

    try:
        computed_conversation_root = conversation_accumulator.finalize()
    except Exception as e:
        typer.echo(f"[ERROR] Error finalizing conversation Verkle tree: {e}", err=True)
        raise typer.Exit(1)

    # Compare conversation roots
    if computed_conversation_root == expected_conversation_root:
        typer.echo(f"\n[OK] Conversation Verification PASSED [OK]")
        typer.echo(f"  Session ID: {session_id}")
        typer.echo(f"  Conversation root matches: {conversation_root_b64[:30]}...")
        typer.echo(f"  Prompts verified: {len(computed_prompt_roots)}")
        typer.echo(f"  Spans verified: {total_spans_verified}")
        typer.echo(f"  Events verified: {len(all_events)}")
        raise typer.Exit(0)
    else:
        typer.echo(f"\n[ERROR] Conversation Verification FAILED [ERROR]", err=True)
        typer.echo(f"  Expected root: {conversation_root_b64[:30]}...", err=True)
        typer.echo(f"  Computed root: {base64.b64encode(computed_conversation_root).decode()[:30]}...", err=True)
        raise typer.Exit(1)


def main() -> None:
    """Entry point for CLI"""
    app()


if __name__ == "__main__":
    main()
