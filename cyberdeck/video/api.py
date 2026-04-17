from __future__ import annotations

import ipaddress
from typing import Any, Dict, Optional
import sys
from urllib.parse import urlencode, urlsplit, urlunsplit

from ..auth import MediaTokenDep
from .core import *
from .streamer import video_streamer
from .mjpeg import *
from .ffmpeg import *
from .wayland import *
from .stream_adaptation import feedback_store
from fastapi.responses import Response

router = APIRouter()


def _stream_preflight_headers(detail: Optional[str] = None) -> dict[str, str]:
    """Return headers for lightweight stream preflight responses."""
    headers = dict(_facade_call("_stream_headers", _stream_headers) or {})
    if detail:
        headers["X-CyberDeck-Stream-Error"] = str(detail)[:180]
    return headers


def _stream_preflight_response(status_code: int, detail: Optional[str] = None) -> Response:
    """Build empty response used by HEAD requests to avoid spawning streaming backends."""
    return Response(status_code=int(status_code), headers=_stream_preflight_headers(detail))


def _codec_stream_preflight_ok(codec: str, monitor: int, fps: int) -> tuple[bool, str]:
    """Return whether codec stream is likely startable without spawning ffmpeg."""
    can_capture = bool(_facade_call("_capture_input_available", _capture_input_available, int(monitor), int(fps)))
    capture_reliable = bool(
        can_capture
        and _facade_call("_ffmpeg_wayland_capture_reliable", _ffmpeg_wayland_capture_reliable)
    )
    if not can_capture or not capture_reliable:
        diag = _get_ffmpeg_diag()
        detail = str(diag.get("ffmpeg_last_error") or "ffmpeg_capture_unavailable")
        return False, detail
    if not bool(_facade_call("_codec_encoder_available", _codec_encoder_available, codec)):
        return False, f"ffmpeg_missing_encoder:{codec}"
    return True, ""


def _audio_stream_preflight_ok() -> tuple[bool, str]:
    """Return whether audio relay is likely startable without spawning encoder process."""
    caps = _facade_call("_ffmpeg_audio_relay_capabilities", _ffmpeg_audio_relay_capabilities) or {}
    if bool(caps.get("real_audio_available")) or bool(caps.get("silent_fallback_enabled")):
        return True, ""
    diag = _get_ffmpeg_diag()
    detail = str(diag.get("ffmpeg_last_error") or "audio_capture_unavailable")
    return False, detail


def _facade_attr(name: str, default: Any) -> Any:
    """Read attribute from `cyberdeck.video` facade when present for test-time patching."""
    facade = sys.modules.get("cyberdeck.video")
    if facade is None:
        return default
    return getattr(facade, name, default)


def _facade_call(name: str, fallback: Any, *args: Any, **kwargs: Any) -> Any:
    """Call function from facade if patched there, otherwise use local fallback."""
    fn = _facade_attr(name, fallback)
    return fn(*args, **kwargs)


def _to_int(value: Any, default: int = 0) -> int:
    """Parse integer-like values from mixed payloads safely."""
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return int(str(value or "").strip())
    except Exception:
        return int(default)


def _to_float(value: Any, default: float = 0.0) -> float:
    """Parse float-like values from mixed payloads safely."""
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_bool(value: Any, default: bool = False) -> bool:
    """Parse bool-like values from mixed payloads safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return bool(default)


def _clamp_int(value: int, lo: int, hi: int) -> int:
    """Return bounded integer value with stable low/high ordering."""
    lo_i = int(min(lo, hi))
    hi_i = int(max(lo, hi))
    return max(lo_i, min(hi_i, int(value)))


def _public_base_url(request: Request) -> str:
    """Build public-facing base URL, preferring configured or forwarded origin."""
    hinted = str(getattr(config, "PUBLIC_ORIGIN_HINT", "") or "").strip()
    if hinted:
        if "://" not in hinted:
            hinted = f"https://{hinted}"
        parsed_hint = urlsplit(hinted)
        if parsed_hint.scheme and parsed_hint.netloc:
            hint_path = parsed_hint.path or "/"
            return urlunsplit((parsed_hint.scheme, parsed_hint.netloc, hint_path, "", "")).rstrip("/")

    headers = getattr(request, "headers", None)
    if headers is not None:
        try:
            proto = str(headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
            host = str(headers.get("x-forwarded-host") or headers.get("host") or "").split(",", 1)[0].strip()
            port = str(headers.get("x-forwarded-port") or "").split(",", 1)[0].strip()
            if host:
                if port and (":" not in host) and (not host.startswith("[")):
                    host = f"{host}:{port}"
                base_path = urlsplit(str(request.base_url)).path or "/"
                base_scheme = proto or (urlsplit(str(request.base_url)).scheme or "http")
                return urlunsplit((base_scheme, host, base_path, "", "")).rstrip("/")
        except Exception:
            pass

    return str(request.base_url).rstrip("/")


def _host_is_private_or_local(host: str) -> bool:
    """Return whether host points to a private/local origin."""
    normalized = str(host or "").strip().lower().strip("[]")
    if not normalized:
        return True
    if normalized in {"localhost", "0.0.0.0", "::", "::1"}:
        return True
    if normalized.endswith(".local") or "." not in normalized:
        return True

    zone_free = normalized.split("%", 1)[0]
    try:
        parsed = ipaddress.ip_address(zone_free)
    except ValueError:
        return False

    if parsed.is_loopback or parsed.is_link_local or parsed.is_private:
        return True
    if parsed.version == 4:
        octets = zone_free.split(".")
        if len(octets) == 4:
            try:
                a = int(octets[0])
                b = int(octets[1])
            except Exception:
                return False
            if a == 100 and 64 <= b <= 127:
                return True
    return False


def _base_prefers_compatibility_transport(base_url: str) -> bool:
    """Return whether public-facing origin should prefer compatibility-first transports."""
    try:
        host = str(urlsplit(str(base_url or "")).hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    if host.endswith(".trycloudflare.com"):
        return True
    return not _host_is_private_or_local(host)


def _stream_profile_for_request(profile: Optional[str], low_latency: bool) -> str:
    """Resolve effective stream profile for request with low-latency override."""
    if str(profile or "").strip():
        return _normalize_stream_profile(profile)
    if bool(low_latency):
        return "low_latency"
    return _normalize_stream_profile(_facade_attr("_STREAM_PROFILE_DEFAULT", _STREAM_PROFILE_DEFAULT))


def _offer_audio_requested(value: Optional[int]) -> bool:
    """Resolve whether audio should be requested for offer/video endpoints."""
    if value is None:
        return bool(int(_facade_attr("_DEFAULT_OFFER_AUDIO", _DEFAULT_OFFER_AUDIO)))
    return bool(_to_int(value, 0))


def _apply_stream_profile(
    *,
    profile: str,
    fps: int,
    max_w: int,
    quality: int,
    bitrate_k: int,
    gop: int,
    preset: str,
    force_low_latency: bool,
) -> tuple[str, int, int, int, int, int, str, bool]:
    """Apply stream profile to normalize quality/FPS/bitrate and latency intent."""
    out_profile = _normalize_stream_profile(profile)
    out_fps = _clamp_int(int(fps), 5, 120)
    out_w = _clamp_int(int(max_w), 640, 4096)
    out_quality = _clamp_int(int(quality), 10, 95)
    out_bitrate = _clamp_int(int(bitrate_k), 200, 30000)
    out_gop = _clamp_int(int(gop), 10, 600)
    out_preset = str(preset or "veryfast")
    out_low = bool(force_low_latency) or out_profile == "low_latency"

    if out_profile == "quality":
        out_fps = max(out_fps, 24)
        out_quality = max(out_quality, 65)
        out_bitrate = _clamp_int(int(round(out_bitrate * 1.25)), 300, 30000)
        if out_preset in {"ultrafast", "superfast"}:
            out_preset = "veryfast"
    elif out_profile == "balanced":
        out_quality = max(out_quality, _MIN_MJPEG_Q)

    if out_low:
        out_fps = min(out_fps, _LOW_LATENCY_MAX_FPS)
        out_w = min(out_w, _LOW_LATENCY_MAX_W)
        out_quality = max(_MIN_MJPEG_Q_LOWLAT, min(out_quality, _LOW_LATENCY_MAX_Q))
        out_bitrate = min(out_bitrate, _lowlat_bitrate_cap_k(out_w, out_fps, "h264"))
        out_gop = min(out_gop, max(10, out_fps))
        out_preset = "ultrafast"

    return out_profile, out_fps, out_w, out_quality, out_bitrate, out_gop, out_preset, out_low


def _apply_mjpeg_profile(
    *,
    profile: str,
    fps: int,
    max_w: int,
    quality: int,
    force_low_latency: bool,
) -> tuple[str, int, int, int, bool]:
    """Apply profile tuning for MJPEG endpoints."""
    out_profile = _normalize_stream_profile(profile)
    out_fps = _clamp_int(int(fps), 5, 120)
    out_w = _clamp_int(int(max_w), 640, 4096)
    out_q = _clamp_int(int(quality), _MIN_MJPEG_Q, 95)
    out_low = bool(force_low_latency) or out_profile == "low_latency"
    if out_profile == "quality":
        out_fps = max(out_fps, 24)
        out_q = max(out_q, 65)
    if out_low:
        out_fps = min(out_fps, _LOW_LATENCY_MAX_FPS)
        out_w = min(out_w, _LOW_LATENCY_MAX_W)
        out_q = max(_MIN_MJPEG_Q_LOWLAT, min(out_q, _LOW_LATENCY_MAX_Q))
    return out_profile, out_fps, out_w, out_q, out_low


def _feedback_tuning_for_offer(
    token: str,
    *,
    fps: int,
    max_w: int,
    quality: int,
    bitrate_k: int,
    low_latency: bool,
) -> tuple[int, int, int, int, bool, dict[str, Any]]:
    """Apply latest stream feedback recommendation to outgoing stream offer knobs."""
    feedback = feedback_store.recommend(token)
    profile = str(feedback.get("network_profile") or "unknown").strip().lower()
    suggested_raw = feedback.get("suggested")
    suggested = suggested_raw if isinstance(suggested_raw, dict) else {}

    fps_delta = _to_int(suggested.get("fps_delta"), 0)
    width_delta = _to_int(suggested.get("max_w_delta"), 0)
    quality_delta = _to_int(suggested.get("quality_delta"), 0)
    prefer_low = _to_bool(suggested.get("prefer_low_latency"), False)

    out_fps = int(fps)
    out_w = int(max_w)
    out_quality = int(quality)
    out_bitrate = int(bitrate_k)
    out_low = bool(low_latency)
    applied = False

    # Only automatic degradation path is applied server-side.
    # Positive suggestions are left for client-side adaptive loop.
    should_degrade = profile in ("critical", "degraded")
    if should_degrade:
        if fps_delta < 0:
            out_fps = _clamp_int(out_fps + fps_delta, 10, 120)
            applied = applied or out_fps != int(fps)
        if width_delta < 0:
            out_w = _clamp_int(out_w + width_delta, 640, 4096)
            applied = applied or out_w != int(max_w)
        if quality_delta < 0:
            out_quality = _clamp_int(out_quality + quality_delta, 10, 95)
            applied = applied or out_quality != int(quality)
        if prefer_low:
            out_low = True
            applied = applied or (out_low != bool(low_latency))

        jitter = _to_float(feedback.get("jitter_ms"), 0.0)
        drop = _to_float(feedback.get("drop_ratio"), 0.0)
        if profile == "critical":
            scale = 0.72 if (jitter >= 120.0 or drop >= 0.10) else 0.82
        else:
            scale = 0.90 if (jitter >= 60.0 or drop >= 0.05) else 0.94
        out_bitrate = _clamp_int(int(round(out_bitrate * scale)), 200, 20000)
        applied = applied or out_bitrate != int(bitrate_k)

    details = {
        "profile": profile,
        "suggested": {
            "fps_delta": fps_delta,
            "max_w_delta": width_delta,
            "quality_delta": quality_delta,
            "prefer_low_latency": bool(prefer_low),
        },
        "sample": {
            "rtt_ms": _to_float(feedback.get("rtt_ms"), 0.0),
            "jitter_ms": _to_float(feedback.get("jitter_ms"), 0.0),
            "drop_ratio": _to_float(feedback.get("drop_ratio"), 0.0),
            "decode_fps": _to_float(feedback.get("decode_fps"), 0.0),
        },
        "applied": bool(applied),
        "effective": {
            "fps": int(out_fps),
            "max_w": int(out_w),
            "quality": int(out_quality),
            "bitrate_k": int(out_bitrate),
            "low_latency": bool(out_low),
        },
    }
    return out_fps, out_w, out_quality, out_bitrate, out_low, details

@router.api_route("/video_feed", methods=["GET", "HEAD"])
def video_feed(
    request: Request,
    token: str = MediaTokenDep,
    w: Optional[int] = None,
    q: Optional[int] = None,
    max_w: Optional[int] = None,
    quality: Optional[int] = None,
    fps: int = _DEFAULT_OFFER_FPS,
    cursor: int = 1,
    low_latency: int = _DEFAULT_MJPEG_LOW_LATENCY,
    monitor: int = 1,
    backend: Optional[str] = None,
    profile: Optional[str] = None,
) -> Any:
    """Serve MJPEG endpoint by selecting best backend for current runtime health and request profile."""
    require_perm(token, "perm_stream")

    requested_w = int(max_w if max_w is not None else (w if w is not None else _DEFAULT_MJPEG_W))
    eff_w = _WIDTH_STABILIZER.decide(token, requested_w)
    eff_q = int(quality if quality is not None else (q if q is not None else _DEFAULT_MJPEG_Q))
    eff_fps = int(fps if fps is not None else _DEFAULT_OFFER_FPS)
    eff_monitor = int(monitor)
    req_profile = _stream_profile_for_request(profile, bool(int(low_latency)))
    _, eff_fps, eff_w, eff_q, _ = _apply_mjpeg_profile(
        profile=req_profile,
        fps=eff_fps,
        max_w=eff_w,
        quality=eff_q,
        force_low_latency=bool(int(low_latency)),
    )

    requested_backend = _normalize_mjpeg_backend(backend)
    status = _mjpeg_backend_status(eff_monitor, eff_fps)
    order = _mjpeg_backend_order(requested_backend, status)
    if _stream_log_enabled():
        log.info(
            "video_feed request: backend=%s monitor=%s fps=%s req_w=%s eff_w=%s q=%s low_latency=%s profile=%s order=%s available=%s",
            requested_backend,
            eff_monitor,
            eff_fps,
            requested_w,
            eff_w,
            eff_q,
            int(low_latency),
            req_profile,
            ",".join(order) if order else "-",
            status,
        )
    if not order:
        order = []
        if requested_backend != "auto":
            order.append(requested_backend)
        for x in _MJPEG_BACKENDS:
            if x not in order:
                order.append(x)

    if request.method == "HEAD":
        if order:
            return _stream_preflight_response(204)
        diag = _get_ffmpeg_diag()
        reason = video_streamer.disabled_reason() or "mjpeg_backends_failed"
        detail = str(diag.get("ffmpeg_last_error") or f"stream_unavailable:{reason}")
        return _stream_preflight_response(501, detail)

    for name in order:
        stream = _mjpeg_stream_for_backend(
            name,
            monitor=eff_monitor,
            fps=eff_fps,
            quality=eff_q,
            width=eff_w,
            cursor=cursor,
        )
        if stream is not None:
            if _stream_log_enabled():
                log.info(
                    "video_feed selected backend=%s monitor=%s fps=%s max_w=%s q=%s",
                    name,
                    eff_monitor,
                    eff_fps,
                    eff_w,
                    eff_q,
                )
            return stream
        if _stream_log_enabled():
            log.warning("video_feed backend failed: %s", name)

    from fastapi import HTTPException

    diag = _get_ffmpeg_diag()
    reason = video_streamer.disabled_reason() or "mjpeg_backends_failed"
    detail = diag.get("ffmpeg_last_error") or f"stream_unavailable:{reason}"
    if _stream_log_enabled():
        log.warning("video_feed unavailable: reason=%s detail=%s status=%s", reason, detail, status)
    raise HTTPException(501, detail)


@router.get("/api/stream_stats")
def stream_stats(token: str = TokenDep) -> Any:
    """Return stream subsystem statistics, backend status, and protocol capability diagnostics."""
    require_perm(token, "perm_stream")
    out = video_streamer.get_stats()
    try:
        out.update(_get_ffmpeg_diag())
        stats_fps = int(out.get("base_fps") or 30)
        stats_monitor = int(out.get("desired_monitor") or 1)
        mjpeg_status = _mjpeg_backend_status(stats_monitor, stats_fps)
        out["mjpeg_backends"] = mjpeg_status
        out["mjpeg_order_auto"] = _mjpeg_backend_order("auto", mjpeg_status)
        out["input_backend"] = getattr(INPUT_BACKEND, "name", "unknown")
        out["input_can_pointer"] = bool(getattr(INPUT_BACKEND, "can_pointer", False))
        out["input_can_keyboard"] = bool(getattr(INPUT_BACKEND, "can_keyboard", False))
        out["wayland_session"] = bool(_is_wayland_session())
        out["feedback"] = feedback_store.recommend(token)
        out["audio"] = _ffmpeg_audio_relay_capabilities()
    except Exception:
        pass
    try:
        out.update(protocol_payload())
    except Exception:
        pass
    return out


@router.get("/api/stream_backends")
def stream_backends(
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = 30,
    backend: Optional[str] = None,
) -> Any:
    """Return backend availability matrix and effective backend order for MJPEG."""
    require_perm(token, "perm_stream")
    eff_monitor = int(monitor)
    eff_fps = max(5, int(fps))
    selected = _normalize_mjpeg_backend(backend)
    status = _mjpeg_backend_status(eff_monitor, eff_fps)
    order = _mjpeg_backend_order(selected, status)
    return {
        "selected": selected,
        "available": status,
        "order": order,
        "supported_values": ["auto", *_MJPEG_BACKENDS],
        "diag": _get_ffmpeg_diag(),
        **protocol_payload(),
    }


@router.get("/api/stream_offer")
def stream_offer(
    request: Request,
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = _DEFAULT_OFFER_FPS,
    max_w: int = _DEFAULT_OFFER_MAX_W,
    quality: int = _DEFAULT_OFFER_Q,
    bitrate_k: int = _DEFAULT_H264_BITRATE_K,
    gop: int = _DEFAULT_OFFER_GOP,
    preset: str = _DEFAULT_OFFER_PRESET,
    low_latency: int = _DEFAULT_OFFER_LOW_LATENCY,
    audio: Optional[int] = None,
    cursor: int = _DEFAULT_OFFER_CURSOR,
    backend: Optional[str] = None,
    profile: Optional[str] = None,
) -> Any:
    """Build candidate stream transports (TS/MJPEG) for adaptive client negotiation."""
    require_perm(token, "perm_stream")
    width_stabilizer = _facade_attr("_WIDTH_STABILIZER", _WIDTH_STABILIZER)

    eff_monitor = int(monitor)
    eff_fps = max(5, int(fps if fps is not None else _DEFAULT_OFFER_FPS))
    req_w = max(0, int(max_w))
    eff_w = width_stabilizer.decide(token, req_w if req_w > 0 else _DEFAULT_OFFER_MAX_W)
    eff_q = max(10, min(95, int(quality)))
    eff_bitrate = max(200, int(bitrate_k))
    eff_gop = max(10, int(gop))
    eff_preset = str(preset or _DEFAULT_OFFER_PRESET)
    eff_low = bool(int(low_latency))
    req_profile = _stream_profile_for_request(profile, eff_low)
    eff_audio_requested = _offer_audio_requested(audio)
    eff_cursor = 1 if int(cursor) == 1 else 0
    _, eff_fps, eff_w, eff_q, eff_bitrate, eff_gop, eff_preset, eff_low = _apply_stream_profile(
        profile=req_profile,
        fps=eff_fps,
        max_w=eff_w,
        quality=eff_q,
        bitrate_k=eff_bitrate,
        gop=eff_gop,
        preset=eff_preset,
        force_low_latency=eff_low,
    )

    eff_fps, eff_w, eff_q, eff_bitrate, eff_low, feedback_hint = _feedback_tuning_for_offer(
        token,
        fps=eff_fps,
        max_w=eff_w,
        quality=eff_q,
        bitrate_k=eff_bitrate,
        low_latency=eff_low,
    )
    if eff_low:
        eff_fps = min(eff_fps, _LOW_LATENCY_MAX_FPS)
        eff_w = min(eff_w, _LOW_LATENCY_MAX_W)
        eff_q = max(_MIN_MJPEG_Q_LOWLAT, min(eff_q, _LOW_LATENCY_MAX_Q))
        eff_bitrate = min(eff_bitrate, _lowlat_bitrate_cap_k(eff_w, eff_fps, "h264"))
        eff_gop = min(eff_gop, max(10, eff_fps))
        eff_preset = "ultrafast"

    audio_relay_ok = False
    audio_mux_ok = False
    silent_audio_ok = False
    if eff_audio_requested:
        audio_caps = _facade_call("_ffmpeg_audio_relay_capabilities", _ffmpeg_audio_relay_capabilities) or {}
        audio_relay_ok = bool(audio_caps.get("real_audio_available"))
        audio_mux_ok = bool(audio_caps.get("muxed_audio_available"))
        silent_audio_ok = bool(audio_caps.get("silent_fallback_enabled"))
    audio_stream_ok = bool(audio_relay_ok or silent_audio_ok)
    eff_audio_muxed = bool(eff_audio_requested and audio_mux_ok)
    eff_audio_separate = bool(eff_audio_requested and (not eff_audio_muxed) and audio_stream_ok)
    if eff_audio_requested and (not audio_stream_ok) and _stream_log_enabled():
        log.warning("stream_offer requested audio but no audio backend is available")

    can_capture = _facade_call("_capture_input_available", _capture_input_available, eff_monitor, eff_fps)
    ffmpeg_codec_capture_ok = can_capture and _facade_call(
        "_ffmpeg_wayland_capture_reliable",
        _ffmpeg_wayland_capture_reliable,
    )
    h264_ok = ffmpeg_codec_capture_ok and _facade_call("_codec_encoder_available", _codec_encoder_available, "h264")
    h265_ok = ffmpeg_codec_capture_ok and _facade_call("_codec_encoder_available", _codec_encoder_available, "h265")
    mjpeg_status = _facade_call("_mjpeg_backend_status", _mjpeg_backend_status, eff_monitor, eff_fps)
    mjpeg_order = _facade_call(
        "_mjpeg_backend_order",
        _mjpeg_backend_order,
        _normalize_mjpeg_backend(backend),
        mjpeg_status,
    )
    mjpeg_ok = any(mjpeg_status.values())
    base = _public_base_url(request)
    prefer_compatibility_relay = _base_prefers_compatibility_transport(base)
    prefer_mjpeg_offer = _env_bool("CYBERDECK_PREFER_MJPEG_OFFER", True)
    if prefer_compatibility_relay:
        prefer_mjpeg_offer = _env_bool("CYBERDECK_PREFER_COMPATIBILITY_RELAY_OFFER", prefer_mjpeg_offer)

    def _url(path: str, params: Dict[str, Any]) -> str:
        """Build absolute URL with filtered query parameters for stream candidate payloads."""
        qp = urlencode({k: v for k, v in params.items() if v is not None})
        return f"{base}{path}?{qp}" if qp else f"{base}{path}"

    candidates = []

    def _append_mjpeg_candidates() -> None:
        """Append MJPEG candidates in backend-priority order into transport offers."""
        if not mjpeg_ok:
            return
        nonlocal mjpeg_order
        if not mjpeg_order:
            mjpeg_order = [x for x in _MJPEG_BACKENDS if mjpeg_status.get(x, False)]
        for i, mj_backend in enumerate(mjpeg_order):
            candidates.append(
                {
                    "id": "mjpeg" if i == 0 else f"mjpeg_{mj_backend}",
                    "codec": "mjpeg",
                    "container": "multipart",
                    "mime": "multipart/x-mixed-replace; boundary=frame",
                    "backend": mj_backend,
                    "url": _url(
                        "/video_feed",
                        {
                            "token": token,
                            "monitor": eff_monitor,
                            "fps": eff_fps,
                            "max_w": eff_w,
                            "quality": eff_q,
                            "cursor": eff_cursor,
                            "low_latency": 1 if eff_low else 0,
                            "backend": mj_backend,
                            "profile": req_profile,
                        },
                    ),
                }
            )

    def _append_h264_candidate() -> None:
        """Append H.264 transport candidate."""
        if not h264_ok:
            return
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
                        "profile": req_profile,
                        "audio": 1 if eff_audio_muxed else None,
                    },
                ),
            }
        )

    def _append_h265_candidate() -> None:
        """Append H.265 transport candidate."""
        if not h265_ok:
            return
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
                        "profile": req_profile,
                        "audio": 1 if eff_audio_muxed else None,
                    },
                ),
            }
        )

    def _append_audio_candidate() -> None:
        """Append optional separate audio relay candidate when muxed audio is unavailable."""
        if not eff_audio_separate:
            return
        candidates.append(
            {
                "id": "audio_ts",
                "codec": "aac",
                "container": "mpegts",
                "mime": "audio/mp2t",
                "url": _url(
                    "/audio_stream",
                    {
                        "token": token,
                    },
                ),
            }
        )

    if prefer_mjpeg_offer:
        _append_mjpeg_candidates()
        _append_h264_candidate()
    else:
        _append_h264_candidate()
        _append_mjpeg_candidates()
    _append_h265_candidate()
    _append_audio_candidate()

    if _stream_log_enabled():
        cand_ids = [str(c.get("id") or "") for c in candidates]
        log.info(
            "stream_offer monitor=%s fps=%s req_w=%s eff_w=%s q=%s low_latency=%s profile=%s audio_req=%s audio_mux=%s audio_sep=%s candidates=%s mjpeg=%s h264=%s h265=%s",
            eff_monitor,
            eff_fps,
            req_w,
            eff_w,
            eff_q,
            int(eff_low),
            req_profile,
            int(eff_audio_requested),
            int(eff_audio_muxed),
            int(eff_audio_separate),
            ",".join(cand_ids) if cand_ids else "-",
            mjpeg_status,
            bool(h264_ok),
            bool(h265_ok),
        )

    return {
        "recommended": candidates[0]["id"] if candidates else None,
        "candidates": candidates,
        "fallback_policy": "ordered_candidates",
        "reconnect_hint_ms": int(_facade_attr("_STREAM_RECONNECT_HINT_MS", _STREAM_RECONNECT_HINT_MS)),
        "feedback": feedback_hint,
        "audio": {
            "requested": bool(eff_audio_requested),
            "muxed": bool(eff_audio_muxed),
            "separate": bool(eff_audio_separate),
            "relay_available": bool(audio_relay_ok),
            "muxed_available": bool(audio_mux_ok),
            "silent_fallback_available": bool(silent_audio_ok),
            "separate_url": _url("/audio_stream", {"token": token}) if eff_audio_separate else None,
        },
        "adaptive_hint": {
            "min_quality": int(
                _facade_attr(
                    "_MIN_MJPEG_Q_LOWLAT" if eff_low else "_MIN_MJPEG_Q",
                    _MIN_MJPEG_Q_LOWLAT if eff_low else _MIN_MJPEG_Q,
                )
            ),
            "max_quality": int(eff_q),
            "rtt_high_ms": int(_facade_attr("_ADAPTIVE_RTT_HIGH_MS", _ADAPTIVE_RTT_HIGH_MS)),
            "rtt_critical_ms": int(_facade_attr("_ADAPTIVE_RTT_CRIT_MS", _ADAPTIVE_RTT_CRIT_MS)),
            "fps_drop_threshold": float(_facade_attr("_ADAPTIVE_FPS_DROP_THRESHOLD", _ADAPTIVE_FPS_DROP_THRESHOLD)),
            "decrease_step": {
                "fps": int(_facade_attr("_ADAPTIVE_DEC_FPS_STEP", _ADAPTIVE_DEC_FPS_STEP)),
                "max_w": int(_facade_attr("_ADAPTIVE_DEC_W_STEP", _ADAPTIVE_DEC_W_STEP)),
                "quality": int(_facade_attr("_ADAPTIVE_DEC_Q_STEP", _ADAPTIVE_DEC_Q_STEP)),
            },
            "increase_step": {
                "fps": int(_facade_attr("_ADAPTIVE_INC_FPS_STEP", _ADAPTIVE_INC_FPS_STEP)),
                "max_w": int(_facade_attr("_ADAPTIVE_INC_W_STEP", _ADAPTIVE_INC_W_STEP)),
                "quality": int(_facade_attr("_ADAPTIVE_INC_Q_STEP", _ADAPTIVE_INC_Q_STEP)),
            },
            "width_ladder": _facade_attr("_ADAPTIVE_WIDTH_LADDER", _ADAPTIVE_WIDTH_LADDER),
            "min_switch_interval_ms": int(float(_facade_attr("_ADAPTIVE_MIN_SWITCH_S", _ADAPTIVE_MIN_SWITCH_S)) * 1000),
            "hysteresis_ratio": float(_facade_attr("_ADAPTIVE_HYST_RATIO", _ADAPTIVE_HYST_RATIO)),
            "min_width_floor": int(_facade_attr("_STREAM_MIN_W_FLOOR", _STREAM_MIN_W_FLOOR)),
            "prefer_low_latency_default": bool(_facade_attr("_DEFAULT_OFFER_LOW_LATENCY", _DEFAULT_OFFER_LOW_LATENCY)),
            "prefer_quality_before_resize": True,
            "recommended_stream_cursor": int(_facade_attr("_DEFAULT_OFFER_CURSOR", _DEFAULT_OFFER_CURSOR)),
        },
        "support": {
            "capture_input": can_capture,
            "h264_encoder": _facade_call("_codec_encoder_available", _codec_encoder_available, "h264"),
            "h265_encoder": _facade_call("_codec_encoder_available", _codec_encoder_available, "h265"),
            "mjpeg_native": bool(mjpeg_status.get("native")),
            "mjpeg_ffmpeg": bool(mjpeg_status.get("ffmpeg")),
            "mjpeg_gstreamer": bool(mjpeg_status.get("gstreamer")),
            "mjpeg_grim": bool(mjpeg_status.get("screenshot")),
            "mjpeg_order": mjpeg_order,
        },
        "diag": _facade_call("_get_ffmpeg_diag", _get_ffmpeg_diag),
        **protocol_payload(),
    }


@router.get("/api/monitors")
def list_monitors(token: str = TokenDep) -> Any:
    """Return monitor geometry list available to capture backend."""
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


@router.api_route("/video_h264", methods=["GET", "HEAD"])
def video_h264(
    request: Request,
    token: str = MediaTokenDep,
    monitor: int = 1,
    fps: int = _DEFAULT_OFFER_FPS,
    bitrate_k: int = _DEFAULT_H264_BITRATE_K,
    gop: int = _DEFAULT_OFFER_GOP,
    preset: str = _DEFAULT_OFFER_PRESET,
    max_w: int = _DEFAULT_OFFER_MAX_W,
    low_latency: int = _DEFAULT_OFFER_LOW_LATENCY,
    audio: Optional[int] = None,
    profile: Optional[str] = None,
) -> Any:
    """Serve H.264 MPEG-TS stream with low-latency caps and bitrate guardrails."""
    require_perm(token, "perm_stream")
    eff_monitor = int(monitor)
    eff_fps = int(fps if fps is not None else _DEFAULT_OFFER_FPS)
    eff_bitrate = int(bitrate_k)
    eff_gop = int(gop if gop is not None else _DEFAULT_OFFER_GOP)
    eff_preset = str(preset or _DEFAULT_OFFER_PRESET)
    eff_w = int(max_w if max_w is not None else _DEFAULT_OFFER_MAX_W)
    eff_low = bool(int(low_latency))
    req_profile = _stream_profile_for_request(profile, eff_low)
    eff_audio_requested = _offer_audio_requested(audio)
    _, eff_fps, eff_w, _, eff_bitrate, eff_gop, eff_preset, eff_low = _apply_stream_profile(
        profile=req_profile,
        fps=eff_fps,
        max_w=eff_w,
        quality=_DEFAULT_OFFER_Q,
        bitrate_k=eff_bitrate,
        gop=eff_gop,
        preset=eff_preset,
        force_low_latency=eff_low,
    )
    eff_fps, eff_w, _, eff_bitrate, eff_low, _ = _feedback_tuning_for_offer(
        token,
        fps=eff_fps,
        max_w=eff_w,
        quality=_DEFAULT_OFFER_Q,
        bitrate_k=eff_bitrate,
        low_latency=eff_low,
    )
    if eff_low:
        eff_fps = min(_LOW_LATENCY_MAX_FPS, max(10, eff_fps))
        eff_w = min(eff_w, _LOW_LATENCY_MAX_W)
        eff_bitrate = min(eff_bitrate, _lowlat_bitrate_cap_k(eff_w, eff_fps, "h264"))
        eff_gop = min(eff_gop, max(10, eff_fps))
        eff_preset = "ultrafast"
    eff_audio = False
    if eff_audio_requested:
        audio_caps = _facade_call("_ffmpeg_audio_relay_capabilities", _ffmpeg_audio_relay_capabilities) or {}
        eff_audio = bool(audio_caps.get("muxed_audio_available"))
    if eff_audio_requested and (not eff_audio) and _stream_log_enabled():
        log.warning("video_h264 requested muxed audio but muxed audio backend is unavailable")
    if request.method == "HEAD":
        ok, detail = _codec_stream_preflight_ok("h264", eff_monitor, eff_fps)
        return _stream_preflight_response(204 if ok else 502, detail or None)
    stream = _ffmpeg_stream(
        "h264",
        eff_monitor,
        eff_fps,
        eff_bitrate,
        eff_gop,
        eff_preset,
        max_w=eff_w,
        low_latency=eff_low,
        audio=eff_audio,
    )
    if stream is None:
        from fastapi import HTTPException
        diag = _get_ffmpeg_diag()
        detail = diag.get("ffmpeg_last_error") or "ffmpeg_unavailable_or_unsupported"
        raise HTTPException(502, detail)
    return stream


@router.api_route("/video_h265", methods=["GET", "HEAD"])
def video_h265(
    request: Request,
    token: str = MediaTokenDep,
    monitor: int = 1,
    fps: int = _DEFAULT_OFFER_FPS,
    bitrate_k: int = _DEFAULT_H265_BITRATE_K,
    gop: int = _DEFAULT_OFFER_GOP,
    preset: str = _DEFAULT_OFFER_PRESET,
    max_w: int = _DEFAULT_OFFER_MAX_W,
    low_latency: int = _DEFAULT_OFFER_LOW_LATENCY,
    audio: Optional[int] = None,
    profile: Optional[str] = None,
) -> Any:
    """Serve H.265 MPEG-TS stream with low-latency caps and bitrate guardrails."""
    require_perm(token, "perm_stream")
    eff_monitor = int(monitor)
    eff_fps = int(fps if fps is not None else _DEFAULT_OFFER_FPS)
    eff_bitrate = int(bitrate_k)
    eff_gop = int(gop if gop is not None else _DEFAULT_OFFER_GOP)
    eff_preset = str(preset or _DEFAULT_OFFER_PRESET)
    eff_w = int(max_w if max_w is not None else _DEFAULT_OFFER_MAX_W)
    eff_low = bool(int(low_latency))
    req_profile = _stream_profile_for_request(profile, eff_low)
    eff_audio_requested = _offer_audio_requested(audio)
    _, eff_fps, eff_w, _, eff_bitrate, eff_gop, eff_preset, eff_low = _apply_stream_profile(
        profile=req_profile,
        fps=eff_fps,
        max_w=eff_w,
        quality=_DEFAULT_OFFER_Q,
        bitrate_k=eff_bitrate,
        gop=eff_gop,
        preset=eff_preset,
        force_low_latency=eff_low,
    )
    eff_fps, eff_w, _, eff_bitrate, eff_low, _ = _feedback_tuning_for_offer(
        token,
        fps=eff_fps,
        max_w=eff_w,
        quality=_DEFAULT_OFFER_Q,
        bitrate_k=eff_bitrate,
        low_latency=eff_low,
    )
    if eff_low:
        eff_fps = min(_LOW_LATENCY_MAX_FPS, max(10, eff_fps))
        eff_w = min(eff_w, _LOW_LATENCY_MAX_W)
        eff_bitrate = min(eff_bitrate, _lowlat_bitrate_cap_k(eff_w, eff_fps, "h265"))
        eff_gop = min(eff_gop, max(10, eff_fps))
        eff_preset = "ultrafast"
    eff_audio = False
    if eff_audio_requested:
        audio_caps = _facade_call("_ffmpeg_audio_relay_capabilities", _ffmpeg_audio_relay_capabilities) or {}
        eff_audio = bool(audio_caps.get("muxed_audio_available"))
    if eff_audio_requested and (not eff_audio) and _stream_log_enabled():
        log.warning("video_h265 requested muxed audio but muxed audio backend is unavailable")
    if request.method == "HEAD":
        ok, detail = _codec_stream_preflight_ok("h265", eff_monitor, eff_fps)
        return _stream_preflight_response(204 if ok else 502, detail or None)
    stream = _ffmpeg_stream(
        "h265",
        eff_monitor,
        eff_fps,
        eff_bitrate,
        eff_gop,
        eff_preset,
        max_w=eff_w,
        low_latency=eff_low,
        audio=eff_audio,
    )
    if stream is None:
        from fastapi import HTTPException
        diag = _get_ffmpeg_diag()
        detail = diag.get("ffmpeg_last_error") or "ffmpeg_unavailable_or_unsupported"
        raise HTTPException(502, detail)
    return stream


@router.api_route("/audio_stream", methods=["GET", "HEAD"])
def audio_stream(request: Request, token: str = MediaTokenDep) -> Any:
    """Serve low-latency audio relay stream captured from the host audio backend."""
    require_perm(token, "perm_stream")
    if request.method == "HEAD":
        ok, detail = _audio_stream_preflight_ok()
        return _stream_preflight_response(204 if ok else 503, detail or None)
    stream = _ffmpeg_audio_stream()
    if stream is None:
        from fastapi import HTTPException

        diag = _get_ffmpeg_diag()
        detail = diag.get("ffmpeg_last_error") or "audio_capture_unavailable"
        raise HTTPException(503, detail)
    return stream


@router.post("/api/stream_feedback")
def stream_feedback(
    token: str = TokenDep,
    rtt_ms: float = 0.0,
    jitter_ms: float = 0.0,
    drop_ratio: float = 0.0,
    decode_fps: float = 0.0,
) -> Any:
    """Accept stream telemetry feedback and return quality tuning hint."""
    require_perm(token, "perm_stream")
    return feedback_store.update(
        token,
        rtt_ms=float(rtt_ms),
        jitter_ms=float(jitter_ms),
        drop_ratio=float(drop_ratio),
        decode_fps=float(decode_fps),
    )


__all__ = [name for name in globals() if not name.startswith("__")]

