"""
Tests for the verification CLI module.

Tests include:
- Verify command with valid log and commitment
- Verify command with mismatched commitments
- Extract metadata command
- Export proof command with various options
- Hash verification
- Error handling for invalid inputs
"""

import base64
import json
import hashlib
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.crypto.verkle import VerkleAccumulator
from src.tools.verify_cli import app
from typer.testing import CliRunner


@pytest.fixture
def cli_runner() -> CliRunner:
    """CLI test runner"""
    return CliRunner()


@pytest.fixture
def sample_events() -> list[dict[str, Any]]:
    """Create sample events for testing"""
    return [
        {
            "session_id": "test_session_1",
            "event_type": "agent_started",
            "counter": 0,
            "timestamp": "2025-01-02T12:00:00.000Z",
            "data": {"action": "initialize"}
        },
        {
            "session_id": "test_session_1",
            "event_type": "tool_call",
            "counter": 1,
            "timestamp": "2025-01-02T12:00:01.000Z",
            "data": {"tool": "search", "query": "test query"}
        },
        {
            "session_id": "test_session_1",
            "event_type": "llm_response",
            "counter": 2,
            "timestamp": "2025-01-02T12:00:02.000Z",
            "data": {"model": "mistral-7b", "tokens": 150}
        },
        {
            "session_id": "test_session_1",
            "event_type": "agent_completed",
            "counter": 3,
            "timestamp": "2025-01-02T12:00:03.000Z",
            "data": {"status": "success"}
        }
    ]


@pytest.fixture
def log_file_with_commitment(sample_events: list[dict[str, Any]], tmp_path: Path) -> tuple[Path, str, str]:
    """Create a temporary log file and compute its commitment"""
    # Create accumulator and compute commitment
    session_id = sample_events[0]["session_id"]
    accumulator = VerkleAccumulator(session_id)
    
    for event in sample_events:
        accumulator.add_event(event)
    
    root = accumulator.finalize()
    root_b64 = base64.b64encode(root).decode()
    
    # Write events to temporary file
    temp_file = tmp_path / f"test_log_{session_id}.json"
    with open(temp_file, "w") as f:
        json.dump(sample_events, f)
    
    log_hash = hashlib.sha256(json.dumps(sample_events).encode()).hexdigest()
    
    yield temp_file, root_b64, log_hash
    
    # Cleanup
    if temp_file.exists():
        temp_file.unlink()


class TestVerifyCommand:
    """Tests for the verify command"""
    
    def test_verify_with_valid_commitment(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test successful verification with valid commitment"""
        log_file, root_b64, _ = log_file_with_commitment
        
        result = cli_runner.invoke(
            app,
            ["verify", str(log_file), root_b64]
        )
        
        assert result.exit_code == 0
        assert "Verification PASSED" in result.stdout
        assert "Root matches" in result.stdout
        assert "4" in result.stdout  # 4 events
    
    def test_verify_with_hash_validation(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test verification with hash validation"""
        log_file, root_b64, log_hash = log_file_with_commitment
        
        result = cli_runner.invoke(
            app,
            ["verify", str(log_file), root_b64, "--expected-hash", log_hash]
        )
        
        assert result.exit_code == 0
        assert "Canonical log hash verified" in result.stdout
        assert "Verification PASSED" in result.stdout
    
    def test_verify_with_wrong_hash(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test verification fails with wrong hash"""
        log_file, root_b64, _ = log_file_with_commitment
        wrong_hash = "abcdef" * 10  # Invalid hash
        
        result = cli_runner.invoke(
            app,
            ["verify", str(log_file), root_b64, "--expected-hash", wrong_hash]
        )
        
        assert result.exit_code == 1
        assert "Hash mismatch" in result.stdout or "Hash mismatch" in result.stderr
    
    def test_verify_with_wrong_root(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test verification fails with wrong root"""
        log_file, _, _ = log_file_with_commitment
        wrong_root = base64.b64encode(b"wrong_root_data_here" * 3).decode()
        
        result = cli_runner.invoke(
            app,
            ["verify", str(log_file), wrong_root]
        )
        
        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "Verification FAILED" in output or "FAILED" in output
    
    def test_verify_with_nonexistent_file(self, cli_runner: CliRunner) -> None:
        """Test verification fails with nonexistent file"""
        fake_root = base64.b64encode(b"x" * 48).decode()
        
        result = cli_runner.invoke(
            app,
            ["verify", "/nonexistent/path/log.json", fake_root]
        )
        
        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "Log file not found" in output or "not found" in output
    
    def test_verify_with_invalid_json(self, cli_runner: CliRunner) -> None:
        """Test verification fails with invalid JSON"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            temp_file = f.name
        
        try:
            fake_root = base64.b64encode(b"x" * 48).decode()
            
            result = cli_runner.invoke(
                app,
                ["verify", temp_file, fake_root]
            )
            
            assert result.exit_code == 1
            output = result.stdout + (result.stderr or "")
            assert "Invalid JSON" in output or "JSON" in output
        finally:
            Path(temp_file).unlink()
    
    def test_verify_with_invalid_base64_root(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test verification fails with invalid Base64 root"""
        log_file, _, _ = log_file_with_commitment
        invalid_root = "not-valid-base64!!!@#$"
        
        result = cli_runner.invoke(
            app,
            ["verify", str(log_file), invalid_root]
        )
        
        assert result.exit_code == 1
        output = result.stdout + (result.stderr or "")
        assert "Invalid Base64" in output or "Base64" in output
    
    def test_verify_verbose_mode(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test verbose mode provides detailed output"""
        log_file, root_b64, _ = log_file_with_commitment
        
        result = cli_runner.invoke(
            app,
            ["verify", str(log_file), root_b64, "--verbose"]
        )
        
        assert result.exit_code == 0
        assert "test_session_1" in result.stdout
        assert "Parsed 4 events" in result.stdout
        assert "Verification PASSED" in result.stdout


class TestExtractCommand:
    """Tests for the extract command"""
    
    def test_extract_metadata(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test metadata extraction"""
        log_file, _, _ = log_file_with_commitment
        
        result = cli_runner.invoke(
            app,
            ["extract", str(log_file)]
        )
        
        assert result.exit_code == 0
        assert "Canonical Log Metadata" in result.stdout
        assert "test_session_1" in result.stdout
        assert "Event Count:       4" in result.stdout
        assert "agent_started" in result.stdout
        assert "tool_call" in result.stdout
    
    def test_extract_with_nonexistent_file(self, cli_runner: CliRunner) -> None:
        """Test extract fails with nonexistent file"""
        result = cli_runner.invoke(
            app,
            ["extract", "/nonexistent/path/log.json"]
        )
        
        assert result.exit_code == 1
        assert "Log file not found" in result.stdout
    
    def test_extract_with_invalid_json(self, cli_runner: CliRunner) -> None:
        """Test extract fails with invalid JSON"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ broken json [[[")
            temp_file = f.name
        
        try:
            result = cli_runner.invoke(
                app,
                ["extract", temp_file]
            )
            
            assert result.exit_code == 1
            assert "Invalid JSON" in result.stdout
        finally:
            Path(temp_file).unlink()


class TestExportProofCommand:
    """Tests for the export-proof command"""
    
    def test_export_proof_basic(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test basic proof export"""
        log_file, root_b64, _ = log_file_with_commitment
        
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_file = Path(tmpdir) / "proof.json"
            
            result = cli_runner.invoke(
                app,
                ["export-proof", str(log_file), root_b64, "--output", str(proof_file)]
            )
            
            assert result.exit_code == 0
            assert "Proof exported" in result.stdout
            assert proof_file.exists()
            
            # Verify proof structure
            with open(proof_file) as f:
                proof = json.load(f)
            
            assert "version" in proof
            assert "metadata" in proof
            assert "verification" in proof
            assert proof["metadata"]["event_count"] == 4
            assert proof["verification"]["verification_passed"] is True
    
    def test_export_proof_with_events(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test proof export with event summary"""
        log_file, root_b64, _ = log_file_with_commitment
        
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_file = Path(tmpdir) / "proof_with_events.json"
            
            result = cli_runner.invoke(
                app,
                [
                    "export-proof", str(log_file), root_b64,
                    "--output", str(proof_file),
                    "--include-events"
                ]
            )
            
            assert result.exit_code == 0
            
            with open(proof_file) as f:
                proof = json.load(f)
            
            assert "event_summary" in proof
            assert "sample_events" in proof
            assert proof["event_summary"]["agent_started"] == 1
            assert proof["event_summary"]["tool_call"] == 1
    
    def test_export_proof_with_log(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test proof export with full log included"""
        log_file, root_b64, _ = log_file_with_commitment
        
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_file = Path(tmpdir) / "proof_with_log.json"
            
            result = cli_runner.invoke(
                app,
                [
                    "export-proof", str(log_file), root_b64,
                    "--output", str(proof_file),
                    "--include-log"
                ]
            )
            
            assert result.exit_code == 0
            
            with open(proof_file) as f:
                proof = json.load(f)
            
            assert "canonical_log_b64" in proof
            
            # Verify we can decode it
            decoded_log = json.loads(
                base64.b64decode(proof["canonical_log_b64"]).decode()
            )
            assert len(decoded_log) == 4
    
    def test_export_proof_with_failed_verification(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test proof export when verification fails"""
        log_file, _, _ = log_file_with_commitment
        wrong_root = base64.b64encode(b"wrong_data" * 5).decode()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_file = Path(tmpdir) / "failed_proof.json"
            
            result = cli_runner.invoke(
                app,
                [
                    "export-proof", str(log_file), wrong_root,
                    "--output", str(proof_file)
                ]
            )
            
            assert result.exit_code == 0
            assert "FAILED" in result.stdout
            
            with open(proof_file) as f:
                proof = json.load(f)
            
            assert proof["verification"]["verification_passed"] is False


class TestCLIIntegration:
    """Integration tests for CLI workflows"""
    
    def test_full_workflow(
        self, cli_runner: CliRunner, log_file_with_commitment: tuple[Path, str, str]
    ) -> None:
        """Test complete workflow: extract -> verify -> export proof"""
        log_file, root_b64, _ = log_file_with_commitment
        
        # Step 1: Extract metadata
        extract_result = cli_runner.invoke(
            app,
            ["extract", str(log_file)]
        )
        assert extract_result.exit_code == 0
        
        # Step 2: Verify
        verify_result = cli_runner.invoke(
            app,
            ["verify", str(log_file), root_b64]
        )
        assert verify_result.exit_code == 0
        
        # Step 3: Export proof
        with tempfile.TemporaryDirectory() as tmpdir:
            proof_file = Path(tmpdir) / "proof.json"
            
            export_result = cli_runner.invoke(
                app,
                ["export-proof", str(log_file), root_b64, "--output", str(proof_file)]
            )
            assert export_result.exit_code == 0
            assert proof_file.exists()
