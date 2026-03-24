"""Web/API hardening tests for security headers, CORS, route validation, and HTTPS startup modes."""

import re
import time
from pathlib import Path

from fastapi.testclient import TestClient

import backend.server as backend_server


client = TestClient(backend_server.app)


def _signed_headers(token: str, hmac_key: str, method: str, path: str, body: str = "") -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    nonce = f"nonce-{time.time_ns()}"
    signature = backend_server.http_security.compute_signature(
        hmac_key,
        timestamp,
        nonce,
        method,
        path,
        body,
    )
    return {
        "X-Session-Token": token,
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }


def _new_session() -> tuple[str, str]:
    resp = client.post("/api/session/init")
    assert resp.status_code == 200
    payload = resp.json()["result"]
    return payload["session_token"], payload["hmac_key"]


def test_security_headers_and_csp_nonce_present_on_root_page() -> None:
    """Root page should include defense headers and replace CSP nonce placeholder."""
    resp = client.get("/")
    assert resp.status_code == 200

    headers = resp.headers
    assert "Content-Security-Policy" in headers
    assert "X-Content-Type-Options" in headers
    assert "X-Frame-Options" in headers
    assert "Referrer-Policy" in headers
    assert "Permissions-Policy" in headers
    assert "Strict-Transport-Security" in headers

    html = resp.text
    assert "{{CSP_NONCE}}" not in html

    match = re.search(r'<script nonce="([^"]+)" src="/static/script.js"></script>', html)
    assert match is not None
    nonce = match.group(1)
    assert f"'nonce-{nonce}'" in headers["Content-Security-Policy"]


def test_cors_preflight_allows_configured_origin() -> None:
    """Configured origins should pass CORS preflight."""
    resp = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:8000"


def test_cors_preflight_denies_unconfigured_origin() -> None:
    """Unexpected origins should fail CORS preflight."""
    resp = client.options(
        "/api/chat",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (400, 403)
    assert resp.headers.get("access-control-allow-origin") is None


def test_route_level_conversation_id_validation_rejects_invalid_chars() -> None:
    """Conversation route handlers should reject invalid conversation ID patterns."""
    token, hmac_key = _new_session()
    path = "/api/conversations/bad!id/messages"
    headers = _signed_headers(token, hmac_key, "GET", path)

    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32002


def test_route_level_conversation_id_validation_rejects_oversized_id() -> None:
    """Conversation route handlers should reject conversation IDs over max length."""
    token, hmac_key = _new_session()
    long_id = "a" * (backend_server.MAX_CONVERSATION_ID_LENGTH + 1)
    path = f"/api/conversations/{long_id}/messages"
    headers = _signed_headers(token, hmac_key, "GET", path)

    resp = client.get(path, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32002


def test_route_level_conversation_ownership_denies_cross_session_access() -> None:
    """Conversation endpoints should deny access from a different owner session."""
    # Use two distinct client IP identities so ownership cannot be auto-reclaimed.
    session_a = backend_server.http_security.create_session("198.51.100.10")
    session_b = backend_server.http_security.create_session("203.0.113.11")

    create_path = "/api/conversations"
    create_headers = _signed_headers(
        session_a["session_token"],
        session_a["hmac_key"],
        "POST",
        create_path,
        "",
    )
    create_resp = client.post(create_path, headers=create_headers, content="")
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["result"]["conversation_id"]

    read_path = f"/api/conversations/{conversation_id}/messages"
    read_headers = _signed_headers(
        session_b["session_token"],
        session_b["hmac_key"],
        "GET",
        read_path,
        "",
    )
    read_resp = client.get(read_path, headers=read_headers)

    assert read_resp.status_code == 200
    assert read_resp.json()["error"]["code"] == -32004


def test_https_startup_mode_falls_back_cleanly_when_disabled(tmp_path: Path) -> None:
    """When HTTPS mode is disabled, SSL config should be safely bypassed."""
    cert, key = backend_server.resolve_ssl_config(use_https=False, project_root=tmp_path)
    assert cert is None
    assert key is None


def test_https_startup_mode_errors_when_certs_missing(tmp_path: Path) -> None:
    """HTTPS mode should fail closed if certificate files are missing."""
    try:
        backend_server.resolve_ssl_config(use_https=True, project_root=tmp_path)
        assert False, "Expected FileNotFoundError for missing certs"
    except FileNotFoundError as exc:
        assert "certificates not found" in str(exc)


def test_https_startup_mode_uses_certs_when_present(tmp_path: Path) -> None:
    """HTTPS mode should resolve cert/key paths when files exist."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir(parents=True, exist_ok=True)
    cert_file = certs_dir / "localhost.crt"
    key_file = certs_dir / "localhost.key"
    cert_file.write_text("dummy-cert", encoding="utf-8")
    key_file.write_text("dummy-key", encoding="utf-8")

    cert, key = backend_server.resolve_ssl_config(use_https=True, project_root=tmp_path)
    assert Path(cert).parent.name == "certs"
    assert Path(cert).name == "localhost.crt"
    assert Path(key).parent.name == "certs"
    assert Path(key).name == "localhost.key"
