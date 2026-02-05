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


class PinLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_ip: Dict[str, _PinState] = {}

    def _get_limits(self) -> Tuple[int, int, int]:
        window_s = max(1, int(getattr(config, "PIN_WINDOW_S", 60) or 60))
        max_fails = max(1, int(getattr(config, "PIN_MAX_FAILS", 8) or 8))
        block_s = max(1, int(getattr(config, "PIN_BLOCK_S", 300) or 300))
        return window_s, max_fails, block_s

    def _state(self, ip: str, now: float) -> _PinState:
        st = self._by_ip.get(ip)
        if st is None:
            st = _PinState(window_start=now)
            self._by_ip[ip] = st
        return st

    def check(self, ip: str, now: Optional[float] = None) -> Tuple[bool, int]:
        """Returns (allowed, retry_after_s)."""
        now = float(time.time() if now is None else now)
        window_s, max_fails, block_s = self._get_limits()
        with self._lock:
            st = self._state(ip, now)
            if st.blocked_until and now < st.blocked_until:
                return False, int(max(1, st.blocked_until - now))
            if (now - st.window_start) > window_s:
                st.window_start = now
                st.fails = 0
                st.blocked_until = 0.0
            if st.fails >= max_fails:
                st.blocked_until = now + block_s
                return False, int(block_s)
            return True, 0

    def record_failure(self, ip: str, now: Optional[float] = None) -> None:
        now = float(time.time() if now is None else now)
        window_s, max_fails, block_s = self._get_limits()
        with self._lock:
            st = self._state(ip, now)
            if (now - st.window_start) > window_s:
                st.window_start = now
                st.fails = 0
                st.blocked_until = 0.0
            st.fails += 1
            if st.fails >= max_fails:
                st.blocked_until = now + block_s

    def record_success(self, ip: str) -> None:
        with self._lock:
            self._by_ip.pop(ip, None)

    def reset(self) -> None:
        with self._lock:
            self._by_ip.clear()


pin_limiter = PinLimiter()

