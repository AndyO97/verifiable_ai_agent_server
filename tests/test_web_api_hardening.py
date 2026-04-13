"""Web/API hardening tests for security headers, CORS, route validation, and HTTPS startup modes."""

import re
import statistics
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


def test_chat_prompt_length_enforces_exact_character_boundary(monkeypatch) -> None:
    """Prompt length gate should accept exactly MAX_PROMPT_LENGTH and reject MAX+1."""
    token, hmac_key = _new_session()

    # Isolate character-length validation by relaxing byte limit for this test.
    monkeypatch.setattr(backend_server, "MAX_PROMPT_BYTES", backend_server.MAX_PROMPT_LENGTH + 1000)

    class _Score:
        is_complex = False

    class _FakeConversation:
        conversation_id = "limit-conv"

        def __init__(self) -> None:
            self.messages = []

        async def send_prompt(self, prompt: str):
            now = time.time()
            self.messages = [
                {"role": "user", "content": prompt, "timestamp": now, "prompt_index": 0},
                {"role": "assistant", "content": "ok", "timestamp": now, "prompt_index": 0},
            ]
            return {
                "output": "ok",
                "prompt_root": "p-root",
                "prompt_index": 0,
                "canonical_log_hash": "hash",
            }

        def finalize(self):
            return {"conversation_root": "c-root"}

        def get_summary(self):
            return {
                "conversation_id": self.conversation_id,
                "is_finalized": False,
            }

    class _FakeConvManager:
        def create_conversation(self):
            return _FakeConversation()

    monkeypatch.setattr(
        backend_server.llm_rate_limiter,
        "validate_and_score",
        lambda session_token, prompt: (True, "", _Score()),
    )
    monkeypatch.setattr(backend_server, "conv_manager", _FakeConvManager())
    monkeypatch.setattr(backend_server.db, "save_conversation", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_integrity", lambda *args, **kwargs: None)

    exact_prompt = "a" * backend_server.MAX_PROMPT_LENGTH
    exact_body = f'{{"prompt":"{exact_prompt}"}}'
    exact_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", exact_body)
    exact_resp = client.post("/api/chat", headers=exact_headers, content=exact_body)
    assert exact_resp.status_code == 200
    assert "error" not in exact_resp.json()

    too_long_prompt = "a" * (backend_server.MAX_PROMPT_LENGTH + 1)
    too_long_body = f'{{"prompt":"{too_long_prompt}"}}'
    too_long_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", too_long_body)
    too_long_resp = client.post("/api/chat", headers=too_long_headers, content=too_long_body)

    assert too_long_resp.status_code == 200
    err = too_long_resp.json()["error"]
    assert err["code"] == -32006
    assert err["data"]["max_length"] == backend_server.MAX_PROMPT_LENGTH
    assert err["data"]["current_length"] == backend_server.MAX_PROMPT_LENGTH + 1


def test_chat_prompt_oversized_rejects_before_rate_limit_and_llm_path(monkeypatch) -> None:
    """Oversized prompt should fail at input gate before rate-limiter/LLM-conversation work."""
    token, hmac_key = _new_session()

    calls = {"rate_limiter": 0, "create_conversation": 0}

    class _Score:
        is_complex = False

    def _counting_validate_and_score(session_token, prompt):
        calls["rate_limiter"] += 1
        return True, "", _Score()

    class _CountingConvManager:
        def create_conversation(self):
            calls["create_conversation"] += 1
            raise AssertionError("create_conversation should not be called for oversized prompt")

    monkeypatch.setattr(
        backend_server.llm_rate_limiter,
        "validate_and_score",
        _counting_validate_and_score,
    )
    monkeypatch.setattr(backend_server, "conv_manager", _CountingConvManager())

    oversized_prompt = "x" * (backend_server.MAX_PROMPT_LENGTH + 1)
    body = f'{{"prompt":"{oversized_prompt}"}}'
    headers = _signed_headers(token, hmac_key, "POST", "/api/chat", body)
    resp = client.post("/api/chat", headers=headers, content=body)

    assert resp.status_code == 200
    assert resp.json()["error"]["code"] == -32006
    assert calls["rate_limiter"] == 0
    assert calls["create_conversation"] == 0


def test_chat_prompt_oversized_rejection_median_is_faster_than_valid_path(monkeypatch) -> None:
    """
    Oversized payload validation should provide efficient early rejection.

    Uses a deterministic instrumented valid path to make the avoided downstream
    work measurable and stable in CI-like environments.
    """
    token, hmac_key = _new_session()

    class _Score:
        is_complex = False

    class _FakeConversation:
        conversation_id = "bench-conv"

        def __init__(self) -> None:
            self.messages = []

        async def send_prompt(self, prompt: str):
            digest = b"valid-path-work"
            for _ in range(3000):
                digest = digest[::-1]
            now = time.time()
            self.messages = [
                {"role": "user", "content": prompt, "timestamp": now, "prompt_index": 0},
                {"role": "assistant", "content": str(len(digest)), "timestamp": now, "prompt_index": 0},
            ]
            return {
                "output": "ok",
                "prompt_root": "p-root",
                "prompt_index": 0,
                "canonical_log_hash": "hash",
            }

        def finalize(self):
            return {"conversation_root": "c-root"}

        def get_summary(self):
            return {
                "conversation_id": self.conversation_id,
                "is_finalized": False,
            }

    class _FakeConvManager:
        def create_conversation(self):
            return _FakeConversation()

    monkeypatch.setattr(
        backend_server.llm_rate_limiter,
        "validate_and_score",
        lambda session_token, prompt: (True, "", _Score()),
    )
    monkeypatch.setattr(backend_server, "conv_manager", _FakeConvManager())
    monkeypatch.setattr(backend_server.db, "save_conversation", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_integrity", lambda *args, **kwargs: None)

    valid_prompt = "v" * 128
    oversized_prompt = "o" * (backend_server.MAX_PROMPT_LENGTH + 1)
    valid_body = f'{{"prompt":"{valid_prompt}"}}'
    oversized_body = f'{{"prompt":"{oversized_prompt}"}}'

    iterations = 20
    valid_latencies_ms = []
    reject_latencies_ms = []

    for _ in range(iterations):
        valid_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", valid_body)
        t0 = time.perf_counter_ns()
        valid_resp = client.post("/api/chat", headers=valid_headers, content=valid_body)
        t1 = time.perf_counter_ns()
        assert valid_resp.status_code == 200
        assert "error" not in valid_resp.json()
        valid_latencies_ms.append((t1 - t0) / 1_000_000)

        reject_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", oversized_body)
        t2 = time.perf_counter_ns()
        reject_resp = client.post("/api/chat", headers=reject_headers, content=oversized_body)
        t3 = time.perf_counter_ns()
        assert reject_resp.status_code == 200
        assert reject_resp.json()["error"]["code"] == -32006
        reject_latencies_ms.append((t3 - t2) / 1_000_000)

    valid_median_ms = statistics.median(valid_latencies_ms)
    reject_median_ms = statistics.median(reject_latencies_ms)
    median_saved_ms = valid_median_ms - reject_median_ms

    assert median_saved_ms > 0

    print(
        "[6.5.3 prompt-length metrics] "
        f"limit_chars={backend_server.MAX_PROMPT_LENGTH}, "
        f"valid_median_ms={valid_median_ms:.3f}, "
        f"reject_median_ms={reject_median_ms:.3f}, "
        f"median_saved_ms={median_saved_ms:.3f}"
    )


def test_chat_prompt_byte_length_enforces_exact_boundary(monkeypatch) -> None:
    """UTF-8 byte-size gate should accept exact MAX_PROMPT_BYTES and reject MAX+1."""
    token, hmac_key = _new_session()

    class _Score:
        is_complex = False

    class _FakeConversation:
        conversation_id = "byte-limit-conv"

        def __init__(self) -> None:
            self.messages = []

        async def send_prompt(self, prompt: str):
            now = time.time()
            self.messages = [
                {"role": "user", "content": prompt, "timestamp": now, "prompt_index": 0},
                {"role": "assistant", "content": "ok", "timestamp": now, "prompt_index": 0},
            ]
            return {
                "output": "ok",
                "prompt_root": "p-root",
                "prompt_index": 0,
                "canonical_log_hash": "hash",
            }

        def finalize(self):
            return {"conversation_root": "c-root"}

        def get_summary(self):
            return {
                "conversation_id": self.conversation_id,
                "is_finalized": False,
            }

    class _FakeConvManager:
        def create_conversation(self):
            return _FakeConversation()

    monkeypatch.setattr(
        backend_server.llm_rate_limiter,
        "validate_and_score",
        lambda session_token, prompt: (True, "", _Score()),
    )
    monkeypatch.setattr(backend_server, "conv_manager", _FakeConvManager())
    monkeypatch.setattr(backend_server.db, "save_conversation", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_integrity", lambda *args, **kwargs: None)

    exact_prompt = "a" * backend_server.MAX_PROMPT_BYTES
    exact_body = f'{{"prompt":"{exact_prompt}"}}'
    exact_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", exact_body)
    exact_resp = client.post("/api/chat", headers=exact_headers, content=exact_body)

    assert exact_resp.status_code == 200
    assert "error" not in exact_resp.json()

    too_large_prompt = "a" * (backend_server.MAX_PROMPT_BYTES + 1)
    too_large_body = f'{{"prompt":"{too_large_prompt}"}}'
    too_large_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", too_large_body)
    too_large_resp = client.post("/api/chat", headers=too_large_headers, content=too_large_body)

    assert too_large_resp.status_code == 200
    err = too_large_resp.json()["error"]
    assert err["code"] == -32006
    assert err["data"]["max_bytes"] == backend_server.MAX_PROMPT_BYTES
    assert err["data"]["current_bytes"] == backend_server.MAX_PROMPT_BYTES + 1


def test_chat_prompt_oversized_bytes_rejection_median_shows_clearer_savings(monkeypatch) -> None:
    """
    Benchmark byte-limit rejection against a heavier valid path.

    This test is intended for chapter metrics capture and emphasizes
    measurable saved time from early byte-size validation.
    """
    token, hmac_key = _new_session()

    class _Score:
        is_complex = False

    class _FakeConversation:
        conversation_id = "byte-bench-conv"

        def __init__(self) -> None:
            self.messages = []

        async def send_prompt(self, prompt: str):
            digest = b"byte-benchmark-valid-path"
            for _ in range(20000):
                digest = digest[::-1]
            now = time.time()
            self.messages = [
                {"role": "user", "content": prompt, "timestamp": now, "prompt_index": 0},
                {"role": "assistant", "content": str(len(digest)), "timestamp": now, "prompt_index": 0},
            ]
            return {
                "output": "ok",
                "prompt_root": "p-root",
                "prompt_index": 0,
                "canonical_log_hash": "hash",
            }

        def finalize(self):
            return {"conversation_root": "c-root"}

        def get_summary(self):
            return {
                "conversation_id": self.conversation_id,
                "is_finalized": False,
            }

    class _FakeConvManager:
        def create_conversation(self):
            return _FakeConversation()

    monkeypatch.setattr(
        backend_server.llm_rate_limiter,
        "validate_and_score",
        lambda session_token, prompt: (True, "", _Score()),
    )
    monkeypatch.setattr(backend_server, "conv_manager", _FakeConvManager())
    monkeypatch.setattr(backend_server.db, "save_conversation", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(backend_server.db, "save_integrity", lambda *args, **kwargs: None)

    valid_prompt = "v" * 128
    oversized_bytes_prompt = "a" * (backend_server.MAX_PROMPT_BYTES + 1)
    valid_body = f'{{"prompt":"{valid_prompt}"}}'
    oversized_body = f'{{"prompt":"{oversized_bytes_prompt}"}}'

    iterations = 20
    valid_latencies_ms = []
    reject_latencies_ms = []

    for _ in range(iterations):
        backend_server.http_security._rate_limits.pop("testclient", None)
        valid_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", valid_body)
        t0 = time.perf_counter_ns()
        valid_resp = client.post("/api/chat", headers=valid_headers, content=valid_body)
        t1 = time.perf_counter_ns()
        assert valid_resp.status_code == 200
        assert "error" not in valid_resp.json()
        valid_latencies_ms.append((t1 - t0) / 1_000_000)

        backend_server.http_security._rate_limits.pop("testclient", None)
        reject_headers = _signed_headers(token, hmac_key, "POST", "/api/chat", oversized_body)
        t2 = time.perf_counter_ns()
        reject_resp = client.post("/api/chat", headers=reject_headers, content=oversized_body)
        t3 = time.perf_counter_ns()
        assert reject_resp.status_code == 200
        assert reject_resp.json()["error"]["code"] == -32006
        reject_latencies_ms.append((t3 - t2) / 1_000_000)

    valid_median_ms = statistics.median(valid_latencies_ms)
    reject_median_ms = statistics.median(reject_latencies_ms)
    median_saved_ms = valid_median_ms - reject_median_ms

    assert median_saved_ms > 1.0

    print(
        "[6.5.3 prompt-byte metrics] "
        f"limit_bytes={backend_server.MAX_PROMPT_BYTES}, "
        f"valid_median_ms={valid_median_ms:.3f}, "
        f"reject_median_ms={reject_median_ms:.3f}, "
        f"median_saved_ms={median_saved_ms:.3f}"
    )


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
