from __future__ import annotations

from typing import Any
import sys

from .video_core import *
from .video_streamer import video_streamer
from .video_mjpeg import *
from .video_ffmpeg import *
from .video_wayland import *

router = APIRouter()


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

@router.api_route("/video_feed", methods=["GET", "HEAD"])
def video_feed(
    token: str = TokenDep,
    w: Optional[int] = None,
    q: Optional[int] = None,
    max_w: Optional[int] = None,
    quality: Optional[int] = None,
    fps: int = 30,
    cursor: int = 1,
    low_latency: int = _DEFAULT_MJPEG_LOW_LATENCY,
    monitor: int = 1,
    backend: Optional[str] = None,
) -> Any:
    """Serve MJPEG endpoint by selecting best backend for current runtime health and request profile."""
    require_perm(token, "perm_stream")

    requested_w = int(max_w if max_w is not None else (w if w is not None else _DEFAULT_MJPEG_W))
    eff_w = _WIDTH_STABILIZER.decide(token, requested_w)
    eff_q = int(quality if quality is not None else (q if q is not None else _DEFAULT_MJPEG_Q))
    eff_fps = int(fps)
    eff_monitor = int(monitor)
    eff_q = max(eff_q, _MIN_MJPEG_Q)

    if int(low_latency) == 1:
        eff_w = min(eff_w, _LOW_LATENCY_MAX_W)
        eff_q = max(_MIN_MJPEG_Q_LOWLAT, min(eff_q, _LOW_LATENCY_MAX_Q))
        eff_fps = min(eff_fps, _LOW_LATENCY_MAX_FPS)

    requested_backend = _normalize_mjpeg_backend(backend)
    status = _mjpeg_backend_status(eff_monitor, eff_fps)
    order = _mjpeg_backend_order(requested_backend, status)
    if _stream_log_enabled():
        log.info(
            "video_feed request: backend=%s monitor=%s fps=%s req_w=%s eff_w=%s q=%s low_latency=%s order=%s available=%s",
            requested_backend,
            eff_monitor,
            eff_fps,
            requested_w,
            eff_w,
            eff_q,
            int(low_latency),
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
    fps: int = 30,
    max_w: int = _DEFAULT_OFFER_MAX_W,
    quality: int = _DEFAULT_OFFER_Q,
    bitrate_k: int = _DEFAULT_H264_BITRATE_K,
    gop: int = 60,
    preset: str = "veryfast",
    low_latency: int = _DEFAULT_OFFER_LOW_LATENCY,
    cursor: int = _DEFAULT_OFFER_CURSOR,
    backend: Optional[str] = None,
) -> Any:
    """Build candidate stream transports (TS/MJPEG) for adaptive client negotiation."""
    require_perm(token, "perm_stream")
    width_stabilizer = _facade_attr("_WIDTH_STABILIZER", _WIDTH_STABILIZER)

    eff_monitor = int(monitor)
    eff_fps = max(5, int(fps))
    req_w = max(0, int(max_w))
    eff_w = width_stabilizer.decide(token, req_w if req_w > 0 else _DEFAULT_OFFER_MAX_W)
    eff_q = max(10, min(95, int(quality)))
    eff_bitrate = max(200, int(bitrate_k))
    eff_gop = max(10, int(gop))
    eff_preset = str(preset or "veryfast")
    eff_low = bool(int(low_latency))
    eff_cursor = 1 if int(cursor) == 1 else 0
    if eff_low:
        eff_fps = min(eff_fps, _LOW_LATENCY_MAX_FPS)
        eff_w = min(eff_w, _LOW_LATENCY_MAX_W)
        eff_bitrate = min(eff_bitrate, _lowlat_bitrate_cap_k(eff_w, eff_fps, "h264"))

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
    prefer_mjpeg_offer = (
        os.name != "nt"
        and _is_wayland_session()
        and (os.environ.get("CYBERDECK_PREFER_MJPEG_OFFER", "1") == "1")
    )

    base = str(request.base_url).rstrip("/")

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

    if _stream_log_enabled():
        cand_ids = [str(c.get("id") or "") for c in candidates]
        log.info(
            "stream_offer monitor=%s fps=%s req_w=%s eff_w=%s q=%s low_latency=%s candidates=%s mjpeg=%s h264=%s h265=%s",
            eff_monitor,
            eff_fps,
            req_w,
            eff_w,
            eff_q,
            int(eff_low),
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
        "adaptive_hint": {
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
    token: str = TokenDep,
    monitor: int = 1,
    fps: int = 30,
    bitrate_k: int = _DEFAULT_H264_BITRATE_K,
    gop: int = 60,
    preset: str = "veryfast",
    max_w: int = _DEFAULT_OFFER_MAX_W,
    low_latency: int = 1,
) -> Any:
    """Serve H.264 MPEG-TS stream with low-latency caps and bitrate guardrails."""
    require_perm(token, "perm_stream")
    eff_monitor = int(monitor)
    eff_fps = int(fps)
    eff_bitrate = int(bitrate_k)
    eff_gop = int(gop)
    eff_preset = str(preset or "veryfast")
    eff_w = int(max_w)
    eff_low = bool(int(low_latency))
    if eff_low:
        eff_fps = min(_LOW_LATENCY_MAX_FPS, max(10, eff_fps))
        eff_w = min(eff_w, _LOW_LATENCY_MAX_W)
        eff_bitrate = min(eff_bitrate, _lowlat_bitrate_cap_k(eff_w, eff_fps, "h264"))
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
    bitrate_k: int = _DEFAULT_H265_BITRATE_K,
    gop: int = 60,
    preset: str = "veryfast",
    max_w: int = _DEFAULT_OFFER_MAX_W,
    low_latency: int = 1,
) -> Any:
    """Serve H.265 MPEG-TS stream with low-latency caps and bitrate guardrails."""
    require_perm(token, "perm_stream")
    eff_monitor = int(monitor)
    eff_fps = int(fps)
    eff_bitrate = int(bitrate_k)
    eff_gop = int(gop)
    eff_preset = str(preset or "veryfast")
    eff_w = int(max_w)
    eff_low = bool(int(low_latency))
    if eff_low:
        eff_fps = min(_LOW_LATENCY_MAX_FPS, max(10, eff_fps))
        eff_w = min(eff_w, _LOW_LATENCY_MAX_W)
        eff_bitrate = min(eff_bitrate, _lowlat_bitrate_cap_k(eff_w, eff_fps, "h265"))
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


__all__ = [name for name in globals() if not name.startswith("__")]
