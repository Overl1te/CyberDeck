"""In-memory one-time token storage for QR login flow."""

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from . import config


@dataclass
class _QrToken:
    """Internal token record with creation and expiration timestamps."""

    created_ts: float
    expires_ts: float


class QrTokenStore:
    """Thread-safe one-time QR token storage with TTL and bounded size."""

    def __init__(self) -> None:
        """Initialize QrTokenStore state and collaborator references."""
        self._lock = threading.Lock()
        self._tokens: Dict[str, _QrToken] = {}

    def _ttl_s(self) -> int:
        """Return normalized TTL (seconds) from config with safe defaults."""
        try:
            return max(10, int(getattr(config, "QR_TOKEN_TTL_S", 120) or 120))
        except Exception:
            return 120

    def _cleanup_locked(self, now: Optional[float] = None) -> None:
        """Remove expired tokens and trim store to a reasonable upper bound."""
        t = float(time.time() if now is None else now)
        expired = [k for k, v in self._tokens.items() if t >= float(v.expires_ts)]
        for k in expired:
            self._tokens.pop(k, None)
        if len(self._tokens) <= 8192:
            return
        keys = sorted(self._tokens.keys(), key=lambda x: float(self._tokens[x].created_ts))
        for k in keys[: max(0, len(self._tokens) - 8192)]:
            self._tokens.pop(k, None)

    def issue(self) -> str:
        """Issue a new single-use token and store it until expiration."""
        token = uuid.uuid4().hex
        now = time.time()
        ttl_s = self._ttl_s()
        with self._lock:
            self._cleanup_locked(now=now)
            self._tokens[token] = _QrToken(created_ts=now, expires_ts=now + ttl_s)
        return token

    def consume(self, token: str) -> bool:
        """Consume token once and validate it has not expired."""
        key = str(token or "").strip()
        if not key:
            return False
        now = time.time()
        with self._lock:
            self._cleanup_locked(now=now)
            item = self._tokens.pop(key, None)
            if not item:
                return False
            return now < float(item.expires_ts)


qr_token_store = QrTokenStore()


