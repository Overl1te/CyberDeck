import asyncio
import ctypes
import os
import sys
import threading
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from . import config
from .auth import get_perm
from .context import device_manager
from .input_backend import INPUT_BACKEND
from .logging_config import log


router = APIRouter()

_mouse_remainders_lock = threading.Lock()
_mouse_remainders = {}
_virtual_cursor_lock = threading.Lock()
_virtual_cursor = {}
_IS_WINDOWS = os.name == "nt"
_IS_WAYLAND = (os.environ.get("XDG_SESSION_TYPE") or "").lower() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def _safe_screen_size() -> tuple[int, int]:
    try:
        wh = INPUT_BACKEND.screen_size()
        if wh and int(wh[0]) > 0 and int(wh[1]) > 0:
            return int(wh[0]), int(wh[1])
    except Exception:
        pass
    # Fallback: best-effort logical canvas for client cursor overlay.
    try:
        w = max(320, int(os.environ.get("CYBERDECK_STREAM_W", "1920")))
    except Exception:
        w = 1920
    try:
        h = max(240, int(os.environ.get("CYBERDECK_STREAM_H", "1080")))
    except Exception:
        h = 1080
    return w, h


def _init_virtual_cursor(token: str) -> None:
    w, h = _safe_screen_size()
    x = w // 2
    y = h // 2
    try:
        pos = INPUT_BACKEND.position()
        if pos:
            x = int(pos[0])
            y = int(pos[1])
    except Exception:
        pass
    x = max(0, min(max(0, w - 1), int(x)))
    y = max(0, min(max(0, h - 1), int(y)))
    with _virtual_cursor_lock:
        _virtual_cursor[token] = (x, y, w, h)


def _get_virtual_cursor(token: str) -> tuple[int, int, int, int]:
    with _virtual_cursor_lock:
        pos = _virtual_cursor.get(token)
    if pos is None:
        _init_virtual_cursor(token)
        with _virtual_cursor_lock:
            pos = _virtual_cursor.get(token) or (0, 0, 1920, 1080)
    return int(pos[0]), int(pos[1]), int(pos[2]), int(pos[3])


def _move_virtual_cursor(token: str, dx: int, dy: int) -> None:
    x, y, w, h = _get_virtual_cursor(token)
    nx = max(0, min(max(0, w - 1), int(x) + int(dx)))
    ny = max(0, min(max(0, h - 1), int(y) + int(dy)))
    with _virtual_cursor_lock:
        _virtual_cursor[token] = (nx, ny, w, h)


async def _cursor_stream(websocket: WebSocket, token: str):
    min_dt = 1.0 / max(5, int(config.CURSOR_STREAM_FPS))
    last_pos = None
    while True:
        try:
            if INPUT_BACKEND.can_position and INPUT_BACKEND.can_screen_size:
                pos_xy = INPUT_BACKEND.position()
                wh = INPUT_BACKEND.screen_size()
                if not pos_xy or not wh:
                    await asyncio.sleep(min_dt)
                    continue
                x, y = pos_xy
                w, h = wh
                pos = (int(x), int(y), int(w), int(h))
            else:
                pos = _get_virtual_cursor(token)
            if pos != last_pos:
                await websocket.send_json({"type": "cursor", "x": pos[0], "y": pos[1], "w": pos[2], "h": pos[3]})
                last_pos = pos
        except asyncio.CancelledError:
            break
        except Exception:
            break
        await asyncio.sleep(min_dt)


@router.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket, token: Optional[str] = Query(None)):
    auth_header = str(websocket.headers.get("authorization") or "").strip()
    bearer = ""
    if auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip()
    ws_qs_token = str(websocket.query_params.get("token") or "").strip()
    resolved_token = str(token or "").strip() or ws_qs_token or bearer

    if not resolved_token or not device_manager.get_session(resolved_token):
        await websocket.close(code=4003)
        return
    token = resolved_token

    if not (get_perm(token, "perm_mouse") or get_perm(token, "perm_keyboard")):
        await websocket.close(code=4003)
        return
    await websocket.accept()
    device_manager.register_socket(token, websocket)
    log.info(f"WS connected: {token}")
    if (not INPUT_BACKEND.can_pointer or not INPUT_BACKEND.can_keyboard) and (
        get_perm(token, "perm_mouse") or get_perm(token, "perm_keyboard")
    ):
        try:
            await websocket.send_json(
                {"type": "warning", "code": "wayland_input_limited" if _IS_WAYLAND else "input_backend_limited"}
            )
        except Exception:
            pass
    if not INPUT_BACKEND.can_pointer and not INPUT_BACKEND.can_keyboard:
        try:
            await websocket.send_json({"type": "error", "code": "input_backend_unavailable"})
        except Exception:
            pass
        await websocket.close(code=1011)
        return
    _init_virtual_cursor(token)
    cursor_task: Optional[asyncio.Task] = (
        asyncio.create_task(_cursor_stream(websocket, token))
        if config.CURSOR_STREAM
        else None
    )
    try:
        while True:
            data = await websocket.receive_json()
            t = (data.get("type") or "").lower()

            if t == "move":
                if not get_perm(token, "perm_mouse"):
                    continue
                try:
                    dx = float(data.get("dx", 0) or 0)
                    dy = float(data.get("dy", 0) or 0)
                except Exception:
                    dx, dy = 0.0, 0.0

                with _mouse_remainders_lock:
                    rx, ry = _mouse_remainders.get(token, (0.0, 0.0))
                    dx += rx
                    dy += ry
                    mx = int(round(dx))
                    my = int(round(dy))
                    _mouse_remainders[token] = (dx - mx, dy - my)

                if mx or my:
                    INPUT_BACKEND.move_rel(mx, my)
                    _move_virtual_cursor(token, mx, my)

            elif t == "click":
                if not get_perm(token, "perm_mouse"):
                    continue
                INPUT_BACKEND.click("left")

            elif t == "rclick":
                if not get_perm(token, "perm_mouse"):
                    continue
                INPUT_BACKEND.click("right")

            elif t == "dclick":
                if not get_perm(token, "perm_mouse"):
                    continue
                INPUT_BACKEND.click("left", double=True)

            elif t == "scroll":
                if not get_perm(token, "perm_mouse"):
                    continue
                INPUT_BACKEND.scroll(int(data.get("dy", 0)))

            elif t == "drag_s":
                if not get_perm(token, "perm_mouse"):
                    continue
                INPUT_BACKEND.mouse_down("left")

            elif t == "drag_e":
                if not get_perm(token, "perm_mouse"):
                    continue
                INPUT_BACKEND.mouse_up("left")

            elif t == "text":
                if not get_perm(token, "perm_keyboard"):
                    continue
                text = str(data.get("text", ""))
                if text:
                    if _IS_WINDOWS:
                        try:
                            hwnd = ctypes.windll.user32.GetForegroundWindow()
                            if hwnd:
                                for char in text:
                                    ctypes.windll.user32.SendMessageW(hwnd, 0x0102, ord(char), 0)
                        except Exception:
                            pass
                    else:
                        try:
                            INPUT_BACKEND.write_text(text)
                        except Exception:
                            if config.DEBUG:
                                log.exception("Keyboard text injection failed")

            elif t == "key":
                if not get_perm(token, "perm_keyboard"):
                    continue
                val = str(data.get("key", "")).lower()
                if _IS_WINDOWS:
                    key_map = {"enter": 0x0D, "backspace": 0x08, "space": 0x20, "win": 0x5B}
                    vk = key_map.get(val)
                    if vk:
                        try:
                            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                        except Exception:
                            pass
                else:
                    if val == "win":
                        if sys.platform == "darwin":
                            py_key = "command"
                        else:
                            py_key = "winleft"
                    else:
                        py_key = {"enter": "enter", "backspace": "backspace", "space": "space"}.get(val)
                    if py_key:
                        try:
                            INPUT_BACKEND.press(py_key)
                        except Exception:
                            if config.DEBUG:
                                log.exception("Keyboard press failed")

            elif t == "hotkey":
                if not get_perm(token, "perm_keyboard"):
                    continue
                keys = data.get("keys") or []
                if isinstance(keys, list) and keys:
                    keys = [str(k).lower() for k in keys]
                    INPUT_BACKEND.hotkey(*keys)

            elif t == "media":
                if not get_perm(token, "perm_keyboard"):
                    continue
                act = str(data.get("action", "")).lower()
                media_map = {
                    "play_pause": "playpause",
                    "next": "nexttrack",
                    "prev": "prevtrack",
                    "stop": "stop",
                    "mute": "volumemute",
                    "vol_up": "volumeup",
                    "vol_down": "volumedown",
                }
                key = media_map.get(act)
                if key:
                    INPUT_BACKEND.press(key)

            elif t == "shortcut":
                if not get_perm(token, "perm_keyboard"):
                    continue
                act = str(data.get("action", "")).lower()
                if act == "copy":
                    INPUT_BACKEND.hotkey("ctrl", "c")
                elif act == "paste":
                    INPUT_BACKEND.hotkey("ctrl", "v")
                elif act == "cut":
                    INPUT_BACKEND.hotkey("ctrl", "x")
                elif act == "undo":
                    INPUT_BACKEND.hotkey("ctrl", "z")
                elif act == "redo":
                    INPUT_BACKEND.hotkey("ctrl", "y")

    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WS error")
    finally:
        if cursor_task:
            cursor_task.cancel()
        device_manager.unregister_socket(token)
        try:
            with _mouse_remainders_lock:
                _mouse_remainders.pop(token, None)
        except Exception:
            pass
        try:
            with _virtual_cursor_lock:
                _virtual_cursor.pop(token, None)
        except Exception:
            pass
        log.info(f"WS disconnected: {token}")
