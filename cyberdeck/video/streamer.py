from __future__ import annotations

import zlib
from typing import Any

from .core import *

class _VideoStreamer:
    """Maintain native (mss) capture loop state and provide cached JPEG frames to clients."""
    def __init__(self) -> Any:
        """Initialize instance state, caches, and background worker dependencies."""
        self._lock = threading.Lock()
        self._latest_raw = None
        self._raw_seq = 0
        self._latest_jpeg = None
        self._latest_jpeg_key = None
        self._latest_jpeg_seq = -1
        self._last_raw_crc = None
        self._last_raw_size = None
        self._reused_jpeg_frames = 0
        self._encoded_jpeg_frames = 0
        self._ts = 0.0
        self._last_error = None
        self._last_error_ts = 0.0
        self._error_streak = 0
        self._disabled_reason = None
        self.base_w = max(320, _env_int("CYBERDECK_STREAM_W", 960))
        self.base_q = max(10, min(95, _env_int("CYBERDECK_STREAM_Q", 25)))
        self.max_fps = max(10, _env_int("CYBERDECK_STREAM_MAX_FPS", 120))
        self.base_fps = min(self.max_fps, max(5, _env_int("CYBERDECK_STREAM_FPS", 60)))
        self.base_cursor = _env_bool("CYBERDECK_STREAM_CURSOR", False)
        self.base_monitor = max(1, _env_int("CYBERDECK_STREAM_MONITOR", int(getattr(config, "STREAM_MONITOR", 1))))
        self._desired_key = (self.base_w, self.base_q, self.base_cursor, self.base_monitor)
        self._desired_fps = int(self.base_fps)
        self._ema_encode_ms = None
        self._ema_grab_ms = None
        self._ema_loop_fps = None
        self._last_loop_t = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> Any:
        """Request graceful termination of the background capture loop."""
        self._stop.set()

    def disabled_reason(self) -> Optional[str]:
        """Return native capture disable reason if native backend is unavailable."""
        with self._lock:
            return self._disabled_reason

    def is_native_healthy(self, max_stale_s: float = 2.5, min_error_streak: int = 3) -> bool:
        """Return whether native capture is currently healthy enough to be considered usable."""
        with self._lock:
            ts = float(self._ts or 0.0)
            err = int(self._error_streak or 0)
            disabled = self._disabled_reason
        if disabled:
            return False
        # Startup: allow native path a chance to warm up.
        if ts <= 0.0 and err <= 0:
            return True
        stale = ts <= 0.0 or (time.time() - ts) > float(max_stale_s)
        if stale and err >= int(min_error_streak):
            return False
        return True

    def _record_error(self, msg: str) -> None:
        """Record capture failure details and increment error streak counters."""
        now = time.time()
        with self._lock:
            self._last_error = str(msg)[:400]
            self._last_error_ts = now
            self._error_streak += 1

    def _record_ok(self) -> None:
        """Clear consecutive error streak after a successful capture iteration."""
        with self._lock:
            self._error_streak = 0

    def _disable_native_capture(self, reason: str, log_msg: str) -> None:
        """Disable native capture path and emit explicit warning with reason."""
        with self._lock:
            self._disabled_reason = str(reason or "native_capture_disabled")
        log.warning(log_msg)

    def _is_wayland_session(self) -> bool:
        """Detect whether current Linux session is Wayland."""
        if os.name == "nt":
            return False
        xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
        if xdg_type == "wayland":
            return True
        if xdg_type == "x11":
            return False
        return bool(os.environ.get("WAYLAND_DISPLAY")) and not bool(os.environ.get("DISPLAY"))

    def _loop(self) -> Any:
        """Run native capture loop: grab frame, encode JPEG, update caches, and track health metrics."""
        try:
            if self._is_wayland_session():
                with self._lock:
                    self._disabled_reason = "wayland_session"
                log.warning("MJPEG screen capture disabled: Wayland session detected (mss requires X11).")
                return
            if os.name != "nt" and not os.environ.get("DISPLAY"):
                with self._lock:
                    self._disabled_reason = "no_display"
                log.warning("MJPEG screen capture disabled: DISPLAY is not set (no X11 session).")
                return
            with mss.mss() as sct:
                backoff_s = 0.05
                last_log_t = 0.0
                while not self._stop.is_set():
                    t0 = time.perf_counter()
                    min_dt = 1.0 / float(max(5, self.base_fps))
                    try:
                        g0 = time.perf_counter()
                        with self._lock:
                            desired_w, desired_q, desired_cursor, desired_monitor = self._desired_key
                            desired_fps = int(self._desired_fps or self.base_fps)
                        desired_fps = max(5, min(self.max_fps, desired_fps))
                        min_dt = 1.0 / float(desired_fps)
                        monitors = sct.monitors
                        if not monitors:
                            raise RuntimeError("mss_no_monitors")
                        if len(monitors) == 1:
                            # Some environments report a single monitor entry only.
                            monitor = monitors[0]
                            desired_monitor = 1
                        else:
                            if desired_monitor < 1 or desired_monitor >= len(monitors):
                                desired_monitor = 1
                            monitor = monitors[desired_monitor]

                        sct_img = sct.grab(monitor)
                        self._record_ok()
                        backoff_s = 0.05
                        g_ms = (time.perf_counter() - g0) * 1000.0
                        raw = bytes(sct_img.bgra)
                        size = sct_img.size
                        allow_crc_reuse = (not desired_cursor) and desired_fps <= 35
                        raw_crc = (zlib.crc32(raw) & 0xFFFFFFFF) if allow_crc_reuse else None
                        key = (desired_w, desired_q, desired_cursor, desired_monitor)
                        can_reuse_jpeg = False
                        with self._lock:
                            self._raw_seq += 1
                            raw_seq = self._raw_seq
                            self._latest_raw = (raw, size, monitor, raw_seq, desired_monitor)
                            can_reuse_jpeg = (
                                allow_crc_reuse
                                and self._latest_jpeg is not None
                                and self._latest_jpeg_key == key
                                and self._last_raw_crc == raw_crc
                                and self._last_raw_size == size
                            )

                        e_ms = 0.0
                        if not can_reuse_jpeg:
                            e0 = time.perf_counter()
                            jpeg = self._encode(
                                raw,
                                size,
                                monitor,
                                desired_w,
                                desired_q,
                                desired_cursor,
                                target_fps=desired_fps,
                            )
                            e_ms = (time.perf_counter() - e0) * 1000.0
                        with self._lock:
                            if can_reuse_jpeg:
                                self._reused_jpeg_frames += 1
                            else:
                                self._latest_jpeg = jpeg
                                self._latest_jpeg_key = key
                                self._encoded_jpeg_frames += 1
                            self._latest_jpeg_seq = raw_seq
                            self._ts = time.time()
                            self._last_raw_crc = raw_crc if allow_crc_reuse else None
                            self._last_raw_size = size if allow_crc_reuse else None

                            a = 0.15
                            self._ema_encode_ms = e_ms if self._ema_encode_ms is None else (self._ema_encode_ms * (1 - a) + e_ms * a)
                            self._ema_grab_ms = g_ms if self._ema_grab_ms is None else (self._ema_grab_ms * (1 - a) + g_ms * a)
                            now = time.perf_counter()
                            if self._last_loop_t is not None:
                                dt = max(0.0001, now - self._last_loop_t)
                                fps_now = 1.0 / dt
                                self._ema_loop_fps = fps_now if self._ema_loop_fps is None else (self._ema_loop_fps * (1 - a) + fps_now * a)
                            self._last_loop_t = now
                    except mss.exception.ScreenShotError as e:
                        self._record_error(f"{type(e).__name__}: {e}")
                        now = time.time()
                        if now - last_log_t > 3.0:
                            last_log_t = now
                            log.warning("Video grab failed (mss): %s", e)
                        with self._lock:
                            streak = int(self._error_streak)
                        if streak >= 10:
                            self._disable_native_capture(
                                "mss_capture_failed",
                                "MJPEG native capture disabled after repeated mss failures; ffmpeg/gstreamer fallback will be used.",
                            )
                            return
                        time.sleep(backoff_s)
                        backoff_s = min(2.0, backoff_s * 1.5)
                    except Exception as e:
                        self._record_error(f"{type(e).__name__}: {e}")
                        now = time.time()
                        if now - last_log_t > 3.0:
                            last_log_t = now
                            log.exception("Video grab/encode failed")
                        with self._lock:
                            streak = int(self._error_streak)
                        if streak >= 10:
                            self._disable_native_capture(
                                "mss_capture_failed",
                                "MJPEG native capture disabled after repeated internal failures; ffmpeg/gstreamer fallback will be used.",
                            )
                            return
                        time.sleep(backoff_s)
                        backoff_s = min(2.0, backoff_s * 1.5)
                    dt = time.perf_counter() - t0
                    if dt < min_dt:
                        time.sleep(min_dt - dt)
        except Exception:
            log.exception("Video streamer died")

    def _encode(
        self,
        raw_bgra: bytes,
        size: Any,
        monitor: Any,
        w: int,
        q: int,
        cursor: bool,
        target_fps: int = 30,
    ) -> bytes:
        """Encode BGRA raw monitor frame into JPEG with optional cursor overlay and resizing."""
        img = Image.frombytes("RGB", size, raw_bgra, "raw", "BGRX")
        if cursor:
            try:
                cur = INPUT_BACKEND.position()
                if not cur:
                    raise RuntimeError("cursor_position_unavailable")
                cx, cy = cur
                rx, ry = cx - monitor["left"], cy - monitor["top"]
                draw = ImageDraw.Draw(img)
                draw.ellipse((rx - 6, ry - 6, rx + 6, ry + 6), outline=(0, 255, 65), width=2)
                draw.line((rx, ry, rx + 18, ry + 18), fill=(0, 255, 65), width=2)
            except Exception:
                pass

        if w and img.width > w:
            h = int(img.height * (w / img.width))
            resample = Image.Resampling.BILINEAR if int(target_fps) >= 45 else _RESAMPLE_FILTER
            img = img.resize((w, max(1, h)), resample)
        high_fps = int(target_fps) >= 45
        subsampling = 2 if high_fps else None
        return _save_jpeg(img, q, subsampling_override=subsampling)

    def get_jpeg(self, w: int, q: int, cursor: bool, monitor: int, fps: Optional[int] = None) -> bytes:
        """Return latest JPEG frame for requested parameters, re-encoding when cache key differs."""
        with self._lock:
            raw = self._latest_raw
            jpeg = self._latest_jpeg
            jpeg_key = self._latest_jpeg_key
            jpeg_seq = self._latest_jpeg_seq
        if raw is None:
            return b""

        key = (int(w), int(q), bool(cursor), int(monitor))
        raw_bgra, size, raw_monitor, raw_seq, raw_monitor_id = raw
        if jpeg is not None and jpeg_key == key and jpeg_seq == raw_seq:
            return jpeg

        try:
            with self._lock:
                self._desired_key = key
                if fps is not None:
                    self._desired_fps = max(5, min(self.max_fps, int(fps)))
        except Exception:
            pass

        if raw_monitor_id != key[3]:
            return b""

        desired_fps = int(fps) if fps is not None else self.base_fps
        out = self._encode(
            raw_bgra,
            size,
            raw_monitor,
            key[0],
            key[1],
            key[2],
            target_fps=desired_fps,
        )
        try:
            with self._lock:
                if self._latest_raw and self._latest_raw[3] == raw_seq:
                    self._latest_jpeg = out
                    self._latest_jpeg_key = key
                    self._latest_jpeg_seq = raw_seq
        except Exception:
            pass
        return out

    def get_stats(self) -> Dict[str, Any]:
        """Return internal capture-loop metrics used by diagnostics endpoints."""
        with self._lock:
            desired = tuple(self._desired_key)
            encoded = int(self._encoded_jpeg_frames)
            reused = int(self._reused_jpeg_frames)
            total = encoded + reused
            return {
                "desired_w": int(desired[0]),
                "desired_q": int(desired[1]),
                "desired_cursor": bool(desired[2]),
                "desired_monitor": int(desired[3]) if len(desired) > 3 else 1,
                "base_fps": int(self.base_fps),
                "max_fps": int(self.max_fps),
                "desired_fps": int(self._desired_fps),
                "ema_encode_ms": float(self._ema_encode_ms) if self._ema_encode_ms is not None else None,
                "ema_grab_ms": float(self._ema_grab_ms) if self._ema_grab_ms is not None else None,
                "ema_loop_fps": float(self._ema_loop_fps) if self._ema_loop_fps is not None else None,
                "ts": float(self._ts),
                "disabled_reason": self._disabled_reason,
                "last_error": self._last_error,
                "last_error_ts": float(self._last_error_ts) if self._last_error_ts else None,
                "error_streak": int(self._error_streak),
                "encoded_jpeg_frames": encoded,
                "reused_jpeg_frames": reused,
                "jpeg_reuse_ratio": (float(reused) / float(total)) if total > 0 else 0.0,
            }

video_streamer = _VideoStreamer()


__all__ = [name for name in globals() if not name.startswith("__")]

