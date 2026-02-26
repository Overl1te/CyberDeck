from __future__ import annotations

import logging
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Optional

from fastapi.responses import StreamingResponse

try:
    import numpy as _np
except Exception:
    _np = None

try:
    import soundcard as _soundcard
except Exception:
    _soundcard = None

from .core import (
    _STREAM_FIRST_CHUNK_TIMEOUT_S,
    _STREAM_STDOUT_QUEUE_SIZE,
    _STREAM_STDOUT_READ_CHUNK,
    _available_codec_encoders,
    _build_ffmpeg_input_arg_sets,
    _cmd_preview,
    _codec_encoder_available,
    _env_bool,
    _env_float,
    _env_int,
    _extract_first_jpeg,
    _ffmpeg_available,
    _ffmpeg_binary,
    _ffmpeg_formats,
    _ffmpeg_last_error,
    _ffmpeg_supports_pipewire,
    _is_wayland_session,
    _jpeg_has_visible_content,
    _set_ffmpeg_diag,
    _stream_headers,
    _stream_log_enabled,
)

log = logging.getLogger(__name__)

_FFMPEG_DEMUXER_CACHE: dict[str, tuple[float, bool]] = {}
_FFMPEG_DSHOW_AUDIO_CACHE: tuple[float, list[str]] = (0.0, [])
_FFMPEG_LAST_GOOD_CMD: dict[str, tuple[float, str]] = {}
_SOUNDCARD_PROBE_CACHE: tuple[float, bool, Optional[str]] = (0.0, False, None)
_PULSE_MONITOR_CACHE: tuple[float, list[str]] = (0.0, [])


def _soundcard_speaker_names() -> list[str]:
    """Return available output-speaker names for soundcard loopback diagnostics."""
    if os.name != "nt" or _soundcard is None:
        return []
    out: list[str] = []
    try:
        speakers = list(_soundcard.all_speakers() or [])
    except Exception:
        speakers = []
    for sp in speakers:
        name = str(getattr(sp, "name", "") or "").strip()
        if name and name not in out:
            out.append(name)
    return out


def _soundcard_pick_speaker() -> tuple[Optional[Any], Optional[str]]:
    """Pick speaker for Windows loopback, honoring optional env override."""
    if os.name != "nt" or _soundcard is None:
        return None, None
    forced = str(os.environ.get("CYBERDECK_AUDIO_SOUNDCARD_SPEAKER", "") or "").strip().lower()
    try:
        speakers = list(_soundcard.all_speakers() or [])
    except Exception:
        speakers = []
    if forced:
        for sp in speakers:
            name = str(getattr(sp, "name", "") or "").strip()
            if name and forced in name.lower():
                return sp, name
    try:
        speaker = _soundcard.default_speaker()
    except Exception:
        speaker = None
    if speaker is not None:
        name = str(getattr(speaker, "name", "") or "").strip() or None
        return speaker, name
    if speakers:
        first = speakers[0]
        name = str(getattr(first, "name", "") or "").strip() or None
        return first, name
    return None, None


def _numpy_enable_fromstring_binary_compat() -> None:
    """Patch numpy>=2 compatibility for soundcard binary reads (fromstring -> frombuffer)."""
    np = _np
    if np is None:
        return
    marker = "_cyberdeck_fromstring_binary_compat"
    if bool(getattr(np, marker, False)):
        return
    old_fn = getattr(np, "fromstring", None)
    frombuffer = getattr(np, "frombuffer", None)
    if (not callable(old_fn)) or (not callable(frombuffer)):
        return

    def _compat_fromstring(string: Any, dtype: Any = float, count: int = -1, sep: str = "") -> Any:
        if sep == "":
            try:
                return frombuffer(string, dtype=dtype, count=count)
            except Exception:
                pass
        return old_fn(string, dtype=dtype, count=count, sep=sep)

    try:
        setattr(np, "fromstring", _compat_fromstring)
        setattr(np, marker, True)
    except Exception:
        return


def _soundcard_loopback_probe() -> tuple[bool, Optional[str]]:
    """Probe optional soundcard loopback backend availability for Windows audio relay fallback."""
    global _SOUNDCARD_PROBE_CACHE
    now = time.time()
    ts, ok, name = _SOUNDCARD_PROBE_CACHE
    if ts > 0.0 and (now - float(ts) < 10.0):
        return bool(ok), (str(name) if name else None)
    if os.name != "nt" or _soundcard is None or _np is None:
        _SOUNDCARD_PROBE_CACHE = (now, False, None)
        return False, None
    try:
        _numpy_enable_fromstring_binary_compat()
        speaker, speaker_name = _soundcard_pick_speaker()
        if speaker is None:
            _SOUNDCARD_PROBE_CACHE = (now, False, None)
            return False, None
        _SOUNDCARD_PROBE_CACHE = (now, True, speaker_name)
        return True, speaker_name
    except Exception:
        _SOUNDCARD_PROBE_CACHE = (now, False, None)
        return False, None


def _is_loopback_audio_device_name(name: str) -> bool:
    """Return True when device name likely represents system-output loopback capture."""
    lower = str(name or "").strip().lower()
    if not lower:
        return False
    return any(
        key in lower
        for key in (
            "virtual-audio-capturer",
            "stereo mix",
            "what u hear",
            "wave out",
            "loopback",
            "render",
            "playback",
            "mixagem estereo",
            "mixagem estéreo",
            "стерео микшер",
            "что слышу",
            "what you hear",
        )
    )


def _is_mic_audio_device_name(name: str) -> bool:
    """Return True when device name likely represents microphone capture."""
    lower = str(name or "").strip().lower()
    if not lower:
        return False
    return any(
        key in lower
        for key in (
            "microphone",
            "mic",
            "микрофон",
            "гарнит",
            "headset",
            "headphone",
            "headphones",
            "earphone",
            "головной телефон",
            "науш",
            "buds",
            "airpods",
            "bluetooth",
            "line in",
            "line-in",
            "array",
        )
    )


def _ffmpeg_demuxer_available(name: str) -> bool:
    """Return True when ffmpeg reports requested demuxer/device support."""
    key = str(name or "").strip().lower()
    if not key:
        return False
    now = time.time()
    cached = _FFMPEG_DEMUXER_CACHE.get(key)
    if cached and (now - float(cached[0]) < 300.0):
        return bool(cached[1])

    ok = False
    try:
        for line in str(_ffmpeg_formats() or "").splitlines():
            txt = line.strip()
            if not txt or txt.lower().startswith("demuxers"):
                continue
            parts = txt.split()
            if len(parts) < 2:
                continue
            flags = parts[0]
            fmt = parts[1]
            if len(parts) >= 3 and len(fmt) == 1 and fmt in {"d", ".", "E", "D", "e"}:
                # ffmpeg -formats may render as: "<demux> <mux> <dev> <name> ..."
                fmt = parts[2]
            if ("D" in flags) and fmt.lower() == key:
                ok = True
                break
    except Exception:
        ok = False

    _FFMPEG_DEMUXER_CACHE[key] = (now, ok)
    return ok


def _ffmpeg_dshow_audio_devices() -> list[str]:
    """List DirectShow audio devices ordered by likely system-audio suitability."""
    global _FFMPEG_DSHOW_AUDIO_CACHE
    now = time.time()
    ts, cached = _FFMPEG_DSHOW_AUDIO_CACHE
    if ts > 0.0 and (now - float(ts) < 300.0):
        return list(cached)

    ffmpeg_bin = _ffmpeg_binary() or "ffmpeg"
    out: list[str] = []
    try:
        proc = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
            check=False,
        )
        in_audio = False
        seen: set[str] = set()
        for line in str(proc.stdout or "").splitlines():
            lower = line.lower()
            if "directshow audio devices" in lower:
                in_audio = True
                continue
            if "directshow video devices" in lower:
                in_audio = False
                continue
            is_audio_line = "(audio)" in lower
            if (not in_audio) and (not is_audio_line):
                continue
            if ("alternative name" in lower) or ("(none)" in lower):
                continue
            m = re.search(r'"([^"]+)"', line)
            if not m:
                continue
            name = str(m.group(1) or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
    except Exception:
        out = []

    def _score(name: str) -> tuple[int, str]:
        lower = name.lower()
        if _is_loopback_audio_device_name(name):
            return (0, lower)
        if ("stereo" in lower and "micro" not in lower and "микро" not in lower):
            return (20, lower)
        if _is_mic_audio_device_name(name):
            return (80, lower)
        return (50, lower)

    out.sort(key=_score)
    _FFMPEG_DSHOW_AUDIO_CACHE = (now, list(out))
    return out


def _pulse_monitor_sources() -> list[str]:
    """Discover PulseAudio monitor sources and prioritize default sink monitor."""
    global _PULSE_MONITOR_CACHE
    now = time.time()
    ts, cached = _PULSE_MONITOR_CACHE
    if ts > 0.0 and (now - float(ts) < 20.0):
        return list(cached)

    pactl = shutil.which("pactl")
    if not pactl:
        _PULSE_MONITOR_CACHE = (now, [])
        return []

    probe_timeout = max(0.15, min(2.5, float(_env_float("CYBERDECK_AUDIO_PULSE_PROBE_TIMEOUT_S", 0.45))))

    default_sink = ""
    default_source = ""
    try:
        info = subprocess.run(
            [pactl, "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=probe_timeout,
            check=False,
        )
        for raw in str(info.stdout or "").splitlines():
            line = str(raw or "").strip()
            lower = line.lower()
            if lower.startswith("default sink:"):
                default_sink = line.split(":", 1)[1].strip()
            elif lower.startswith("default source:"):
                default_source = line.split(":", 1)[1].strip()
    except Exception:
        default_sink = ""
        default_source = ""

    out: list[str] = []
    if default_source and ".monitor" in default_source.lower():
        out.append(default_source)
    if default_sink:
        out.append(f"{default_sink}.monitor")

    try:
        ls = subprocess.run(
            [pactl, "list", "short", "sources"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=probe_timeout,
            check=False,
        )
        for raw in str(ls.stdout or "").splitlines():
            parts = [x.strip() for x in str(raw or "").split("\t") if str(x or "").strip()]
            if len(parts) < 2:
                parts = [x for x in str(raw or "").split() if x]
                if len(parts) < 2:
                    continue
            name = str(parts[1] or "").strip()
            if not name:
                continue
            lower = name.lower()
            if ".monitor" in lower:
                out.append(name)
            elif ("monitor" in lower) and ("input" not in lower):
                out.append(name)
    except Exception:
        pass

    uniq: list[str] = []
    seen: set[str] = set()
    for x in out:
        name = str(x or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(name)

    _PULSE_MONITOR_CACHE = (now, list(uniq))
    return uniq


def _ffmpeg_audio_args_supported(args: list) -> bool:
    """Validate optional env-provided ffmpeg audio args against available demuxers."""
    if not args:
        return False
    arg_list = [str(x) for x in args]
    formats: list[str] = []
    for idx, token in enumerate(arg_list):
        if token != "-f":
            continue
        if idx + 1 >= len(arg_list):
            continue
        fmt = str(arg_list[idx + 1] or "").strip().lower()
        if fmt:
            formats.append(fmt)
    if not formats:
        return True
    for fmt in formats:
        if not _ffmpeg_demuxer_available(fmt):
            if _stream_log_enabled():
                log.warning(
                    "skip CYBERDECK_AUDIO_INPUT_ARGS candidate: demuxer '%s' is unavailable (%s)",
                    fmt,
                    " ".join(arg_list),
                )
            return False
    return True


def _ffmpeg_audio_input_arg_sets() -> list[list]:
    """Build optional ffmpeg audio-input candidates for system audio relay."""
    raw = str(os.environ.get("CYBERDECK_AUDIO_INPUT_ARGS", "") or "").strip()
    if raw:
        if raw.lower() in {"0", "off", "none", "disabled"}:
            return []
        env_out: list[list] = []
        for part in raw.split("||"):
            txt = str(part or "").strip()
            if not txt:
                continue
            try:
                args = shlex.split(txt, posix=(os.name != "nt"))
            except Exception:
                args = []
            if args and _ffmpeg_audio_args_supported(args):
                env_out.append(args)
        if env_out:
            return env_out
        if _stream_log_enabled():
            log.warning(
                "CYBERDECK_AUDIO_INPUT_ARGS is set but no candidate is usable; fallback to auto audio input detection"
            )

    # Best-effort defaults; can be overridden via CYBERDECK_AUDIO_INPUT_ARGS.
    if os.name == "nt":
        force_soundcard = _env_bool("CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD", True)
        fallback_from_force_soundcard = False
        if force_soundcard:
            soundcard_enabled = _env_bool("CYBERDECK_AUDIO_ENABLE_SOUNDCARD_LOOPBACK", True)
            snd_ok, snd_name = _soundcard_loopback_probe() if soundcard_enabled else (False, None)
            if snd_ok:
                return []
            fallback_from_force_soundcard = True
            if _stream_log_enabled():
                if soundcard_enabled:
                    log.warning(
                        "CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD=1 but soundcard loopback is unavailable; "
                        "fallback to ffmpeg dshow/wasapi candidates (speaker=%s)",
                        snd_name,
                    )
                else:
                    log.warning(
                        "CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD=1 but soundcard loopback is disabled; "
                        "fallback to ffmpeg dshow/wasapi candidates"
                    )
        out: list[list] = []
        max_candidates = max(1, min(8, int(_env_int("CYBERDECK_AUDIO_INPUT_MAX_CANDIDATES", 2))))
        allow_mic_fallback = _env_bool("CYBERDECK_AUDIO_ALLOW_MIC_FALLBACK", False) or fallback_from_force_soundcard
        prefer_dshow = _env_bool("CYBERDECK_AUDIO_WINDOWS_PREFER_DSHOW", True)
        enable_wasapi = _env_bool("CYBERDECK_AUDIO_ENABLE_WASAPI", True) or fallback_from_force_soundcard
        dshow_out: list[list] = []
        wasapi_out: list[list] = []

        if _ffmpeg_demuxer_available("dshow"):
            devices = _ffmpeg_dshow_audio_devices()
            loopback_devices = [dev for dev in devices if _is_loopback_audio_device_name(dev)]
            selected = loopback_devices
            if (not selected) and allow_mic_fallback:
                selected = [dev for dev in devices if _is_mic_audio_device_name(dev)]
            for dev in selected[:max_candidates]:
                dshow_out.append(["-f", "dshow", "-i", f"audio={dev}"])
            if _stream_log_enabled() and (not selected):
                if devices and (not allow_mic_fallback):
                    log.warning(
                        "audio relay requested but loopback capture device was not found; "
                        "enable CYBERDECK_AUDIO_ALLOW_MIC_FALLBACK=1, install a virtual loopback device, "
                        "or use soundcard loopback fallback"
                    )
                elif not devices:
                    log.warning(
                        "audio relay requested but no dshow audio devices detected "
                        "(set CYBERDECK_AUDIO_INPUT_ARGS to force source)"
                    )
        if enable_wasapi and _ffmpeg_demuxer_available("wasapi"):
            wasapi_out.append(["-f", "wasapi", "-i", "default"])

        if prefer_dshow:
            out.extend(dshow_out)
            out.extend(wasapi_out)
        else:
            out.extend(wasapi_out)
            out.extend(dshow_out)
        return out
    if sys.platform == "darwin":
        return [["-f", "avfoundation", "-i", ":0"]] if _ffmpeg_demuxer_available("avfoundation") else []
    out: list[list] = []
    if _ffmpeg_demuxer_available("pulse"):
        pulse_max = max(1, min(8, int(_env_int("CYBERDECK_AUDIO_PULSE_MAX_CANDIDATES", 2))))
        out.append(["-f", "pulse", "-i", "@DEFAULT_MONITOR@"])
        pulse_sources = _pulse_monitor_sources()
        for src in pulse_sources[:pulse_max]:
            out.append(["-f", "pulse", "-i", src])
        out.append(["-f", "pulse", "-i", "default"])
    if _ffmpeg_demuxer_available("pipewire") and _env_bool("CYBERDECK_AUDIO_ENABLE_PIPEWIRE", True):
        out.append(["-f", "pipewire", "-i", "default"])
    if _ffmpeg_demuxer_available("alsa"):
        out.append(["-f", "alsa", "-i", "default"])
    uniq: list[list] = []
    seen: set[str] = set()
    for args in out:
        sig = "\x1f".join(str(x) for x in (args or []))
        if sig in seen:
            continue
        seen.add(sig)
        uniq.append(args)
    return uniq


def _build_ffmpeg_audio_silent_cmd() -> list:
    """Build a synthetic silent-audio relay command when capture backends are unavailable."""
    ffmpeg_bin = _ffmpeg_binary() or "ffmpeg"
    audio_bitrate_k = max(48, min(320, int(_env_int("CYBERDECK_AUDIO_BITRATE_K", 128))))
    audio_channels = max(1, min(2, int(_env_int("CYBERDECK_AUDIO_CHANNELS", 2))))
    audio_rate = max(8000, min(96000, int(_env_int("CYBERDECK_AUDIO_SAMPLE_RATE", 48000))))
    channel_layout = "mono" if audio_channels == 1 else "stereo"
    return [
        ffmpeg_bin,
        "-loglevel",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r={audio_rate}:cl={channel_layout}",
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "aac",
        "-b:a",
        f"{audio_bitrate_k}k",
        "-ac",
        str(audio_channels),
        "-ar",
        str(audio_rate),
        "-flush_packets",
        "1",
        "-muxdelay",
        "0",
        "-muxpreload",
        "0",
        "-f",
        "mpegts",
        "pipe:1",
    ]


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
    stdout_read_chunk: Optional[int] = None,
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
    read_chunk = max(256, int(stdout_read_chunk or _STREAM_STDOUT_READ_CHUNK))

    def _stdout_reader() -> None:
        """Drain backend stdout into bounded queue to keep stream near realtime."""
        try:
            if not proc.stdout:
                return
            for chunk in iter(lambda: proc.stdout.read(read_chunk), b""):
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
    video_input_queue = max(32, min(8192, int(_env_int("CYBERDECK_STREAM_INPUT_QUEUE_SIZE", 1024))))
    audio_input_queue = max(32, min(8192, int(_env_int("CYBERDECK_AUDIO_INPUT_QUEUE_SIZE", 1024))))
    stream_rtbuf_mb = max(16, min(1024, int(_env_int("CYBERDECK_STREAM_RTBUF_MB", 128))))

    input_arg_sets = _build_ffmpeg_input_arg_sets(monitor, fps)
    if not input_arg_sets:
        return []
    audio_input_sets = _ffmpeg_audio_input_arg_sets() if bool(audio) else []
    allow_silent_fallback = _env_bool("CYBERDECK_AUDIO_FALLBACK_TO_SILENT", True)
    if bool(audio) and (not audio_input_sets) and _stream_log_enabled():
        log.warning("audio relay requested but no audio input backend detected (override with CYBERDECK_AUDIO_INPUT_ARGS)")
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
            "-nostdin",
            "-thread_queue_size",
            str(video_input_queue),
            "-rtbufsize",
            f"{stream_rtbuf_mb}M",
            "-use_wallclock_as_timestamps",
            "1",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-max_delay",
            "0",
            *input_args,
        ]
        if include_audio and audio_args:
            cmd.extend(["-thread_queue_size", str(audio_input_queue), *audio_args])
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

    out_audio: list[list] = []
    out_silent: list[list] = []
    for enc in encoders:
        for input_args in input_arg_sets:
            if audio_input_sets:
                for audio_args in audio_input_sets:
                    _append_cmd(out_audio, input_args, enc, include_audio=True, audio_args=audio_args)
            if (not bool(audio)) or allow_silent_fallback:
                _append_cmd(out_silent, input_args, enc, include_audio=False, audio_args=None)
    return [*out_audio, *out_silent]


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

    def _cmd_sig(cmd: list) -> str:
        return "\x1f".join(str(x) for x in (cmd or []))

    cache_key = (
        f"{str(codec)}|m={int(monitor)}|fps={int(fps)}|w={int(max_w)}|"
        f"low={1 if bool(low_latency) else 0}|a={1 if bool(audio) else 0}"
    )
    now = time.time()
    cached = _FFMPEG_LAST_GOOD_CMD.get(cache_key)
    if cached and (now - float(cached[0]) <= 1800.0):
        cached_sig = str(cached[1] or "")
        idx = next((i for i, c in enumerate(cmds) if _cmd_sig(c) == cached_sig), -1)
        if idx > 0:
            cmds = [cmds[idx], *cmds[:idx], *cmds[idx + 1 :]]
    elif cached:
        _FFMPEG_LAST_GOOD_CMD.pop(cache_key, None)

    max_cmd_candidates = max(1, min(24, int(_env_int("CYBERDECK_STREAM_MAX_CMD_CANDIDATES", 6))))
    if len(cmds) > max_cmd_candidates:
        cmds = cmds[:max_cmd_candidates]
    startup_budget_s = max(1.5, min(30.0, float(_env_float("CYBERDECK_STREAM_STARTUP_BUDGET_S", 6.5))))
    start_deadline = time.time() + startup_budget_s

    fast_first_chunk_timeout = max(
        0.6,
        min(
            float(_STREAM_FIRST_CHUNK_TIMEOUT_S),
            float(_env_float("CYBERDECK_STREAM_FIRST_CHUNK_TIMEOUT_FAST_S", 1.25)),
        ),
    )
    for idx, cmd in enumerate(cmds):
        remaining_s = start_deadline - time.time()
        if remaining_s <= 0.25:
            break
        is_last = idx >= (len(cmds) - 1)
        first_chunk_timeout = _STREAM_FIRST_CHUNK_TIMEOUT_S if is_last else fast_first_chunk_timeout
        first_chunk_timeout = max(0.35, min(float(first_chunk_timeout), float(remaining_s)))
        stream = _spawn_stream_process(
            cmd,
            "video/mp2t",
            settle_s=0.15 if is_last else 0.08,
            stderr_lines=80,
            exit_tag="ffmpeg_exited",
            first_chunk_timeout=first_chunk_timeout,
        )
        if stream is not None:
            _FFMPEG_LAST_GOOD_CMD[cache_key] = (time.time(), _cmd_sig(cmd))
            return stream
    return None


def _build_ffmpeg_audio_cmds() -> list[list]:
    """Build ffmpeg audio-only command candidates for desktop-audio relay."""
    audio_input_sets = _ffmpeg_audio_input_arg_sets()
    if not audio_input_sets:
        return []
    ffmpeg_bin = _ffmpeg_binary() or "ffmpeg"
    audio_input_queue = max(32, min(8192, int(_env_int("CYBERDECK_AUDIO_INPUT_QUEUE_SIZE", 1024))))
    audio_bitrate_k = max(48, min(320, int(_env_int("CYBERDECK_AUDIO_BITRATE_K", 128))))
    audio_channels = max(1, min(2, int(_env_int("CYBERDECK_AUDIO_CHANNELS", 2))))
    audio_rate = max(8000, min(96000, int(_env_int("CYBERDECK_AUDIO_SAMPLE_RATE", 48000))))
    stream_rtbuf_mb = max(16, min(1024, int(_env_int("CYBERDECK_STREAM_RTBUF_MB", 128))))
    pad_with_silence = _env_bool("CYBERDECK_AUDIO_PAD_WITH_SILENCE", True)
    channel_layout = "mono" if audio_channels == 1 else "stereo"

    out: list[list] = []
    for audio_args in audio_input_sets:
        cmd = [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-nostdin",
            "-thread_queue_size",
            str(audio_input_queue),
            "-rtbufsize",
            f"{stream_rtbuf_mb}M",
            "-use_wallclock_as_timestamps",
            "1",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-max_delay",
            "0",
            *audio_args,
        ]
        if pad_with_silence:
            cmd += [
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r={audio_rate}:cl={channel_layout}",
                "-filter_complex",
                "[0:a:0][1:a:0]amix=inputs=2:duration=longest:dropout_transition=0,aresample=async=1:first_pts=0[aout]",
                "-map",
                "[aout]",
            ]
        else:
            cmd += ["-map", "0:a:0"]
        cmd += [
            "-vn",
            "-sn",
            "-dn",
            "-c:a",
            "aac",
            "-b:a",
            f"{audio_bitrate_k}k",
            "-ac",
            str(audio_channels),
            "-ar",
            str(audio_rate),
            "-flush_packets",
            "1",
            "-muxdelay",
            "0",
            "-muxpreload",
            "0",
            "-f",
            "mpegts",
            "pipe:1",
        ]
        out.append(cmd)
    return out


def _build_ffmpeg_audio_pipe_cmd(*, sample_rate: int, channels: int, bitrate_k: int) -> list:
    """Build ffmpeg command for audio encoding from stdin PCM stream."""
    ffmpeg_bin = _ffmpeg_binary() or "ffmpeg"
    return [
        ffmpeg_bin,
        "-loglevel",
        "error",
        "-f",
        "s16le",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-i",
        "pipe:0",
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "aac",
        "-b:a",
        f"{bitrate_k}k",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-flush_packets",
        "1",
        "-muxdelay",
        "0",
        "-muxpreload",
        "0",
        "-f",
        "mpegts",
        "pipe:1",
    ]


def _soundcard_loopback_stream() -> Any:
    """Capture Windows desktop loopback audio via soundcard and relay through ffmpeg encoder."""
    ok, speaker_name = _soundcard_loopback_probe()
    if not ok or _soundcard is None or _np is None:
        return None
    if not _ffmpeg_available():
        return None
    try:
        _numpy_enable_fromstring_binary_compat()
        speaker, speaker_name = _soundcard_pick_speaker()
        if speaker is None:
            return None
        mic = _soundcard.get_microphone(id=str(getattr(speaker, "name", "") or ""), include_loopback=True)
    except Exception as e:
        if _stream_log_enabled():
            log.warning("soundcard loopback probe failed: %s", e)
        return None

    sample_rate = max(8000, min(96000, int(_env_int("CYBERDECK_AUDIO_SAMPLE_RATE", 48000))))
    channels = max(1, min(2, int(_env_int("CYBERDECK_AUDIO_CHANNELS", 2))))
    bitrate_k = max(48, min(320, int(_env_int("CYBERDECK_AUDIO_BITRATE_K", 128))))
    block_frames = max(256, min(8192, int(_env_int("CYBERDECK_AUDIO_SOUNDCARD_BLOCK_FRAMES", 1024))))
    cmd = _build_ffmpeg_audio_pipe_cmd(sample_rate=sample_rate, channels=channels, bitrate_k=bitrate_k)

    _set_ffmpeg_diag_compat(cmd, None)
    if _stream_log_enabled():
        log.info("soundcard loopback stream start: speaker=%s cmd=%s", speaker_name, _cmd_preview(cmd))

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            bufsize=0,
        )
    except Exception as e:
        _set_ffmpeg_diag_compat(cmd, f"{type(e).__name__}: {e}")
        if _stream_log_enabled():
            log.warning("soundcard loopback encoder spawn failed: %s", e)
        return None

    stop_evt = threading.Event()
    stdout_q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=_STREAM_STDOUT_QUEUE_SIZE)
    stdout_chunk = max(512, min(16384, int(_env_int("CYBERDECK_AUDIO_STDOUT_READ_CHUNK", 4096))))

    def _stderr_reader() -> None:
        try:
            if not proc.stderr:
                return
            last = None
            for _ in range(100):
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

    def _stdout_reader() -> None:
        try:
            if not proc.stdout:
                return
            for chunk in iter(lambda: proc.stdout.read(stdout_chunk), b""):
                if not chunk:
                    break
                try:
                    stdout_q.put_nowait(chunk)
                except queue.Full:
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

    def _stdin_writer() -> None:
        write_silence_when_idle = _env_bool("CYBERDECK_AUDIO_SOUNDCARD_WRITE_SILENCE_WHEN_IDLE", True)
        sleep_s = max(0.004, min(0.12, float(block_frames) / float(sample_rate)))
        silence = _np.zeros((block_frames, channels), dtype=_np.float32)

        def _write_float_frame(arr: Any) -> bool:
            if proc.stdin is None:
                return False
            try:
                pcm16 = (_np.clip(arr, -1.0, 1.0) * 32767.0).astype(_np.int16, copy=False)
                proc.stdin.write(pcm16.tobytes())
                proc.stdin.flush()
                return True
            except Exception:
                return False

        try:
            if proc.stdin is None:
                return
            with mic.recorder(samplerate=sample_rate, channels=channels, blocksize=block_frames) as rec:
                while (not stop_evt.is_set()) and (proc.poll() is None):
                    arr = None
                    try:
                        frame = rec.record(numframes=block_frames)
                    except Exception:
                        frame = None
                    if frame is None:
                        if write_silence_when_idle:
                            arr = silence
                        else:
                            time.sleep(sleep_s)
                            continue
                    else:
                        arr = _np.asarray(frame, dtype=_np.float32)
                        if arr.ndim == 1:
                            arr = arr.reshape(-1, 1)
                        if arr.shape[1] != channels:
                            if arr.shape[1] > channels:
                                arr = arr[:, :channels]
                            else:
                                arr = _np.pad(arr, ((0, 0), (0, channels - arr.shape[1])), mode="constant")
                    if not _write_float_frame(arr):
                        break
        except Exception as e:
            if _stream_log_enabled():
                log.warning("soundcard loopback capture failed: %s", e)
            if write_silence_when_idle and proc.stdin is not None:
                while (not stop_evt.is_set()) and (proc.poll() is None):
                    if not _write_float_frame(silence):
                        break
                    time.sleep(sleep_s)
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass

    threading.Thread(target=_stderr_reader, daemon=True).start()
    threading.Thread(target=_stdout_reader, daemon=True).start()
    threading.Thread(target=_stdin_writer, daemon=True).start()

    default_timeout = float(_env_float("CYBERDECK_AUDIO_FIRST_CHUNK_TIMEOUT_S", 6.0))
    first_chunk_timeout = max(
        1.2,
        min(20.0, float(_env_float("CYBERDECK_AUDIO_SOUNDCARD_FIRST_CHUNK_TIMEOUT_S", default_timeout))),
    )
    first_chunk: Optional[bytes] = None
    deadline = time.time() + first_chunk_timeout
    while time.time() < deadline and first_chunk is None:
        if proc.poll() is not None:
            _set_ffmpeg_diag_compat(cmd, _ffmpeg_last_error or f"soundcard_audio_exited:{proc.returncode}")
            stop_evt.set()
            return None
        try:
            item = stdout_q.get(timeout=0.1)
        except queue.Empty:
            continue
        if item is None:
            _set_ffmpeg_diag_compat(cmd, _ffmpeg_last_error or "soundcard_audio_eof")
            stop_evt.set()
            return None
        first_chunk = item

    if first_chunk is None:
        _set_ffmpeg_diag_compat(cmd, "soundcard_audio_no_output_timeout")
        stop_evt.set()
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        return None

    def _gen() -> Any:
        try:
            yield first_chunk
            while True:
                item = stdout_q.get()
                if item is None:
                    break
                yield item
        finally:
            stop_evt.set()
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.kill()
            except Exception:
                pass

    return StreamingResponse(_gen(), media_type="video/mp2t", headers=_stream_headers())


def _ffmpeg_audio_stream() -> Any:
    """Start ffmpeg audio-only relay stream optimized for fast startup on mobile clients."""
    if not _ffmpeg_available():
        _set_ffmpeg_diag(None, "ffmpeg_unavailable")
        return None
    force_windows_soundcard = os.name == "nt" and _env_bool("CYBERDECK_AUDIO_WINDOWS_FORCE_SOUNDCARD", True)
    if force_windows_soundcard and _env_bool("CYBERDECK_AUDIO_ENABLE_SOUNDCARD_LOOPBACK", True):
        stream = _soundcard_loopback_stream()
        if stream is not None:
            _FFMPEG_LAST_GOOD_CMD["audio_only"] = (time.time(), "soundcard_loopback_forced")
            return stream
    allow_silent_fallback = _env_bool("CYBERDECK_AUDIO_FALLBACK_TO_SILENT", False)
    cmds = _build_ffmpeg_audio_cmds()
    if (not cmds) and os.name == "nt" and _env_bool("CYBERDECK_AUDIO_ENABLE_SOUNDCARD_LOOPBACK", True):
        stream = _soundcard_loopback_stream()
        if stream is not None:
            _FFMPEG_LAST_GOOD_CMD["audio_only"] = (time.time(), "soundcard_loopback")
            return stream
    if (not cmds) and allow_silent_fallback:
        silent_cmd = _build_ffmpeg_audio_silent_cmd()
        _set_ffmpeg_diag_compat(silent_cmd, "audio_input_unavailable_using_silent_fallback")
        cmds = [silent_cmd]
    if not cmds:
        _set_ffmpeg_diag(None, "audio_input_unavailable")
        return None

    def _cmd_sig(cmd: list) -> str:
        return "\x1f".join(str(x) for x in (cmd or []))

    cache_key = "audio_only"
    now = time.time()
    cached = _FFMPEG_LAST_GOOD_CMD.get(cache_key)
    if cached and (now - float(cached[0]) <= 1800.0):
        cached_sig = str(cached[1] or "")
        idx = next((i for i, c in enumerate(cmds) if _cmd_sig(c) == cached_sig), -1)
        if idx > 0:
            cmds = [cmds[idx], *cmds[:idx], *cmds[idx + 1 :]]
    elif cached:
        _FFMPEG_LAST_GOOD_CMD.pop(cache_key, None)

    max_cmd_candidates = max(1, min(16, int(_env_int("CYBERDECK_AUDIO_MAX_CMD_CANDIDATES", 4))))
    if len(cmds) > max_cmd_candidates:
        cmds = cmds[:max_cmd_candidates]
    startup_budget_s = max(1.0, min(20.0, float(_env_float("CYBERDECK_AUDIO_STARTUP_BUDGET_S", 5.5))))
    start_deadline = time.time() + startup_budget_s

    first_chunk_timeout = max(
        1.2,
        min(
            10.0,
            float(_env_float("CYBERDECK_AUDIO_FIRST_CHUNK_TIMEOUT_S", 4.0)),
        ),
    )
    fast_first_chunk_timeout = max(
        0.8,
        min(
            first_chunk_timeout,
            float(_env_float("CYBERDECK_AUDIO_FIRST_CHUNK_TIMEOUT_FAST_S", 1.6)),
        ),
    )
    stdout_chunk = max(512, min(16384, int(_env_int("CYBERDECK_AUDIO_STDOUT_READ_CHUNK", 4096))))
    for idx, cmd in enumerate(cmds):
        remaining_s = start_deadline - time.time()
        if remaining_s <= 0.25:
            break
        is_last = idx >= (len(cmds) - 1)
        cmd_timeout = first_chunk_timeout if is_last else fast_first_chunk_timeout
        cmd_timeout = max(0.35, min(float(cmd_timeout), float(remaining_s)))
        stream = _spawn_stream_process(
            cmd,
            "video/mp2t",
            settle_s=0.08,
            stderr_lines=80,
            exit_tag="ffmpeg_audio_exited",
            first_chunk_timeout=cmd_timeout,
            stdout_read_chunk=stdout_chunk,
        )
        if stream is not None:
            _FFMPEG_LAST_GOOD_CMD[cache_key] = (time.time(), _cmd_sig(cmd))
            return stream

    if os.name == "nt" and _env_bool("CYBERDECK_AUDIO_ENABLE_SOUNDCARD_LOOPBACK", True):
        stream = _soundcard_loopback_stream()
        if stream is not None:
            _FFMPEG_LAST_GOOD_CMD[cache_key] = (time.time(), "soundcard_loopback")
            return stream

    if allow_silent_fallback:
        silent_cmd = _build_ffmpeg_audio_silent_cmd()
        stream = _spawn_stream_process(
            silent_cmd,
            "video/mp2t",
            settle_s=0.05,
            stderr_lines=40,
            exit_tag="ffmpeg_audio_silent_exited",
            first_chunk_timeout=max(1.0, min(6.0, first_chunk_timeout)),
            stdout_read_chunk=stdout_chunk,
        )
        if stream is not None:
            _FFMPEG_LAST_GOOD_CMD[cache_key] = (time.time(), "silent_fallback")
            return stream

    return None


__all__ = [name for name in globals() if not name.startswith("__")]

