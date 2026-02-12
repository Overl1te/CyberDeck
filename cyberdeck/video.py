import os
import queue
import shutil
import subprocess
import threading
import time
from io import BytesIO
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import mss
from PIL import Image, ImageDraw
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .auth import TokenDep, require_perm
from . import config
from .input_backend import INPUT_BACKEND
from .logging_config import log


router = APIRouter()

_ffmpeg_diag_lock = threading.Lock()
_ffmpeg_last_cmd: Optional[str] = None
_ffmpeg_last_error: Optional[str] = None
_ffmpeg_last_error_ts: float = 0.0

_ffmpeg_formats_lock = threading.Lock()
_ffmpeg_formats_cached: Optional[str] = None

_ffmpeg_encoders_lock = threading.Lock()
_ffmpeg_encoders_cached: Optional[str] = None


def _set_ffmpeg_diag(cmd: Optional[list], err: Optional[str]) -> None:
    global _ffmpeg_last_cmd, _ffmpeg_last_error, _ffmpeg_last_error_ts
    with _ffmpeg_diag_lock:
        _ffmpeg_last_cmd = " ".join([str(x) for x in (cmd or [])]) if cmd else None
        _ffmpeg_last_error = str(err)[:800] if err else None
        _ffmpeg_last_error_ts = time.time() if err else _ffmpeg_last_error_ts


def _get_ffmpeg_diag() -> Dict[str, Any]:
    with _ffmpeg_diag_lock:
        return {
            "ffmpeg_available": bool(_ffmpeg_available()),
            "ffmpeg_pipewire": bool(_ffmpeg_supports_pipewire()),
            "ffmpeg_libx264": bool(_ffmpeg_supports_encoder("libx264")),
            "ffmpeg_libx265": bool(_ffmpeg_supports_encoder("libx265")),
            "gst_available": bool(_gst_available()),
            "gst_pipewire": bool(_gst_supports_pipewire()),
            "ffmpeg_last_cmd": _ffmpeg_last_cmd,
            "ffmpeg_last_error": _ffmpeg_last_error,
            "ffmpeg_last_error_ts": float(_ffmpeg_last_error_ts) if _ffmpeg_last_error_ts else None,
        }


def _ffmpeg_formats() -> str:
    global _ffmpeg_formats_cached
    with _ffmpeg_formats_lock:
        if _ffmpeg_formats_cached is not None:
            return _ffmpeg_formats_cached
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-formats"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
        out = str(proc.stdout or "")
    except Exception:
        out = ""
    with _ffmpeg_formats_lock:
        _ffmpeg_formats_cached = out
    return out


def _ffmpeg_supports_pipewire() -> bool:
    txt = _ffmpeg_formats()
    return "pipewire" in txt.lower()


def _ffmpeg_encoders() -> str:
    global _ffmpeg_encoders_cached
    with _ffmpeg_encoders_lock:
        if _ffmpeg_encoders_cached is not None:
            return _ffmpeg_encoders_cached
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
        out = str(proc.stdout or "")
    except Exception:
        out = ""
    with _ffmpeg_encoders_lock:
        _ffmpeg_encoders_cached = out
    return out


def _ffmpeg_supports_encoder(name: str) -> bool:
    needle = str(name or "").strip().lower()
    if not needle:
        return False
    txt = _ffmpeg_encoders().lower()
    return needle in txt


def _gst_available() -> bool:
    return bool(shutil.which("gst-launch-1.0"))


def _gst_supports_pipewire() -> bool:
    gst_inspect = shutil.which("gst-inspect-1.0")
    if not gst_inspect:
        return False
    try:
        proc = subprocess.run(
            [gst_inspect, "pipewiresrc"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
        return int(proc.returncode) == 0
    except Exception:
        return False


def _is_wayland_session() -> bool:
    if os.name == "nt":
        return False
    xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    if xdg_type == "wayland":
        return True
    if xdg_type == "x11":
        return False
    return bool(os.environ.get("WAYLAND_DISPLAY")) and not bool(os.environ.get("DISPLAY"))


def _get_monitor_rect(monitor: int) -> Optional[tuple[int, int, int, int]]:
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if not monitors:
                return None
            if len(monitors) == 1:
                m = monitors[0]
            else:
                if monitor < 1 or monitor >= len(monitors):
                    monitor = 1
                m = monitors[monitor]
            return int(m.get("left", 0)), int(m.get("top", 0)), int(m.get("width", 0)), int(m.get("height", 0))
    except Exception:
        return None


def _pipewire_source_candidates() -> list[str]:
    out: list[str] = []
    env_sources = [
        os.environ.get("CYBERDECK_PIPEWIRE_NODE"),
        os.environ.get("PIPEWIRE_NODE"),
    ]
    for item in env_sources:
        val = str(item or "").strip()
        if val:
            out.append(val)
    # Different ffmpeg builds expect different default aliases.
    out.extend(["default", "0", "pipewire:"])
    uniq: list[str] = []
    for x in out:
        if x not in uniq:
            uniq.append(x)
    return uniq


def _x11_input_args(monitor: int, fps: int) -> Optional[list]:
    rect = _get_monitor_rect(monitor)
    if not rect:
        return None
    left, top, width, height = rect
    display = os.environ.get("DISPLAY") or ":0.0"
    return [
        "-f",
        "x11grab",
        "-draw_mouse",
        "1",
        "-framerate",
        str(fps),
        "-video_size",
        f"{width}x{height}",
        "-i",
        f"{display}+{left},{top}",
    ]


def _build_ffmpeg_input_arg_sets(monitor: int, fps: int) -> list[list]:
    fps = max(5, int(fps))
    is_wayland = _is_wayland_session()
    if os.name == "nt":
        rect = _get_monitor_rect(monitor)
        if not rect:
            return []
        left, top, width, height = rect
        return [[
            "-f",
            "gdigrab",
            "-draw_mouse",
            "1",
            "-framerate",
            str(fps),
            "-offset_x",
            str(left),
            "-offset_y",
            str(top),
            "-video_size",
            f"{width}x{height}",
            "-i",
            "desktop",
        ]]

    if is_wayland:
        out: list[list] = []
        if _ffmpeg_supports_pipewire():
            for src in _pipewire_source_candidates():
                out.append(["-f", "pipewire", "-framerate", str(fps), "-i", src])
        # In mixed Wayland sessions (XWayland available), x11grab can still work.
        if os.environ.get("DISPLAY"):
            x11_args = _x11_input_args(monitor, fps)
            if x11_args:
                out.append(x11_args)
        return out

    x11_args = _x11_input_args(monitor, fps)
    if not x11_args:
        return []
    return [x11_args]


def _build_ffmpeg_input_args(monitor: int, fps: int) -> Optional[list]:
    sets = _build_ffmpeg_input_arg_sets(monitor, fps)
    return sets[0] if sets else None


class _VideoStreamer:
    def __init__(self):
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

    def stop(self):
        self._stop.set()

    def disabled_reason(self) -> Optional[str]:
        with self._lock:
            return self._disabled_reason

    def is_native_healthy(self, max_stale_s: float = 2.5, min_error_streak: int = 3) -> bool:
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
        now = time.time()
        with self._lock:
            self._last_error = str(msg)[:400]
            self._last_error_ts = now
            self._error_streak += 1

    def _record_ok(self) -> None:
        with self._lock:
            self._error_streak = 0

    def _disable_native_capture(self, reason: str, log_msg: str) -> None:
        with self._lock:
            self._disabled_reason = str(reason or "native_capture_disabled")
        log.warning(log_msg)

    def _is_wayland_session(self) -> bool:
        if os.name == "nt":
            return False
        xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
        if xdg_type == "wayland":
            return True
        if xdg_type == "x11":
            return False
        return bool(os.environ.get("WAYLAND_DISPLAY")) and not bool(os.environ.get("DISPLAY"))

    def _loop(self):
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

    def _encode(self, raw_bgra: bytes, size, monitor, w: int, q: int, cursor: bool) -> bytes:
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
            img = img.resize((w, max(1, h)), Image.Resampling.NEAREST)

        buf = BytesIO()
        q = max(10, min(95, int(q)))
        img.save(buf, format="JPEG", quality=q, subsampling=2, progressive=False, optimize=False)
        return buf.getvalue()

    def get_jpeg(self, w: int, q: int, cursor: bool, monitor: int) -> bytes:
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


def generate_video_stream(w: int, q: int, fps: int, cursor: bool, monitor: int):
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    min_dt = 1.0 / max(5, int(fps))
    while True:
        t0 = time.perf_counter()
        try:
            frame = video_streamer.get_jpeg(w, q, cursor, monitor)
            if frame:
                yield boundary + frame + b"\r\n"
        except Exception:
            log.exception("Video stream generator error")
            time.sleep(0.05)
        dt = time.perf_counter() - t0
        if dt < min_dt:
            time.sleep(min_dt - dt)


@router.api_route("/video_feed", methods=["GET", "HEAD"])
def video_feed(
    token: str = TokenDep,
    w: Optional[int] = None,
    q: Optional[int] = None,
    max_w: Optional[int] = None,
    quality: Optional[int] = None,
    fps: int = 30,
    cursor: int = 1,
    low_latency: int = 0,
    monitor: int = 1,
):
    require_perm(token, "perm_stream")

    eff_w = int(max_w if max_w is not None else (w if w is not None else 960))
    eff_q = int(quality if quality is not None else (q if q is not None else 25))
    eff_fps = int(fps)
    eff_monitor = int(monitor)

    if int(low_latency) == 1:
        eff_w = min(eff_w, 960)
        eff_q = min(eff_q, 35)
        eff_fps = min(eff_fps, 60)

    disabled = video_streamer.disabled_reason()
    native_ok = (disabled is None) and video_streamer.is_native_healthy()
    if not native_ok:
        # Wayland or broken mss path: try ffmpeg/GStreamer fallback for MJPEG endpoint.
        ffmpeg_stream = _ffmpeg_mjpeg_stream(eff_monitor, eff_fps, eff_q, eff_w)
        if ffmpeg_stream is not None:
            return ffmpeg_stream
        gst_stream = _gst_mjpeg_stream(eff_fps, eff_q, eff_w)
        if gst_stream is not None:
            return gst_stream
        from fastapi import HTTPException
        reason = disabled or "native_capture_unhealthy"
        detail = _get_ffmpeg_diag().get("ffmpeg_last_error") or f"stream_unavailable:{reason}"
        raise HTTPException(501, detail)

    return StreamingResponse(
        generate_video_stream(eff_w, eff_q, eff_fps, bool(int(cursor)), eff_monitor),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/stream_stats")
def stream_stats(token: str = TokenDep):
    require_perm(token, "perm_stream")
    out = video_streamer.get_stats()
    try:
        out.update(_get_ffmpeg_diag())
        out["input_backend"] = getattr(INPUT_BACKEND, "name", "unknown")
        out["input_can_pointer"] = bool(getattr(INPUT_BACKEND, "can_pointer", False))
        out["input_can_keyboard"] = bool(getattr(INPUT_BACKEND, "can_keyboard", False))
        out["wayland_session"] = bool(_is_wayland_session())
    except Exception:
        pass
    return out


@router.get("/api/stream_offer")
def stream_offer(
    request: Request,
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = 30,
    max_w: int = 1280,
    quality: int = 25,
    bitrate_k: int = 1500,
    gop: int = 60,
    preset: str = "ultrafast",
    low_latency: int = 1,
):
    require_perm(token, "perm_stream")

    eff_monitor = int(monitor)
    eff_fps = max(5, int(fps))
    eff_w = max(0, int(max_w))
    eff_q = max(10, min(95, int(quality)))
    eff_bitrate = max(200, int(bitrate_k))
    eff_gop = max(10, int(gop))
    eff_preset = str(preset or "ultrafast")
    eff_low = bool(int(low_latency))

    can_capture = _capture_input_available(eff_monitor, eff_fps)
    h264_ok = can_capture and _codec_encoder_available("h264")
    h265_ok = can_capture and _codec_encoder_available("h265")
    mjpeg_native = video_streamer.disabled_reason() is None
    mjpeg_ffmpeg = _ffmpeg_available() and can_capture
    mjpeg_gst = os.name != "nt" and _is_wayland_session() and _gst_available() and _gst_supports_pipewire()
    mjpeg_ok = mjpeg_native or mjpeg_ffmpeg or mjpeg_gst

    base = str(request.base_url).rstrip("/")

    def _url(path: str, params: Dict[str, Any]) -> str:
        qp = urlencode({k: v for k, v in params.items() if v is not None})
        return f"{base}{path}?{qp}" if qp else f"{base}{path}"

    candidates = []
    if h264_ok:
        candidates.append(
            {
                "id": "h264_ts",
                "codec": "h264",
                "container": "mpegts",
                "mime": "video/mp2t",
                "url": _url(
                    "/video_h264",
                    {
                        "token": token,
                        "monitor": eff_monitor,
                        "fps": eff_fps,
                        "bitrate_k": eff_bitrate,
                        "gop": eff_gop,
                        "preset": eff_preset,
                        "max_w": eff_w,
                        "low_latency": 1 if eff_low else 0,
                    },
                ),
            }
        )

    if mjpeg_ok:
        candidates.append(
            {
                "id": "mjpeg",
                "codec": "mjpeg",
                "container": "multipart",
                "mime": "multipart/x-mixed-replace; boundary=frame",
                "url": _url(
                    "/video_feed",
                    {
                        "token": token,
                        "monitor": eff_monitor,
                        "fps": eff_fps,
                        "max_w": eff_w,
                        "quality": eff_q,
                        "cursor": 1,
                        "low_latency": 1 if eff_low else 0,
                    },
                ),
            }
        )

    if h265_ok:
        candidates.append(
            {
                "id": "h265_ts",
                "codec": "h265",
                "container": "mpegts",
                "mime": "video/mp2t",
                "url": _url(
                    "/video_h265",
                    {
                        "token": token,
                        "monitor": eff_monitor,
                        "fps": eff_fps,
                        "bitrate_k": max(300, int(eff_bitrate * 0.8)),
                        "gop": eff_gop,
                        "preset": eff_preset,
                        "max_w": eff_w,
                        "low_latency": 1 if eff_low else 0,
                    },
                ),
            }
        )

    return {
        "recommended": candidates[0]["id"] if candidates else None,
        "candidates": candidates,
        "support": {
            "capture_input": can_capture,
            "h264_encoder": _codec_encoder_available("h264"),
            "h265_encoder": _codec_encoder_available("h265"),
            "mjpeg_native": mjpeg_native,
            "mjpeg_ffmpeg": mjpeg_ffmpeg,
            "mjpeg_gstreamer": mjpeg_gst,
        },
        "diag": _get_ffmpeg_diag(),
    }


@router.get("/api/monitors")
def list_monitors(token: str = TokenDep):
    require_perm(token, "perm_stream")
    out = []
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if len(monitors) == 1:
                m = monitors[0]
                out.append(
                    {
                        "id": 1,
                        "left": int(m.get("left", 0)),
                        "top": int(m.get("top", 0)),
                        "width": int(m.get("width", 0)),
                        "height": int(m.get("height", 0)),
                        "primary": True,
                    }
                )
            else:
                for i, m in enumerate(monitors):
                    if i == 0:
                        continue
                    out.append(
                        {
                            "id": i,
                            "left": int(m.get("left", 0)),
                            "top": int(m.get("top", 0)),
                            "width": int(m.get("width", 0)),
                            "height": int(m.get("height", 0)),
                            "primary": i == 1,
                        }
                    )
    except Exception:
        pass
    return {"monitors": out}


def _ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg"))


def _stream_headers() -> Dict[str, str]:
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Accel-Buffering": "no",
    }


def _codec_encoder_available(codec: str) -> bool:
    if not _ffmpeg_available():
        return False
    if codec == "h264":
        return _ffmpeg_supports_encoder("libx264")
    if codec == "h265":
        return _ffmpeg_supports_encoder("libx265")
    return False


def _capture_input_available(monitor: int, fps: int) -> bool:
    return bool(_build_ffmpeg_input_arg_sets(monitor, fps))


def _spawn_stream_process(
    cmd: list,
    media_type: str,
    *,
    settle_s: float,
    stderr_lines: int,
    exit_tag: str,
    first_chunk_timeout: float = 2.5,
):
    _set_ffmpeg_diag(cmd, None)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, bufsize=0)
    except Exception as e:
        _set_ffmpeg_diag(cmd, f"{type(e).__name__}: {e}")
        return None

    def _stderr_reader():
        try:
            if not proc.stderr:
                return
            last = None
            for _ in range(max(1, int(stderr_lines))):
                line = proc.stderr.readline()
                if not line:
                    break
                txt = line.decode("utf-8", errors="replace").strip()
                if txt:
                    last = txt
            if last:
                _set_ffmpeg_diag(cmd, last)
        except Exception:
            pass

    threading.Thread(target=_stderr_reader, daemon=True).start()

    stdout_q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=16)

    def _stdout_reader():
        try:
            if not proc.stdout:
                return
            for chunk in iter(lambda: proc.stdout.read(64 * 1024), b""):
                if not chunk:
                    break
                try:
                    stdout_q.put(chunk, timeout=1.0)
                except Exception:
                    pass
        finally:
            try:
                stdout_q.put(None, timeout=0.2)
            except Exception:
                pass

    threading.Thread(target=_stdout_reader, daemon=True).start()

    try:
        time.sleep(max(0.05, float(settle_s)))
        if proc.poll() is not None:
            _set_ffmpeg_diag(cmd, _ffmpeg_last_error or f"{exit_tag}:{proc.returncode}")
            return None
    except Exception:
        pass

    first_chunk: Optional[bytes] = None
    deadline = time.time() + max(0.3, float(first_chunk_timeout))
    while time.time() < deadline and first_chunk is None:
        if proc.poll() is not None:
            _set_ffmpeg_diag(cmd, _ffmpeg_last_error or f"{exit_tag}:{proc.returncode}")
            return None
        try:
            item = stdout_q.get(timeout=0.1)
        except queue.Empty:
            continue
        if item is None:
            _set_ffmpeg_diag(cmd, _ffmpeg_last_error or f"{exit_tag}:eof_before_output")
            return None
        first_chunk = item

    if first_chunk is None:
        _set_ffmpeg_diag(cmd, f"{exit_tag}:no_output_timeout")
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        return None

    def _gen():
        try:
            yield first_chunk
            while True:
                item = stdout_q.get()
                if item is None:
                    break
                yield item
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass

    return StreamingResponse(_gen(), media_type=media_type, headers=_stream_headers())


def _build_ffmpeg_cmds(
    codec: str,
    monitor: int,
    fps: int,
    bitrate_k: int,
    gop: int,
    preset: str,
    max_w: int = 0,
    low_latency: bool = False,
) -> list[list]:
    if codec not in ("h264", "h265"):
        return []
    if not _codec_encoder_available(codec):
        return []
    fps = max(5, int(fps))
    bitrate_k = max(200, int(bitrate_k))
    gop = max(10, int(gop))
    if low_latency:
        gop = min(gop, max(10, fps))
    preset = str(preset or "ultrafast")
    max_w = max(0, int(max_w))

    enc = "libx264" if codec == "h264" else "libx265"
    input_arg_sets = _build_ffmpeg_input_arg_sets(monitor, fps)
    if not input_arg_sets:
        return []

    out: list[list] = []
    for input_args in input_arg_sets:
        cmd = ["ffmpeg", "-loglevel", "error", *input_args]
        cmd += [
            "-an",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            enc,
        ]
        if max_w > 0:
            cmd += ["-vf", f"scale={max_w}:-2:flags=fast_bilinear:force_original_aspect_ratio=decrease"]
        if codec == "h264":
            cmd += ["-profile:v", "baseline"]
        cmd += [
            "-preset",
            preset,
            "-tune",
            "zerolatency",
            "-b:v",
            f"{bitrate_k}k",
            "-maxrate",
            f"{bitrate_k}k",
            "-bufsize",
            f"{bitrate_k * 2}k",
            "-g",
            str(gop),
            "-keyint_min",
            str(gop),
            "-bf",
            "0",
            "-f",
            "mpegts",
            "pipe:1",
        ]
        if codec == "h265":
            cmd.extend(["-x265-params", "repeat-headers=1:log-level=error"])
        out.append(cmd)
    return out


def _ffmpeg_mjpeg_stream(monitor: int, fps: int, quality: int, width: int):
    if not _ffmpeg_available():
        _set_ffmpeg_diag(None, "ffmpeg_unavailable")
        return None

    input_arg_sets = _build_ffmpeg_input_arg_sets(monitor, fps)
    if not input_arg_sets:
        if os.name != "nt" and _is_wayland_session() and not _ffmpeg_supports_pipewire():
            _set_ffmpeg_diag(None, "ffmpeg_missing_pipewire_support")
        else:
            _set_ffmpeg_diag(None, "ffmpeg_unsupported_or_capture_unavailable")
        return None

    q = max(10, min(95, int(quality)))
    # ffmpeg MJPEG q:v scale: 2(best) .. 31(worst)
    qv = int(round(31 - ((q - 10) * 29.0 / 85.0)))
    qv = max(2, min(31, qv))
    w = max(0, int(width))

    for input_args in input_arg_sets:
        cmd = [
            "ffmpeg",
            "-loglevel",
            "error",
            *input_args,
            "-an",
        ]
        if w > 0:
            cmd += ["-vf", f"scale={w}:-2:flags=fast_bilinear:force_original_aspect_ratio=decrease"]
        cmd += [
            "-c:v",
            "mjpeg",
            "-q:v",
            str(qv),
            "-f",
            "mpjpeg",
            "-boundary_tag",
            "frame",
            "pipe:1",
        ]
        stream = _spawn_stream_process(
            cmd,
            "multipart/x-mixed-replace; boundary=frame",
            settle_s=0.2,
            stderr_lines=120,
            exit_tag="ffmpeg_exited",
            first_chunk_timeout=2.5,
        )
        if stream is not None:
            return stream
    return None


def _ffmpeg_stream(
    codec: str,
    monitor: int,
    fps: int,
    bitrate_k: int,
    gop: int,
    preset: str,
    max_w: int = 0,
    low_latency: bool = False,
):
    if not _ffmpeg_available():
        _set_ffmpeg_diag(None, "ffmpeg_unavailable")
        return None
    cmds = _build_ffmpeg_cmds(codec, monitor, fps, bitrate_k, gop, preset, max_w=max_w, low_latency=low_latency)
    if not cmds:
        if not _codec_encoder_available(codec):
            _set_ffmpeg_diag(None, f"ffmpeg_missing_encoder:{codec}")
            return None
        is_wayland = _is_wayland_session()
        if os.name != "nt" and is_wayland and not _ffmpeg_supports_pipewire():
            _set_ffmpeg_diag(None, "ffmpeg_missing_pipewire_support")
        else:
            _set_ffmpeg_diag(None, "ffmpeg_unsupported_or_capture_unavailable")
        return None

    for cmd in cmds:
        stream = _spawn_stream_process(
            cmd,
            "video/mp2t",
            settle_s=0.15,
            stderr_lines=80,
            exit_tag="ffmpeg_exited",
            first_chunk_timeout=2.5,
        )
        if stream is not None:
            return stream
    return None


def _gst_mjpeg_stream(fps: int, quality: int, width: int):
    if not _is_wayland_session():
        return None
    if not _gst_available():
        return None
    if not _gst_supports_pipewire():
        _set_ffmpeg_diag(None, "gstreamer_missing_pipewire_support")
        return None

    fps = max(5, int(fps))
    q = max(10, min(95, int(quality)))
    w = max(0, int(width))
    node = str(os.environ.get("CYBERDECK_PIPEWIRE_NODE", "") or "").strip()

    cmd = ["gst-launch-1.0", "-q", "pipewiresrc"]
    # Allow explicit node override; otherwise let plugin choose default.
    if node and node.lower() not in ("default", "pipewire:"):
        cmd.append(f"path={node}")
    cmd += ["do-timestamp=true", "!", "videorate", "!", f"video/x-raw,framerate={fps}/1", "!", "videoconvert"]
    if w > 0:
        cmd += ["!", "videoscale", "!", f"video/x-raw,width={w}"]
    cmd += ["!", "jpegenc", f"quality={q}", "!", "multipartmux", "boundary=frame", "!", "fdsink", "fd=1"]

    return _spawn_stream_process(
        cmd,
        "multipart/x-mixed-replace; boundary=frame",
        settle_s=0.2,
        stderr_lines=120,
        exit_tag="gstreamer_exited",
        first_chunk_timeout=2.5,
    )


@router.api_route("/video_h264", methods=["GET", "HEAD"])
def video_h264(
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = 30,
    bitrate_k: int = 1500,
    gop: int = 60,
    preset: str = "ultrafast",
    max_w: int = 1280,
    low_latency: int = 1,
):
    require_perm(token, "perm_stream")
    eff_monitor = int(monitor)
    eff_fps = int(fps)
    eff_bitrate = int(bitrate_k)
    eff_gop = int(gop)
    eff_preset = str(preset or "ultrafast")
    eff_w = int(max_w)
    eff_low = bool(int(low_latency))
    if eff_low:
        eff_fps = min(60, max(10, eff_fps))
        eff_gop = min(eff_gop, max(10, eff_fps))
        eff_preset = "ultrafast"
    stream = _ffmpeg_stream(
        "h264",
        eff_monitor,
        eff_fps,
        eff_bitrate,
        eff_gop,
        eff_preset,
        max_w=eff_w,
        low_latency=eff_low,
    )
    if stream is None:
        from fastapi import HTTPException
        diag = _get_ffmpeg_diag()
        detail = diag.get("ffmpeg_last_error") or "ffmpeg_unavailable_or_unsupported"
        raise HTTPException(502, detail)
    return stream


@router.api_route("/video_h265", methods=["GET", "HEAD"])
def video_h265(
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = 30,
    bitrate_k: int = 1200,
    gop: int = 60,
    preset: str = "ultrafast",
    max_w: int = 1280,
    low_latency: int = 1,
):
    require_perm(token, "perm_stream")
    eff_monitor = int(monitor)
    eff_fps = int(fps)
    eff_bitrate = int(bitrate_k)
    eff_gop = int(gop)
    eff_preset = str(preset or "ultrafast")
    eff_w = int(max_w)
    eff_low = bool(int(low_latency))
    if eff_low:
        eff_fps = min(60, max(10, eff_fps))
        eff_gop = min(eff_gop, max(10, eff_fps))
        eff_preset = "ultrafast"
    stream = _ffmpeg_stream(
        "h265",
        eff_monitor,
        eff_fps,
        eff_bitrate,
        eff_gop,
        eff_preset,
        max_w=eff_w,
        low_latency=eff_low,
    )
    if stream is None:
        from fastapi import HTTPException
        diag = _get_ffmpeg_diag()
        detail = diag.get("ffmpeg_last_error") or "ffmpeg_unavailable_or_unsupported"
        raise HTTPException(502, detail)
    return stream
