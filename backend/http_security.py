"""
HTTP Transport Security Middleware for FastAPI

Provides cryptographic protection at the HTTP API layer:
- HMAC-SHA256 request signing (tamper resistance)
- Nonce + timestamp replay protection
- Session token authentication
- Rate limiting per IP
- CORS origin restriction

Architecture:
    Browser                         FastAPI Server
    ───────                         ──────────────
    1. GET /api/session/init  ─────>  Generate session_token + hmac_key
       <──── { session_token, hmac_key }
    
    2. Every subsequent request includes:
       Headers:
         X-Session-Token: <token>
         X-Timestamp: <unix_ms>
         X-Nonce: <random_hex>
         X-Signature: HMAC-SHA256(hmac_key, timestamp|nonce|method|path|body)
    
    Server validates:
       ✓ Token exists and is valid
       ✓ Timestamp within ±30s window (anti-replay)
       ✓ Nonce never seen before (anti-replay)
       ✓ HMAC signature matches (tamper-proof)
       ✓ Rate limit not exceeded
"""

import hashlib
import hmac
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# --- Configuration ---

TIMESTAMP_TOLERANCE_SEC = 30       # Reject requests older than ±30s
NONCE_EXPIRY_SEC = 120             # Nonce cache TTL (2 min)
RATE_LIMIT_WINDOW_SEC = 60         # Rate limit window
RATE_LIMIT_MAX_REQUESTS = 60       # Max requests per window per IP
SESSION_TTL_SEC = 3600             # Session lifetime (1 hour)

# Paths that bypass security (static assets, page load, session init)
BYPASS_PATHS = frozenset({
    "/",
    "/favicon.ico",
    "/api/session/init",
})
BYPASS_PREFIXES = ("/static/",)


@dataclass
class SessionInfo:
    """Server-side session state."""
    token: str
    hmac_key: str               # Hex-encoded 32-byte key
    created_at: float
    ip_address: str


@dataclass
class RateLimitBucket:
    """Sliding window rate limiter per IP."""
    timestamps: list = field(default_factory=list)

    def is_allowed(self, now: float) -> bool:
        """Check if request is within rate limit."""
        cutoff = now - RATE_LIMIT_WINDOW_SEC
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        if len(self.timestamps) >= RATE_LIMIT_MAX_REQUESTS:
            return False
        self.timestamps.append(now)
        return True


class HTTPSecurityManager:
    """
    Manages sessions, nonces, and rate limits.
    All state is in-memory (acceptable for single-process server).
    """

    def __init__(self):
        # token -> SessionInfo
        self.sessions: dict[str, SessionInfo] = {}
        # Set of seen nonces (with expiry tracking)
        self._nonce_store: dict[str, float] = {}
        # IP -> RateLimitBucket
        self._rate_limits: defaultdict[str, RateLimitBucket] = defaultdict(RateLimitBucket)

    # --- Session management ---

    def create_session(self, ip_address: str) -> dict:
        """Create a new authenticated session. Returns token + HMAC key."""
        token = os.urandom(24).hex()          # 48-char hex session token
        hmac_key = os.urandom(32).hex()        # 64-char hex HMAC key
        now = time.time()

        session = SessionInfo(
            token=token,
            hmac_key=hmac_key,
            created_at=now,
            ip_address=ip_address,
        )
        self.sessions[token] = session

        # Prune expired sessions periodically
        self._prune_sessions(now)

        logger.info("http_session_created", token_prefix=token[:8], ip=ip_address)

        return {
            "session_token": token,
            "hmac_key": hmac_key,
            "expires_in": SESSION_TTL_SEC,
        }

    def get_session(self, token: str) -> Optional[SessionInfo]:
        """Retrieve and validate a session by token."""
        session = self.sessions.get(token)
        if not session:
            return None
        if time.time() - session.created_at > SESSION_TTL_SEC:
            del self.sessions[token]
            return None
        return session

    def _prune_sessions(self, now: float):
        """Remove expired sessions."""
        expired = [t for t, s in self.sessions.items()
                   if now - s.created_at > SESSION_TTL_SEC]
        for t in expired:
            del self.sessions[t]

    # --- Nonce tracking ---

    def check_nonce(self, nonce: str) -> bool:
        """
        Returns True if nonce is fresh (never seen).
        Returns False if nonce was already used (replay attempt).
        """
        now = time.time()

        # Prune expired nonces
        cutoff = now - NONCE_EXPIRY_SEC
        expired = [n for n, ts in self._nonce_store.items() if ts < cutoff]
        for n in expired:
            del self._nonce_store[n]

        if nonce in self._nonce_store:
            return False  # Replay!

        self._nonce_store[nonce] = now
        return True

    # --- Rate limiting ---

    def check_rate_limit(self, ip: str) -> bool:
        """Returns True if request is within rate limit."""
        return self._rate_limits[ip].is_allowed(time.time())

    # --- HMAC verification ---

    @staticmethod
    def compute_signature(hmac_key_hex: str, timestamp: str, nonce: str,
                          method: str, path: str, body: str) -> str:
        """
        Compute HMAC-SHA256 signature over the request envelope.
        
        message = f"{timestamp}|{nonce}|{method}|{path}|{body}"
        signature = HMAC-SHA256(key, message)
        """
        key = bytes.fromhex(hmac_key_hex)
        message = f"{timestamp}|{nonce}|{method}|{path}|{body}".encode("utf-8")
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def verify_signature(self, session: SessionInfo, timestamp: str,
                         nonce: str, method: str, path: str,
                         body: str, provided_sig: str) -> bool:
        """Verify the client-provided HMAC signature."""
        expected = self.compute_signature(
            session.hmac_key, timestamp, nonce, method, path, body
        )
        return hmac.compare_digest(expected, provided_sig)


class HTTPSecurityMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enforces HTTP-level security on all /api/ endpoints.
    
    Checks (in order):
    1. Rate limit (per IP)
    2. Session token validity (X-Session-Token header)
    3. Timestamp freshness (X-Timestamp header, ±30s)
    4. Nonce uniqueness (X-Nonce header, replay prevention)
    5. HMAC signature (X-Signature header, tamper resistance)
    """

    def __init__(self, app, security_manager: HTTPSecurityManager):
        super().__init__(app)
        self.security = security_manager

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Bypass security for static assets, index page, session init
        if path in BYPASS_PATHS or any(path.startswith(p) for p in BYPASS_PREFIXES):
            return await call_next(request)

        # Only enforce on /api/ routes
        if not path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # 1. Rate limit
        if not self.security.check_rate_limit(client_ip):
            logger.warning("rate_limit_exceeded", ip=client_ip, path=path)
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Try again later."},
            )

        # 2. Session token
        token = request.headers.get("X-Session-Token", "")
        session = self.security.get_session(token)
        if not session:
            logger.warning("invalid_session", ip=client_ip, path=path,
                           token_prefix=token[:8] if token else "none")
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or expired session. Call /api/session/init first."},
            )

        # Store validated session token for route-level access control
        request.state.session_token = token

        # 3. Timestamp freshness
        timestamp_str = request.headers.get("X-Timestamp", "")
        try:
            timestamp_ms = int(timestamp_str)
            age = abs(time.time() * 1000 - timestamp_ms)
            if age > TIMESTAMP_TOLERANCE_SEC * 1000:
                logger.warning("stale_timestamp", ip=client_ip, age_ms=age, path=path)
                return JSONResponse(
                    status_code=403,
                    content={"error": "Request timestamp outside acceptable window (replay attempt)."},
                )
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=400,
                content={"error": "Missing or invalid X-Timestamp header."},
            )

        # 4. Nonce uniqueness
        nonce = request.headers.get("X-Nonce", "")
        if not nonce or len(nonce) < 16:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing or too-short X-Nonce header (min 16 chars)."},
            )
        if not self.security.check_nonce(nonce):
            logger.warning("replay_attempt", ip=client_ip, nonce=nonce[:16], path=path)
            return JSONResponse(
                status_code=403,
                content={"error": "Nonce already used (replay attempt blocked)."},
            )

        # 5. HMAC signature verification
        signature = request.headers.get("X-Signature", "")
        if not signature:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing X-Signature header."},
            )

        # Read body for signature verification
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8") if body_bytes else ""

        method = request.method.upper()
        if not self.security.verify_signature(
            session, timestamp_str, nonce, method, path, body_str, signature
        ):
            logger.warning("invalid_signature", ip=client_ip, path=path)
            return JSONResponse(
                status_code=403,
                content={"error": "HMAC signature verification failed (tampered request)."},
            )

        # All checks passed — log and continue
        logger.debug("http_request_authenticated",
                      ip=client_ip, path=path, method=method)

        return await call_next(request)
