"""
Attack-oriented security tests for high-risk threat scenarios.

These tests complement the existing suite by covering:
- HTTP tamper resistance and replay controls
- Commitment-level tamper detection
- Identity spoofing resistance (IBS verification)
- Encrypted channel tamper resistance (AES-GCM)
- Request correlation replay/mismatch rejection
- Adversarial burst throttling
"""

import base64
import asyncio
import json
import threading
import time
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from backend.http_security import (
    HTTPSecurityManager,
    HTTPSecurityMiddleware,
    RATE_LIMIT_MAX_REQUESTS,
    TIMESTAMP_TOLERANCE_SEC,
)
from src.crypto.encoding import CanonicalEncoder, canonicalize_json
from src.crypto.kex import (
    decrypt_data,
    serialize_public_key,
    derive_shared_key,
    encrypt_data,
    generate_ecdh_keypair,
)
from src.crypto.verkle import VerkleAccumulator
from src.security import SecurityMiddleware
from src.security.key_management import KeyAuthority, Verifier
from src.transport import secure_mcp as secure_mcp_module
from src.transport.secure_mcp import SecureMCPClient
from src.tools.verify_cli import app as verify_cli_app


class TestSecurityAttackScenarios:
    """Focused tests for concrete attack classes from the threat model."""

    def test_http_signature_rejects_path_tampering(self):
        """A signature bound to one path must fail verification on another path."""
        manager = HTTPSecurityManager()
        session_data = manager.create_session("127.0.0.1")
        session = manager.get_session(session_data["session_token"])

        timestamp = "1700000000000"
        nonce = "abcdef0123456789"
        method = "POST"
        body = '{"prompt":"hello"}'
        signed_path = "/api/chat"

        signature = manager.compute_signature(
            session_data["hmac_key"],
            timestamp,
            nonce,
            method,
            signed_path,
            body,
        )

        assert manager.verify_signature(
            session, timestamp, nonce, method, signed_path, body, signature
        )
        assert not manager.verify_signature(
            session, timestamp, nonce, method, "/api/conversations", body, signature
        )

    def test_http_nonce_reuse_is_blocked(self):
        """Reusing the same nonce should be detected as replay."""
        manager = HTTPSecurityManager()
        nonce = "replay-nonce-123456"

        assert manager.check_nonce(nonce)
        assert not manager.check_nonce(nonce)

    def test_verkle_verification_fails_after_event_removal(self):
        """Removing an event from a valid log must invalidate root verification."""
        acc = VerkleAccumulator("tamper-test")

        events = [
            {"counter": 0, "type": "prompt", "payload": {"text": "a"}},
            {"counter": 1, "type": "tool_input", "payload": {"tool": "calc"}},
            {"counter": 2, "type": "tool_output", "payload": {"result": 3}},
        ]
        for event in events:
            acc.add_event(event)

        root = acc.finalize()
        original_log = json.loads(acc.get_canonical_log().decode("utf-8"))
        tampered_log = [original_log[0], original_log[2]]  # remove middle event
        tampered_log_bytes = json.dumps(tampered_log).encode("utf-8")

        # Counter gaps are also a valid tamper signal and may raise during replay.
        with pytest.raises(ValueError, match="Counter mismatch"):
            acc.verify_against_root(tampered_log_bytes, root)

    def test_ibs_identity_spoofing_fails_verification(self):
        """A signature by one identity must not verify as another identity."""
        authority = KeyAuthority()
        verifier = Verifier(authority.mpk)

        signer = authority.provision_tool("calculator")
        message = b'{"tool":"calculator","result":42}'
        signature = signer.sign_message(message)

        assert verifier.verify_tool_signature("calculator", message, signature)
        assert not verifier.verify_tool_signature("weather_api", message, signature)

    def test_aes_gcm_detects_ciphertext_tampering(self):
        """Bit-flipping ciphertext must fail authenticated decryption."""
        priv_a, pub_a = generate_ecdh_keypair()
        priv_b, pub_b = generate_ecdh_keypair()
        key_a = derive_shared_key(priv_a, pub_b)
        key_b = derive_shared_key(priv_b, pub_a)
        assert key_a == key_b

        plaintext = b"sensitive payload"
        encrypted = bytearray(encrypt_data(key_a, plaintext))
        encrypted[-1] ^= 0x01  # tamper with auth tag/ciphertext

        with pytest.raises(Exception):
            decrypt_data(key_b, bytes(encrypted))

    def test_secure_mcp_rejects_mismatched_request_id(self):
        """Response request_id mismatch should be rejected as replay/confusion."""
        client = SecureMCPClient(
            tool_name="calculator",
            host="localhost",
            port=5555,
            middleware=None,
        )

        forged_response = {
            "tool": "calculator",
            "result": 3,
            "request_id": "different-id",
            "signature": "fake-signature",
        }

        with pytest.raises(ValueError, match="Replay/Mismatched Request ID"):
            client._verify_response_integrity(forged_response, "expected-id")

    def test_http_rate_limit_blocks_adversarial_burst(self):
        """A burst over limit from one IP should be throttled."""
        manager = HTTPSecurityManager()
        ip = "198.51.100.10"

        for _ in range(RATE_LIMIT_MAX_REQUESTS):
            assert manager.check_rate_limit(ip)

        assert not manager.check_rate_limit(ip)


def _build_http_test_app() -> tuple[FastAPI, HTTPSecurityManager]:
    security = HTTPSecurityManager()
    app = FastAPI()
    app.add_middleware(HTTPSecurityMiddleware, security_manager=security)

    @app.post("/api/session/init")
    async def init_session(request: Request):
        ip = request.client.host if request.client else "unknown"
        return security.create_session(ip)

    @app.post("/api/protected")
    async def protected_endpoint(payload: dict):
        return {"ok": True, "payload": payload}

    @app.post("/api/protected2")
    async def protected_endpoint_2(payload: dict):
        return {"ok": True, "payload": payload}

    return app, security


def _signed_headers(
    security: HTTPSecurityManager,
    session_token: str,
    hmac_key: str,
    method: str,
    path: str,
    body: str,
    nonce: str = "nonce-e2e-test-1234",
    timestamp_ms: str | None = None,
) -> dict[str, str]:
    timestamp = timestamp_ms or str(int(time.time() * 1000))
    signature = security.compute_signature(
        hmac_key,
        timestamp,
        nonce,
        method,
        path,
        body,
    )
    return {
        "X-Session-Token": session_token,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }


def _build_two_span_workflow_artifacts(tmp_path: Path) -> tuple[Path, str, dict]:
    """Create canonical/commitment artifacts with two spans for composition tamper tests."""
    authority = KeyAuthority(
        master_secret_hex="22" * 32,
        keyring_path=tmp_path / "master_keyring_two_span.enc.json",
    )
    signer = authority.provision_tool("server")

    session_id = "sig-verify-session-two-span"

    # Two spans, one signed event each.
    span_events = [
        ("span-a", "span_a", {"prompt": "a", "response": "A"}),
        ("span-b", "span_b", {"prompt": "b", "response": "B"}),
    ]
    events = []
    span_roots_b64 = {}
    span_names = {}

    for idx, (span_id, span_name, attributes) in enumerate(span_events):
        payload_bytes = CanonicalEncoder.encode_event(attributes)
        signature = signer.sign_message(payload_bytes)
        timestamp = f"2026-03-23T12:00:0{idx}Z"
        events.append(
            {
                "session_id": session_id,
                "span_id": span_id,
                "span_name": span_name,
                "timestamp": timestamp,
                "event_type": "model_output",
                "attributes": attributes,
                "signature": str(signature),
                "signer_id": "server",
            }
        )

        span_acc = VerkleAccumulator(f"{session_id}_{span_id}")
        span_acc.add_event(
            {
                "session_id": session_id,
                "counter": 0,
                "timestamp": timestamp,
                "event_type": "model_output",
                "payload": attributes,
                "span_id": span_id,
            }
        )
        span_root = span_acc.finalize()
        span_roots_b64[span_id] = base64.b64encode(span_root).decode("utf-8")
        span_names[span_id] = span_name

    canonical_log_path = tmp_path / "canonical_log.json"
    canonical_log_path.write_text(json.dumps(events), encoding="utf-8")

    commitments_path = tmp_path / "commitments.json"
    commitments_path.write_text(
        json.dumps({"span_roots": span_roots_b64}), encoding="utf-8"
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
                "event_count": 1,
            }
        )
    expected_root_b64 = base64.b64encode(session_acc.finalize()).decode("utf-8")

    crypto_params_path = tmp_path / "crypto_params.json"
    crypto_params_path.write_text(
        json.dumps({"mpk": authority.export_mpk()}), encoding="utf-8"
    )

    return canonical_log_path, expected_root_b64, span_roots_b64


def _build_signed_workflow_artifacts(tmp_path: Path, signer_id: str) -> tuple[Path, str]:
    """Create minimal canonical log + commitments + crypto params for CLI verification."""
    authority = KeyAuthority(
        master_secret_hex="11" * 32,
        keyring_path=tmp_path / "master_keyring.enc.json",
    )
    signer = authority.provision_tool(signer_id)

    session_id = "sig-verify-session-001"
    span_id = "span-1"
    span_name = "test_span"

    attributes = {"prompt": "hello", "response": "world"}
    payload_bytes = CanonicalEncoder.encode_event(attributes)
    signature = signer.sign_message(payload_bytes)

    event = {
        "session_id": session_id,
        "span_id": span_id,
        "span_name": span_name,
        "timestamp": "2026-03-23T12:00:00Z",
        "event_type": "model_output",
        "attributes": attributes,
        "signature": str(signature),
        "signer_id": signer_id,
    }

    canonical_log_path = tmp_path / "canonical_log.json"
    canonical_log_path.write_text(json.dumps([event]), encoding="utf-8")

    # Reconstruct expected span root exactly like verify_cli does.
    span_acc = VerkleAccumulator(f"{session_id}_{span_id}")
    span_acc.add_event(
        {
            "session_id": session_id,
            "counter": 0,
            "timestamp": event["timestamp"],
            "event_type": event["event_type"],
            "payload": attributes,
            "span_id": span_id,
        }
    )
    span_root = span_acc.finalize()
    span_root_b64 = base64.b64encode(span_root).decode("utf-8")

    commitments_path = tmp_path / "commitments.json"
    commitments_path.write_text(
        json.dumps({"span_roots": {span_id: span_root_b64}}),
        encoding="utf-8",
    )

    # Session root from span commitments (same logic as verify_cli).
    session_acc = VerkleAccumulator(session_id)
    session_acc.add_event(
        {
            "session_id": session_id,
            "counter": 0,
            "event_type": "span_commitment",
            "span_id": span_id,
            "span_name": span_name,
            "span_root": span_root_b64,
            "event_count": 1,
        }
    )
    expected_root_b64 = base64.b64encode(session_acc.finalize()).decode("utf-8")

    crypto_params_path = tmp_path / "crypto_params.json"
    crypto_params_path.write_text(
        json.dumps({"mpk": authority.export_mpk()}),
        encoding="utf-8",
    )

    return canonical_log_path, expected_root_b64


def test_http_security_middleware_allows_valid_signed_request_e2e():
    """Full middleware chain should allow a correctly signed protected request."""
    app, security = _build_http_test_app()
    client = TestClient(app)

    init_resp = client.post("/api/session/init")
    assert init_resp.status_code == 200
    session_data = init_resp.json()

    session_token = session_data["session_token"]
    hmac_key = session_data["hmac_key"]

    body = json.dumps({"message": "hello"}, separators=(",", ":"))
    headers = _signed_headers(
        security,
        session_token,
        hmac_key,
        "POST",
        "/api/protected",
        body,
    )

    response = client.post("/api/protected", headers=headers, content=body)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["payload"]["message"] == "hello"


def test_http_security_short_circuits_before_hmac_on_stale_timestamp():
    """Stale timestamps must be rejected before the expensive HMAC verification path."""
    app, security = _build_http_test_app()
    client = TestClient(app)

    init_resp = client.post("/api/session/init")
    assert init_resp.status_code == 200
    session_data = init_resp.json()

    session_token = session_data["session_token"]
    hmac_key = session_data["hmac_key"]

    body = json.dumps({"message": "stale"}, separators=(",", ":"))
    stale_timestamp = str(int(time.time() * 1000) - ((TIMESTAMP_TOLERANCE_SEC + 5) * 1000))
    headers = _signed_headers(
        security,
        session_token,
        hmac_key,
        "POST",
        "/api/protected",
        body,
        nonce="stale-ts-nonce-123456",
        timestamp_ms=stale_timestamp,
    )

    with patch.object(security, "verify_signature", side_effect=AssertionError("HMAC path should not run")):
        response = client.post("/api/protected", headers=headers, content=body)

    assert response.status_code == 403
    assert "timestamp" in response.json().get("error", "").lower()


def test_verify_cli_verify_signatures_passes_with_valid_signature(tmp_path: Path):
    """verify --verify-signatures should pass when signature/identity/payload match."""
    runner = CliRunner()
    canonical_log_path, expected_root_b64 = _build_signed_workflow_artifacts(
        tmp_path, signer_id="server"
    )

    result = runner.invoke(
        verify_cli_app,
        [
            "verify",
            str(canonical_log_path),
            expected_root_b64,
            "--verify-signatures",
        ],
    )

    assert result.exit_code == 0
    assert "Signatures verified: 1" in result.stdout
    assert "All 1 signatures verified" in result.stdout


def test_verify_cli_ignores_telemetry_only_event_fields_for_root_reconstruction(tmp_path: Path):
    """Telemetry-only fields should not affect reconstructed commitment verification."""
    authority = KeyAuthority(
        master_secret_hex="33" * 32,
        keyring_path=tmp_path / "master_keyring_telemetry.enc.json",
    )
    signer = authority.provision_tool("server")

    session_id = "telemetry-safe-session"
    span_id = "span-telemetry"
    span_name = "telemetry_span"

    attributes = {"prompt": "hello", "response": "world"}
    payload_bytes = CanonicalEncoder.encode_event(attributes)
    signature = signer.sign_message(payload_bytes)

    # Include telemetry-only fields that should not be part of commitment reconstruction.
    event = {
        "session_id": session_id,
        "span_id": span_id,
        "span_name": span_name,
        "timestamp": "2026-03-24T12:00:00Z",
        "event_type": "model_output",
        "attributes": attributes,
        "signature": str(signature),
        "signer_id": "server",
        "trace_id": "trace-abc-123",
        "span_duration_ms": 42,
        "otel_status": "OK",
    }

    canonical_log_path = tmp_path / "canonical_log.json"
    canonical_log_path.write_text(json.dumps([event]), encoding="utf-8")

    # Commitments are computed only from core deterministic fields.
    span_acc = VerkleAccumulator(f"{session_id}_{span_id}")
    span_acc.add_event(
        {
            "session_id": session_id,
            "counter": 0,
            "timestamp": event["timestamp"],
            "event_type": event["event_type"],
            "payload": attributes,
            "span_id": span_id,
        }
    )
    span_root_b64 = base64.b64encode(span_acc.finalize()).decode("utf-8")

    commitments_path = tmp_path / "commitments.json"
    commitments_path.write_text(
        json.dumps({"span_roots": {span_id: span_root_b64}}),
        encoding="utf-8",
    )

    session_acc = VerkleAccumulator(session_id)
    session_acc.add_event(
        {
            "session_id": session_id,
            "counter": 0,
            "event_type": "span_commitment",
            "span_id": span_id,
            "span_name": span_name,
            "span_root": span_root_b64,
            "event_count": 1,
        }
    )
    expected_root_b64 = base64.b64encode(session_acc.finalize()).decode("utf-8")

    (tmp_path / "crypto_params.json").write_text(
        json.dumps({"mpk": authority.export_mpk()}),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        verify_cli_app,
        ["verify", str(canonical_log_path), expected_root_b64],
    )

    assert result.exit_code == 0
    assert "Verification PASSED" in result.stdout


def test_verify_cli_verify_signatures_fails_with_forged_signer_id(tmp_path: Path):
    """verify --verify-signatures should fail when signer_id is forged."""
    runner = CliRunner()
    canonical_log_path, expected_root_b64 = _build_signed_workflow_artifacts(
        tmp_path, signer_id="server"
    )

    # Forge signer_id while keeping signature unchanged.
    events = json.loads(canonical_log_path.read_text(encoding="utf-8"))
    events[0]["signer_id"] = "forged_server"
    canonical_log_path.write_text(json.dumps(events), encoding="utf-8")

    result = runner.invoke(
        verify_cli_app,
        [
            "verify",
            str(canonical_log_path),
            expected_root_b64,
            "--verify-signatures",
        ],
    )

    assert result.exit_code == 1
    output = result.stdout + (result.stderr or "")
    assert "Signature verification FAILED" in output


def test_verify_cli_fails_when_span_commitments_are_tampered(tmp_path: Path):
    """Tampering commitment metadata for spans must fail verification."""
    runner = CliRunner()
    canonical_log_path, expected_root_b64, span_roots = _build_two_span_workflow_artifacts(tmp_path)

    # Swap roots between span IDs to simulate commitment tampering.
    span_ids = sorted(span_roots.keys())
    tampered = {
        span_ids[0]: span_roots[span_ids[1]],
        span_ids[1]: span_roots[span_ids[0]],
    }
    (tmp_path / "commitments.json").write_text(
        json.dumps({"span_roots": tampered}), encoding="utf-8"
    )

    result = runner.invoke(
        verify_cli_app,
        ["verify", str(canonical_log_path), expected_root_b64],
    )

    assert result.exit_code == 1
    assert "span root mismatch" in (result.stdout + (result.stderr or "")).lower()


def test_verify_cli_fails_when_span_assignment_is_tampered(tmp_path: Path):
    """Moving an event to another span must break span/session composition verification."""
    runner = CliRunner()
    canonical_log_path, expected_root_b64, _ = _build_two_span_workflow_artifacts(tmp_path)

    events = json.loads(canonical_log_path.read_text(encoding="utf-8"))
    # Tamper composition by changing span_id of first event.
    events[0]["span_id"] = "span-b"
    canonical_log_path.write_text(json.dumps(events), encoding="utf-8")

    result = runner.invoke(
        verify_cli_app,
        ["verify", str(canonical_log_path), expected_root_b64],
    )

    assert result.exit_code == 1


def test_secure_mcp_rejects_signature_for_modified_payload():
    """A valid signature must fail if response payload is modified in transit."""
    authority = KeyAuthority()
    middleware = SimpleNamespace(authority=authority)

    client = SecureMCPClient(
        tool_name="calculator",
        host="localhost",
        port=5555,
        middleware=middleware,
    )
    signer = authority.provision_tool("calculator")

    original_payload = {
        "tool": "calculator",
        "result": 3,
        "request_id": "req-123",
    }
    signature = signer.sign_message(canonicalize_json(original_payload).encode("utf-8"))

    tampered_response = {
        "tool": "calculator",
        "result": 999,  # tampered result
        "request_id": "req-123",
        "signature": str(signature),
    }

    with pytest.raises(ValueError, match="Signature Verification Failed"):
        client._verify_response_integrity(tampered_response, "req-123")


def test_secure_mcp_rejects_signature_reuse_from_other_response():
    """Reusing a signature from a different payload must be rejected."""
    authority = KeyAuthority()
    middleware = SimpleNamespace(authority=authority)

    client = SecureMCPClient(
        tool_name="calculator",
        host="localhost",
        port=5555,
        middleware=middleware,
    )
    signer = authority.provision_tool("calculator")

    payload_a = {"tool": "calculator", "result": 10, "request_id": "req-a"}
    payload_b = {"tool": "calculator", "result": 20, "request_id": "req-b"}
    sig_a = signer.sign_message(canonicalize_json(payload_a).encode("utf-8"))

    forged_response = {
        "tool": "calculator",
        "result": payload_b["result"],
        "request_id": payload_b["request_id"],
        "signature": str(sig_a),
    }

    with pytest.raises(ValueError, match="Signature Verification Failed"):
        client._verify_response_integrity(forged_response, "req-b")


def test_http_timestamp_within_tolerance_is_accepted_e2e():
    """Timestamp just inside tolerance should be accepted by middleware."""
    app, security = _build_http_test_app()
    client = TestClient(app)

    session = client.post("/api/session/init").json()
    body = json.dumps({"message": "edge-pass"}, separators=(",", ":"))

    near_boundary_ts = str(int(time.time() * 1000) - (TIMESTAMP_TOLERANCE_SEC * 1000) + 250)
    headers = _signed_headers(
        security,
        session["session_token"],
        session["hmac_key"],
        "POST",
        "/api/protected",
        body,
        nonce="nonce-ts-pass-123456",
        timestamp_ms=near_boundary_ts,
    )

    response = client.post("/api/protected", headers=headers, content=body)
    assert response.status_code == 200


def test_http_timestamp_outside_tolerance_is_rejected_e2e():
    """Timestamp just outside tolerance should be rejected as replay/stale."""
    app, security = _build_http_test_app()
    client = TestClient(app)

    session = client.post("/api/session/init").json()
    body = json.dumps({"message": "edge-fail"}, separators=(",", ":"))

    stale_ts = str(int(time.time() * 1000) - (TIMESTAMP_TOLERANCE_SEC * 1000) - 2000)
    headers = _signed_headers(
        security,
        session["session_token"],
        session["hmac_key"],
        "POST",
        "/api/protected",
        body,
        nonce="nonce-ts-fail-123456",
        timestamp_ms=stale_ts,
    )

    response = client.post("/api/protected", headers=headers, content=body)
    assert response.status_code == 403
    assert "timestamp outside acceptable window" in response.json()["error"].lower()


def test_http_nonce_replay_is_blocked_across_endpoints_e2e():
    """Nonce replay should be blocked even if the attacker changes endpoint and re-signs."""
    app, security = _build_http_test_app()
    client = TestClient(app)

    session = client.post("/api/session/init").json()
    nonce = "nonce-cross-endpoint-123456"

    body1 = json.dumps({"message": "one"}, separators=(",", ":"))
    headers1 = _signed_headers(
        security,
        session["session_token"],
        session["hmac_key"],
        "POST",
        "/api/protected",
        body1,
        nonce=nonce,
    )
    r1 = client.post("/api/protected", headers=headers1, content=body1)
    assert r1.status_code == 200

    body2 = json.dumps({"message": "two"}, separators=(",", ":"))
    headers2 = _signed_headers(
        security,
        session["session_token"],
        session["hmac_key"],
        "POST",
        "/api/protected2",
        body2,
        nonce=nonce,
    )
    r2 = client.post("/api/protected2", headers=headers2, content=body2)
    assert r2.status_code == 403
    assert "nonce already used" in r2.json()["error"].lower()


def test_http_concurrent_same_nonce_allows_only_one_request():
    """Concurrent replay race: one request should pass, the duplicate nonce should fail."""
    app, security = _build_http_test_app()
    client = TestClient(app)

    session = client.post("/api/session/init").json()
    body = json.dumps({"message": "race"}, separators=(",", ":"))
    timestamp_ms = str(int(time.time() * 1000))
    nonce = "nonce-race-1234567890"
    headers = _signed_headers(
        security,
        session["session_token"],
        session["hmac_key"],
        "POST",
        "/api/protected",
        body,
        nonce=nonce,
        timestamp_ms=timestamp_ms,
    )

    statuses = []
    errors = []

    def worker():
        try:
            r = client.post("/api/protected", headers=headers, content=body)
            statuses.append(r.status_code)
        except Exception as exc:  # pragma: no cover - diagnostic safety
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert sorted(statuses) == [200, 403]


def test_secure_mcp_requires_tls_channel_binding_when_enforced(monkeypatch):
    """Client should fail closed when TLS channel binding is required but unavailable."""
    authority = KeyAuthority()
    middleware = SimpleNamespace(authority=authority)

    # Minimal fake websocket to pass initial key exchange steps.
    _, server_pub = generate_ecdh_keypair()
    server_pub_bytes = serialize_public_key(server_pub)

    class FakeWebSocket:
        def __init__(self):
            self._recv_count = 0

        async def recv(self):
            self._recv_count += 1
            if self._recv_count == 1:
                return server_pub_bytes
            return b""

        async def send(self, _data):
            return None

    async def fake_connect(_uri, ssl=None):
        return FakeWebSocket()

    monkeypatch.setattr(secure_mcp_module, "connect", fake_connect)

    client = SecureMCPClient(
        tool_name="calculator",
        host="localhost",
        port=5555,
        middleware=middleware,
        require_tls_channel_binding=True,
    )

    with pytest.raises(RuntimeError, match="TLS channel binding is required"):
        asyncio.run(client.connect_and_provision())


def test_security_middleware_unauthorized_response_has_no_capability_leakage():
    """Blocked response should remain neutral and not leak authorized tool names."""
    security = SecurityMiddleware()
    security.register_authorized_tools(["add", "multiply"])

    blocked_message = security.auth_manager.handle_unauthorized_access(
        "session-1", "delete_database"
    )

    assert "blocked" in blocked_message.lower()
    assert "add" not in blocked_message.lower()
    assert "multiply" not in blocked_message.lower()
    assert "delete_database" not in blocked_message.lower()


def test_security_middleware_repeated_unauthorized_attempts_stay_blocked():
    """Repeated prompt-injection style attempts must remain blocked across turns."""
    security = SecurityMiddleware()
    security.register_authorized_tools(["add"])

    for _ in range(5):
        assert not security.validate_tool_invocation("session-2", "delete_database")
