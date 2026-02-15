from __future__ import annotations

from typing import Any

from .video_core import *

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
        self._ts = 0.0
        self._last_error = None
        self._last_error_ts = 0.0
        self._error_streak = 0
        self._disabled_reason = None
        self.base_w = int(os.environ.get("CYBERDECK_STREAM_W", "960"))
        self.base_q = int(os.environ.get("CYBERDECK_STREAM_Q", "25"))
        self.base_fps = int(os.environ.get("CYBERDECK_STREAM_FPS", "30"))
        self.base_cursor = int(os.environ.get("CYBERDECK_STREAM_CURSOR", "0")) == 1
        self.base_monitor = int(os.environ.get("CYBERDECK_STREAM_MONITOR", str(getattr(config, "STREAM_MONITOR", 1))))
        self._desired_key = (self.base_w, self.base_q, self.base_cursor, self.base_monitor)
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
                min_dt = 1.0 / max(5, self.base_fps)
                backoff_s = 0.05
                last_log_t = 0.0
                while not self._stop.is_set():
                    t0 = time.perf_counter()
                    try:
                        g0 = time.perf_counter()
                        with self._lock:
                            desired_w, desired_q, desired_cursor, desired_monitor = self._desired_key
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
                        with self._lock:
                            self._raw_seq += 1
                            raw_seq = self._raw_seq
                            self._latest_raw = (raw, size, monitor, raw_seq, desired_monitor)

                        e0 = time.perf_counter()
                        jpeg = self._encode(raw, size, monitor, desired_w, desired_q, desired_cursor)
                        e_ms = (time.perf_counter() - e0) * 1000.0
                        with self._lock:
                            self._latest_jpeg = jpeg
                            self._latest_jpeg_key = (desired_w, desired_q, desired_cursor, desired_monitor)
                            self._latest_jpeg_seq = raw_seq
                            self._ts = time.time()

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

    def _encode(self, raw_bgra: bytes, size: Any, monitor: Any, w: int, q: int, cursor: bool) -> bytes:
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
            img = img.resize((w, max(1, h)), _RESAMPLE_FILTER)
        return _save_jpeg(img, q)

    def get_jpeg(self, w: int, q: int, cursor: bool, monitor: int) -> bytes:
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
        except Exception:
            pass

        if raw_monitor_id != key[3]:
            return b""

        out = self._encode(raw_bgra, size, raw_monitor, key[0], key[1], key[2])
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
            return {
                "desired_w": int(desired[0]),
                "desired_q": int(desired[1]),
                "desired_cursor": bool(desired[2]),
                "desired_monitor": int(desired[3]) if len(desired) > 3 else 1,
                "base_fps": int(self.base_fps),
                "ema_encode_ms": float(self._ema_encode_ms) if self._ema_encode_ms is not None else None,
                "ema_grab_ms": float(self._ema_grab_ms) if self._ema_grab_ms is not None else None,
                "ema_loop_fps": float(self._ema_loop_fps) if self._ema_loop_fps is not None else None,
                "ts": float(self._ts),
                "disabled_reason": self._disabled_reason,
                "last_error": self._last_error,
                "last_error_ts": float(self._last_error_ts) if self._last_error_ts else None,
                "error_streak": int(self._error_streak),
            }

video_streamer = _VideoStreamer()


__all__ = [name for name in globals() if not name.startswith("__")]
