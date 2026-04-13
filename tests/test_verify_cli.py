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
import time
from pathlib import Path
from typing import Any

import pytest

from src.crypto.verkle import VerkleAccumulator
from src.crypto.encoding import CanonicalEncoder
from src.crypto.signatures import IBSScheme
from src.security.key_management import KeyAuthority
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


def _build_large_signed_cli_artifacts(
    tmp_path: Path,
    event_count: int = 50,
    span_count: int = 6,
) -> tuple[Path, str, int]:
    """Build large signed artifacts by replaying existing valid signatures from workflow logs."""
    workflows_root = Path("workflows")
    seed_candidates: list[tuple[int, Path, list[dict[str, Any]]]] = []

    for canonical_path in workflows_root.rglob("canonical_log.json"):
        crypto_path = canonical_path.parent / "crypto_params.json"
        if not crypto_path.exists():
            continue
        try:
            events = json.loads(canonical_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(events, list):
            continue
        signed_events = [
            event
            for event in events
            if isinstance(event, dict)
            and "attributes" in event
            and "signature" in event
            and "signer_id" in event
        ]
        if signed_events:
            seed_candidates.append((len(signed_events), canonical_path.parent, signed_events))

    if not seed_candidates:
        pytest.skip("No workflow artifacts with signatures and crypto_params available for benchmark")

    # Prefer the richest signed corpus available to maximize event diversity in replay.
    _, seed_dir, seed_signed_events = max(seed_candidates, key=lambda row: row[0])

    crypto_params = json.loads((seed_dir / "crypto_params.json").read_text(encoding="utf-8"))
    mpk = KeyAuthority.import_mpk(crypto_params["mpk"])
    valid_seed_events: list[dict[str, Any]] = []
    for event in seed_signed_events:
        try:
            signature = KeyAuthority.parse_ibs_signature(event["signature"])
            payload_bytes = CanonicalEncoder.encode_event(event["attributes"])
            if IBSScheme.verify(mpk, event["signer_id"], payload_bytes, signature):
                valid_seed_events.append(event)
        except Exception:
            continue

    if not valid_seed_events:
        pytest.skip("No MPK-valid signed events found in workflow corpus for benchmark")

    session_id = "perf-verify-session-001"
    events: list[dict[str, Any]] = []
    events_by_span: dict[str, list[dict[str, Any]]] = {}

    for idx in range(event_count):
        span_idx = idx % span_count
        span_id = f"span-{span_idx:02d}"
        span_name = f"perf_span_{span_idx:02d}"
        seed_event = valid_seed_events[idx % len(valid_seed_events)]
        attributes = seed_event["attributes"]
        event = {
            "session_id": session_id,
            "span_id": span_id,
            "span_name": span_name,
            "timestamp": f"2026-03-24T12:{(idx // 60) % 60:02d}:{idx % 60:02d}Z",
            "event_type": "model_output",
            "attributes": attributes,
            "signature": seed_event["signature"],
            "signer_id": seed_event["signer_id"],
        }
        events.append(event)
        events_by_span.setdefault(span_id, []).append(event)

    canonical_log_path = tmp_path / "canonical_log_large.json"
    canonical_log_path.write_text(json.dumps(events), encoding="utf-8")
    canonical_log_bytes = canonical_log_path.stat().st_size

    span_roots_b64: dict[str, str] = {}
    span_names: dict[str, str] = {}
    for span_id, span_events in events_by_span.items():
        span_acc = VerkleAccumulator(f"{session_id}_{span_id}")
        for counter, event in enumerate(span_events):
            span_acc.add_event(
                {
                    "session_id": session_id,
                    "counter": counter,
                    "timestamp": event["timestamp"],
                    "event_type": event["event_type"],
                    "payload": event["attributes"],
                    "span_id": span_id,
                }
            )
        span_roots_b64[span_id] = base64.b64encode(span_acc.finalize()).decode("utf-8")
        span_names[span_id] = span_events[0]["span_name"]

    (tmp_path / "commitments.json").write_text(
        json.dumps({"span_roots": span_roots_b64}),
        encoding="utf-8",
    )

    session_acc = VerkleAccumulator(session_id)
    for idx, span_id in enumerate(sorted(span_roots_b64.keys())):
        session_acc.add_event(
            {
                "session_id": session_id,
                "counter": idx,
                "event_type": "span_commitment",
                "span_id": span_id,
                "span_name": span_names[span_id],
                "span_root": span_roots_b64[span_id],
                "event_count": len(events_by_span[span_id]),
            }
        )
    expected_root_b64 = base64.b64encode(session_acc.finalize()).decode("utf-8")

    (tmp_path / "crypto_params.json").write_text(
        (seed_dir / "crypto_params.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    return canonical_log_path, expected_root_b64, canonical_log_bytes


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

    def test_offline_verifier_large_log_signature_performance(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """Benchmark offline verifier practicality for a large signed canonical log."""
        canonical_log_path, expected_root_b64, canonical_log_bytes = _build_large_signed_cli_artifacts(
            tmp_path,
            event_count=50,
            span_count=6,
        )

        start = time.perf_counter()
        result = cli_runner.invoke(
            app,
            [
                "verify",
                str(canonical_log_path),
                expected_root_b64,
                "--verify-signatures",
            ],
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        throughput_eps = 50 / (elapsed_ms / 1000)

        assert result.exit_code == 0
        assert "Verification PASSED" in result.stdout
        assert "All 50 signatures verified" in result.stdout

        print(
            "[6.11.2 verifier performance] "
            "events=50, "
            f"canonical_log_bytes={canonical_log_bytes}, "
            f"canonical_log_mb={canonical_log_bytes / (1024 * 1024):.3f}, "
            f"verify_elapsed_ms={elapsed_ms:.3f}, "
            f"throughput_events_per_sec={throughput_eps:.2f}"
        )

        # Guardrail: keep verification within a practical offline-auditing envelope on commodity hardware.
        assert elapsed_ms < 180000, f"Verifier runtime too high: {elapsed_ms:.1f}ms"
