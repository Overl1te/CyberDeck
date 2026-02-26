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
from ..context import device_manager, input_guard, local_events
from ..logging_config import log
from ..net import get_local_ip
from ..pairing import pairing_meta, rotate_pairing_code
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


class LocalApproveRequest(BaseModel):
    token: str
    allow: bool = True


class LocalRenameRequest(BaseModel):
    token: str
    alias: Optional[str] = None
    note: Optional[str] = None


class LocalInputLockRequest(BaseModel):
    locked: bool = True
    reason: Optional[str] = None
    actor: Optional[str] = None


class LocalPanicRequest(BaseModel):
    keep_token: Optional[str] = None
    lock_input: bool = True
    reason: Optional[str] = None


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


def _find_token_by_device_id(device_id: str) -> Optional[str]:
    """Compatibility helper for manager implementations in tests."""
    if hasattr(device_manager, "find_token_by_device_id"):
        try:
            return device_manager.find_token_by_device_id(device_id, include_pending=True)
        except TypeError:
            return device_manager.find_token_by_device_id(device_id)
    sessions = getattr(device_manager, "sessions", {}) or {}
    for t, s in list(sessions.items()):
        if str(getattr(s, "device_id", "") or "") == str(device_id or ""):
            return str(t)
    return None


def _list_tokens() -> list[str]:
    """Compatibility helper for manager implementations in tests."""
    if hasattr(device_manager, "list_tokens"):
        try:
            return [str(x) for x in device_manager.list_tokens(include_pending=True)]
        except TypeError:
            return [str(x) for x in device_manager.list_tokens()]
    sessions = getattr(device_manager, "sessions", {}) or {}
    return [str(x) for x in list(sessions.keys())]


def _get_session(token: str, *, include_pending: bool = False):
    """Compatibility helper for manager implementations in tests."""
    if include_pending:
        try:
            return device_manager.get_session(token, include_pending=True)
        except TypeError:
            return device_manager.get_session(token)
    return device_manager.get_session(token)


def _close_socket_if_online(token: str) -> None:
    """Best-effort close of a connected websocket for a session token."""
    import cyberdeck.context as ctx

    s = _get_session(token, include_pending=True)
    try:
        if s and getattr(s, "websocket", None) and ctx.running_loop is not None:
            asyncio.run_coroutine_threadsafe(s.websocket.close(code=1000), ctx.running_loop)
    except Exception:
        pass
    try:
        device_manager.unregister_socket(token)
    except Exception:
        pass


def _revoke_tokens(*, keep_token: str = "") -> int:
    """Revoke all sessions except optional keep token and return revoked count."""
    keep = str(keep_token or "").strip()
    revoked = 0
    for token in _list_tokens():
        if keep and token == keep:
            continue
        _close_socket_if_online(token)
        if device_manager.delete_session(token):
            revoked += 1
    return int(revoked)


def _trusted_device_payload(device: dict, now: float) -> dict:
    """Normalize trusted-device row payload for launcher and local diagnostics."""
    row = dict(device or {})
    settings = row.get("settings") if isinstance(row.get("settings"), dict) else {}
    last_seen_ts = float(row.get("last_seen_ts") or 0.0)
    created_ts = float(row.get("created_ts") or 0.0)
    row["alias"] = str(settings.get("alias") or "").strip()
    row["note"] = str(settings.get("note") or "").strip()
    row["last_seen_ago_s"] = int(max(0.0, now - last_seen_ts)) if last_seen_ts > 0 else None
    row["created_ago_s"] = int(max(0.0, now - created_ts)) if created_ts > 0 else None
    return row


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
    pairing = pairing_meta()
    return {
        "version": config.VERSION,
        "server_id": config.SERVER_ID,
        "pairing_code": pairing.get("pairing_code"),
        "pairing_expires_at": pairing.get("pairing_expires_at"),
        "pairing_expires_in_s": pairing.get("pairing_expires_in_s"),
        "pairing_ttl_s": pairing.get("pairing_ttl_s"),
        "pairing_single_use": pairing.get("pairing_single_use"),
        "ip": str(get_local_ip() or "127.0.0.1"),
        "port": port,
        "scheme": scheme,
        "tls": bool(getattr(config, "TLS_ENABLED", False)),
        "hostname": config.HOSTNAME,
        "log_file": config.LOG_FILE,
        "approval_required": bool(getattr(config, "DEVICE_APPROVAL_REQUIRED", False)),
        "security": input_guard.snapshot(),
        "pin_limiter": pin_limiter.stats(),
        "devices": device_manager.get_all_devices(),
        "pending_devices": (
            device_manager.get_pending_devices() if hasattr(device_manager, "get_pending_devices") else []
        ),
        **protocol_payload(),
    }


@router.get("/api/local/events")
def local_events_feed(request: Request, since_id: int = 0, limit: int = 100):
    """Return local runtime event stream for launcher notifications."""
    _require_localhost(request)
    out = local_events.list_after(since_id, limit=limit)
    return {
        "events": out.get("events", []),
        "latest_id": int(out.get("latest_id") or 0),
    }


@router.get("/api/local/pending_devices")
def local_pending_devices(request: Request):
    """Return device sessions waiting for local approval."""
    _require_localhost(request)
    if hasattr(device_manager, "get_pending_devices"):
        return {"pending_devices": device_manager.get_pending_devices()}
    return {"pending_devices": []}


@router.get("/api/local/trusted_devices")
def local_trusted_devices(request: Request):
    """Return approved devices with activity metadata for trusted-device management UI."""
    _require_localhost(request)
    now = float(time.time())
    rows = []
    for item in device_manager.get_all_devices():
        if not bool(item.get("approved", True)):
            continue
        rows.append(_trusted_device_payload(item, now))
    rows.sort(key=lambda x: float(x.get("last_seen_ts") or 0.0), reverse=True)
    return {"trusted_devices": rows, "total": len(rows)}


@router.get("/api/local/security_state")
def local_security_state(request: Request):
    """Return current remote-input lock state and pairing TTL metadata."""
    _require_localhost(request)
    return {
        "security": input_guard.snapshot(),
        **pairing_meta(),
    }


@router.post("/api/local/device_approve")
def local_device_approve(req: LocalApproveRequest, request: Request):
    """Approve or deny pending device session."""
    _require_localhost(request)
    token = str(req.token or "").strip()
    if not token:
        raise HTTPException(400, detail="token_required")
    allow = bool(req.allow)
    s = _get_session(token, include_pending=True)
    if not s:
        raise HTTPException(404, detail="device_not_found")
    if allow:
        if not device_manager.set_approved(token, True):
            raise HTTPException(500, detail="approve_failed")
        local_events.emit(
            "device_approved",
            title="CyberDeck",
            message=f"Device approved: {getattr(s, 'device_name', 'Unknown')}",
            payload={"token": token, "device_id": getattr(s, "device_id", ""), "name": getattr(s, "device_name", "")},
        )
        local_events.emit(
            "device_connected",
            title="CyberDeck",
            message=f"Device connected: {getattr(s, 'device_name', 'Unknown')}",
            payload={
                "token": token,
                "device_id": getattr(s, "device_id", ""),
                "name": getattr(s, "device_name", ""),
                "ip": getattr(s, "ip", ""),
            },
        )
        return {"ok": True, "approved": True}
    ok = device_manager.delete_session(token)
    if not ok:
        raise HTTPException(500, detail="delete_failed")
    local_events.emit(
        "device_denied",
        title="CyberDeck",
        message=f"Device denied: {getattr(s, 'device_name', 'Unknown')}",
        payload={"token": token, "device_id": getattr(s, "device_id", ""), "name": getattr(s, "device_name", "")},
    )
    return {"ok": True, "approved": False}


@router.get("/api/local/updates")
def local_updates(request: Request, force_refresh: int = 0):
    """Return latest release-tag status for server/launcher/mobile channels."""
    _require_localhost(request)
    timeout_s = max(0.5, min(15.0, float(getattr(config, "UPDATE_CHECK_TIMEOUT_S", 2.5) or 2.5)))
    ttl_s = max(15, min(3600, int(getattr(config, "UPDATE_CHECK_TTL_S", 300) or 300)))
    return build_update_status(
        current_server_version=str(getattr(config, "VERSION", "") or ""),
        current_launcher_version=str(getattr(config, "VERSION", "") or ""),
        current_mobile_version=str(getattr(config, "MOBILE_VERSION", "1.1.2") or "1.1.2"),
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
    pairing = pairing_meta()
    payload = {
        "type": "cyberdeck_qr_v1",
        "server_id": config.SERVER_ID,
        "hostname": config.HOSTNAME,
        "version": config.VERSION,
        "app_pkg": str(getattr(config, "MOBILE_ANDROID_PACKAGE", "") or ""),
        "ip": ip,
        "port": port,
        "scheme": scheme,
        "pairing_code": pairing.get("pairing_code"),
        "pairing_expires_at": pairing.get("pairing_expires_at"),
        "pairing_expires_in_s": pairing.get("pairing_expires_in_s"),
        "pairing_ttl_s": pairing.get("pairing_ttl_s"),
        "pairing_single_use": pairing.get("pairing_single_use"),
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
                "app_pkg": payload["app_pkg"],
                "ip": payload["ip"],
                "port": payload["port"],
                "code": payload["pairing_code"],
                "ts": payload["ts"],
                "nonce": payload["nonce"],
                "qr_token": payload["qr_token"],
                "exp": (
                    str(int(float(payload["pairing_expires_at"])))
                    if payload.get("pairing_expires_at") not in (None, "")
                    else ""
                ),
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

    approval_required = bool(getattr(config, "DEVICE_APPROVAL_REQUIRED", False))
    token = device_manager.authorize(device_id, device_name, ip, approved=(not approval_required))
    session = _get_session(token, include_pending=True)
    approved = bool(getattr(session, "approved", True)) if session else (not approval_required)
    if approved:
        local_events.emit(
            "device_connected",
            title="CyberDeck",
            message=f"Device connected: {device_name}",
            payload={"token": token, "device_id": device_id, "name": device_name, "ip": ip},
        )
    else:
        local_events.emit(
            "device_pending",
            title="CyberDeck",
            message=f"Device approval required: {device_name}",
            payload={"token": token, "device_id": device_id, "name": device_name, "ip": ip},
        )
    rotated = False
    if bool(getattr(config, "PAIRING_SINGLE_USE", False)):
        try:
            rotate_pairing_code()
            pin_limiter.reset()
            rotated = True
            local_events.emit(
                "pairing_rotated",
                title="CyberDeck",
                message="Pairing code rotated after successful QR login",
                payload={"source": "qr_login", "device_id": device_id, "name": device_name},
            )
        except Exception:
            rotated = False
    log.info("QR login OK: %s (%s) -> %s | approved=%s", device_name, device_id, ip, approved)
    return {
        "status": "ok",
        "approved": bool(approved),
        "approval_pending": bool(not approved),
        "token": token,
        "server_name": config.HOSTNAME,
        "pairing_rotated": bool(rotated),
        **pairing_meta(),
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


@router.post("/api/local/device_rename")
def local_device_rename(req: LocalRenameRequest, request: Request):
    """Update human-friendly alias/note for a trusted device token."""
    _require_localhost(request)
    token = str(req.token or "").strip()
    if not token:
        raise HTTPException(400, detail="token_required")
    s = _get_session(token, include_pending=True)
    if not s:
        raise HTTPException(404, detail="device_not_found")
    alias = str(req.alias or "").strip()
    note = str(req.note or "").strip()
    patch = {
        "alias": alias if alias else None,
        "note": note if note else None,
    }
    if not device_manager.update_settings(token, patch):
        raise HTTPException(500, detail="rename_failed")
    return {
        "ok": True,
        "token": token,
        "alias": alias,
        "note": note,
    }


@router.get("/api/local/device_settings")
def local_get_device_settings(token: str, request: Request):
    """Return persisted per-device settings for the provided session token."""
    _require_localhost(request)
    s = _get_session(token, include_pending=True)
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
    s = _get_session(req.token, include_pending=True)
    if not s:
        raise HTTPException(404)
    had_socket = bool(getattr(s, "websocket", None))
    _close_socket_if_online(req.token)
    local_events.emit(
        "device_disconnected",
        title="CyberDeck",
        message=f"Device disconnected: {getattr(s, 'device_name', 'Unknown')}",
        payload={"token": req.token, "device_id": getattr(s, "device_id", ""), "name": getattr(s, "device_name", "")},
    )
    if not had_socket:
        return {"ok": True, "msg": "already_offline"}
    return {"ok": True}


@router.post("/api/local/device_delete")
def local_device_delete(req: LocalTokenRequest, request: Request):
    """Delete a device session by token and close any active connection."""
    _require_localhost(request)
    s = _get_session(req.token, include_pending=True)
    if not s:
        raise HTTPException(404)
    _close_socket_if_online(req.token)
    ok = device_manager.delete_session(req.token)
    if not ok:
        raise HTTPException(500)
    local_events.emit(
        "device_deleted",
        title="CyberDeck",
        message=f"Device removed: {getattr(s, 'device_name', 'Unknown')}",
        payload={"token": req.token, "device_id": getattr(s, "device_id", ""), "name": getattr(s, "device_name", "")},
    )
    return {"ok": True}


@router.post("/api/local/device_delete_by_id")
def local_device_delete_by_id(req: LocalDeviceIdRequest, request: Request):
    """Delete a device session by device ID and close any active connection."""
    _require_localhost(request)
    device_id = str(req.device_id or "").strip()
    if not device_id:
        raise HTTPException(400, detail="device_id_required")

    hit_token = _find_token_by_device_id(device_id)
    if not hit_token:
        raise HTTPException(404, detail="device_not_found")

    s = _get_session(hit_token, include_pending=True)
    _close_socket_if_online(hit_token)
    ok = device_manager.delete_session(hit_token)
    if not ok:
        raise HTTPException(500, detail="delete_failed")
    local_events.emit(
        "device_deleted",
        title="CyberDeck",
        message=f"Device removed: {getattr(s, 'device_name', 'Unknown') if s else 'Unknown'}",
        payload={
            "token": hit_token,
            "device_id": device_id,
            "name": getattr(s, "device_name", "") if s else "",
        },
    )
    return {"ok": True, "token": hit_token, "device_id": device_id}


@router.post("/api/local/revoke_all")
def local_revoke_all(req: LocalRevokeAllRequest, request: Request):
    """Revoke all device sessions except an optional token."""
    _require_localhost(request)
    keep = str((req.keep_token or "")).strip()
    revoked = _revoke_tokens(keep_token=keep)
    if revoked > 0:
        local_events.emit(
            "sessions_revoked",
            title="CyberDeck",
            message=f"Revoked {revoked} session(s)",
            payload={"revoked": int(revoked), "kept": keep or None},
        )
    return {"ok": True, "revoked": revoked, "kept": keep or None}


@router.post("/api/local/input_lock")
def local_input_lock(req: LocalInputLockRequest, request: Request):
    """Enable or disable remote-input lock for active and future websocket sessions."""
    _require_localhost(request)
    snapshot = input_guard.set_locked(
        bool(req.locked),
        reason=str(req.reason or "").strip(),
        actor=str(req.actor or "local_api").strip() or "local_api",
    )
    local_events.emit(
        "input_lock_changed",
        title="CyberDeck",
        message="Remote input locked" if snapshot.get("locked") else "Remote input unlocked",
        payload={"security": snapshot},
    )
    return {"ok": True, "security": snapshot}


@router.post("/api/local/panic_mode")
def local_panic_mode(req: LocalPanicRequest, request: Request):
    """Disconnect/revoke sessions in one action and optionally lock remote input."""
    _require_localhost(request)
    keep = str((req.keep_token or "")).strip()
    revoked = _revoke_tokens(keep_token=keep)
    if bool(req.lock_input):
        reason = str(req.reason or "").strip() or "panic_mode"
        security = input_guard.set_locked(True, reason=reason, actor="panic_mode")
    else:
        security = input_guard.snapshot()
    local_events.emit(
        "panic_mode",
        title="CyberDeck",
        message=f"Panic mode executed: revoked={revoked}",
        payload={"revoked": int(revoked), "kept": keep or None, "security": security},
    )
    return {"ok": True, "revoked": int(revoked), "kept": keep or None, "security": security}


@router.get("/api/local/diag_bundle")
def local_diag_bundle(request: Request):
    """Return bundled diagnostics payload for support and troubleshooting."""
    _require_localhost(request)
    now = _safe_stat(time.time, 0.0)
    boot = _safe_stat(psutil.boot_time, now)
    uptime = int(max(0.0, now - boot))
    pairing = pairing_meta(now=now)
    return {
        "collected_at": int(now),
        "version": str(getattr(config, "VERSION", "") or ""),
        "server_id": str(getattr(config, "SERVER_ID", "") or ""),
        "hostname": str(getattr(config, "HOSTNAME", "") or ""),
        "scheme": str(getattr(config, "SCHEME", "http") or "http"),
        "port": _safe_port(getattr(config, "PORT", 0), scheme=str(getattr(config, "SCHEME", "http") or "http")),
        "tls_enabled": bool(getattr(config, "TLS_ENABLED", False)),
        "approval_required": bool(getattr(config, "DEVICE_APPROVAL_REQUIRED", False)),
        "cpu": _safe_stat(lambda: psutil.cpu_percent(interval=None), 0.0),
        "ram": _safe_stat(lambda: psutil.virtual_memory().percent, 0.0),
        "process_ram": _safe_process_rss(),
        "uptime_s": uptime,
        "pairing": pairing,
        "security": input_guard.snapshot(),
        "pin_limiter": pin_limiter.stats(),
        "devices": device_manager.get_all_devices(),
        "pending_devices": (
            device_manager.get_pending_devices() if hasattr(device_manager, "get_pending_devices") else []
        ),
        "protocol": protocol_payload(),
    }


@router.post("/api/local/regenerate_code")
def regenerate_code(request: Request):
    """Regenerate code."""
    _require_localhost(request)
    new_code = rotate_pairing_code()

    try:
        pin_limiter.reset()
    except Exception:
        pass
    log.info("Pairing code regenerated -> %s", new_code)
    return {"new_code": new_code, **pairing_meta()}

