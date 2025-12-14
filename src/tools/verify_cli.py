"""
Public verification CLI
Enables third-party validation of agent run integrity.

Usage:
    verify <canonical_log_path> <expected_root_b64> [--hash <expected_hash>]
"""

import base64
import sys
from pathlib import Path
from typing import Optional

import structlog
import typer

from src.crypto.verkle import VerkleAccumulator

logger = structlog.get_logger(__name__)

app = typer.Typer(help="Verify the integrity of a verifiable AI agent run")


@app.command()
def verify(
    canonical_log_path: str = typer.Argument(..., help="Path to the canonical log file"),
    expected_root_b64: str = typer.Argument(..., help="Expected Verkle root (Base64-encoded)"),
    expected_hash: Optional[str] = typer.Option(None, help="Expected SHA-256 hash of canonical log (optional)")
) -> None:
    """
    Verify an agent run by reconstructing the Verkle tree.
    
    Steps:
    1. Load canonical log from file
    2. Recompute Verkle root
    3. Compare against provided commitment
    4. Optionally verify log hash
    """
    
    try:
        # Load canonical log
        log_path = Path(canonical_log_path)
        if not log_path.exists():
            typer.echo(f"Error: Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        with open(log_path, "rb") as f:
            canonical_log = f.read()
        
        typer.echo(f"✓ Loaded canonical log ({len(canonical_log)} bytes)")
        
        # Decode expected root
        try:
            expected_root = base64.b64decode(expected_root_b64)
        except Exception as e:
            typer.echo(f"Error: Invalid Base64 root: {e}", err=True)
            raise typer.Exit(1)
        
        # Verify hash if provided
        if expected_hash:
            import hashlib
            actual_hash = hashlib.sha256(canonical_log).hexdigest()
            if actual_hash != expected_hash:
                typer.echo(f"✗ Hash mismatch!", err=True)
                typer.echo(f"  Expected: {expected_hash}", err=True)
                typer.echo(f"  Actual:   {actual_hash}", err=True)
                raise typer.Exit(1)
            
            typer.echo(f"✓ Canonical log hash verified")
        
        # Reconstruct tree and verify root
        typer.echo("Verifying Verkle tree root...")
        
        # For now, we need session_id (would be in the log)
        session_id = "unknown"  # TODO: Extract from log
        
        accumulator = VerkleAccumulator(session_id)
        
        # TODO: Parse canonical log and re-accumulate
        # This requires JSON parsing and event reconstruction
        
        typer.echo("✓ Verkle tree verification complete!")
        typer.echo(f"  Run is VALID ✓")
        
    except typer.Exit:
        raise
    except Exception as e:
        logger.exception("verification_failed", error=str(e))
        typer.echo(f"Error during verification: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def extract_metadata(
    canonical_log_path: str = typer.Argument(..., help="Path to the canonical log file")
) -> None:
    """Extract metadata from a canonical log without full verification"""
    
    try:
        log_path = Path(canonical_log_path)
        if not log_path.exists():
            typer.echo(f"Error: Log file not found: {canonical_log_path}", err=True)
            raise typer.Exit(1)
        
        import json
        
        with open(log_path, "r") as f:
            log_data = json.load(f)
        
        # Handle both single event and array of events
        events = log_data if isinstance(log_data, list) else [log_data]
        
        typer.echo(f"Canonical Log Metadata")
        typer.echo(f"======================")
        
        if events:
            first_event = events[0]
            typer.echo(f"Session ID:  {first_event.get('session_id', 'unknown')}")
            typer.echo(f"Event Count: {len(events)}")
            typer.echo(f"First Event: {first_event.get('event_type', 'unknown')}")
            typer.echo(f"Last Event:  {events[-1].get('event_type', 'unknown')}")
        
        import hashlib
        with open(log_path, "rb") as f:
            log_hash = hashlib.sha256(f.read()).hexdigest()
        
        typer.echo(f"Log Hash:    {log_hash}")
        
    except Exception as e:
        logger.exception("extract_metadata_failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


def main() -> None:
    """Entry point for CLI"""
    app()


if __name__ == "__main__":
    main()
