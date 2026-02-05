import os
import shutil
import subprocess
import threading
import time
from io import BytesIO
from typing import Any, Dict, Optional

import mss
import pyautogui
from PIL import Image, ImageDraw
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .auth import TokenDep, require_perm
from . import config
from .logging_config import log


router = APIRouter()


class _VideoStreamer:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_raw = None
        self._raw_seq = 0
        self._latest_jpeg = None
        self._latest_jpeg_key = None
        self._latest_jpeg_seq = -1
        self._ts = 0.0
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

    def _loop(self):
        try:
            with mss.mss() as sct:
                min_dt = 1.0 / max(5, self.base_fps)
                while not self._stop.is_set():
                    t0 = time.perf_counter()
                    try:
                        g0 = time.perf_counter()
                        with self._lock:
                            desired_w, desired_q, desired_cursor, desired_monitor = self._desired_key
                        monitors = sct.monitors
                        if not monitors or len(monitors) < 2:
                            monitor = monitors[0]
                            desired_monitor = 0
                        else:
                            if desired_monitor < 1 or desired_monitor >= len(monitors):
                                desired_monitor = 1
                            monitor = monitors[desired_monitor]

                        sct_img = sct.grab(monitor)
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
                    except Exception:
                        log.exception("Video grab/encode failed")
                        time.sleep(0.05)
                    dt = time.perf_counter() - t0
                    if dt < min_dt:
                        time.sleep(min_dt - dt)
        except Exception:
            log.exception("Video streamer died")

    def _encode(self, raw_bgra: bytes, size, monitor, w: int, q: int, cursor: bool) -> bytes:
        img = Image.frombytes("RGB", size, raw_bgra, "raw", "BGRX")
        if cursor:
            try:
                cx, cy = pyautogui.position()
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


@router.get("/video_feed")
def video_feed(
    token: str = TokenDep,
    w: Optional[int] = None,
    q: Optional[int] = None,
    max_w: Optional[int] = None,
    quality: Optional[int] = None,
    fps: int = 30,
    cursor: int = 0,
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
    return video_streamer.get_stats()


@router.get("/api/monitors")
def list_monitors(token: str = TokenDep):
    require_perm(token, "perm_stream")
    out = []
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
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


def _build_ffmpeg_cmd(codec: str, monitor: int, fps: int, bitrate_k: int, gop: int, preset: str) -> Optional[list]:
    if os.name != "nt":
        return None
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if not monitors:
                return None
            if monitor < 1 or monitor >= len(monitors):
                monitor = 1
            m = monitors[monitor]
            left = int(m.get("left", 0))
            top = int(m.get("top", 0))
            width = int(m.get("width", 0))
            height = int(m.get("height", 0))
    except Exception:
        return None

    fps = max(5, int(fps))
    bitrate_k = max(200, int(bitrate_k))
    gop = max(10, int(gop))
    preset = str(preset or "ultrafast")

    enc = "libx264" if codec == "h264" else "libx265"

    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-f",
        "gdigrab",
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
        "-an",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        enc,
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
    return cmd


def _ffmpeg_stream(codec: str, monitor: int, fps: int, bitrate_k: int, gop: int, preset: str):
    if not _ffmpeg_available():
        return None
    cmd = _build_ffmpeg_cmd(codec, monitor, fps, bitrate_k, gop, preset)
    if not cmd:
        return None
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)

    def _gen():
        try:
            if not proc.stdout:
                return
            for chunk in iter(lambda: proc.stdout.read(64 * 1024), b""):
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass

    return StreamingResponse(
        _gen(),
        media_type="video/mp2t",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/video_h264")
def video_h264(
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = 30,
    bitrate_k: int = 1500,
    gop: int = 60,
    preset: str = "ultrafast",
):
    require_perm(token, "perm_stream")
    stream = _ffmpeg_stream("h264", int(monitor), int(fps), int(bitrate_k), int(gop), preset)
    if stream is None:
        from fastapi import HTTPException
        raise HTTPException(501, "ffmpeg_unavailable_or_unsupported")
    return stream


@router.get("/video_h265")
def video_h265(
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = 30,
    bitrate_k: int = 1200,
    gop: int = 60,
    preset: str = "ultrafast",
):
    require_perm(token, "perm_stream")
    stream = _ffmpeg_stream("h265", int(monitor), int(fps), int(bitrate_k), int(gop), preset)
    if stream is None:
        from fastapi import HTTPException
        raise HTTPException(501, "ffmpeg_unavailable_or_unsupported")
    return stream
