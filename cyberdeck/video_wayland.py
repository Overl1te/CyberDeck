from __future__ import annotations

from typing import Any

from .video_core import *
from .video_ffmpeg import _spawn_stream_process

def _gst_mjpeg_stream(fps: int, quality: int, width: int) -> Any:
    """Start GStreamer MJPEG multipart stream using pipewire source."""
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
    for node in _gst_pipewire_source_candidates():
        cmd = ["gst-launch-1.0", "-q", "pipewiresrc"]
        if node:
            cmd.append(f"path={node}")
        cmd += ["do-timestamp=true", "!", "videorate", "!", f"video/x-raw,framerate={fps}/1", "!", "videoconvert"]
        if w > 0:
            cmd += ["!", "videoscale", "!", f"video/x-raw,width={w}"]
        cmd += ["!", "jpegenc", f"quality={q}", "!", "multipartmux", "boundary=frame", "!", "fdsink", "fd=1"]

        stream = _spawn_stream_process(
            cmd,
            "multipart/x-mixed-replace; boundary=frame",
            settle_s=0.2,
            stderr_lines=120,
            exit_tag="gstreamer_exited",
            first_chunk_timeout=_STREAM_FIRST_CHUNK_TIMEOUT_S,
            require_mjpeg_soi=True,
        )
        if stream is not None:
            return stream
    return None


def _wayland_grim_frame(width: int, quality: int) -> Optional[bytes]:
    """Capture a single frame with grim and convert it to JPEG bytes."""
    grim = shutil.which("grim")
    if not grim:
        return None
    try:
        proc = subprocess.run(
            [grim, "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
            check=False,
        )
        raw = bytes(proc.stdout or b"")
        if not raw:
            return None
        img = Image.open(BytesIO(raw)).convert("RGB")
        w = max(0, int(width))
        if w > 0 and img.width > w:
            h = int(img.height * (w / img.width))
            img = img.resize((w, max(1, h)), _RESAMPLE_FILTER)
        return _save_jpeg(img, quality)
    except Exception:
        return None


def _wayland_screenshot_tool_frame(width: int, quality: int) -> Optional[bytes]:
    """Capture a single Wayland frame via DBus/CLI screenshot tool chain."""
    def _decode_out_path(raw: str) -> str:
        """Decode screenshot command output into filesystem path."""
        val = str(raw or "").strip().strip("'\"")
        if not val:
            return ""
        if val.startswith("file://"):
            try:
                parsed = urlparse(val)
                return unquote(parsed.path or "")
            except Exception:
                return ""
        return unquote(val)

    def _extract_out_path(text: str) -> str:
        """Extract screenshot image path candidates from command output text."""
        out = str(text or "")
        if not out:
            return ""
        patterns = [
            r"'(file://[^']+\.(?:png|jpg|jpeg))'",
            r'"(file://[^"]+\.(?:png|jpg|jpeg))"',
            r"'(/[^']+\.(?:png|jpg|jpeg))'",
            r'"(/[^"]+\.(?:png|jpg|jpeg))"',
            r"(/[^'\"\\n\\r]+\.(?:png|jpg|jpeg))",
        ]
        seen: list[str] = []
        for pat in patterns:
            for m in re.finditer(pat, out, flags=re.IGNORECASE):
                cand = _decode_out_path(m.group(1))
                if cand and cand not in seen:
                    seen.append(cand)
                    if os.path.exists(cand):
                        return cand
        return seen[0] if seen else ""

    def _wait_existing(paths: list[str], timeout_s: float = 0.8) -> str:
        """Wait for screenshot output file creation and non-empty size."""
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        uniq: list[str] = []
        for p in paths:
            sp = str(p or "").strip()
            if sp and sp not in uniq:
                uniq.append(sp)
        while True:
            for sp in uniq:
                try:
                    if os.path.exists(sp) and os.path.getsize(sp) > 0:
                        return sp
                except Exception:
                    pass
            if time.monotonic() >= deadline:
                return ""
            time.sleep(0.05)

    tool_list: list[str] = []
    cached = _selected_screenshot_tool()
    if cached:
        tool_list.append(cached)
    for t in _screenshot_tool_candidates():
        if t not in tool_list:
            tool_list.append(t)
    if not tool_list:
        return None

    fd, path = tempfile.mkstemp(prefix="cyberdeck-shot-", suffix=".png")
    os.close(fd)
    try:
        for tool in tool_list:
            cmd: list[str]
            capture_path = path
            if tool == "gdbus_gnome_shell":
                gdbus = shutil.which("gdbus")
                if not gdbus:
                    continue
                found = ""
                gdbus_cmds = [
                    [
                        gdbus,
                        "call",
                        "--session",
                        "--dest",
                        "org.gnome.Shell.Screenshot",
                        "--object-path",
                        "/org/gnome/Shell/Screenshot",
                        "--method",
                        "org.gnome.Shell.Screenshot.Screenshot",
                        "false",
                        "false",
                        path,
                    ],
                    [
                        gdbus,
                        "call",
                        "--session",
                        "--dest",
                        "org.gnome.Shell.Screenshot",
                        "--object-path",
                        "/org/gnome/Shell/Screenshot",
                        "--method",
                        "org.gnome.Shell.Screenshot.Screenshot",
                        "false",
                        "false",
                        "",
                    ],
                ]
                for gcmd in gdbus_cmds:
                    try:
                        proc = subprocess.run(
                            gcmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            timeout=4.5,
                            check=False,
                            text=True,
                        )
                    except Exception:
                        continue
                    if int(proc.returncode) != 0:
                        continue
                    out = str(proc.stdout or "").strip()
                    parsed_path = _extract_out_path(out)
                    found = _wait_existing([parsed_path, str(gcmd[-1]), path], timeout_s=1.0)
                    if found:
                        break
                if not found:
                    continue
                capture_path = found
                cmd = []
            elif tool == "qdbus_kwin":
                qdbus = shutil.which("qdbus") or shutil.which("qdbus6")
                if not qdbus:
                    continue
                # KWin API names differ across versions/builds.
                outputs: list[str] = []
                tried_cmds = [
                    [qdbus, "org.kde.KWin", "/Screenshot", "screenshotFullscreen"],
                    [qdbus, "org.kde.KWin", "/Screenshot", "org.kde.KWin.ScreenShot2.screenshotFullscreen"],
                ]
                for qcmd in tried_cmds:
                    try:
                        proc = subprocess.run(
                            qcmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL,
                            timeout=3.0,
                            check=False,
                            text=True,
                        )
                        if int(proc.returncode) == 0:
                            out = str(proc.stdout or "").strip()
                            if out:
                                outputs.append(out)
                    except Exception:
                        continue
                found_path = ""
                for out in outputs:
                    m = re.search(r"(/[^'\"\\s]+\.(?:png|jpg|jpeg))", out, flags=re.IGNORECASE)
                    if m:
                        found_path = m.group(1).strip()
                        break
                    if os.path.exists(out):
                        found_path = out
                        break
                if not found_path:
                    continue
                capture_path = found_path
                cmd = []
            elif tool == "gnome-screenshot":
                cmd = [tool, "-f", path]
            elif tool == "spectacle":
                cmd = [tool, "-b", "-n", "-o", path]
            elif tool == "grim":
                cmd = [tool, path]
            else:
                continue
            try:
                if cmd:
                    proc = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=3.0,
                        check=False,
                    )
                    if int(proc.returncode) != 0:
                        continue
                if not os.path.exists(capture_path) or os.path.getsize(capture_path) <= 0:
                    continue
                img = Image.open(capture_path).convert("RGB")
                w = max(0, int(width))
                if w > 0 and img.width > w:
                    h = int(img.height * (w / img.width))
                    img = img.resize((w, max(1, h)), _RESAMPLE_FILTER)
                out_jpeg = _save_jpeg(img, quality)
                _mark_screenshot_tool(tool)
                if capture_path != path:
                    try:
                        if os.path.exists(capture_path):
                            os.remove(capture_path)
                    except Exception:
                        pass
                return out_jpeg
            except Exception:
                continue
    finally:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    return None


def _grim_mjpeg_stream(fps: int, quality: int, width: int) -> Any:
    """Produce MJPEG multipart stream using screenshot fallback loop on Wayland."""
    if os.name == "nt" or not _is_wayland_session():
        return None
    if not _grim_available() and not _screenshot_tool_available():
        return None

    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    fps = min(_SCREENSHOT_MAX_FPS, max(2, int(fps)))
    quality = min(_SCREENSHOT_MAX_Q, max(20, int(quality)))
    width = min(_SCREENSHOT_MAX_W, max(0, int(width or 0))) if int(width or 0) > 0 else _SCREENSHOT_MAX_W
    min_dt = 1.0 / max(2, int(fps))
    first = _wayland_grim_frame(width, quality)
    if not first:
        first = _wayland_screenshot_tool_frame(width, quality)
    if not first:
        _set_ffmpeg_diag(None, "screenshot_capture_no_output")
        return None

    def _gen() -> Any:
        """Yield stream bytes from queue and guarantee backend process cleanup on client disconnect."""
        last_frame = first
        last_emit_ts = time.monotonic()
        yield boundary + first + b"\r\n"
        last_fail_log = 0.0
        while True:
            t0 = time.perf_counter()
            frame = _wayland_grim_frame(width, quality)
            if not frame:
                frame = _wayland_screenshot_tool_frame(width, quality)
            if frame:
                yield boundary + frame + b"\r\n"
                last_frame = frame
                last_emit_ts = time.monotonic()
            else:
                now = time.time()
                if now - last_fail_log > 3.0:
                    last_fail_log = now
                    _set_ffmpeg_diag(None, "screenshot_capture_failed")
                now_m = time.monotonic()
                if last_frame and (now_m - last_emit_ts) >= _STREAM_STALE_FRAME_KEEPALIVE_S:
                    yield boundary + last_frame + b"\r\n"
                    last_emit_ts = now_m
            dt = time.perf_counter() - t0
            if dt < min_dt:
                time.sleep(min_dt - dt)

    return StreamingResponse(_gen(), media_type="multipart/x-mixed-replace; boundary=frame", headers=_stream_headers())


__all__ = [name for name in globals() if not name.startswith("__")]
