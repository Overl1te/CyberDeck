import asyncio
import ipaddress
import os
import time
import uuid
import urllib.parse
from typing import Any, Dict, Optional

import psutil
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .. import config
from ..context import device_manager
from ..logging_config import log
from ..net import get_local_ip
from ..pin_limiter import pin_limiter
from ..protocol import protocol_payload
from ..qr_auth import qr_token_store
from ..transfer import trigger_file_send_logic
from ..update_checker import build_update_status


router = APIRouter()


class LocalFileRequest(BaseModel):
    token: str
    file_path: str


class LocalSettingsRequest(BaseModel):
    token: str
    settings: Dict[str, Any]


class LocalTokenRequest(BaseModel):
    token: str


class LocalRevokeAllRequest(BaseModel):
    keep_token: Optional[str] = None


class LocalDeviceIdRequest(BaseModel):
    device_id: str


class QrLoginRequest(BaseModel):
    # Compatibility with mobile clients:
    # old payload: {"nonce": "..."}
    # new payload: {"qr_token": "..."}
    nonce: Optional[str] = None
    qr_token: Optional[str] = None
    device_id: Optional[str] = None
    device_name: Optional[str] = None


def _safe_port(value: Any, *, scheme: str = "http") -> int:
    """Return a validated TCP port with a scheme-specific default fallback."""
    default_port = 443 if str(scheme).lower() == "https" else 80
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return default_port
    if port < 1 or port > 65535:
        return default_port
    return port


def _safe_stat(read_fn, fallback: float) -> float:
    """Read a host metric and return fallback on runtime errors."""
    try:
        return float(read_fn())
    except Exception:
        return float(fallback)


def _safe_process_rss() -> int:
    """Read current process RSS memory and return 0 if unavailable."""
    try:
        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        return 0


def _is_loopback_host(host: str) -> bool:
    """Return True when the host is localhost/loopback, including IPv4-mapped IPv6."""
    value = str(host or "").strip()
    if not value:
        return False
    if value.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(value)
    except Exception:
        return False
    if ip.is_loopback:
        return True
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(mapped and mapped.is_loopback)


def _require_localhost(request: Request) -> None:
    """Allow access only from localhost or loopback addresses."""
    host = str(getattr(getattr(request, "client", None), "host", "") or "").strip()
    if not _is_loopback_host(host):
        raise HTTPException(403)


@router.post("/api/local/trigger_file")
def local_trigger_file(req: LocalFileRequest, request: Request):
    """Trigger file transfer to a paired device from a localhost-only API call."""
    _require_localhost(request)
    ok, msg = trigger_file_send_logic(req.token, req.file_path)
    return {"ok": ok, "msg": msg}


@router.get("/api/local/info")
def local_info(request: Request):
    """Return local runtime information for launcher and diagnostics."""
    _require_localhost(request)
    scheme = str(getattr(config, "SCHEME", "http") or "http")
    port = _safe_port(getattr(config, "PORT", 0), scheme=scheme)
    return {
        "version": config.VERSION,
        "server_id": config.SERVER_ID,
        "pairing_code": config.PAIRING_CODE,
        "ip": str(get_local_ip() or "127.0.0.1"),
        "port": port,
        "scheme": scheme,
        "tls": bool(getattr(config, "TLS_ENABLED", False)),
        "hostname": config.HOSTNAME,
        "log_file": config.LOG_FILE,
        "devices": device_manager.get_all_devices(),
        **protocol_payload(),
    }


@router.get("/api/local/updates")
def local_updates(request: Request, force_refresh: int = 0):
    """Return latest release-tag status for server/launcher/mobile channels."""
    _require_localhost(request)
    timeout_s = max(0.5, min(15.0, float(getattr(config, "UPDATE_CHECK_TIMEOUT_S", 2.5) or 2.5)))
    ttl_s = max(15, min(3600, int(getattr(config, "UPDATE_CHECK_TTL_S", 300) or 300)))
    return build_update_status(
        current_server_version=str(getattr(config, "VERSION", "") or ""),
        current_launcher_version=str(getattr(config, "VERSION", "") or ""),
        current_mobile_version=str(getattr(config, "MOBILE_VERSION", "1.1.1") or "1.1.1"),
        server_repo=str(getattr(config, "CYBERDECK_GITHUB_REPO", "Overl1te/CyberDeck") or "Overl1te/CyberDeck"),
        mobile_repo=str(
            getattr(config, "CYBERDECK_MOBILE_GITHUB_REPO", "Overl1te/CyberDeck-Mobile")
            or "Overl1te/CyberDeck-Mobile"
        ),
        timeout_s=timeout_s,
        ttl_s=ttl_s,
        force_refresh=bool(int(force_refresh or 0)),
    )


@router.get("/api/local/qr_payload")
def local_qr_payload(request: Request):
    """Issue a one-time QR payload used for secure mobile pairing."""
    _require_localhost(request)
    ip = str(get_local_ip() or "127.0.0.1")
    scheme = str(getattr(config, "SCHEME", "http") or "http")
    port = _safe_port(getattr(config, "PORT", 0), scheme=scheme)
    qr_token = qr_token_store.issue()
    payload = {
        "type": "cyberdeck_qr_v1",
        "server_id": config.SERVER_ID,
        "hostname": config.HOSTNAME,
        "version": config.VERSION,
        "ip": ip,
        "port": port,
        "scheme": scheme,
        "pairing_code": config.PAIRING_CODE,
        "ts": int(time.time()),
        "nonce": qr_token,  # backward compatibility with old mobile payload
        "qr_token": qr_token,
    }

    # Encode QR as URL so mobile cameras can open the web app directly.
    # Server serves `static/index.html` on `/` when present.
    try:
        qs = urllib.parse.urlencode(
            {
                "type": payload["type"],
                "server_id": payload["server_id"],
                "hostname": payload["hostname"],
                "version": payload["version"],
                "ip": payload["ip"],
                "port": payload["port"],
                "code": payload["pairing_code"],
                "ts": payload["ts"],
                "nonce": payload["nonce"],
                "qr_token": payload["qr_token"],
            },
            doseq=False,
        )
        url = f"{scheme}://{ip}:{port}/?{qs}"
    except Exception:
        url = f"{scheme}://{ip}:{port}/"

    return {"payload": payload, "url": url}


@router.post("/api/qr/login")
def qr_login(req: QrLoginRequest, request: Request):
    """Authorize a device using a one-time QR token and create a session."""
    qr_token = str((req.qr_token or req.nonce or "")).strip()
    if not qr_token:
        raise HTTPException(400, detail="qr_token_required")
    if not qr_token_store.consume(qr_token):
        raise HTTPException(403, detail="invalid_or_expired_qr_token")

    try:
        exp = getattr(config, "PAIRING_EXPIRES_AT", None)
        if exp is not None and time.time() > float(exp):
            raise HTTPException(403, detail="pairing_expired")
    except HTTPException:
        raise
    except Exception:
        pass

    ip = str(getattr(getattr(request, "client", None), "host", "") or "unknown")
    device_id = str((req.device_id or "")).strip() or f"qr-{uuid.uuid4().hex[:12]}"
    device_name = str((req.device_name or "")).strip() or "CyberDeck Mobile"

    token = device_manager.authorize(device_id, device_name, ip)
    log.info("QR login OK: %s (%s) -> %s", device_name, device_id, ip)
    return {
        "status": "ok",
        "token": token,
        "server_name": config.HOSTNAME,
        **protocol_payload(),
    }


@router.get("/api/local/stats")
def local_stats(request: Request):
    """Return host CPU, RAM, uptime, and process memory metrics."""
    _require_localhost(request)
    now = _safe_stat(time.time, 0.0)
    boot = _safe_stat(psutil.boot_time, now)
    uptime = int(max(0.0, now - boot))
    return {
        "cpu": _safe_stat(lambda: psutil.cpu_percent(interval=None), 0.0),
        "ram": _safe_stat(lambda: psutil.virtual_memory().percent, 0.0),
        "uptime_s": uptime,
        "process_ram": _safe_process_rss(),
    }


@router.get("/api/local/device_settings")
def local_get_device_settings(token: str, request: Request):
    """Return persisted per-device settings for the provided session token."""
    _require_localhost(request)
    s = device_manager.get_session(token)
    if not s:
        raise HTTPException(404)
    return {"token": token, "settings": s.settings}


@router.post("/api/local/device_settings")
def local_set_device_settings(req: LocalSettingsRequest, request: Request):
    """Update persisted per-device settings for the provided session token."""
    _require_localhost(request)
    ok = device_manager.update_settings(req.token, req.settings)
    if not ok:
        raise HTTPException(404)
    return {"ok": True}


@router.post("/api/local/device_disconnect")
def local_device_disconnect(req: LocalTokenRequest, request: Request):
    """Disconnect an active device session and close its WebSocket."""
    _require_localhost(request)
    s = device_manager.get_session(req.token)
    if not s:
        raise HTTPException(404)
    import cyberdeck.context as ctx
    if not s.websocket or ctx.running_loop is None:
        device_manager.unregister_socket(req.token)
        return {"ok": True, "msg": "already_offline"}
    try:
        asyncio.run_coroutine_threadsafe(s.websocket.close(code=1000), ctx.running_loop)
    except Exception:
        pass
    device_manager.unregister_socket(req.token)
    return {"ok": True}


@router.post("/api/local/device_delete")
def local_device_delete(req: LocalTokenRequest, request: Request):
    """Delete a device session by token and close any active connection."""
    _require_localhost(request)
    s = device_manager.get_session(req.token)
    if not s:
        raise HTTPException(404)
    import cyberdeck.context as ctx
    try:
        if s.websocket and ctx.running_loop is not None:
            asyncio.run_coroutine_threadsafe(s.websocket.close(code=1000), ctx.running_loop)
    except Exception:
        pass
    device_manager.unregister_socket(req.token)
    ok = device_manager.delete_session(req.token)
    if not ok:
        raise HTTPException(500)
    return {"ok": True}


@router.post("/api/local/device_delete_by_id")
def local_device_delete_by_id(req: LocalDeviceIdRequest, request: Request):
    """Delete a device session by device ID and close any active connection."""
    _require_localhost(request)
    device_id = str(req.device_id or "").strip()
    if not device_id:
        raise HTTPException(400, detail="device_id_required")

    hit_token: Optional[str] = None
    for t, s in list(device_manager.sessions.items()):
        if str(getattr(s, "device_id", "") or "") == device_id:
            hit_token = str(t)
            break
    if not hit_token:
        raise HTTPException(404, detail="device_not_found")

    import cyberdeck.context as ctx

    s = device_manager.get_session(hit_token)
    try:
        if s and s.websocket and ctx.running_loop is not None:
            asyncio.run_coroutine_threadsafe(s.websocket.close(code=1000), ctx.running_loop)
    except Exception:
        pass
    device_manager.unregister_socket(hit_token)
    ok = device_manager.delete_session(hit_token)
    if not ok:
        raise HTTPException(500, detail="delete_failed")
    return {"ok": True, "token": hit_token, "device_id": device_id}


@router.post("/api/local/revoke_all")
def local_revoke_all(req: LocalRevokeAllRequest, request: Request):
    """Revoke all device sessions except an optional token."""
    _require_localhost(request)
    keep = str((req.keep_token or "")).strip()
    import cyberdeck.context as ctx

    tokens = [str(t) for t in list(device_manager.sessions.keys())]
    revoked = 0
    for t in tokens:
        if keep and t == keep:
            continue
        s = device_manager.get_session(t)
        if s and s.websocket and ctx.running_loop is not None:
            try:
                asyncio.run_coroutine_threadsafe(s.websocket.close(code=1000), ctx.running_loop)
            except Exception:
                pass
        device_manager.unregister_socket(t)
        if device_manager.delete_session(t):
            revoked += 1
    return {"ok": True, "revoked": revoked, "kept": keep or None}


@router.post("/api/local/regenerate_code")
def regenerate_code(request: Request):
    """Regenerate code."""
    _require_localhost(request)
    config.PAIRING_CODE = str(uuid.uuid4().int)[:4]
    try:
        ttl = int(getattr(config, "PAIRING_TTL_S", 0) or 0)
        config.PAIRING_EXPIRES_AT = (time.time() + ttl) if ttl > 0 else None
    except Exception:
        config.PAIRING_EXPIRES_AT = None

    try:
        pin_limiter.reset()
    except Exception:
        pass
    log.info(f"Pairing code regenerated -> {config.PAIRING_CODE}")
    return {"new_code": config.PAIRING_CODE}

