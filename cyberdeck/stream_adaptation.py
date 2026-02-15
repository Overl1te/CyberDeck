import threading
import time
from typing import Dict, List, Optional, Tuple


def parse_width_ladder(raw: str, default: List[int]) -> List[int]:
    """Normalize and transform values used to parse width ladder."""
    # Normalize inputs early so downstream logic receives stable values.
    out: List[int] = []
    txt = str(raw or "").strip()
    if txt:
        for x in txt.split(","):
            sx = str(x or "").strip()
            if not sx:
                continue
            try:
                v = int(sx)
            except Exception:
                continue
            if v > 0 and v not in out:
                out.append(v)
    if not out:
        out = list(default)
    out = sorted([int(v) for v in out if int(v) > 0], reverse=True)
    uniq: List[int] = []
    for v in out:
        if v not in uniq:
            uniq.append(v)
    return uniq


class WidthStabilizer:
    def __init__(
        self,
        *,
        ladder: List[int],
        min_switch_s: float = 8.0,
        hysteresis_ratio: float = 0.18,
        min_floor: int = 0,
        enabled: bool = True,
    ):
        """Initialize WidthStabilizer state and collaborator references."""
        self.ladder = sorted([int(x) for x in ladder if int(x) > 0], reverse=True) or [1280, 960, 768, 640]
        self.min_switch_s = max(0.0, float(min_switch_s))
        self.hysteresis_ratio = max(0.0, min(0.9, float(hysteresis_ratio)))
        self.min_floor = max(0, int(min_floor))
        self.enabled = bool(enabled)
        self._state: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _snap(self, requested: int) -> int:
        """Snap measured width to adaptation steps to reduce oscillation."""
        req = max(1, int(requested))
        chosen = self.ladder[-1]
        for v in self.ladder:
            if req >= int(v):
                chosen = int(v)
                break
        if self.min_floor > 0:
            chosen = max(self.min_floor, chosen)
        return chosen

    def decide(self, token: str, requested: int, now: Optional[float] = None) -> int:
        """Choose next stream width from recent throughput and latency samples."""
        snapped = self._snap(requested)
        if not self.enabled:
            return snapped
        t = float(time.monotonic() if now is None else now)
        key = str(token or "")
        if not key:
            return snapped

        with self._lock:
            prev = self._state.get(key)
            if not prev:
                self._state[key] = (snapped, t)
                return snapped

            prev_w, prev_ts = int(prev[0]), float(prev[1])
            if snapped == prev_w:
                self._state[key] = (prev_w, t)
                return prev_w

            # Ignore micro-jitter around current width.
            hysteresis_px = max(1, int(round(prev_w * self.hysteresis_ratio)))
            if abs(snapped - prev_w) <= hysteresis_px:
                self._state[key] = (prev_w, prev_ts)
                return prev_w

            # Cooldown for frequent switching; allow only major jumps during cooldown.
            dt = max(0.0, t - prev_ts)
            if dt < self.min_switch_s:
                major_drop = snapped < int(round(prev_w * (1.0 - self.hysteresis_ratio * 1.8)))
                major_rise = snapped > int(round(prev_w * (1.0 + self.hysteresis_ratio * 1.8)))
                if not (major_drop or major_rise):
                    self._state[key] = (prev_w, prev_ts)
                    return prev_w

            self._state[key] = (snapped, t)
            return snapped
