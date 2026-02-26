from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi.responses import StreamingResponse

from .core import (
    _MJPEG_BACKENDS,
    _MJPEG_BACKEND_ALIASES,
    _STREAM_STALE_FRAME_KEEPALIVE_S,
    _build_ffmpeg_input_arg_sets,
    _env_bool,
    _ffmpeg_available,
    _ffmpeg_mjpeg_capture_healthy,
    _ffmpeg_supports_pipewire,
    _ffmpeg_supports_x11grab,
    _grim_available,
    _gst_available,
    _gst_pipewire_capture_healthy,
    _gst_supports_pipewire,
    _is_gnome_session,
    _is_wayland_session,
    _jpeg_has_visible_content,
    _screenshot_tool_available,
    _shot_probe_lock,
    _shot_probe_ok,
    _shot_probe_ts,
    _stream_headers,
    _wayland_allow_x11_fallback,
)
from .streamer import video_streamer
from .ffmpeg import _ffmpeg_mjpeg_stream
from .wayland import _gst_mjpeg_stream, _grim_mjpeg_stream, _wayland_grim_frame, _wayland_screenshot_tool_frame

log = logging.getLogger(__name__)

def generate_video_stream(w: int, q: int, fps: int, cursor: bool, monitor: int) -> Any:
    """Yield multipart MJPEG frames from native streamer with stale-frame keepalive fallback."""
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    min_dt = 1.0 / max(5, int(fps))
    last_frame = b""
    last_emit_ts = 0.0
    while True:
        t0 = time.perf_counter()
        try:
            frame = video_streamer.get_jpeg(w, q, cursor, monitor, fps=fps)
            if frame:
                yield boundary + frame + b"\r\n"
                last_frame = frame
                last_emit_ts = time.monotonic()
            elif last_frame:
                now_m = time.monotonic()
                if (now_m - last_emit_ts) >= _STREAM_STALE_FRAME_KEEPALIVE_S:
                    yield boundary + last_frame + b"\r\n"
                    last_emit_ts = now_m
        except Exception:
            log.exception("Video stream generator error")
            time.sleep(0.05)
        dt = time.perf_counter() - t0
        if dt < min_dt:
            time.sleep(min_dt - dt)


def _lowlat_bitrate_cap_k(max_w: int, fps: int, codec: str = "h264") -> int:
    """Estimate conservative bitrate cap for low-latency transport at given size/fps."""
    w = max(320, int(max_w or 1280))
    f = max(10, int(fps or 30))
    # Empirical bitrate budget tuned for low latency on LAN/Wi-Fi:
    # keep enough detail for desktop UI, but avoid queue growth under jitter.
    base = 4200.0 * (w / 1280.0) * (f / 30.0)
    if str(codec or "").lower() == "h265":
        base *= 0.72
    cap = int(round(base))
    return max(1200, min(18000, cap))


def _normalize_mjpeg_backend(value: Optional[str]) -> str:
    """Normalize user/backend aliases into canonical backend identifiers."""
    raw = str(value or "").strip().lower()
    if not raw:
        return "auto"
    return _MJPEG_BACKEND_ALIASES.get(raw, "auto")


def _mjpeg_backend_status(monitor: int, fps: int, probe: bool = False) -> Dict[str, bool]:
    """Return backend availability map for native/ffmpeg/gstreamer/screenshot MJPEG paths.

    `probe=False` keeps this path fast for request-time negotiation (`/api/stream_offer`,
    `/video_feed`) by relying on capability checks only.
    """
    disabled = video_streamer.disabled_reason()
    native_ok = (disabled is None) and video_streamer.is_native_healthy()
    gstreamer_capable = (
        os.name != "nt"
        and _is_wayland_session()
        and _gst_available()
        and _gst_supports_pipewire()
    )
    gstreamer_ok = (
        gstreamer_capable
        and (not probe or _gst_pipewire_capture_healthy())
    )
    screenshot_capable = (
        os.name != "nt"
        and _is_wayland_session()
        and (_grim_available() or _screenshot_tool_available())
    )
    ffmpeg_enabled = not _env_bool("CYBERDECK_DISABLE_FFMPEG_MJPEG", False)
    ffmpeg_capable = ffmpeg_enabled and _ffmpeg_available() and bool(_build_ffmpeg_input_arg_sets(monitor, fps))
    ffmpeg_ok = ffmpeg_capable and (not probe or _ffmpeg_mjpeg_capture_healthy(monitor, fps))

    # Wayland + x11grab-only ffmpeg is frequently unstable for mobile MJPEG clients.
    # If screenshot/gstreamer is available, prefer those by masking ffmpeg in auto selection.
    wayland_pref_non_x11grab = _env_bool("CYBERDECK_WAYLAND_PREFER_NON_X11GRAB", True)
    force_x11grab = _env_bool("CYBERDECK_FORCE_WAYLAND_X11GRAB", False)
    if (
        ffmpeg_ok
        and os.name != "nt"
        and _is_wayland_session()
        and wayland_pref_non_x11grab
        and not force_x11grab
        and not _ffmpeg_supports_pipewire()
        and _ffmpeg_supports_x11grab()
        and (gstreamer_capable or screenshot_capable)
    ):
        ffmpeg_ok = False

    screenshot_ok = (
        screenshot_capable
        and (not probe or _screenshot_capture_healthy())
    )
    return {
        "native": bool(native_ok),
        "ffmpeg": bool(ffmpeg_ok),
        "gstreamer": bool(gstreamer_ok),
        "screenshot": bool(screenshot_ok),
    }


def _mjpeg_backend_order(preferred: str, status: Dict[str, bool]) -> list[str]:
    """Compute effective backend order and keep only currently available backends."""
    preferred = _normalize_mjpeg_backend(preferred)
    env_order = str(os.environ.get("CYBERDECK_MJPEG_BACKEND_ORDER", "") or "").strip()
    parsed_env: list[str] = []
    if env_order:
        for x in env_order.split(","):
            name = _normalize_mjpeg_backend(x)
            if name != "auto" and name in _MJPEG_BACKENDS and name not in parsed_env:
                parsed_env.append(name)

    if parsed_env:
        base = parsed_env
    elif _is_wayland_session() and _is_gnome_session():
        # GNOME screenshot path is reliable but often low-fps/blurred.
        # Keep realtime pipelines first and leave screenshot as fallback.
        if _prefer_gst_over_ffmpeg_mjpeg():
            base = ["gstreamer", "ffmpeg", "screenshot", "native"]
        else:
            base = ["ffmpeg", "gstreamer", "screenshot", "native"]
    elif _prefer_gst_over_ffmpeg_mjpeg():
        base = ["gstreamer", "screenshot", "ffmpeg", "native"]
    else:
        base = ["native", "ffmpeg", "gstreamer", "screenshot"]

    if preferred != "auto":
        ordered = [preferred] + [x for x in base if x != preferred]
    else:
        ordered = list(base)

    for x in _MJPEG_BACKENDS:
        if x not in ordered:
            ordered.append(x)

    # Keep only currently available backends, preserve order.
    available = [x for x in ordered if status.get(x, False)]
    return available


def _native_mjpeg_stream(w: int, q: int, fps: int, cursor: int, monitor: int) -> Any:
    """Create StreamingResponse for native MJPEG generator path."""
    return StreamingResponse(
        generate_video_stream(w, q, fps, bool(int(cursor)), monitor),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers=_stream_headers(),
    )


def _mjpeg_stream_for_backend(
    backend: str,
    *,
    monitor: int,
    fps: int,
    quality: int,
    width: int,
    cursor: int,
) -> Any:
    """Dispatch MJPEG stream creation to the selected backend implementation."""
    name = _normalize_mjpeg_backend(backend)
    if name == "native":
        return _native_mjpeg_stream(width, quality, fps, cursor, monitor)
    if name == "ffmpeg":
        if _env_bool("CYBERDECK_DISABLE_FFMPEG_MJPEG", False):
            return None
        return _ffmpeg_mjpeg_stream(monitor, fps, quality, width)
    if name == "gstreamer":
        return _gst_mjpeg_stream(fps, quality, width)
    if name == "screenshot":
        return _grim_mjpeg_stream(fps, quality, width)
    return None


def _ffmpeg_wayland_capture_reliable() -> bool:
    """Return whether ffmpeg capture path is reliable in current Wayland context."""
    if os.name == "nt":
        return True
    if not _is_wayland_session():
        return True
    if not _ffmpeg_available():
        return False
    if _ffmpeg_supports_pipewire():
        return True
    if _wayland_allow_x11_fallback() and _ffmpeg_supports_x11grab():
        return True
    return False


def _prefer_gst_over_ffmpeg_mjpeg() -> bool:
    """Return True when GStreamer should be preferred over ffmpeg for MJPEG."""
    return (
        os.name != "nt"
        and _is_wayland_session()
        and not _ffmpeg_wayland_capture_reliable()
        and _gst_supports_pipewire()
    )


def _screenshot_capture_healthy() -> bool:
    """Probe screenshot fallback to verify it can return visible non-empty frames."""
    global _shot_probe_ok, _shot_probe_ts
    now = time.time()
    with _shot_probe_lock:
        if _shot_probe_ok is not None and (now - _shot_probe_ts) < 8.0:
            return bool(_shot_probe_ok)

    ok = False
    if os.name != "nt" and _is_wayland_session():
        frame = _wayland_grim_frame(640, 45)
        if not frame:
            frame = _wayland_screenshot_tool_frame(640, 45)
        ok = bool(frame) and _jpeg_has_visible_content(frame)

    with _shot_probe_lock:
        _shot_probe_ok = bool(ok)
        _shot_probe_ts = now
    return bool(ok)


__all__ = [name for name in globals() if not name.startswith("__")]

