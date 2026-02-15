from __future__ import annotations

from typing import Any

import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from io import BytesIO
from typing import Any, Dict, Optional
from urllib.parse import urlencode, unquote, urlparse

import mss
from PIL import Image, ImageDraw, ImageStat
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .auth import TokenDep, require_perm
from . import config
from .input_backend import INPUT_BACKEND
from .logging_config import log
from .protocol import protocol_payload
from .stream_adaptation import WidthStabilizer, parse_width_ladder



_ffmpeg_diag_lock = threading.Lock()
_ffmpeg_last_cmd: Optional[str] = None
_ffmpeg_last_error: Optional[str] = None
_ffmpeg_last_error_ts: float = 0.0

_ffmpeg_formats_lock = threading.Lock()
_ffmpeg_formats_cached: Optional[str] = None

_ffmpeg_encoders_lock = threading.Lock()
_ffmpeg_encoders_cached: Optional[str] = None

_pipewire_nodes_lock = threading.Lock()
_pipewire_nodes_cached: Optional[list[str]] = None
_pipewire_nodes_cached_ts: float = 0.0

_screenshot_tool_lock = threading.Lock()
_screenshot_tool_cached: Optional[str] = None

_gst_probe_lock = threading.Lock()
_gst_probe_ok: Optional[bool] = None
_gst_probe_ts: float = 0.0
_ffmpeg_probe_lock = threading.Lock()
_ffmpeg_probe_ok: Optional[bool] = None
_ffmpeg_probe_ts: float = 0.0
_shot_probe_lock = threading.Lock()
_shot_probe_ok: Optional[bool] = None
_shot_probe_ts: float = 0.0

_MJPEG_BACKENDS = ("native", "ffmpeg", "gstreamer", "screenshot")
_MJPEG_BACKEND_ALIASES = {
    "auto": "auto",
    "native": "native",
    "mss": "native",
    "ffmpeg": "ffmpeg",
    "gst": "gstreamer",
    "gstreamer": "gstreamer",
    "grim": "screenshot",
    "screenshot": "screenshot",
    "tool": "screenshot",
}

_ENV_WAYLAND = (
    os.name != "nt"
    and (
        (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower() == "wayland"
        or bool(os.environ.get("WAYLAND_DISPLAY"))
    )
)
_ALLOW_GNOME_SCREENSHOT = str(os.environ.get("CYBERDECK_ALLOW_GNOME_SCREENSHOT", "0") or "0").strip() == "1"
_DEFAULT_MJPEG_W = max(640, int(os.environ.get("CYBERDECK_MJPEG_DEFAULT_W", "960" if _ENV_WAYLAND else "1280")))
_DEFAULT_MJPEG_Q = max(20, min(95, int(os.environ.get("CYBERDECK_MJPEG_DEFAULT_Q", "42" if _ENV_WAYLAND else "55"))))
_DEFAULT_MJPEG_LOW_LATENCY = 1 if os.environ.get("CYBERDECK_MJPEG_LOWLAT_DEFAULT", "1") == "1" else 0
_DEFAULT_OFFER_MAX_W = max(640, int(os.environ.get("CYBERDECK_STREAM_OFFER_MAX_W", "1600")))
_DEFAULT_OFFER_Q = max(20, min(95, int(os.environ.get("CYBERDECK_STREAM_OFFER_Q", "55"))))
_DEFAULT_H264_BITRATE_K = max(500, int(os.environ.get("CYBERDECK_H264_BITRATE_K", "3200")))
_DEFAULT_H265_BITRATE_K = max(500, int(os.environ.get("CYBERDECK_H265_BITRATE_K", "2400")))
_LOW_LATENCY_MAX_W = max(640, int(os.environ.get("CYBERDECK_LOWLAT_MAX_W", "960" if _ENV_WAYLAND else "1280")))
_LOW_LATENCY_MAX_Q = max(20, min(95, int(os.environ.get("CYBERDECK_LOWLAT_MAX_Q", "42" if _ENV_WAYLAND else "50"))))
_LOW_LATENCY_MAX_FPS = max(10, int(os.environ.get("CYBERDECK_LOWLAT_MAX_FPS", "24" if _ENV_WAYLAND else "45")))
_MIN_MJPEG_Q = max(10, min(95, int(os.environ.get("CYBERDECK_MJPEG_MIN_Q", "45"))))
_MIN_MJPEG_Q_LOWLAT = max(10, min(95, int(os.environ.get("CYBERDECK_MJPEG_MIN_Q_LOWLAT", "35"))))
_SCREENSHOT_MAX_W = max(480, int(os.environ.get("CYBERDECK_SCREENSHOT_MAX_W", "960")))
_SCREENSHOT_MAX_Q = max(20, min(95, int(os.environ.get("CYBERDECK_SCREENSHOT_MAX_Q", "40"))))
_SCREENSHOT_MAX_FPS = max(2, int(os.environ.get("CYBERDECK_SCREENSHOT_MAX_FPS", "10" if _ENV_WAYLAND else "15")))
try:
    _JPEG_SUBSAMPLING = int(os.environ.get("CYBERDECK_JPEG_SUBSAMPLING", "2" if _ENV_WAYLAND else "0"))
except Exception:
    _JPEG_SUBSAMPLING = 2 if _ENV_WAYLAND else 0
if _JPEG_SUBSAMPLING not in (0, 1, 2):
    _JPEG_SUBSAMPLING = 2 if _ENV_WAYLAND else 0
_FAST_RESIZE = str(os.environ.get("CYBERDECK_FAST_RESIZE", "1" if _ENV_WAYLAND else "0") or "0").strip() == "1"
_RESAMPLE_FILTER = Image.Resampling.BILINEAR if _FAST_RESIZE else Image.Resampling.LANCZOS
_DEFAULT_OFFER_CURSOR = 1 if os.environ.get("CYBERDECK_OFFER_CURSOR_DEFAULT", "0") == "1" else 0
_STREAM_FIRST_CHUNK_TIMEOUT_S = max(2.5, float(os.environ.get("CYBERDECK_STREAM_FIRST_CHUNK_TIMEOUT_S", "4.0")))
_STREAM_STALE_FRAME_KEEPALIVE_S = max(0.2, float(os.environ.get("CYBERDECK_STREAM_STALE_KEEPALIVE_S", "0.35")))
_STREAM_STDOUT_QUEUE_SIZE = max(1, int(os.environ.get("CYBERDECK_STREAM_STDOUT_QUEUE_SIZE", "1")))
_STREAM_STDOUT_READ_CHUNK = max(4096, int(os.environ.get("CYBERDECK_STREAM_STDOUT_READ_CHUNK", "32768")))
_STREAM_RECONNECT_HINT_MS = max(250, int(os.environ.get("CYBERDECK_STREAM_RECONNECT_HINT_MS", "700")))
_DEFAULT_OFFER_LOW_LATENCY = 1 if os.environ.get("CYBERDECK_OFFER_LOW_LATENCY_DEFAULT", "1") == "1" else 0
_ADAPTIVE_WIDTH_LADDER = parse_width_ladder(
    os.environ.get("CYBERDECK_ADAPT_WIDTH_LADDER", ""),
    [1920, 1600, 1440, 1366, 1280, 1152, 1024, 960, 854, 768, 640],
)
_ADAPTIVE_MIN_SWITCH_S = max(0.0, float(os.environ.get("CYBERDECK_ADAPT_MIN_SWITCH_S", "8.0")))
_ADAPTIVE_HYST_RATIO = max(0.0, min(0.9, float(os.environ.get("CYBERDECK_ADAPT_HYST_RATIO", "0.18"))))
_STREAM_MIN_W_FLOOR = max(0, int(os.environ.get("CYBERDECK_STREAM_MIN_W_FLOOR", "1024")))
_ADAPTIVE_RTT_HIGH_MS = max(80, int(os.environ.get("CYBERDECK_ADAPT_RTT_HIGH_MS", "220")))
_ADAPTIVE_RTT_CRIT_MS = max(_ADAPTIVE_RTT_HIGH_MS + 40, int(os.environ.get("CYBERDECK_ADAPT_RTT_CRIT_MS", "340")))
_ADAPTIVE_FPS_DROP_THRESHOLD = max(0.3, min(0.95, float(os.environ.get("CYBERDECK_ADAPT_FPS_DROP_THRESHOLD", "0.62"))))
_ADAPTIVE_DEC_FPS_STEP = max(1, int(os.environ.get("CYBERDECK_ADAPT_DEC_FPS_STEP", "2")))
_ADAPTIVE_DEC_W_STEP = max(16, int(os.environ.get("CYBERDECK_ADAPT_DEC_W_STEP", "64")))
_ADAPTIVE_DEC_Q_STEP = max(1, int(os.environ.get("CYBERDECK_ADAPT_DEC_Q_STEP", "5")))
_ADAPTIVE_INC_FPS_STEP = max(1, int(os.environ.get("CYBERDECK_ADAPT_INC_FPS_STEP", "1")))
_ADAPTIVE_INC_W_STEP = max(16, int(os.environ.get("CYBERDECK_ADAPT_INC_W_STEP", "64")))
_ADAPTIVE_INC_Q_STEP = max(1, int(os.environ.get("CYBERDECK_ADAPT_INC_Q_STEP", "2")))
_WIDTH_STABILIZER = WidthStabilizer(
    ladder=_ADAPTIVE_WIDTH_LADDER,
    min_switch_s=_ADAPTIVE_MIN_SWITCH_S,
    hysteresis_ratio=_ADAPTIVE_HYST_RATIO,
    min_floor=_STREAM_MIN_W_FLOOR,
    enabled=(os.environ.get("CYBERDECK_DISABLE_WIDTH_STABILIZER", "0") != "1"),
)

def _stream_log_enabled() -> bool:
    """Return whether stream-level verbose logs should be emitted."""
    return bool(getattr(config, "VERBOSE_STREAM_LOG", True) or getattr(config, "DEBUG", False))


def _cmd_preview(cmd: list, max_len: int = 260) -> str:
    """Render a bounded one-line command preview suitable for diagnostics logs."""
    txt = " ".join([str(x) for x in (cmd or [])]).strip()
    if len(txt) > max_len:
        return txt[:max_len] + "..."
    return txt


def _stream_headers() -> Dict[str, str]:
    """Return response headers that disable proxy/client buffering for live streams."""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Accel-Buffering": "no",
    }


def _ffmpeg_available() -> bool:
    """Return True when ffmpeg binary is available in PATH."""
    return bool(shutil.which("ffmpeg"))


def _set_ffmpeg_diag(cmd: Optional[list], err: Optional[str]) -> None:
    """Persist the last backend command and error snippet for troubleshooting endpoints."""
    global _ffmpeg_last_cmd, _ffmpeg_last_error, _ffmpeg_last_error_ts
    with _ffmpeg_diag_lock:
        _ffmpeg_last_cmd = " ".join([str(x) for x in (cmd or [])]) if cmd else None
        _ffmpeg_last_error = str(err)[:800] if err else None
        _ffmpeg_last_error_ts = time.time() if err else _ffmpeg_last_error_ts


def _get_ffmpeg_diag() -> Dict[str, Any]:
    """Return a snapshot of backend availability and recent ffmpeg/gstreamer diagnostics."""
    with _ffmpeg_diag_lock:
        return {
            "ffmpeg_available": bool(_ffmpeg_available()),
            "ffmpeg_pipewire": bool(_ffmpeg_supports_pipewire()),
            "ffmpeg_libx264": bool(_ffmpeg_supports_encoder("libx264")),
            "ffmpeg_libx265": bool(_ffmpeg_supports_encoder("libx265")),
            "gst_available": bool(_gst_available()),
            "gst_pipewire": bool(_gst_supports_pipewire()),
            "grim_available": bool(_grim_available()),
            "screenshot_tool_available": bool(_screenshot_tool_available()),
            "screenshot_tool_selected": _selected_screenshot_tool(),
            "ffmpeg_last_cmd": _ffmpeg_last_cmd,
            "ffmpeg_last_error": _ffmpeg_last_error,
            "ffmpeg_last_error_ts": float(_ffmpeg_last_error_ts) if _ffmpeg_last_error_ts else None,
            "pipewire_sources": _pipewire_source_candidates()[:8],
        }


def _ffmpeg_formats() -> str:
    """Return cached `ffmpeg -formats` output, probing the binary when cache is empty."""
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
    """Return True when ffmpeg input formats include the pipewire capture source."""
    txt = _ffmpeg_formats()
    return "pipewire" in txt.lower()


def _ffmpeg_supports_x11grab() -> bool:
    """Return True when ffmpeg input formats include x11grab fallback capture."""
    txt = _ffmpeg_formats()
    return "x11grab" in txt.lower()


def _jpeg_has_visible_content(raw: bytes) -> bool:
    """Reject near-black or near-constant JPEG frames to detect broken capture output."""
    try:
        img = Image.open(BytesIO(raw)).convert("L")
        ex = img.getextrema()
        stat = ImageStat.Stat(img)
        mean = float(stat.mean[0]) if stat.mean else 0.0
        if not ex:
            return True
        span = int(ex[1]) - int(ex[0])
        # Reject fully-black / near-constant dark frames.
        return mean >= 3.0 or span >= 4
    except Exception:
        return True


def _extract_first_jpeg(raw: bytes) -> Optional[bytes]:
    """Extract the first complete JPEG frame from a multipart byte buffer."""
    try:
        buf = bytes(raw or b"")
        if not buf:
            return None
        soi = buf.find(b"\xff\xd8")
        if soi < 0:
            return None
        eoi = buf.find(b"\xff\xd9", soi + 2)
        if eoi < 0:
            return None
        return buf[soi : eoi + 2]
    except Exception:
        return None


def _save_jpeg(img: Image.Image, quality: int) -> bytes:
    """Encode PIL image into JPEG bytes using configured quality/subsampling policy."""
    q = max(10, min(95, int(quality)))
    buf = BytesIO()
    # Keep encode options stable across all video backends to avoid format drift.
    img.save(buf, format="JPEG", quality=q, subsampling=_JPEG_SUBSAMPLING, progressive=False, optimize=False)
    return buf.getvalue()


def _ffmpeg_encoders() -> str:
    """Return cached `ffmpeg -encoders` output, probing ffmpeg when needed."""
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
    """Return True when the requested ffmpeg encoder name is available."""
    needle = str(name or "").strip().lower()
    if not needle:
        return False
    txt = _ffmpeg_encoders().lower()
    return needle in txt


def _gst_available() -> bool:
    """Return True when gst-launch is available in the current runtime environment."""
    return bool(shutil.which("gst-launch-1.0"))


def _grim_available() -> bool:
    """Return True when grim is installed and callable."""
    return bool(shutil.which("grim"))


def _screenshot_tool_candidates() -> list[str]:
    """Build ordered screenshot-tool candidates based on environment and user overrides."""
    out: list[str] = []
    forced = str(os.environ.get("CYBERDECK_SCREENSHOT_TOOL", "") or "").strip()
    if forced:
        out.append(forced)
    # Order: GNOME shell DBus, KDE KWin DBus, then CLI tools.
    if shutil.which("gdbus"):
        out.append("gdbus_gnome_shell")
    if shutil.which("qdbus") or shutil.which("qdbus6"):
        out.append("qdbus_kwin")
    # Prefer silent/fast capture tools first.
    if shutil.which("grim"):
        out.append("grim")
    if shutil.which("spectacle"):
        out.append("spectacle")
    if _ALLOW_GNOME_SCREENSHOT and shutil.which("gnome-screenshot"):
        out.append("gnome-screenshot")
    uniq: list[str] = []
    for x in out:
        sx = str(x or "").strip()
        if sx and sx not in uniq:
            uniq.append(sx)
    return uniq


def _selected_screenshot_tool() -> Optional[str]:
    """Return the currently cached screenshot tool selected by runtime probing."""
    with _screenshot_tool_lock:
        return _screenshot_tool_cached


def _mark_screenshot_tool(name: Optional[str]) -> None:
    """Cache the screenshot tool that successfully produced a frame."""
    with _screenshot_tool_lock:
        global _screenshot_tool_cached
        _screenshot_tool_cached = str(name or "").strip() or None


def _screenshot_tool_available() -> bool:
    """Return True when at least one Wayland screenshot tool can be used."""
    if _selected_screenshot_tool():
        return True
    return bool(_screenshot_tool_candidates())


def _gst_supports_pipewire() -> bool:
    """Return True when GStreamer pipewire source plugin is installed."""
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


def _gst_pipewire_capture_healthy() -> bool:
    """Run a short GStreamer probe to confirm pipewire capture produces frames."""
    global _gst_probe_ok, _gst_probe_ts
    now = time.time()
    with _gst_probe_lock:
        if _gst_probe_ok is not None and (now - _gst_probe_ts) < 8.0:
            return bool(_gst_probe_ok)

    if not _is_wayland_session():
        ok = False
    elif not _gst_available() or not _gst_supports_pipewire():
        ok = False
    else:
        cmd = [
            "gst-launch-1.0",
            "-q",
            "pipewiresrc",
            "num-buffers=1",
            "do-timestamp=true",
            "!",
            "videoconvert",
            "!",
            "jpegenc",
            "quality=45",
            "!",
            "fakesink",
            "sync=false",
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=4.0,
                check=False,
            )
            ok = int(proc.returncode) == 0
        except Exception:
            ok = False

    with _gst_probe_lock:
        _gst_probe_ok = bool(ok)
        _gst_probe_ts = now
    return bool(ok)


def _wayland_allow_x11_fallback() -> bool:
    """Return whether X11 fallback capture is allowed in a Wayland session."""
    if os.name == "nt" or not _is_wayland_session():
        return False
    # Default ON for mixed Wayland/XWayland sessions; can be disabled by env.
    return bool(os.environ.get("DISPLAY")) and (os.environ.get("CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK", "1") == "1")


def _ffmpeg_mjpeg_capture_healthy(monitor: int = 1, fps: int = 20) -> bool:
    """Run a short ffmpeg probe to confirm MJPEG capture is currently healthy."""
    global _ffmpeg_probe_ok, _ffmpeg_probe_ts
    now = time.time()
    with _ffmpeg_probe_lock:
        if _ffmpeg_probe_ok is not None and (now - _ffmpeg_probe_ts) < 8.0:
            return bool(_ffmpeg_probe_ok)

    ok = False
    if _ffmpeg_available():
        for input_args in _build_ffmpeg_input_arg_sets(int(monitor), max(5, int(fps))):
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                *input_args,
                "-an",
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=4.0,
                    check=False,
                )
                raw = bytes(proc.stdout or b"")
                if int(proc.returncode) == 0 and (b"\xff\xd8" in raw) and _jpeg_has_visible_content(raw):
                    ok = True
                    break
            except Exception:
                continue

    with _ffmpeg_probe_lock:
        _ffmpeg_probe_ok = bool(ok)
        _ffmpeg_probe_ts = now
    return bool(ok)


def _is_wayland_session() -> bool:
    """Detect whether current Linux session is Wayland."""
    if os.name == "nt":
        return False
    xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    if xdg_type == "wayland":
        return True
    if xdg_type == "x11":
        return False
    return bool(os.environ.get("WAYLAND_DISPLAY")) and not bool(os.environ.get("DISPLAY"))


def _is_gnome_session() -> bool:
    """Detect whether current desktop environment is GNOME-like."""
    vals = [
        os.environ.get("XDG_CURRENT_DESKTOP"),
        os.environ.get("DESKTOP_SESSION"),
        os.environ.get("GDMSESSION"),
    ]
    txt = " ".join([str(x or "") for x in vals]).lower()
    return "gnome" in txt


def _get_monitor_rect(monitor: int) -> Optional[tuple[int, int, int, int]]:
    """Resolve monitor geometry for the requested monitor index."""
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
    """Build ordered pipewire source candidates from env and runtime discovery."""
    out: list[str] = []
    env_sources = [
        os.environ.get("CYBERDECK_PIPEWIRE_NODE"),
        os.environ.get("PIPEWIRE_NODE"),
    ]
    for item in env_sources:
        val = str(item or "").strip()
        if val:
            out.append(val)
    for item in _discover_pipewire_nodes():
        val = str(item or "").strip()
        if val:
            out.append(val)
    # Different ffmpeg builds expect different default aliases.
    # Avoid hardcoding "0" - it often breaks GStreamer path selection on Linux.
    out.extend(["default", "pipewire:"])
    uniq: list[str] = []
    for x in out:
        if x not in uniq:
            uniq.append(x)
    return uniq


def _discover_pipewire_nodes() -> list[str]:
    """Discover likely screencast node ids from `pw-cli ls Node` output."""
    global _pipewire_nodes_cached, _pipewire_nodes_cached_ts

    now = time.time()
    with _pipewire_nodes_lock:
        if _pipewire_nodes_cached is not None and (now - _pipewire_nodes_cached_ts) < 5.0:
            return list(_pipewire_nodes_cached)

    pw_cli = shutil.which("pw-cli")
    if not pw_cli:
        with _pipewire_nodes_lock:
            _pipewire_nodes_cached = []
            _pipewire_nodes_cached_ts = now
        return []

    try:
        proc = subprocess.run(
            [pw_cli, "ls", "Node"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2.0,
            check=False,
        )
        txt = str(proc.stdout or "")
    except Exception:
        txt = ""

    nodes: list[str] = []
    current_id: Optional[str] = None
    current_name = ""
    current_desc = ""
    current_media = ""

    def _flush_current() -> None:
        """Persist current node id when collected metadata matches screen-capture semantics."""
        nonlocal current_id, current_name, current_desc, current_media
        if not current_id:
            return
        meta = f"{current_name} {current_desc} {current_media}".lower()
        if not meta.strip():
            return
        looks_video = "video" in meta
        looks_screen = any(k in meta for k in ("screen", "monitor", "portal", "xdpw", "screencast", "desktop", "wayland"))
        looks_camera = any(k in meta for k in ("camera", "webcam"))
        if looks_video and looks_screen and not looks_camera:
            nodes.append(current_id)

    for raw in txt.splitlines():
        line = raw.strip()
        if line.startswith("id ") and "," in line:
            _flush_current()
            try:
                current_id = line.split("id ", 1)[1].split(",", 1)[0].strip()
            except Exception:
                current_id = None
            current_name = ""
            current_desc = ""
            current_media = ""
            continue
        if "node.name =" in line:
            current_name = line.split("=", 1)[1].strip().strip('"')
            continue
        if "node.description =" in line:
            current_desc = line.split("=", 1)[1].strip().strip('"')
            continue
        if "media.class =" in line:
            current_media = line.split("=", 1)[1].strip().strip('"')
            continue

    _flush_current()

    uniq: list[str] = []
    for x in nodes:
        sx = str(x).strip()
        if sx and sx not in uniq:
            uniq.append(sx)

    with _pipewire_nodes_lock:
        _pipewire_nodes_cached = uniq
        _pipewire_nodes_cached_ts = now
    return uniq


def _gst_pipewire_source_candidates() -> list[str]:
    """Build sanitized GStreamer pipewire source candidates for probing/streaming."""
    # Prefer default source first (no explicit path). Some sessions expose valid
    # screencast only through default portal routing.
    out: list[str] = [""]
    for src in _pipewire_source_candidates():
        s = str(src or "").strip()
        if not s:
            continue
        sl = s.lower()
        if sl in ("default", "pipewire:"):
            s = ""
        # "0" is a frequent non-working sentinel in distro defaults.
        if s == "0":
            continue
        if s.isdigit() and int(s) <= 0:
            continue
        if s not in out:
            out.append(s)
    return out


def _x11_input_args(monitor: int, fps: int) -> Optional[list]:
    """Build ffmpeg x11grab input arguments for the requested monitor and frame rate."""
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
    """Build ffmpeg input argument candidates across Wayland/X11/Windows paths."""
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
        # Optional escape hatch for mixed sessions where XWayland capture is desired.
        if _wayland_allow_x11_fallback() and _ffmpeg_supports_x11grab():
            x11_args = _x11_input_args(monitor, fps)
            if x11_args:
                out.append(x11_args)
        return out

    x11_args = _x11_input_args(monitor, fps)
    if not x11_args:
        return []
    return [x11_args]


def _build_ffmpeg_input_args(monitor: int, fps: int) -> Optional[list]:
    """Return the first ffmpeg input argument candidate for current environment."""
    sets = _build_ffmpeg_input_arg_sets(monitor, fps)
    return sets[0] if sets else None


__all__ = [name for name in globals() if not name.startswith("__")]
