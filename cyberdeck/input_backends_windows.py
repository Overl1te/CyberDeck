"""Windows-focused input backend implementations."""

from typing import Optional, Tuple

from .input_backends_base import _BaseInputBackend
from .logging_config import log


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

    def configure(self) -> None:
        """Disable failsafe/pause to keep remote input responsive."""
        if not self._ensure():
            return
        self._pg.FAILSAFE = False
        self._pg.PAUSE = 0

    def position(self) -> Optional[Tuple[int, int]]:
        """Return the current pointer position."""
        if not self._ensure():
            return None
        x, y = self._pg.position()
        return int(x), int(y)

    def screen_size(self) -> Optional[Tuple[int, int]]:
        """Return the active screen size in pixels."""
        if not self._ensure():
            return None
        width, height = self._pg.size()
        return int(width), int(height)

    def move_rel(self, dx: int, dy: int) -> bool:
        """Move the pointer by relative delta."""
        if not self._ensure():
            return False
        self._pg.moveRel(int(dx), int(dy), _pause=False)
        return True

    def click(self, button: str = "left", double: bool = False) -> bool:
        """Dispatch a mouse click through the active backend."""
        if not self._ensure():
            return False
        if double:
            if button == "left":
                self._pg.doubleClick(_pause=False)
            else:
                self._pg.click(button=button, clicks=2, _pause=False)
            return True
        self._pg.click(button=button, _pause=False)
        return True

    def scroll(self, dy: int) -> bool:
        """Dispatch a mouse scroll event through the active backend."""
        if not self._ensure():
            return False
        self._pg.scroll(int(dy), _pause=False)
        return True

    def mouse_down(self, button: str = "left") -> bool:
        """Press and hold the requested mouse button."""
        if not self._ensure():
            return False
        self._pg.mouseDown(button=button, _pause=False)
        return True

    def mouse_up(self, button: str = "left") -> bool:
        """Release the requested mouse button."""
        if not self._ensure():
            return False
        self._pg.mouseUp(button=button, _pause=False)
        return True

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

