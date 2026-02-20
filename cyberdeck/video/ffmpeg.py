from __future__ import annotations

import logging
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from typing import Any, Optional

from fastapi.responses import StreamingResponse

from .core import (
    _STREAM_FIRST_CHUNK_TIMEOUT_S,
    _STREAM_STDOUT_QUEUE_SIZE,
    _STREAM_STDOUT_READ_CHUNK,
    _available_codec_encoders,
    _build_ffmpeg_input_arg_sets,
    _cmd_preview,
    _codec_encoder_available,
    _env_bool,
    _env_int,
    _extract_first_jpeg,
    _ffmpeg_available,
    _ffmpeg_binary,
    _ffmpeg_last_error,
    _ffmpeg_supports_pipewire,
    _is_wayland_session,
    _jpeg_has_visible_content,
    _set_ffmpeg_diag,
    _stream_headers,
    _stream_log_enabled,
)

log = logging.getLogger(__name__)


def _ffmpeg_audio_input_arg_sets() -> list[list]:
    """Build optional ffmpeg audio-input candidates for system audio relay."""
    raw = str(os.environ.get("CYBERDECK_AUDIO_INPUT_ARGS", "") or "").strip()
    if raw:
        if raw.lower() in {"0", "off", "none", "disabled"}:
            return []
        out: list[list] = []
        for part in raw.split("||"):
            txt = str(part or "").strip()
            if not txt:
                continue
            try:
                args = shlex.split(txt, posix=(os.name != "nt"))
            except Exception:
                args = []
            if args:
                out.append(args)
        if out:
            return out

    # Best-effort defaults; can be overridden via CYBERDECK_AUDIO_INPUT_ARGS.
    if os.name == "nt":
        return [["-f", "wasapi", "-i", "default"]]
    if sys.platform == "darwin":
        return [["-f", "avfoundation", "-i", ":0"]]
    return [["-f", "pulse", "-i", "default"]]


def _set_ffmpeg_diag_compat(cmd: Optional[list], err: Optional[str]) -> None:
    """Route ffmpeg diagnostics through facade patch point when present."""
    facade = sys.modules.get("cyberdeck.video")
    hook = getattr(facade, "_set_ffmpeg_diag", None) if facade else None
    if callable(hook):
        hook(cmd, err)
        return
    _set_ffmpeg_diag(cmd, err)


def _spawn_stream_process(
    cmd: list,
    media_type: str,
    *,
    settle_s: float,
    stderr_lines: int,
    exit_tag: str,
    first_chunk_timeout: float = 2.5,
    require_mjpeg_soi: bool = False,
) -> Any:
    """Spawn backend process, verify first output chunk, and wrap stdout as StreamingResponse."""
    _set_ffmpeg_diag_compat(cmd, None)
    if _stream_log_enabled():
        log.info(
            "stream process start: media=%s qsize=%s cmd=%s",
            media_type,
            _STREAM_STDOUT_QUEUE_SIZE,
            _cmd_preview(cmd),
        )
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, bufsize=0)
    except Exception as e:
        _set_ffmpeg_diag_compat(cmd, f"{type(e).__name__}: {e}")
        if _stream_log_enabled():
            log.warning("stream process spawn failed: %s", e)
        return None

    def _stderr_reader() -> None:
        """Collect bounded stderr tail for diagnostics when backend process fails."""
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
                _set_ffmpeg_diag_compat(cmd, last)
        except Exception:
            pass

    threading.Thread(target=_stderr_reader, daemon=True).start()

    stdout_q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=_STREAM_STDOUT_QUEUE_SIZE)

    def _stdout_reader() -> None:
        """Drain backend stdout into bounded queue to keep stream near realtime."""
        try:
            if not proc.stdout:
                return
            for chunk in iter(lambda: proc.stdout.read(_STREAM_STDOUT_READ_CHUNK), b""):
                if not chunk:
                    break
                try:
                    stdout_q.put_nowait(chunk)
                except queue.Full:
                    # Keep stream near-realtime: drop oldest buffered chunk.
                    try:
                        _ = stdout_q.get_nowait()
                    except Exception:
                        pass
                    try:
                        stdout_q.put_nowait(chunk)
                    except Exception:
                        pass
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
            _set_ffmpeg_diag_compat(cmd, _ffmpeg_last_error or f"{exit_tag}:{proc.returncode}")
            if _stream_log_enabled():
                log.warning("stream process exited early: tag=%s rc=%s cmd=%s", exit_tag, proc.returncode, _cmd_preview(cmd))
            return None
    except Exception:
        pass

    first_chunk: Optional[bytes] = None
    first_buf = bytearray()
    deadline = time.time() + max(0.3, float(first_chunk_timeout))
    while time.time() < deadline and first_chunk is None:
        if proc.poll() is not None:
            _set_ffmpeg_diag_compat(cmd, _ffmpeg_last_error or f"{exit_tag}:{proc.returncode}")
            if _stream_log_enabled():
                log.warning("stream process exited before first chunk: tag=%s rc=%s", exit_tag, proc.returncode)
            return None
        try:
            item = stdout_q.get(timeout=0.1)
        except queue.Empty:
            continue
        if item is None:
            _set_ffmpeg_diag_compat(cmd, _ffmpeg_last_error or f"{exit_tag}:eof_before_output")
            if _stream_log_enabled():
                log.warning("stream process eof before output: tag=%s", exit_tag)
            return None
        if require_mjpeg_soi:
            first_buf.extend(item)
            # Keep bounded buffer while waiting for first JPEG marker.
            if len(first_buf) > (512 * 1024):
                first_buf = first_buf[-(128 * 1024):]
            jpeg = _extract_first_jpeg(bytes(first_buf))
            if not jpeg:
                continue
            if not _jpeg_has_visible_content(jpeg):
                continue
            first_chunk = bytes(first_buf)
        else:
            first_chunk = item

    if first_chunk is None:
        _set_ffmpeg_diag_compat(cmd, f"{exit_tag}:no_output_timeout")
        if _stream_log_enabled():
            log.warning(
                "stream process no output timeout: tag=%s timeout=%.1fs cmd=%s",
                exit_tag,
                float(first_chunk_timeout),
                _cmd_preview(cmd),
            )
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        return None
    if _stream_log_enabled():
        log.info("stream process ready: media=%s first_chunk=%sB", media_type, len(first_chunk))

    def _gen() -> Any:
        """Yield stream bytes from queue and guarantee backend process cleanup on client disconnect."""
        try:
            yield first_chunk
            while True:
                item = stdout_q.get()
                if item is None:
                    break
                yield item
        finally:
            if _stream_log_enabled():
                log.info("stream process stop: media=%s cmd=%s", media_type, _cmd_preview(cmd))
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
    audio: bool = False,
) -> list[list]:
    """Build ffmpeg MPEG-TS command candidates for H.264/H.265 streaming."""
    if codec not in ("h264", "h265"):
        return []
    encoders = _available_codec_encoders(codec)
    if not encoders:
        return []
    fps = max(5, int(fps))
    bitrate_k = max(200, int(bitrate_k))
    gop = max(10, int(gop))
    if low_latency:
        gop = min(gop, max(10, fps))
    preset = str(preset or "ultrafast")
    max_w = max(0, int(max_w))
    audio_bitrate_k = max(48, min(256, int(_env_int("CYBERDECK_AUDIO_BITRATE_K", 128))))

    input_arg_sets = _build_ffmpeg_input_arg_sets(monitor, fps)
    if not input_arg_sets:
        return []
    audio_input_sets = _ffmpeg_audio_input_arg_sets() if bool(audio) else []
    ffmpeg_bin = _ffmpeg_binary() or "ffmpeg"

    def _append_cmd(
        out_list: list[list],
        input_args: list,
        enc_name: str,
        *,
        include_audio: bool,
        audio_args: Optional[list] = None,
    ) -> None:
        cmd = [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-max_delay",
            "0",
            *input_args,
        ]
        if include_audio and audio_args:
            cmd.extend(audio_args)
        cmd += [
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-vsync",
            "cfr",
            "-c:v",
            enc_name,
        ]
        if max_w > 0:
            cmd += ["-vf", f"scale={max_w}:-2:flags=lanczos:force_original_aspect_ratio=decrease"]
        maxrate_k = int(round(bitrate_k * (1.5 if not low_latency else 1.2)))
        bufsize_k = int(round(bitrate_k * (3.0 if not low_latency else 2.0)))
        if enc_name in {"libx264", "libx265"}:
            cmd += [
                "-preset",
                preset,
                "-tune",
                "zerolatency",
            ]
        if codec == "h264" and enc_name == "libx264":
            cmd += ["-profile:v", "baseline" if low_latency else "main"]
        if include_audio and audio_args:
            cmd += [
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-b:a",
                f"{audio_bitrate_k}k",
                "-ac",
                "2",
                "-ar",
                "48000",
            ]
        else:
            cmd += ["-an"]
        cmd += [
            "-flush_packets",
            "1",
            "-muxdelay",
            "0",
            "-muxpreload",
            "0",
            "-b:v",
            f"{bitrate_k}k",
            "-maxrate",
            f"{maxrate_k}k",
            "-bufsize",
            f"{bufsize_k}k",
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
        if codec == "h265" and enc_name == "libx265":
            cmd.extend(["-x265-params", "repeat-headers=1:log-level=error"])
        out_list.append(cmd)

    out: list[list] = []
    for input_args in input_arg_sets:
        for enc in encoders:
            if audio_input_sets:
                for audio_args in audio_input_sets:
                    _append_cmd(out, input_args, enc, include_audio=True, audio_args=audio_args)
            _append_cmd(out, input_args, enc, include_audio=False, audio_args=None)
    return out


def _ffmpeg_mjpeg_stream(monitor: int, fps: int, quality: int, width: int) -> Any:
    """Start ffmpeg MJPEG multipart stream for requested monitor and stream profile."""
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
    lowlat = _env_bool("CYBERDECK_MJPEG_LOWLAT_DEFAULT", True)
    # ffmpeg MJPEG q:v scale: 2(best) .. 31(worst), tuned for sharper text/UI.
    qv = int(round(2 + ((95 - q) * 14.0 / 85.0)))
    qv = max(2, min(16, qv))
    w = max(0, int(width))
    scale_flags = "fast_bilinear" if lowlat else "lanczos"
    pix_fmt = "yuvj420p" if lowlat else "yuvj444p"
    ffmpeg_bin = _ffmpeg_binary() or "ffmpeg"

    for input_args in input_arg_sets:
        cmd = [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-max_delay",
            "0",
            *input_args,
            "-an",
        ]
        if w > 0:
            cmd += ["-vf", f"scale={w}:-2:flags={scale_flags}:force_original_aspect_ratio=decrease"]
        cmd += [
            "-c:v",
            "mjpeg",
            "-pix_fmt",
            pix_fmt,
            "-q:v",
            str(qv),
            "-flush_packets",
            "1",
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
            first_chunk_timeout=_STREAM_FIRST_CHUNK_TIMEOUT_S,
            require_mjpeg_soi=True,
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
    audio: bool = False,
) -> Any:
    """Start ffmpeg MPEG-TS stream for requested codec and low-latency profile."""
    if not _ffmpeg_available():
        _set_ffmpeg_diag(None, "ffmpeg_unavailable")
        return None
    cmds = _build_ffmpeg_cmds(
        codec,
        monitor,
        fps,
        bitrate_k,
        gop,
        preset,
        max_w=max_w,
        low_latency=low_latency,
        audio=audio,
    )
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
            first_chunk_timeout=_STREAM_FIRST_CHUNK_TIMEOUT_S,
        )
        if stream is not None:
            return stream
    return None


__all__ = [name for name in globals() if not name.startswith("__")]

