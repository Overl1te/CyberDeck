"""Shared base contracts and helpers for platform-specific input backends."""

import os
from typing import Optional, Tuple


def _session_kind() -> str:
    """Detect the active desktop session kind."""
    if os.name == "nt":
        return "windows"
    xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    if xdg_type in ("wayland", "x11"):
        return xdg_type
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


class _BaseInputBackend:
    """Define the minimal input backend contract consumed by API and WS layers."""

    name = "base"
    can_pointer = False
    can_keyboard = False
    can_position = False
    can_screen_size = False

    def configure(self) -> None:
        """Configure the target operation."""
        pass

    def position(self) -> Optional[Tuple[int, int]]:
        """Return the current pointer position."""
        return None

    def screen_size(self) -> Optional[Tuple[int, int]]:
        """Return the active screen size in pixels."""
        return None

    def move_rel(self, dx: int, dy: int) -> bool:
        """Move the pointer by relative delta."""
        return False

    def click(self, button: str = "left", double: bool = False) -> bool:
        """Dispatch a mouse click through the active backend."""
        return False

    def scroll(self, dy: int) -> bool:
        """Dispatch a mouse scroll event through the active backend."""
        return False

    def mouse_down(self, button: str = "left") -> bool:
        """Press and hold the requested mouse button."""
        return False

    def mouse_up(self, button: str = "left") -> bool:
        """Release the requested mouse button."""
        return False

    def write_text(self, text: str) -> bool:
        """Type text using the active input backend."""
        return False

    def press(self, key: str) -> bool:
        """Send a single key press through the active backend."""
        return False

    def hotkey(self, *keys: str) -> bool:
        """Send a key combination through the active backend."""
        return False


class _NullBackend(_BaseInputBackend):
    """Represent a fully unavailable backend."""

    name = "null"

