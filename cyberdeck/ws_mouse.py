import asyncio
import ctypes
import os
import sys
import threading
from typing import Optional

import pyautogui
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from . import config
from .auth import get_perm
from .context import device_manager
from .logging_config import log


router = APIRouter()

_mouse_remainders_lock = threading.Lock()
_mouse_remainders = {}
_IS_WINDOWS = os.name == "nt"


async def _cursor_stream(websocket: WebSocket):
    min_dt = 1.0 / max(5, int(config.CURSOR_STREAM_FPS))
    last_pos = None
    while True:
        try:
            x, y = pyautogui.position()
            w, h = pyautogui.size()
            pos = (int(x), int(y), int(w), int(h))
            if pos != last_pos:
                await websocket.send_json({"type": "cursor", "x": pos[0], "y": pos[1], "w": pos[2], "h": pos[3]})
                last_pos = pos
        except asyncio.CancelledError:
            break
        except Exception:
            break
        await asyncio.sleep(min_dt)


@router.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket, token: str = Query(...)):
    if not device_manager.get_session(token):
        await websocket.close(code=4003)
        return
    if not (get_perm(token, "perm_mouse") or get_perm(token, "perm_keyboard")):
        await websocket.close(code=4003)
        return
    await websocket.accept()
    device_manager.register_socket(token, websocket)
    log.info(f"WS connected: {token}")
    cursor_task: Optional[asyncio.Task] = asyncio.create_task(_cursor_stream(websocket)) if config.CURSOR_STREAM else None
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
                    pyautogui.moveRel(mx, my, _pause=False)

            elif t == "click":
                if not get_perm(token, "perm_mouse"):
                    continue
                pyautogui.click(_pause=False)

            elif t == "rclick":
                if not get_perm(token, "perm_mouse"):
                    continue
                pyautogui.click(button="right", _pause=False)

            elif t == "dclick":
                if not get_perm(token, "perm_mouse"):
                    continue
                pyautogui.doubleClick(_pause=False)

            elif t == "scroll":
                if not get_perm(token, "perm_mouse"):
                    continue
                pyautogui.scroll(int(data.get("dy", 0)), _pause=False)

            elif t == "drag_s":
                if not get_perm(token, "perm_mouse"):
                    continue
                pyautogui.mouseDown(_pause=False)

            elif t == "drag_e":
                if not get_perm(token, "perm_mouse"):
                    continue
                pyautogui.mouseUp(_pause=False)

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
                            pyautogui.write(text, interval=0, _pause=False)
                        except Exception:
                            pass

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
                            pyautogui.press(py_key, _pause=False)
                        except Exception:
                            pass

            elif t == "hotkey":
                if not get_perm(token, "perm_keyboard"):
                    continue
                keys = data.get("keys") or []
                if isinstance(keys, list) and keys:
                    keys = [str(k).lower() for k in keys]
                    pyautogui.hotkey(*keys, _pause=False)

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
                    pyautogui.press(key, _pause=False)

            elif t == "shortcut":
                if not get_perm(token, "perm_keyboard"):
                    continue
                act = str(data.get("action", "")).lower()
                if act == "copy":
                    pyautogui.hotkey("ctrl", "c", _pause=False)
                elif act == "paste":
                    pyautogui.hotkey("ctrl", "v", _pause=False)
                elif act == "cut":
                    pyautogui.hotkey("ctrl", "x", _pause=False)
                elif act == "undo":
                    pyautogui.hotkey("ctrl", "z", _pause=False)
                elif act == "redo":
                    pyautogui.hotkey("ctrl", "y", _pause=False)

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
        log.info(f"WS disconnected: {token}")
