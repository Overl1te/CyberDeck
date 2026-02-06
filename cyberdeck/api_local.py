import asyncio
import os
import time
import uuid
import urllib.parse
from typing import Any, Dict, Optional

import psutil
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import config
from .context import device_manager
from .logging_config import log
from .net import get_local_ip
from .pin_limiter import pin_limiter
from .transfer import trigger_file_send_logic


router = APIRouter()


class LocalFileRequest(BaseModel):
    token: str
    file_path: str


class LocalSettingsRequest(BaseModel):
    token: str
    settings: Dict[str, Any]


class LocalTokenRequest(BaseModel):
    token: str


class QrLoginRequest(BaseModel):
    # Compatibility with mobile clients:
    # old payload: {"nonce": "..."}
    # new payload: {"qr_token": "..."}
    nonce: Optional[str] = None
    qr_token: Optional[str] = None
    device_id: Optional[str] = None
    device_name: Optional[str] = None


def _require_localhost(request: Request) -> None:
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)


@router.post("/api/local/trigger_file")
def local_trigger_file(req: LocalFileRequest, request: Request):
    _require_localhost(request)
    ok, msg = trigger_file_send_logic(req.token, req.file_path)
    return {"ok": ok, "msg": msg}


@router.get("/api/local/info")
def local_info(request: Request):
    _require_localhost(request)
    return {
        "version": config.VERSION,
        "server_id": config.SERVER_ID,
        "pairing_code": config.PAIRING_CODE,
        "ip": get_local_ip(),
        "port": config.PORT,
        "scheme": getattr(config, "SCHEME", "http"),
        "tls": bool(getattr(config, "TLS_ENABLED", False)),
        "hostname": config.HOSTNAME,
        "log_file": config.LOG_FILE,
        "devices": device_manager.get_all_devices(),
    }


@router.get("/api/local/qr_payload")
def local_qr_payload(request: Request):
    _require_localhost(request)
    ip = get_local_ip()
    payload = {
        "type": "cyberdeck_qr_v1",
        "server_id": config.SERVER_ID,
        "hostname": config.HOSTNAME,
        "version": config.VERSION,
        "ip": ip,
        "port": config.PORT,
        "scheme": getattr(config, "SCHEME", "http"),
        "pairing_code": config.PAIRING_CODE,
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
    }

    # QR лучше кодировать как URL: тогда камера телефона откроет веб-страницу, а не покажет JSON.
    # Сервер раздаёт `static/index.html` на `/` (если файл существует).
    scheme = str(getattr(config, "SCHEME", "http") or "http")
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
            },
            doseq=False,
        )
        url = f"{scheme}://{ip}:{int(config.PORT)}/?{qs}"
    except Exception:
        url = f"{scheme}://{ip}:{int(config.PORT)}/"

    return {"payload": payload, "url": url}


@router.post("/api/qr/login")
def qr_login(req: QrLoginRequest):
    raise HTTPException(501, detail="qr_login_not_implemented")


@router.get("/api/local/stats")
def local_stats(request: Request):
    _require_localhost(request)
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "uptime_s": int(time.time() - psutil.boot_time()),
        "process_ram": psutil.Process(os.getpid()).memory_info().rss,
    }


@router.get("/api/local/device_settings")
def local_get_device_settings(token: str, request: Request):
    _require_localhost(request)
    s = device_manager.get_session(token)
    if not s:
        raise HTTPException(404)
    return {"token": token, "settings": s.settings}


@router.post("/api/local/device_settings")
def local_set_device_settings(req: LocalSettingsRequest, request: Request):
    _require_localhost(request)
    ok = device_manager.update_settings(req.token, req.settings)
    if not ok:
        raise HTTPException(404)
    return {"ok": True}


@router.post("/api/local/device_disconnect")
def local_device_disconnect(req: LocalTokenRequest, request: Request):
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


@router.post("/api/local/regenerate_code")
def regenerate_code(request: Request):
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
