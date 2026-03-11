import asyncio
from collections import deque
import ctypes
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .. import config
from ..auth import get_perm
from ..context import device_manager, input_guard, local_events
from ..input import INPUT_BACKEND
from ..logging_config import log
from ..protocol import protocol_payload
from .protocol import build_server_hello, extract_text_payload, is_text_event_type


router = APIRouter()

_mouse_remainders_lock = threading.Lock()
_mouse_remainders = {}
_virtual_cursor_lock = threading.Lock()
_virtual_cursor = {}
_ws_runtime_lock = threading.Lock()
_ws_runtime = {}
_ws_event_ids_lock = threading.Lock()
_ws_event_ids = {}
_IS_WINDOWS = os.name == "nt"
_IS_WAYLAND = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def _env_int(name: str, default: int) -> int:
    """Read integer env var with fallback for malformed values."""
    raw = os.environ.get(name, None)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return int(default)


def _env_float(name: str, default: float) -> float:
    """Read float env var with fallback for malformed values."""
    raw = os.environ.get(name, None)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    """Read bool env var supporting common truthy/falsy forms."""
    raw = os.environ.get(name, None)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on", "y", "t"}:
        return True
    if value in {"0", "false", "no", "off", "n", "f"}:
        return False
    return bool(default)


_MOUSE_GAIN_DEFAULT = 1.35 if _IS_WAYLAND else 1.0
_MOUSE_GAIN = _env_float("CYBERDECK_MOUSE_GAIN", _MOUSE_GAIN_DEFAULT)
_MOUSE_GAIN = max(0.1, min(8.0, _MOUSE_GAIN))
_MOUSE_MAX_DELTA = _env_int("CYBERDECK_MOUSE_MAX_DELTA", 160)
_MOUSE_MAX_DELTA = max(8, _MOUSE_MAX_DELTA)
_MOUSE_DEADZONE = _env_float("CYBERDECK_MOUSE_DEADZONE", 0.2 if _IS_WAYLAND else 0.0)
_MOUSE_DEADZONE = max(0.0, min(2.0, _MOUSE_DEADZONE))
_MOUSE_LAG_DAMP_START_S = _env_float("CYBERDECK_MOUSE_LAG_DAMP_START_S", 0.085 if _IS_WAYLAND else 0.18)
_MOUSE_LAG_DAMP_START_S = max(0.01, min(1.0, _MOUSE_LAG_DAMP_START_S))
_MOUSE_LAG_DAMP_MIN = _env_float("CYBERDECK_MOUSE_LAG_DAMP_MIN", 0.35)
_MOUSE_LAG_DAMP_MIN = max(0.1, min(1.0, _MOUSE_LAG_DAMP_MIN))
_mouse_last_move_ts = {}
_windows_warned_input_block = set()
_windows_gui_block_warned = set()
_windows_protected_cache_lock = threading.Lock()
_windows_protected_cache: dict[str, Any] = {"ts": 0.0, "items": []}
_WINDOWS_GUI_PROTECT_ENABLED = _IS_WINDOWS and _env_bool("CYBERDECK_BLOCK_SELF_GUI_INPUT", True)
_WINDOWS_PROTECT_CACHE_TTL_S = max(0.05, min(2.0, _env_float("CYBERDECK_PROTECTED_GUI_CACHE_TTL_S", 0.35)))
_WINDOWS_LAUNCHER_PID = max(0, _env_int("CYBERDECK_LAUNCHER_PID", 0))
_WINDOWS_PROTECT_TITLE_TOKENS = tuple(
    x.strip().lower()
    for x in str(os.environ.get("CYBERDECK_PROTECTED_GUI_TITLES", "") or "").split(",")
    if x.strip()
)


def _ws_log_enabled() -> bool:
    """Return whether websocket-level verbose logging is enabled."""
    return bool(getattr(config, "VERBOSE_WS_LOG", True) or getattr(config, "DEBUG", False))


def _windows_force_move_rel(dx: int, dy: int) -> bool:
    """Best-effort WinAPI pointer move fallback bypassing backend-specific failures."""
    if not _IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        class _Point(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = _Point()
        if user32.GetCursorPos(ctypes.byref(pt)):
            if user32.SetCursorPos(int(pt.x) + int(dx), int(pt.y) + int(dy)):
                return True
        # Last-resort relative move event.
        user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)
        return True
    except Exception:
        return False


def _windows_force_click(button: str = "left", double: bool = False) -> bool:
    """Best-effort WinAPI mouse button fallback for blocked backend click calls."""
    if not _IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        b = str(button or "left").lower()
        if b == "right":
            down, up = 0x0008, 0x0010
        elif b == "middle":
            down, up = 0x0020, 0x0040
        else:
            down, up = 0x0002, 0x0004
        count = 2 if bool(double) else 1
        for _ in range(count):
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
        return True
    except Exception:
        return False


def _windows_force_scroll(dy: int) -> bool:
    """Best-effort WinAPI wheel fallback when backend scroll fails."""
    if not _IS_WINDOWS:
        return False
    try:
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(dy) * 120, 0)
        return True
    except Exception:
        return False


def _windows_force_button(down: bool, button: str = "left") -> bool:
    """Best-effort WinAPI press/release fallback for drag operations."""
    if not _IS_WINDOWS:
        return False
    try:
        user32 = ctypes.windll.user32
        b = str(button or "left").lower()
        if b == "right":
            flag = 0x0008 if down else 0x0010
        elif b == "middle":
            flag = 0x0020 if down else 0x0040
        else:
            flag = 0x0002 if down else 0x0004
        user32.mouse_event(flag, 0, 0, 0, 0)
        return True
    except Exception:
        return False


def _warn_windows_input_block_once(token: str) -> bool:
    """Emit one warning per session when Windows input path looks blocked."""
    if not _IS_WINDOWS:
        return False
    t = str(token or "")
    if not t or t in _windows_warned_input_block:
        return False
    _windows_warned_input_block.add(t)
    if _ws_log_enabled():
        log.warning(
            "WS input fallback exhausted (token=%s). "
            "Foreground elevated/system windows may block input from non-elevated process.",
            t,
        )
    return True


def _windows_get_title(hwnd: int) -> str:
    """Return top-level window title for HWND."""
    if not _IS_WINDOWS:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        n = int(ctypes.windll.user32.GetWindowTextW(int(hwnd), buf, int(len(buf))))
        if n <= 0:
            return ""
        return str(buf.value or "").strip()
    except Exception:
        return ""


def _windows_get_pid(hwnd: int) -> int:
    """Return owner PID for HWND."""
    if not _IS_WINDOWS:
        return 0
    try:
        pid = ctypes.c_ulong(0)
        ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
        return int(pid.value or 0)
    except Exception:
        return 0


def _windows_get_rect(hwnd: int) -> Optional[tuple[int, int, int, int]]:
    """Return window rectangle `(left, top, right, bottom)` for HWND."""
    if not _IS_WINDOWS:
        return None
    try:
        class _Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rc = _Rect()
        ok = bool(ctypes.windll.user32.GetWindowRect(int(hwnd), ctypes.byref(rc)))
        if not ok:
            return None
        if int(rc.right) <= int(rc.left) or int(rc.bottom) <= int(rc.top):
            return None
        return int(rc.left), int(rc.top), int(rc.right), int(rc.bottom)
    except Exception:
        return None


def _windows_protected_handles(refresh: bool = False) -> list[dict[str, Any]]:
    """Enumerate visible launcher GUI windows that must be excluded from remote input."""
    if not _WINDOWS_GUI_PROTECT_ENABLED:
        return []
    if _WINDOWS_LAUNCHER_PID <= 0 and not _WINDOWS_PROTECT_TITLE_TOKENS:
        return []
    now = time.monotonic()
    with _windows_protected_cache_lock:
        ts = float(_windows_protected_cache.get("ts", 0.0) or 0.0)
        items = _windows_protected_cache.get("items", [])
        if (not refresh) and items and ((now - ts) < _WINDOWS_PROTECT_CACHE_TTL_S):
            return list(items)

    out: list[dict[str, Any]] = []
    try:
        enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        handles: list[int] = []

        @enum_proc_type
        def _cb(hwnd: int, _lparam: int) -> bool:
            try:
                handles.append(int(hwnd))
            except Exception:
                pass
            return True

        ctypes.windll.user32.EnumWindows(_cb, 0)
        for hwnd in handles:
            try:
                if not bool(ctypes.windll.user32.IsWindowVisible(int(hwnd))):
                    continue
                if bool(ctypes.windll.user32.IsIconic(int(hwnd))):
                    continue
            except Exception:
                continue
            pid = _windows_get_pid(hwnd)
            title = _windows_get_title(hwnd)
            title_l = title.lower()
            match_pid = bool(_WINDOWS_LAUNCHER_PID > 0 and pid == _WINDOWS_LAUNCHER_PID)
            match_title = bool(title_l and any(tok in title_l for tok in _WINDOWS_PROTECT_TITLE_TOKENS))
            if not (match_pid or match_title):
                continue
            rect = _windows_get_rect(hwnd)
            if not rect:
                continue
            out.append(
                {
                    "hwnd": int(hwnd),
                    "pid": int(pid),
                    "title": str(title),
                    "left": int(rect[0]),
                    "top": int(rect[1]),
                    "right": int(rect[2]),
                    "bottom": int(rect[3]),
                }
            )
    except Exception:
        out = []

    with _windows_protected_cache_lock:
        _windows_protected_cache["ts"] = now
        _windows_protected_cache["items"] = list(out)
    return out


def _windows_point_hits_protected_window(x: int, y: int) -> bool:
    """Return True when point lands inside protected launcher window bounds."""
    if not _WINDOWS_GUI_PROTECT_ENABLED:
        return False
    px = int(x)
    py = int(y)
    for item in _windows_protected_handles():
        if int(item["left"]) <= px < int(item["right"]) and int(item["top"]) <= py < int(item["bottom"]):
            return True
    return False


def _windows_foreground_is_protected() -> bool:
    """Return True when current foreground window belongs to protected launcher GUI."""
    if not _WINDOWS_GUI_PROTECT_ENABLED:
        return False
    try:
        hwnd = int(ctypes.windll.user32.GetForegroundWindow() or 0)
    except Exception:
        hwnd = 0
    if hwnd <= 0:
        return False
    protected = _windows_protected_handles()
    if not protected:
        return False
    protected_hwnds = {int(x.get("hwnd") or 0) for x in protected}
    if hwnd in protected_hwnds:
        return True
    try:
        # GA_ROOT allows child/owned windows to resolve to top-level handle.
        ga_root = 2
        root = int(ctypes.windll.user32.GetAncestor(int(hwnd), int(ga_root)) or 0)
    except Exception:
        root = 0
    return bool(root > 0 and root in protected_hwnds)


def _pointer_xy_now(token: str) -> tuple[int, int]:
    """Return current pointer position with virtual cursor fallback."""
    try:
        pos = INPUT_BACKEND.position()
        if pos is not None:
            return int(pos[0]), int(pos[1])
    except Exception:
        pass
    x, y, _, _ = _get_virtual_cursor(token)
    return int(x), int(y)


async def _notify_gui_input_blocked(websocket: WebSocket, token: str, *, code: str) -> None:
    """Send one warning per session that launcher GUI input is blocked."""
    t = str(token or "")
    if not t:
        return
    if t in _windows_gui_block_warned:
        return
    _windows_gui_block_warned.add(t)
    try:
        await _send_json(websocket, token, {"type": "warning", "code": str(code or "protected_gui_input_blocked")})
    except Exception:
        pass


async def _should_block_pointer_input(
    websocket: WebSocket,
    token: str,
    *,
    target_x: Optional[int] = None,
    target_y: Optional[int] = None,
) -> bool:
    """Return True when pointer action targets protected launcher GUI."""
    if not _WINDOWS_GUI_PROTECT_ENABLED:
        return False
    if target_x is None or target_y is None:
        px, py = _pointer_xy_now(token)
    else:
        px, py = int(target_x), int(target_y)
    blocked = _windows_point_hits_protected_window(px, py)
    if blocked:
        await _notify_gui_input_blocked(websocket, token, code="launcher_gui_input_blocked")
    return bool(blocked)


async def _should_block_keyboard_input(websocket: WebSocket, token: str) -> bool:
    """Return True when keyboard action would target protected launcher GUI."""
    if not _WINDOWS_GUI_PROTECT_ENABLED:
        return False
    blocked = _windows_foreground_is_protected()
    if blocked:
        await _notify_gui_input_blocked(websocket, token, code="launcher_gui_keyboard_blocked")
    return bool(blocked)


def _normalize_hotkey_keys(raw_keys: list[str]) -> list[str]:
    """Normalize hotkey token names to backend-friendly values."""
    aliases = {
        "control": "ctrl",
        "ctl": "ctrl",
        "return": "enter",
        "escape": "esc",
        "command": "winleft",
        "cmd": "winleft",
        "meta": "winleft",
        "super": "winleft",
        "win": "winleft",
        "windows": "winleft",
        "option": "alt",
        "equals": "equal",
        "plus": "equal",
    }
    out: list[str] = []
    for key in raw_keys:
        token = str(key or "").strip().lower()
        if not token:
            continue
        out.append(aliases.get(token, token))
    return out


def _hotkey_variants(keys: list[str]) -> list[list[str]]:
    """Build fallback variants for backend-specific hotkey token naming."""
    if not keys:
        return []
    variants: list[list[str]] = [list(keys)]
    alt = list(keys)
    changed = False
    if _IS_WINDOWS:
        repl = {"winleft": "win", "winright": "win", "equal": "equals"}
    else:
        repl = {"win": "winleft", "equals": "equal"}
    for idx, token in enumerate(list(alt)):
        mapped = repl.get(str(token))
        if mapped and mapped != token:
            alt[idx] = mapped
            changed = True
    if changed and alt not in variants:
        variants.append(alt)
    return variants


def _ws_diag_init(token: str) -> None:
    """Initialize per-session websocket diagnostics state."""
    now = time.time()
    with _ws_runtime_lock:
        prev = _ws_runtime.get(token) or {}
        _ws_runtime[token] = {
            "connected": True,
            "connected_ts": now,
            "disconnected_ts": None,
            "last_rx_ts": now,
            "last_tx_ts": now,
            "messages_rx": 0,
            "messages_tx": 0,
            "connect_count": int(prev.get("connect_count", 0)) + 1,
            "disconnect_count": int(prev.get("disconnect_count", 0)),
            "heartbeat_required": bool(prev.get("heartbeat_required", False)),
            "heartbeat_interval_s": int(getattr(config, "WS_HEARTBEAT_INTERVAL_S", 15) or 15),
            "heartbeat_timeout_s": int(getattr(config, "WS_HEARTBEAT_TIMEOUT_S", 45) or 45),
            "client_protocol_version": prev.get("client_protocol_version"),
            "last_rx_type": None,
            "last_tx_type": None,
        }


def _ws_diag_set(token: str, **patch) -> None:
    """Patch fields in per-session websocket diagnostics state."""
    with _ws_runtime_lock:
        s = _ws_runtime.get(token)
        if not s:
            return
        for k, v in patch.items():
            s[k] = v


def _ws_diag_mark_rx(token: str, msg_type: str) -> None:
    """Record inbound websocket message metadata in diagnostics state."""
    now = time.time()
    with _ws_runtime_lock:
        s = _ws_runtime.get(token)
        if not s:
            return
        s["last_rx_ts"] = now
        s["messages_rx"] = int(s.get("messages_rx", 0)) + 1
        s["last_rx_type"] = str(msg_type or "")


def _ws_diag_mark_tx(token: str, msg_type: str) -> None:
    """Record outbound websocket message metadata in diagnostics state."""
    now = time.time()
    with _ws_runtime_lock:
        s = _ws_runtime.get(token)
        if not s:
            return
        s["last_tx_ts"] = now
        s["messages_tx"] = int(s.get("messages_tx", 0)) + 1
        s["last_tx_type"] = str(msg_type or "")


def _ws_diag_close(token: str) -> None:
    """Mark websocket diagnostics state as disconnected."""
    now = time.time()
    with _ws_runtime_lock:
        s = _ws_runtime.get(token)
        if not s:
            return
        s["connected"] = False
        s["disconnected_ts"] = now
        s["disconnect_count"] = int(s.get("disconnect_count", 0)) + 1


def _track_event_id(token: str, event_id: str) -> bool:
    """Track event id for idempotency; return True when id is new."""
    eid = str(event_id or "").strip()
    if not eid:
        return True
    key = str(token or "")
    if not key:
        return True
    with _ws_event_ids_lock:
        bucket = _ws_event_ids.get(key)
        if bucket is None:
            bucket = deque(maxlen=256)
            _ws_event_ids[key] = bucket
        if eid in bucket:
            return False
        bucket.append(eid)
        return True


def ws_runtime_diag(token: Optional[str] = None):
    """Return websocket diagnostics for one token or all active sessions."""
    with _ws_runtime_lock:
        if token:
            s = _ws_runtime.get(token)
            return dict(s) if isinstance(s, dict) else {}
        return {str(k): dict(v) for k, v in _ws_runtime.items()}


async def _send_json(websocket: WebSocket, token: str, payload: dict) -> None:
    """Send JSON over websocket and account the outbound frame in diagnostics."""
    await websocket.send_json(payload)
    _ws_diag_mark_tx(token, str(payload.get("type") or ""))


def _copy_text_to_clipboard(text: str) -> bool:
    """Copy text to clipboard through platform-specific toolchain."""
    payload = str(text or "")
    if not payload:
        return False

    def _run_with_stdin(cmd: list[str]) -> bool:
        """Run a command with clipboard payload on stdin and return process success."""
        try:
            proc = subprocess.run(
                cmd,
                input=payload.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0,
                check=False,
            )
            return int(proc.returncode) == 0
        except Exception:
            return False

    if sys.platform.startswith("linux"):
        if _IS_WAYLAND and shutil.which("wl-copy"):
            if _run_with_stdin(["wl-copy", "--type", "text/plain;charset=utf-8"]):
                return True
        if shutil.which("xclip"):
            if _run_with_stdin(["xclip", "-selection", "clipboard", "-in"]):
                return True
        if shutil.which("xsel"):
            if _run_with_stdin(["xsel", "--clipboard", "--input"]):
                return True
        return False

    if sys.platform == "darwin":
        return _run_with_stdin(["pbcopy"])

    return False


def _inject_text_fallback(text: str) -> bool:
    """Fallback text injection path using clipboard paste shortcut."""
    payload = str(text or "")
    if not payload:
        return False
    if not _copy_text_to_clipboard(payload):
        return False
    try:
        return bool(INPUT_BACKEND.hotkey("ctrl", "v"))
    except Exception:
        return False


def _safe_screen_size() -> tuple[int, int]:
    """Return reliable screen size with environment-backed fallback values."""
    try:
        wh = INPUT_BACKEND.screen_size()
        if wh and int(wh[0]) > 0 and int(wh[1]) > 0:
            return int(wh[0]), int(wh[1])
    except Exception:
        pass
    # Fallback: best-effort logical canvas for client cursor overlay.
    w = max(320, _env_int("CYBERDECK_STREAM_W", 1920))
    h = max(240, _env_int("CYBERDECK_STREAM_H", 1080))
    return w, h


def _init_virtual_cursor(token: str) -> None:
    """Initialize virtual cursor state for sessions without absolute pointer support."""
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
    """Read virtual cursor state, lazily initializing when missing."""
    with _virtual_cursor_lock:
        pos = _virtual_cursor.get(token)
    if pos is None:
        _init_virtual_cursor(token)
        with _virtual_cursor_lock:
            pos = _virtual_cursor.get(token) or (0, 0, 1920, 1080)
    return int(pos[0]), int(pos[1]), int(pos[2]), int(pos[3])


def _move_virtual_cursor(token: str, dx: int, dy: int) -> None:
    """Update virtual cursor coordinates with bounds clamping."""
    x, y, w, h = _get_virtual_cursor(token)
    nx = max(0, min(max(0, w - 1), int(x) + int(dx)))
    ny = max(0, min(max(0, h - 1), int(y) + int(dy)))
    with _virtual_cursor_lock:
        _virtual_cursor[token] = (nx, ny, w, h)


async def _apply_pointer_move(websocket: WebSocket, token: str, dx: int, dy: int) -> None:
    """Dispatch relative pointer movement with platform fallback and diagnostics."""
    mx = int(dx)
    my = int(dy)
    if not (mx or my):
        return

    moved = False
    try:
        moved = bool(INPUT_BACKEND.move_rel(mx, my))
    except Exception:
        moved = False
    if (not moved) and _IS_WINDOWS:
        moved = _windows_force_move_rel(mx, my)
    if not moved:
        if _warn_windows_input_block_once(token):
            try:
                await _send_json(
                    websocket,
                    token,
                    {"type": "warning", "code": "windows_input_blocked_or_elevated_window"},
                )
            except Exception:
                pass
    _move_virtual_cursor(token, mx, my)


async def _cursor_stream(websocket: WebSocket, token: str):
    """Continuously push cursor updates over websocket when position changes."""
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
                await _send_json(websocket, token, {"type": "cursor", "x": pos[0], "y": pos[1], "w": pos[2], "h": pos[3]})
                last_pos = pos
        except asyncio.CancelledError:
            break
        except Exception:
            break
        await asyncio.sleep(min_dt)


@router.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket, token: Optional[str] = Query(None)):
    """Serve authenticated WebSocket events for remote input control."""
    allow_query_token = bool(getattr(config, "ALLOW_QUERY_TOKEN", True))
    auth_header = str(websocket.headers.get("authorization") or "").strip()
    bearer = ""
    if auth_header.lower().startswith("bearer "):
        bearer = auth_header[7:].strip()
    ws_qs_token = str(websocket.query_params.get("token") or "").strip() if allow_query_token else ""
    q_token = str(token or "").strip() if allow_query_token else ""
    resolved_token = q_token or ws_qs_token or bearer

    if not resolved_token or not device_manager.get_session(resolved_token):
        await websocket.close(code=4003)
        return
    token = resolved_token

    if not (get_perm(token, "perm_mouse") or get_perm(token, "perm_keyboard")):
        await websocket.close(code=4003)
        return
    await websocket.accept()
    device_manager.register_socket(token, websocket)
    try:
        s_evt = device_manager.get_session(token, include_pending=True)
        if s_evt is not None:
            local_events.emit(
                "device_connected",
                title="CyberDeck",
                message=f"Device connected: {getattr(s_evt, 'device_name', 'Unknown')}",
                payload={
                    "token": token,
                    "device_id": getattr(s_evt, "device_id", ""),
                    "name": getattr(s_evt, "device_name", ""),
                    "ip": getattr(s_evt, "ip", ""),
                },
            )
    except Exception:
        pass
    _ws_diag_init(token)
    if _ws_log_enabled():
        cli_ip = getattr(getattr(websocket, "client", None), "host", None)
        ua = str(websocket.headers.get("user-agent") or "").strip()
        if len(ua) > 120:
            ua = ua[:120] + "..."
        log.info("WS connected: token=%s ip=%s ua=%s", token, cli_ip, ua or "-")
    hb_interval_s = max(5, int(getattr(config, "WS_HEARTBEAT_INTERVAL_S", 15) or 15))
    hb_timeout_s = max(hb_interval_s * 2, int(getattr(config, "WS_HEARTBEAT_TIMEOUT_S", 45) or 45))
    proto_push_enabled = _env_bool("CYBERDECK_WS_PROTO_PUSH", False)
    heartbeat_required = False
    input_lock_warned = False
    last_rx_monotonic = time.monotonic()

    async def _heartbeat_loop():
        """Emit ping frames and close stale sessions when heartbeat acknowledgements stop arriving."""
        nonlocal last_rx_monotonic
        while True:
            await asyncio.sleep(hb_interval_s)
            if not (proto_push_enabled or heartbeat_required):
                continue
            now_ms = int(time.time() * 1000)
            try:
                await _send_json(websocket, token, {"type": "ping", "id": str(now_ms), "ts": now_ms})
            except Exception:
                break
            if heartbeat_required and (time.monotonic() - last_rx_monotonic) > hb_timeout_s:
                try:
                    await websocket.close(code=1001)
                except Exception:
                    pass
                break

    if proto_push_enabled:
        try:
            await _send_json(websocket, token, build_server_hello("hello", hb_interval_s, hb_timeout_s))
        except Exception:
            pass

    if (not INPUT_BACKEND.can_pointer or not INPUT_BACKEND.can_keyboard) and (
        get_perm(token, "perm_mouse") or get_perm(token, "perm_keyboard")
    ):
        try:
            await _send_json(
                websocket,
                token,
                {"type": "warning", "code": "wayland_input_limited" if _IS_WAYLAND else "input_backend_limited"}
            )
        except Exception:
            pass
    if not INPUT_BACKEND.can_pointer and not INPUT_BACKEND.can_keyboard:
        try:
            await _send_json(websocket, token, {"type": "error", "code": "input_backend_unavailable"})
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
    heartbeat_task: Optional[asyncio.Task] = asyncio.create_task(_heartbeat_loop()) if proto_push_enabled else None
    try:
        while True:
            data = await websocket.receive_json()
            last_rx_monotonic = time.monotonic()
            t = (data.get("type") or "").lower()
            _ws_diag_mark_rx(token, t)
            event_id = str(data.get("event_id") or data.get("id") or "").strip()
            if event_id and t not in ("hello", "ping", "pong"):
                is_new = _track_event_id(token, event_id)
                try:
                    await _send_json(
                        websocket,
                        token,
                        {"type": "ack", "event_id": event_id, "accepted": bool(is_new), "ts": int(time.time() * 1000)},
                    )
                except Exception:
                    pass
                if not is_new:
                    continue

            if t == "hello":
                caps = data.get("capabilities") or {}
                if not isinstance(caps, dict):
                    caps = {}
                heartbeat_required = bool(caps.get("heartbeat_ack") or caps.get("ws_heartbeat_ack"))
                _ws_diag_set(
                    token,
                    heartbeat_required=heartbeat_required,
                    client_protocol_version=data.get("protocol_version"),
                )
                if _ws_log_enabled():
                    log.info(
                        "WS hello: token=%s protocol_version=%s heartbeat_required=%s caps=%s",
                        token,
                        data.get("protocol_version"),
                        heartbeat_required,
                        list(caps.keys()),
                    )
                if heartbeat_task is None and heartbeat_required:
                    heartbeat_task = asyncio.create_task(_heartbeat_loop())
                try:
                    await _send_json(
                        websocket,
                        token,
                        {
                            "type": "hello_ack",
                            "heartbeat_required": heartbeat_required,
                            "heartbeat_interval_ms": int(hb_interval_s * 1000),
                            "heartbeat_timeout_ms": int(hb_timeout_s * 1000),
                            **protocol_payload(),
                        },
                    )
                except Exception:
                    pass
                if not proto_push_enabled:
                    try:
                        await _send_json(websocket, token, build_server_hello("hello", hb_interval_s, hb_timeout_s))
                    except Exception:
                        pass
                continue

            if t == "ping":
                try:
                    await _send_json(
                        websocket,
                        token,
                        {"type": "pong", "id": data.get("id"), "ts": int(time.time() * 1000)},
                    )
                except Exception:
                    pass
                continue

            if t == "pong":
                continue

            if input_guard.is_locked():
                if not input_lock_warned:
                    input_lock_warned = True
                    try:
                        await _send_json(websocket, token, {"type": "warning", "code": "remote_input_locked"})
                    except Exception:
                        pass
                continue

            if t == "move":
                if not get_perm(token, "perm_mouse"):
                    continue
                try:
                    dx = float(data.get("dx", 0) or 0)
                    dy = float(data.get("dy", 0) or 0)
                except Exception:
                    dx, dy = 0.0, 0.0

                now_move = time.monotonic()
                with _mouse_remainders_lock:
                    last_ts = _mouse_last_move_ts.get(token)
                    _mouse_last_move_ts[token] = now_move
                    lag_scale = 1.0
                    if _IS_WAYLAND and last_ts is not None:
                        dt = max(0.0, now_move - float(last_ts))
                        if dt > _MOUSE_LAG_DAMP_START_S:
                            lag_scale = max(
                                _MOUSE_LAG_DAMP_MIN,
                                min(1.0, _MOUSE_LAG_DAMP_START_S / max(0.001, dt)),
                            )
                    dx *= _MOUSE_GAIN * lag_scale
                    dy *= _MOUSE_GAIN * lag_scale
                    if abs(dx) < _MOUSE_DEADZONE:
                        dx = 0.0
                    if abs(dy) < _MOUSE_DEADZONE:
                        dy = 0.0
                    rx, ry = _mouse_remainders.get(token, (0.0, 0.0))
                    dx += rx
                    dy += ry
                    mx_raw = int(round(dx))
                    my_raw = int(round(dy))
                    mx = mx_raw
                    my = my_raw
                    if mx > _MOUSE_MAX_DELTA:
                        mx = _MOUSE_MAX_DELTA
                    elif mx < -_MOUSE_MAX_DELTA:
                        mx = -_MOUSE_MAX_DELTA
                    if my > _MOUSE_MAX_DELTA:
                        my = _MOUSE_MAX_DELTA
                    elif my < -_MOUSE_MAX_DELTA:
                        my = -_MOUSE_MAX_DELTA
                    rem_x = dx - mx_raw
                    rem_y = dy - my_raw
                    # If clamped, drop overflow so cursor does not keep drifting.
                    if mx != mx_raw:
                        rem_x = 0.0
                    if my != my_raw:
                        rem_y = 0.0
                    _mouse_remainders[token] = (rem_x, rem_y)

                cur_x, cur_y, w, h = _get_virtual_cursor(token)
                tgt_x = max(0, min(max(0, int(w) - 1), int(cur_x) + int(mx)))
                tgt_y = max(0, min(max(0, int(h) - 1), int(cur_y) + int(my)))
                if await _should_block_pointer_input(
                    websocket,
                    token,
                    target_x=tgt_x,
                    target_y=tgt_y,
                ):
                    continue
                await _apply_pointer_move(websocket, token, mx, my)

            elif t == "move_abs":
                if not get_perm(token, "perm_mouse"):
                    continue
                try:
                    raw_x = float(data.get("x"))
                    raw_y = float(data.get("y"))
                except Exception:
                    continue
                if not math.isfinite(raw_x) or not math.isfinite(raw_y):
                    continue

                cur_x, cur_y, w, h = _get_virtual_cursor(token)
                max_x = max(0, int(w) - 1)
                max_y = max(0, int(h) - 1)
                normalized = 0.0 <= raw_x <= 1.0 and 0.0 <= raw_y <= 1.0
                if normalized:
                    target_x = int(round(raw_x * max_x))
                    target_y = int(round(raw_y * max_y))
                else:
                    target_x = int(round(raw_x))
                    target_y = int(round(raw_y))
                target_x = max(0, min(max_x, target_x))
                target_y = max(0, min(max_y, target_y))

                move_x = int(target_x - cur_x)
                move_y = int(target_y - cur_y)
                with _mouse_remainders_lock:
                    _mouse_remainders[token] = (0.0, 0.0)
                    _mouse_last_move_ts[token] = time.monotonic()
                if await _should_block_pointer_input(
                    websocket,
                    token,
                    target_x=target_x,
                    target_y=target_y,
                ):
                    continue
                await _apply_pointer_move(websocket, token, move_x, move_y)

            elif t == "click":
                if not get_perm(token, "perm_mouse"):
                    continue
                if await _should_block_pointer_input(websocket, token):
                    continue
                clicked = False
                try:
                    clicked = bool(INPUT_BACKEND.click("left"))
                except Exception:
                    clicked = False
                if (not clicked) and _IS_WINDOWS:
                    clicked = _windows_force_click("left")
                if not clicked:
                    if _warn_windows_input_block_once(token):
                        try:
                            await _send_json(
                                websocket,
                                token,
                                {"type": "warning", "code": "windows_input_blocked_or_elevated_window"},
                            )
                        except Exception:
                            pass

            elif t == "rclick":
                if not get_perm(token, "perm_mouse"):
                    continue
                if await _should_block_pointer_input(websocket, token):
                    continue
                clicked = False
                try:
                    clicked = bool(INPUT_BACKEND.click("right"))
                except Exception:
                    clicked = False
                if (not clicked) and _IS_WINDOWS:
                    clicked = _windows_force_click("right")
                if not clicked:
                    if _warn_windows_input_block_once(token):
                        try:
                            await _send_json(
                                websocket,
                                token,
                                {"type": "warning", "code": "windows_input_blocked_or_elevated_window"},
                            )
                        except Exception:
                            pass

            elif t == "dclick":
                if not get_perm(token, "perm_mouse"):
                    continue
                if await _should_block_pointer_input(websocket, token):
                    continue
                clicked = False
                try:
                    clicked = bool(INPUT_BACKEND.click("left", double=True))
                except Exception:
                    clicked = False
                if (not clicked) and _IS_WINDOWS:
                    clicked = _windows_force_click("left", double=True)
                if not clicked:
                    if _warn_windows_input_block_once(token):
                        try:
                            await _send_json(
                                websocket,
                                token,
                                {"type": "warning", "code": "windows_input_blocked_or_elevated_window"},
                            )
                        except Exception:
                            pass

            elif t == "scroll":
                if not get_perm(token, "perm_mouse"):
                    continue
                if await _should_block_pointer_input(websocket, token):
                    continue
                try:
                    dy = int(data.get("dy", 0))
                except Exception:
                    dy = 0
                scrolled = False
                try:
                    scrolled = bool(INPUT_BACKEND.scroll(dy))
                except Exception:
                    scrolled = False
                if (not scrolled) and _IS_WINDOWS:
                    scrolled = _windows_force_scroll(dy)
                if not scrolled:
                    if _warn_windows_input_block_once(token):
                        try:
                            await _send_json(
                                websocket,
                                token,
                                {"type": "warning", "code": "windows_input_blocked_or_elevated_window"},
                            )
                        except Exception:
                            pass

            elif t == "drag_s":
                if not get_perm(token, "perm_mouse"):
                    continue
                if await _should_block_pointer_input(websocket, token):
                    continue
                ok = False
                try:
                    ok = bool(INPUT_BACKEND.mouse_down("left"))
                except Exception:
                    ok = False
                if (not ok) and _IS_WINDOWS:
                    ok = _windows_force_button(True, "left")
                if not ok:
                    if _warn_windows_input_block_once(token):
                        try:
                            await _send_json(
                                websocket,
                                token,
                                {"type": "warning", "code": "windows_input_blocked_or_elevated_window"},
                            )
                        except Exception:
                            pass

            elif t == "drag_e":
                if not get_perm(token, "perm_mouse"):
                    continue
                if await _should_block_pointer_input(websocket, token):
                    continue
                ok = False
                try:
                    ok = bool(INPUT_BACKEND.mouse_up("left"))
                except Exception:
                    ok = False
                if (not ok) and _IS_WINDOWS:
                    ok = _windows_force_button(False, "left")
                if not ok:
                    if _warn_windows_input_block_once(token):
                        try:
                            await _send_json(
                                websocket,
                                token,
                                {"type": "warning", "code": "windows_input_blocked_or_elevated_window"},
                            )
                        except Exception:
                            pass

            elif is_text_event_type(t):
                if not get_perm(token, "perm_keyboard"):
                    continue
                if await _should_block_keyboard_input(websocket, token):
                    continue
                text = extract_text_payload(data)
                if text:
                    delivered = False
                    if _IS_WINDOWS:
                        try:
                            hwnd = ctypes.windll.user32.GetForegroundWindow()
                            if hwnd:
                                for char in text:
                                    ctypes.windll.user32.SendMessageW(hwnd, 0x0102, ord(char), 0)
                                delivered = True
                        except Exception:
                            pass
                    if not delivered:
                        try:
                            delivered = bool(INPUT_BACKEND.write_text(text))
                        except Exception:
                            delivered = False
                    if not delivered and sys.platform != "win32":
                        delivered = _inject_text_fallback(text)
                        if delivered and _ws_log_enabled():
                            log.info("WS text fallback used: token=%s len=%s", token, len(text))
                    if (not delivered) and (config.DEBUG or _ws_log_enabled()):
                        log.warning("WS text injection failed: token=%s len=%s", token, len(text))

            elif t == "key":
                if not get_perm(token, "perm_keyboard"):
                    continue
                if await _should_block_keyboard_input(websocket, token):
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
                if await _should_block_keyboard_input(websocket, token):
                    continue
                raw = data.get("keys") or []
                if isinstance(raw, list) and raw:
                    keys = _normalize_hotkey_keys([str(k) for k in raw])
                    sent = False
                    for variant in _hotkey_variants(keys):
                        try:
                            sent = bool(INPUT_BACKEND.hotkey(*variant))
                        except Exception:
                            sent = False
                        if sent:
                            break
                    if (not sent) and _ws_log_enabled():
                        log.warning("WS hotkey failed: token=%s keys=%s", token, keys)

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
                    try:
                        INPUT_BACKEND.press(key)
                    except Exception:
                        if _ws_log_enabled():
                            log.warning("WS media key failed: token=%s action=%s", token, act)

            elif t == "shortcut":
                if not get_perm(token, "perm_keyboard"):
                    continue
                if await _should_block_keyboard_input(websocket, token):
                    continue
                act = str(data.get("action", "")).lower()
                try:
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
                except Exception:
                    if _ws_log_enabled():
                        log.warning("WS shortcut failed: token=%s action=%s", token, act)
            elif t:
                if _ws_log_enabled():
                    log.info("WS unknown event: token=%s type=%s", token, t)

    except WebSocketDisconnect as e:
        try:
            if _ws_log_enabled():
                log.info("WS disconnect event: token=%s code=%s", token, getattr(e, "code", None))
        except Exception:
            pass
    except Exception:
        log.exception("WS error")
    finally:
        _ws_diag_close(token)
        if heartbeat_task:
            heartbeat_task.cancel()
        if cursor_task:
            cursor_task.cancel()
        device_manager.unregister_socket(token, websocket)
        try:
            with _mouse_remainders_lock:
                _mouse_remainders.pop(token, None)
                _mouse_last_move_ts.pop(token, None)
        except Exception:
            pass
        try:
            with _virtual_cursor_lock:
                _virtual_cursor.pop(token, None)
        except Exception:
            pass
        try:
            _windows_warned_input_block.discard(str(token or ""))
        except Exception:
            pass
        try:
            _windows_gui_block_warned.discard(str(token or ""))
        except Exception:
            pass
        try:
            with _ws_event_ids_lock:
                _ws_event_ids.pop(str(token or ""), None)
        except Exception:
            pass
        if _ws_log_enabled():
            log.info("WS disconnected: token=%s", token)





