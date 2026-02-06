import os
import time

import psutil
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from . import config
from .auth import TokenDep, require_perm
from .context import device_manager
from .input_backend import INPUT_BACKEND
from .logging_config import log
from .pin_limiter import pin_limiter


router = APIRouter()

INPUT_BACKEND.configure()


class HandshakeRequest(BaseModel):
    code: str
    device_id: str
    device_name: str


@router.post("/api/handshake")
def handshake(req: HandshakeRequest, request: Request):
    ip = request.client.host if request.client else "unknown"

    try:
        exp = getattr(config, "PAIRING_EXPIRES_AT", None)
        if exp is not None and time.time() > float(exp):
            raise HTTPException(403, detail="pairing_expired")
    except HTTPException:
        raise
    except Exception:
        pass

    allowed, retry_after = pin_limiter.check(ip)
    if not allowed:
        raise HTTPException(429, detail="pin_rate_limited", headers={"Retry-After": str(int(retry_after))})

    if req.code != config.PAIRING_CODE:
        pin_limiter.record_failure(ip)
        raise HTTPException(403, detail="Invalid Code")

    pin_limiter.record_success(ip)
    token = device_manager.authorize(req.device_id, req.device_name, ip)
    log.info(f"Handshake OK: {req.device_name} ({req.device_id}) -> {ip}")
    return {"status": "ok", "token": token, "server_name": config.HOSTNAME}


@router.get("/api/stats")
def get_stats(token: str = TokenDep):
    return {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent}


@router.post("/api/file/upload")
async def upload_file(file: UploadFile = File(...), token: str = TokenDep):
    require_perm(token, "perm_upload")
    try:
        file_path = os.path.join(config.FILES_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)
        return {"status": "ok"}
    except Exception as e:
        log.exception("Upload failed")
        return {"status": "error", "detail": str(e)}
