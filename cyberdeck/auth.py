from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Query, Request

from .context import device_manager


DEFAULT_PERMS = {
    "perm_mouse": True,
    "perm_keyboard": True,
    "perm_upload": True,
    "perm_file_send": True,
    "perm_stream": True,
    "perm_power": False,
}


def get_perm(token: str, key: str) -> bool:
    s = device_manager.get_session(token)
    if not s:
        return False
    try:
        settings: Dict[str, Any] = s.settings or {}
        if key in settings:
            return bool(settings.get(key))
        return bool(DEFAULT_PERMS.get(key, False))
    except Exception:
        return bool(DEFAULT_PERMS.get(key, False))


def require_perm(token: str, key: str) -> None:
    if not get_perm(token, key):
        raise HTTPException(403, detail=f"permission_denied:{key}")


async def get_token(request: Request, token: Optional[str] = Query(None)) -> str:
    if token and device_manager.get_session(token):
        return token
    auth = request.headers.get("Authorization")
    if auth:
        t = auth.replace("Bearer ", "")
        if device_manager.get_session(t):
            return t
    ws_token = request.query_params.get("token")
    if ws_token and device_manager.get_session(ws_token):
        return ws_token
    raise HTTPException(403, detail="Unauthorized")


TokenDep = Depends(get_token)

