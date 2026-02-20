"""Windows-focused input backend implementations."""

import ctypes
import os
from typing import Optional, Tuple

from .base import _BaseInputBackend
from ...logging_config import log

_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800
_SM_CXSCREEN = 0
_SM_CYSCREEN = 1
_WHEEL_DELTA = 120


class _PyAutoGuiBackend(_BaseInputBackend):
    """Implement input with `pyautogui` for desktop sessions with GUI access."""

    name = "pyautogui"
    can_pointer = True
    can_keyboard = True
    can_position = True
    can_screen_size = True

    def __init__(self) -> None:
        """Initialize backend state and lazy import sentinels."""
        self._pg = None
        self._loaded = False
        self._user32 = None
        self._win_loaded = False

    def _ensure(self) -> bool:
        """Lazy-load `pyautogui` once and report backend readiness."""
        if self._loaded:
            return self._pg is not None
        self._loaded = True
        try:
            import pyautogui  # noqa: PLC0415

            self._pg = pyautogui
            return True
        except Exception as error:
            log.warning("PyAutoGUI backend init failed: %s", error)
            self._pg = None
            return False

    def _ensure_winapi(self) -> bool:
        """Lazy-load WinAPI user32 bindings for robust pointer fallbacks."""
        if self._win_loaded:
            return self._user32 is not None
        self._win_loaded = True
        if os.name != "nt":
            return False
        try:
            self._user32 = ctypes.windll.user32
            return self._user32 is not None
        except Exception as error:
            log.warning("WinAPI mouse backend init failed: %s", error)
            self._user32 = None
            return False

    @staticmethod
    def _mouse_button_flags(button: str) -> tuple[int, int]:
        """Map logical button name to WinAPI down/up flags."""
        b = str(button or "left").lower()
        if b == "right":
            return (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP)
        if b == "middle":
            return (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP)
        return (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP)

    def _mouse_event(self, flags: int, data: int = 0) -> bool:
        """Dispatch a low-level mouse event through WinAPI."""
        if not self._ensure_winapi():
            return False
        try:
            self._user32.mouse_event(int(flags), 0, 0, int(data), 0)
            return True
        except Exception:
            return False

    def configure(self) -> None:
        """Disable failsafe/pause to keep remote input responsive."""
        if self._ensure():
            self._pg.FAILSAFE = False
            self._pg.PAUSE = 0
        self._ensure_winapi()

    def position(self) -> Optional[Tuple[int, int]]:
        """Return the current pointer position."""
        if self._ensure():
            try:
                x, y = self._pg.position()
                return int(x), int(y)
            except Exception:
                pass
        if not self._ensure_winapi():
            return None
        try:
            class _Point(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            pt = _Point()
            ok = self._user32.GetCursorPos(ctypes.byref(pt))
            if not ok:
                return None
            return int(pt.x), int(pt.y)
        except Exception:
            return None

    def screen_size(self) -> Optional[Tuple[int, int]]:
        """Return the active screen size in pixels."""
        if self._ensure():
            try:
                width, height = self._pg.size()
                return int(width), int(height)
            except Exception:
                pass
        if not self._ensure_winapi():
            return None
        try:
            width = int(self._user32.GetSystemMetrics(_SM_CXSCREEN))
            height = int(self._user32.GetSystemMetrics(_SM_CYSCREEN))
            if width <= 0 or height <= 0:
                return None
            return width, height
        except Exception:
            return None

    def move_rel(self, dx: int, dy: int) -> bool:
        """Move the pointer by relative delta."""
        if self._ensure():
            try:
                self._pg.moveRel(int(dx), int(dy), _pause=False)
                return True
            except Exception:
                pass
        if not self._ensure_winapi():
            return False
        pos = self.position()
        if not pos:
            return False
        try:
            return bool(self._user32.SetCursorPos(int(pos[0]) + int(dx), int(pos[1]) + int(dy)))
        except Exception:
            return False

    def click(self, button: str = "left", double: bool = False) -> bool:
        """Dispatch a mouse click through the active backend."""
        if self._ensure():
            try:
                if double:
                    if button == "left":
                        self._pg.doubleClick(_pause=False)
                    else:
                        self._pg.click(button=button, clicks=2, _pause=False)
                    return True
                self._pg.click(button=button, _pause=False)
                return True
            except Exception:
                pass

        down_flag, up_flag = self._mouse_button_flags(button)
        count = 2 if bool(double) else 1
        ok = True
        for _ in range(count):
            ok = self._mouse_event(down_flag) and self._mouse_event(up_flag) and ok
        return ok

    def scroll(self, dy: int) -> bool:
        """Dispatch a mouse scroll event through the active backend."""
        if self._ensure():
            try:
                self._pg.scroll(int(dy), _pause=False)
                return True
            except Exception:
                pass
        steps = int(dy)
        if steps == 0:
            return True
        return self._mouse_event(_MOUSEEVENTF_WHEEL, steps * _WHEEL_DELTA)

    def mouse_down(self, button: str = "left") -> bool:
        """Press and hold the requested mouse button."""
        if self._ensure():
            try:
                self._pg.mouseDown(button=button, _pause=False)
                return True
            except Exception:
                pass
        down_flag, _ = self._mouse_button_flags(button)
        return self._mouse_event(down_flag)

    def mouse_up(self, button: str = "left") -> bool:
        """Release the requested mouse button."""
        if self._ensure():
            try:
                self._pg.mouseUp(button=button, _pause=False)
                return True
            except Exception:
                pass
        _, up_flag = self._mouse_button_flags(button)
        return self._mouse_event(up_flag)

    def write_text(self, text: str) -> bool:
        """Type text using the active input backend."""
        if not self._ensure():
            return False
        self._pg.write(text, interval=0, _pause=False)
        return True

    def press(self, key: str) -> bool:
        """Send a single key press through the active backend."""
        if not self._ensure():
            return False
        self._pg.press(key, _pause=False)
        return True

    def hotkey(self, *keys: str) -> bool:
        """Send a key combination through the active backend."""
        if not self._ensure():
            return False
        self._pg.hotkey(*keys, _pause=False)
        return True
