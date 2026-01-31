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


@app.command()
def verify(
    canonical_log_path: str = typer.Argument(..., help="Path to the canonical log file"),
    expected_root_b64: str = typer.Argument(..., help="Expected Verkle root (Base64-encoded)"),
    expected_hash: Optional[str] = typer.Option(None, "--expected-hash", help="Expected SHA-256 hash of canonical log (optional)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed verification steps")
) -> None:
    """
    Verify an agent run by reconstructing the Verkle tree.
    
    Steps:
    1. Load canonical log from file
    2. Verify hash if provided
    3. Parse events from log
    4. Recompute Verkle root via KZG commitment
    5. Compare against provided commitment
    
    Returns exit code 0 on success, 1 on verification failure.
    
    Example:
        verify ./run_log.json "YWJjZGVmZ2hp..." --hash "abc123..."
    """
    
    try:
        # Load canonical log
        log_path = Path(canonical_log_path)
        if not log_path.exists():
            typer.echo(f"✗ Error: Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        with open(log_path, "r", encoding="utf-8") as f:
            canonical_log = f.read()
        
        typer.echo(f"✓ Loaded canonical log ({len(canonical_log):,} bytes)")
        
        # Verify hash if provided
        if expected_hash:
            if verbose:
                typer.echo("Computing SHA-256 hash...")
            
            actual_hash = hashlib.sha256(canonical_log.encode("utf-8")).hexdigest()
            if actual_hash != expected_hash:
                typer.echo(f"✗ Hash mismatch!", err=True)
                typer.echo(f"  Expected: {expected_hash}", err=True)
                typer.echo(f"  Actual:   {actual_hash}", err=True)
                raise typer.Exit(1)
            
            typer.echo(f"✓ Canonical log hash verified")
            if verbose:
                typer.echo(f"  Hash: {actual_hash[:16]}...")
        
        # Decode expected root
        try:
            expected_root = base64.b64decode(expected_root_b64)
        except Exception as e:
            typer.echo(f"✗ Error: Invalid Base64 root: {e}", err=True)
            raise typer.Exit(1)
        
        if verbose:
            typer.echo(f"Expected root: {expected_root_b64[:20]}...")
        
        # Parse canonical log to extract events
        if verbose:
            typer.echo("Parsing canonical log...")
        
        try:
            log_data = json.loads(canonical_log)
        except json.JSONDecodeError as e:
            typer.echo(f"✗ Error: Invalid JSON in log file: {e}", err=True)
            raise typer.Exit(1)
        
        # Handle both single event and array of events
        events = log_data if isinstance(log_data, list) else [log_data]
        
        if not events:
            typer.echo(f"✗ Error: No events found in log", err=True)
            raise typer.Exit(1)
        
        typer.echo(f"✓ Parsed {len(events)} events from log")
        
        # Extract session_id from first event
        session_id = events[0].get("session_id", "unknown")
        if verbose:
            typer.echo(f"  Session ID: {session_id}")
            typer.echo(f"  First event: {events[0].get('event_type', 'unknown')}")
            typer.echo(f"  Last event: {events[-1].get('event_type', 'unknown')}")
        
        # Reconstruct tree and verify root
        if verbose:
            typer.echo("\nVerifying Verkle tree root...")
        else:
            typer.echo("Verifying Verkle tree root...")
        
        accumulator = VerkleAccumulator(session_id)
        
        for i, event in enumerate(events):
            try:
                accumulator.add_event(event)
                if verbose and (i + 1) % max(1, len(events) // 10) == 0:
                    typer.echo(f"  Processed {i + 1}/{len(events)} events...")
            except Exception as e:
                typer.echo(f"✗ Error processing event {i}: {e}", err=True)
                raise typer.Exit(1)
        
        # Finalize and get computed root
        try:
            computed_root = accumulator.finalize()
        except Exception as e:
            typer.echo(f"✗ Error finalizing Verkle tree: {e}", err=True)
            raise typer.Exit(1)
        
        # Compare roots
        if computed_root == expected_root:
            typer.echo(f"\n✓ Verification PASSED ✓")
            typer.echo(f"  Root matches: {base64.b64encode(computed_root).decode()[:20]}...")
            typer.echo(f"  Events verified: {len(events)}")
            raise typer.Exit(0)
        else:
            typer.echo(f"\n✗ Verification FAILED ✗", err=True)
            typer.echo(f"  Expected root: {expected_root_b64[:30]}...", err=True)
            typer.echo(f"  Computed root: {base64.b64encode(computed_root).decode()[:30]}...", err=True)
            raise typer.Exit(1)
        
    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("verification_failed", error=str(e))
        typer.echo(f"✗ Error during verification: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def extract(
    canonical_log_path: str = typer.Argument(..., help="Path to the canonical log file")
) -> None:
    """
    Extract and display metadata from a canonical log without verification.
    
    Shows:
    - Session ID
    - Event count
    - Event types
    - Log hash (SHA-256)
    - File size
    
    Example:
        extract ./run_log.json
    """
    
    try:
        log_path = Path(canonical_log_path)
        if not log_path.exists():
            typer.echo(f"✗ Error: Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        with open(log_path, "rb") as f:
            canonical_log = f.read()
        
        # Parse JSON
        try:
            log_data = json.loads(canonical_log.decode("utf-8"))
        except json.JSONDecodeError as e:
            typer.echo(f"✗ Error: Invalid JSON in log file: {e}", err=True)
            raise typer.Exit(1)
        
        # Handle both single event and array of events
        events = log_data if isinstance(log_data, list) else [log_data]
        
        typer.echo(f"\n{'='*60}")
        typer.echo(f"{'Canonical Log Metadata':<30}")
        typer.echo(f"{'='*60}\n")
        
        if events:
            first_event = events[0]
            last_event = events[-1]
            
            session_id = first_event.get("session_id", "unknown")
            typer.echo(f"Session ID:        {session_id}")
            typer.echo(f"Event Count:       {len(events)}")
            typer.echo(f"File Size:         {len(canonical_log):,} bytes")
            
            # Compute hash
            log_hash = hashlib.sha256(canonical_log).hexdigest()
            typer.echo(f"SHA-256 Hash:      {log_hash}")
            
            # Event types
            event_types = {}
            for event in events:
                et = event.get("event_type", "unknown")
                event_types[et] = event_types.get(et, 0) + 1
            
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
        typer.echo(f"✗ Error: {e}", err=True)
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
            typer.echo(f"✗ Error: Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        with open(log_path, "rb") as f:
            canonical_log = f.read()
        
        # Parse JSON
        try:
            log_data = json.loads(canonical_log.decode("utf-8"))
        except json.JSONDecodeError as e:
            typer.echo(f"✗ Error: Invalid JSON in log file: {e}", err=True)
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
        verification_status = "✓ Proof exported" if proof["verification"]["verification_passed"] else "✗ Proof exported (FAILED verification)"
        typer.echo(f"{verification_status} to {output_path}")
        typer.echo(f"  Root commitment: {computed_root_b64[:20]}...")
        typer.echo(f"  Events: {len(events)}")
        typer.echo(f"  Size: {output_path.stat().st_size:,} bytes")
        if not proof["verification"]["verification_passed"]:
            typer.echo(f"  [FAILED] Root mismatch - verification failed")
        
        
    except Exception as e:
        logger.exception("export_proof_failed", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1)


def main() -> None:
    """Entry point for CLI"""
    app()


if __name__ == "__main__":
    main()
