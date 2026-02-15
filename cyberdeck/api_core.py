import hashlib
import os
import time
import uuid
from typing import Any, Dict, Optional

import psutil
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from . import config
from .auth import TokenDep, require_perm
from .context import device_manager
from .input_backend import INPUT_BACKEND
from .logging_config import log
from .pin_limiter import pin_limiter
from .protocol import protocol_payload


router = APIRouter()

INPUT_BACKEND.configure()


def _normalized_upload_name(raw_name: str) -> str:
    """Sanitize the upload filename while preserving extension."""
    name = os.path.basename(str(raw_name or "upload.bin")).strip()
    if not name:
        name = "upload.bin"
    if name in (".", ".."):
        name = "upload.bin"
    return name.replace("\x00", "")[:240] or "upload.bin"


def _unique_upload_path(base_dir: str, filename: str) -> tuple[str, str]:
    """Build a non-colliding upload path in the upload directory."""
    stem, ext = os.path.splitext(filename)
    candidate = filename
    path = os.path.join(base_dir, candidate)
    i = 1
    while os.path.exists(path):
        candidate = f"{stem}_{i}{ext}"
        path = os.path.join(base_dir, candidate)
        i += 1
        if i > 10000:
            candidate = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
            path = os.path.join(base_dir, candidate)
            break
    return path, candidate


class HandshakeRequest(BaseModel):
    code: str
    device_id: str
    device_name: str
    protocol_version: Optional[int] = None
    capabilities: Optional[Dict[str, Any]] = None


@router.post("/api/handshake")
def handshake(req: HandshakeRequest, request: Request):
    """Return the public handshake payload for new clients."""
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
    return {
        "status": "ok",
        "token": token,
        "server_name": config.HOSTNAME,
        **protocol_payload(),
    }


@router.get("/api/protocol")
def get_protocol():
    """Return protocol metadata advertised by the current server build."""
    return protocol_payload()


@router.get("/api/stats")
def get_stats(token: str = TokenDep):
    """Return lightweight host metrics for authenticated clients."""
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        **protocol_payload(),
    }


@router.get("/api/diag")
def get_diag(token: str = TokenDep):
    """Return extended diagnostics including stream and input runtime state."""
    require_perm(token, "perm_stream")
    out = {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "hostname": config.HOSTNAME,
        **protocol_payload(),
    }
    try:
        from .video import stream_stats

        out["stream"] = stream_stats(token)
    except Exception:
        out["stream"] = {}
    try:
        from .ws_mouse import ws_runtime_diag

        out["ws"] = ws_runtime_diag(token)
    except Exception:
        out["ws"] = {}
    return out


@router.post("/api/file/upload")
async def upload_file(request: Request, file: UploadFile = File(...), token: str = TokenDep):
    """Validate and atomically persist an uploaded file to `FILES_DIR`."""
    require_perm(token, "perm_upload")
    try:
        name = _normalized_upload_name(str(file.filename or "upload.bin"))
        _, ext = os.path.splitext(name)
        ext = str(ext or "").strip().lower()
        allowed_ext = [str(x).strip().lower() for x in (getattr(config, "UPLOAD_ALLOWED_EXT", []) or []) if str(x).strip()]
        if allowed_ext and ext not in allowed_ext:
            raise HTTPException(415, detail="upload_extension_not_allowed")

        file_path, final_name = _unique_upload_path(config.FILES_DIR, name)
        tmp_path = file_path + f".part-{uuid.uuid4().hex[:8]}"
        sha256 = hashlib.sha256()
        total = 0
        max_bytes = max(0, int(getattr(config, "UPLOAD_MAX_BYTES", 0) or 0))
        with open(tmp_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)
                sha256.update(chunk)
                total += len(chunk)
                if max_bytes > 0 and total > max_bytes:
                    raise HTTPException(413, detail="upload_too_large")
        expected = ""
        try:
            expected = str((request.headers.get("x-file-sha256") or "")).strip().lower()
        except Exception:
            expected = ""
        if not expected:
            try:
                expected = str((file.headers.get("x-file-sha256") or "")).strip().lower()
            except Exception:
                expected = ""
        actual = sha256.hexdigest()
        # Reject corrupted payloads before exposing the temporary file as final.
        if expected and expected != actual:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            raise HTTPException(400, detail="upload_checksum_mismatch")
        # Atomic move prevents clients from observing partially written files.
        os.replace(tmp_path, file_path)
        return {"status": "ok", "filename": final_name, "size": int(total), "sha256": actual}
    except HTTPException:
        try:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            if "tmp_path" in locals() and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        log.exception("Upload failed")
        return {"status": "error", "detail": str(e)}
