import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from . import config


@dataclass
class _PinState:
    window_start: float
    fails: int = 0
    blocked_until: float = 0.0
    last_touch: float = 0.0


class PinLimiter:
    def __init__(self) -> None:
        """Initialize PinLimiter state and collaborator references."""
        self._lock = threading.Lock()
        self._by_ip: Dict[str, _PinState] = {}

    def _get_limits(self) -> Tuple[int, int, int]:
        """Return limits."""
        window_s = max(1, int(getattr(config, "PIN_WINDOW_S", 60) or 60))
        max_fails = max(1, int(getattr(config, "PIN_MAX_FAILS", 8) or 8))
        block_s = max(1, int(getattr(config, "PIN_BLOCK_S", 300) or 300))
        return window_s, max_fails, block_s

    def _get_cleanup_limits(self) -> Tuple[int, int]:
        """Return cleanup limits."""
        stale_s = max(10, int(getattr(config, "PIN_STATE_STALE_S", 7200) or 7200))
        max_ips = max(1, int(getattr(config, "PIN_STATE_MAX_IPS", 4096) or 4096))
        return stale_s, max_ips

    def _cleanup(self, now: float, *, force_compact: bool = False) -> None:
        """Clean up state."""
        stale_s, max_ips = self._get_cleanup_limits()
        stale_keys = [
            ip
            for ip, st in self._by_ip.items()
            if (now - float(st.last_touch or st.window_start)) > stale_s and now >= float(st.blocked_until or 0.0)
        ]
        for ip in stale_keys:
            self._by_ip.pop(ip, None)
        if len(self._by_ip) <= max_ips and not force_compact:
            return
        keys = sorted(self._by_ip.keys(), key=lambda ip: float(self._by_ip[ip].last_touch or self._by_ip[ip].window_start))
        for ip in keys[: max(0, len(keys) - max_ips)]:
            self._by_ip.pop(ip, None)

    def _state(self, ip: str, now: float) -> _PinState:
        """Return the current state snapshot."""
        st = self._by_ip.get(ip)
        if st is None:
            st = _PinState(window_start=now, last_touch=now)
            self._by_ip[ip] = st
        else:
            st.last_touch = now
        return st

    def check(self, ip: str, now: Optional[float] = None) -> Tuple[bool, int]:
        """Returns (allowed, retry_after_s)."""
        now = float(time.time() if now is None else now)
        window_s, max_fails, block_s = self._get_limits()
        with self._lock:
            self._cleanup(now)
            st = self._state(ip, now)
            if st.blocked_until and now < st.blocked_until:
                return False, int(max(1, st.blocked_until - now))
            if (now - st.window_start) > window_s:
                st.window_start = now
                st.fails = 0
                st.blocked_until = 0.0
                st.last_touch = now
            if st.fails >= max_fails:
                st.blocked_until = now + block_s
                st.last_touch = now
                return False, int(block_s)
            return True, 0

    def record_failure(self, ip: str, now: Optional[float] = None) -> None:
        """Record failure."""
        now = float(time.time() if now is None else now)
        window_s, max_fails, block_s = self._get_limits()
        with self._lock:
            self._cleanup(now)
            st = self._state(ip, now)
            if (now - st.window_start) > window_s:
                st.window_start = now
                st.fails = 0
                st.blocked_until = 0.0
            st.fails += 1
            if st.fails >= max_fails:
                st.blocked_until = now + block_s
            st.last_touch = now
            self._cleanup(now, force_compact=True)

    def record_success(self, ip: str) -> None:
        """Record success."""
        with self._lock:
            self._by_ip.pop(ip, None)

    def reset(self) -> None:
        """Reset state."""
        with self._lock:
            self._by_ip.clear()


pin_limiter = PinLimiter()
