from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Query, Request

from . import config
from .context import device_manager


DEFAULT_PERMS = {
    "perm_mouse": True,
    "perm_keyboard": True,
    "perm_upload": True,
    "perm_file_send": True,
    "perm_stream": True,
    "perm_power": False,
}


def _as_bool(value: Any) -> bool:
    """Convert environment-like values to a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off", ""):
            return False
    return bool(value)


def get_perm(token: str, key: str) -> bool:
    """Retrieve data required to get perm."""
    # Read-path helpers should avoid mutating shared state where possible.
    s = device_manager.get_session(token)
    if not s:
        return False
    try:
        settings: Dict[str, Any] = s.settings or {}
        if key in settings:
            return _as_bool(settings.get(key))
        return _as_bool(DEFAULT_PERMS.get(key, False))
    except Exception:
        return _as_bool(DEFAULT_PERMS.get(key, False))


def require_perm(token: str, key: str) -> None:
    """Require perm."""
    if not get_perm(token, key):
        raise HTTPException(403, detail=f"permission_denied:{key}")


async def get_token(request: Request, token: Optional[str] = Query(None)) -> str:
    """Asynchronously retrieve data required to get token."""
    # Read-path helpers should avoid mutating shared state where possible.
    if bool(getattr(config, "ALLOW_QUERY_TOKEN", True)) and token and device_manager.get_session(token):
        return token
    auth = request.headers.get("Authorization")
    if auth:
        t = auth.replace("Bearer ", "")
        if device_manager.get_session(t):
            return t
    if bool(getattr(config, "ALLOW_QUERY_TOKEN", True)):
        ws_token = request.query_params.get("token")
        if ws_token and device_manager.get_session(ws_token):
            return ws_token
    raise HTTPException(403, detail="Unauthorized")


TokenDep = Depends(get_token)
