import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


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


@dataclass
class FeedbackSnapshot:
    ts: float
    rtt_ms: float
    jitter_ms: float
    drop_ratio: float
    decode_fps: float
    network_profile: str


class StreamFeedbackStore:
    """Keep latest per-session network feedback and compute simple tuning hints."""

    def __init__(self, *, stale_after_s: float = 20.0) -> None:
        self._lock = threading.RLock()
        self._state: Dict[str, FeedbackSnapshot] = {}
        self._stale_after_s = max(2.0, float(stale_after_s))

    def update(
        self,
        token: str,
        *,
        rtt_ms: Optional[float] = None,
        jitter_ms: Optional[float] = None,
        drop_ratio: Optional[float] = None,
        decode_fps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update token feedback and return normalized recommendation payload."""
        key = str(token or "").strip()
        if not key:
            return {"ok": False, "error": "token_required"}

        now = time.time()
        rtt = max(0.0, float(rtt_ms or 0.0))
        jitter = max(0.0, float(jitter_ms or 0.0))
        drop = max(0.0, min(1.0, float(drop_ratio or 0.0)))
        fps = max(0.0, float(decode_fps or 0.0))

        profile = "good"
        if (rtt >= 340.0) or (drop >= 0.08) or (fps > 0.0 and fps < 12.0):
            profile = "critical"
        elif (rtt >= 220.0) or (drop >= 0.03) or (fps > 0.0 and fps < 20.0):
            profile = "degraded"

        snap = FeedbackSnapshot(
            ts=now,
            rtt_ms=rtt,
            jitter_ms=jitter,
            drop_ratio=drop,
            decode_fps=fps,
            network_profile=profile,
        )
        with self._lock:
            self._state[key] = snap
        return {"ok": True, **self.recommend(key)}

    def recommend(self, token: str) -> Dict[str, Any]:
        """Return recommendation derived from latest feedback snapshot."""
        item = self.get(token)
        if not item:
            return {"network_profile": "unknown", "suggested": {}}
        profile = str(item.get("network_profile") or "unknown")
        if profile == "critical":
            return {
                **item,
                "suggested": {"fps_delta": -4, "max_w_delta": -128, "quality_delta": -8, "prefer_low_latency": True},
            }
        if profile == "degraded":
            return {
                **item,
                "suggested": {"fps_delta": -2, "max_w_delta": -64, "quality_delta": -4, "prefer_low_latency": True},
            }
        return {
            **item,
            "suggested": {"fps_delta": 1, "max_w_delta": 64, "quality_delta": 2, "prefer_low_latency": False},
        }

    def get(self, token: str) -> Dict[str, Any]:
        """Return latest non-stale feedback snapshot for token."""
        key = str(token or "").strip()
        if not key:
            return {}
        with self._lock:
            snap = self._state.get(key)
            if snap is None:
                return {}
            if (time.time() - float(snap.ts)) > self._stale_after_s:
                self._state.pop(key, None)
                return {}
            return {
                "ts": int(snap.ts),
                "rtt_ms": float(snap.rtt_ms),
                "jitter_ms": float(snap.jitter_ms),
                "drop_ratio": float(snap.drop_ratio),
                "decode_fps": float(snap.decode_fps),
                "network_profile": str(snap.network_profile),
            }


feedback_store = StreamFeedbackStore()
