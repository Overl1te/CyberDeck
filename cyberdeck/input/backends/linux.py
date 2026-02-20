"""Linux-focused input backend implementations (X11 and Wayland)."""

import shutil
import subprocess
from typing import Optional, Tuple

from .base import _BaseInputBackend
from ...logging_config import log


class _X11Backend(_BaseInputBackend):
    """Implement input through pynput for X11 sessions."""

    name = "linux_x11_pynput"
    can_pointer = True
    can_keyboard = True
    can_position = True
    can_screen_size = True

    def __init__(self) -> None:
        """Initialize backend state and lazy import sentinels."""
        self._mouse = None
        self._keyboard = None
        self._button = None
        self._key = None
        self._loaded = False

    def _ensure(self) -> bool:
        """Lazy-load `pynput` once and report backend readiness."""
        if self._loaded:
            return self._mouse is not None and self._keyboard is not None
        self._loaded = True
        try:
            from pynput import keyboard, mouse

            self._mouse = mouse.Controller()
            self._keyboard = keyboard.Controller()
            self._button = mouse.Button
            self._key = keyboard.Key
            return True
        except Exception as error:
            log.warning("X11 backend init failed (pynput): %s", error)
            self._mouse = None
            self._keyboard = None
            return False

    def _key_obj(self, key: str):
        """Resolve a pynput key object from a key descriptor."""
        key = str(key or "").strip().lower()
        key_map = {
            "enter": "enter",
            "backspace": "backspace",
            "space": "space",
            "winleft": "cmd",
            "win": "cmd",
            "playpause": "media_play_pause",
            "nexttrack": "media_next",
            "prevtrack": "media_previous",
            "stop": "media_stop",
            "volumemute": "media_volume_mute",
            "volumeup": "media_volume_up",
            "volumedown": "media_volume_down",
            "ctrl": "ctrl",
            "alt": "alt",
            "shift": "shift",
            "tab": "tab",
            "esc": "esc",
            "delete": "delete",
            "home": "home",
            "end": "end",
            "pageup": "page_up",
            "pagedown": "page_down",
            "up": "up",
            "down": "down",
            "left": "left",
            "right": "right",
        }
        if not self._key:
            return key
        named = key_map.get(key)
        if named and hasattr(self._key, named):
            return getattr(self._key, named)
        if len(key) == 1:
            return key
        return key

    def position(self) -> Optional[Tuple[int, int]]:
        """Return the current pointer position."""
        if not self._ensure():
            return None
        pos = self._mouse.position
        return int(pos[0]), int(pos[1])

    def screen_size(self) -> Optional[Tuple[int, int]]:
        """Return the active screen size in pixels."""
        try:
            out = subprocess.run(
                ["xrandr", "--current"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                text=True,
                timeout=1.0,
            )
            for line in (out.stdout or "").splitlines():
                if " current " in line:
                    part = line.split(" current ", 1)[1].split(",", 1)[0].strip()
                    w_s, h_s = part.split(" x ", 1)
                    return int(w_s), int(h_s)
        except Exception:
            pass
        return None

    def move_rel(self, dx: int, dy: int) -> bool:
        """Move the pointer by relative delta."""
        if not self._ensure():
            return False
        x, y = self._mouse.position
        self._mouse.position = (int(x) + int(dx), int(y) + int(dy))
        return True

    def click(self, button: str = "left", double: bool = False) -> bool:
        """Dispatch a mouse click through the active backend."""
        if not self._ensure():
            return False
        btn = self._button.left if button != "right" else self._button.right
        cnt = 2 if double else 1
        self._mouse.click(btn, cnt)
        return True

    def scroll(self, dy: int) -> bool:
        """Dispatch a mouse scroll event through the active backend."""
        if not self._ensure():
            return False
        self._mouse.scroll(0, int(dy))
        return True

    def mouse_down(self, button: str = "left") -> bool:
        """Press and hold the requested mouse button."""
        if not self._ensure():
            return False
        btn = self._button.left if button != "right" else self._button.right
        self._mouse.press(btn)
        return True

    def mouse_up(self, button: str = "left") -> bool:
        """Release the requested mouse button."""
        if not self._ensure():
            return False
        btn = self._button.left if button != "right" else self._button.right
        self._mouse.release(btn)
        return True

    def write_text(self, text: str) -> bool:
        """Type text using the active input backend."""
        if not self._ensure():
            return False
        self._keyboard.type(str(text))
        return True

    def press(self, key: str) -> bool:
        """Send a single key press through the active backend."""
        if not self._ensure():
            return False
        key_obj = self._key_obj(key)
        self._keyboard.press(key_obj)
        self._keyboard.release(key_obj)
        return True

    def hotkey(self, *keys: str) -> bool:
        """Send a key combination through the active backend."""
        if not self._ensure():
            return False
        seq = [self._key_obj(k) for k in keys if str(k).strip()]
        if not seq:
            return False
        try:
            for key_obj in seq:
                self._keyboard.press(key_obj)
            return True
        finally:
            for key_obj in reversed(seq):
                try:
                    self._keyboard.release(key_obj)
                except Exception:
                    pass


class _WaylandBackend(_BaseInputBackend):
    """Implement input through evdev virtual devices for Wayland sessions."""

    name = "linux_wayland_evdev"
    can_pointer = True
    can_keyboard = True
    can_position = False
    can_screen_size = False

    def __init__(self) -> None:
        """Initialize backend state and lazy import sentinels."""
        self._loaded = False
        self._ui_mouse = None
        self._ui_keyboard = None
        self._e = None

    def _ensure(self) -> bool:
        """Lazy-load `evdev` and virtual input devices once."""
        if self._loaded:
            return self._ui_mouse is not None and self._ui_keyboard is not None
        self._loaded = True
        try:
            from evdev import UInput, ecodes as e

            key_codes = [
                e.KEY_ENTER,
                e.KEY_BACKSPACE,
                e.KEY_SPACE,
                e.KEY_LEFTCTRL,
                e.KEY_RIGHTCTRL,
                e.KEY_LEFTALT,
                e.KEY_RIGHTALT,
                e.KEY_LEFTSHIFT,
                e.KEY_RIGHTSHIFT,
                e.KEY_LEFTMETA,
                e.KEY_RIGHTMETA,
                e.KEY_TAB,
                e.KEY_ESC,
                e.KEY_DELETE,
                e.KEY_HOME,
                e.KEY_END,
                e.KEY_PAGEUP,
                e.KEY_PAGEDOWN,
                e.KEY_UP,
                e.KEY_DOWN,
                e.KEY_LEFT,
                e.KEY_RIGHT,
                e.KEY_C,
                e.KEY_V,
                e.KEY_X,
                e.KEY_Z,
                e.KEY_Y,
                e.KEY_A,
                e.KEY_B,
                e.KEY_D,
                e.KEY_E,
                e.KEY_F,
                e.KEY_G,
                e.KEY_H,
                e.KEY_I,
                e.KEY_J,
                e.KEY_K,
                e.KEY_L,
                e.KEY_M,
                e.KEY_N,
                e.KEY_O,
                e.KEY_P,
                e.KEY_Q,
                e.KEY_R,
                e.KEY_S,
                e.KEY_T,
                e.KEY_U,
                e.KEY_W,
                e.KEY_0,
                e.KEY_1,
                e.KEY_2,
                e.KEY_3,
                e.KEY_4,
                e.KEY_5,
                e.KEY_6,
                e.KEY_7,
                e.KEY_8,
                e.KEY_9,
                e.KEY_MINUS,
                e.KEY_EQUAL,
                e.KEY_LEFTBRACE,
                e.KEY_RIGHTBRACE,
                e.KEY_SEMICOLON,
                e.KEY_APOSTROPHE,
                e.KEY_GRAVE,
                e.KEY_BACKSLASH,
                e.KEY_COMMA,
                e.KEY_DOT,
                e.KEY_SLASH,
                e.KEY_PLAYPAUSE,
                e.KEY_NEXTSONG,
                e.KEY_PREVIOUSSONG,
                e.KEY_STOPCD,
                e.KEY_MUTE,
                e.KEY_VOLUMEUP,
                e.KEY_VOLUMEDOWN,
            ]

            mouse_events = {
                e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
                e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL],
            }
            pointer_props = [e.INPUT_PROP_POINTER] if hasattr(e, "INPUT_PROP_POINTER") else None
            try:
                self._ui_mouse = UInput(
                    events=mouse_events,
                    name="CyberDeck Virtual Mouse",
                    input_props=pointer_props,
                )
            except TypeError:
                # Older python-evdev builds may not expose input_props in UInput.
                self._ui_mouse = UInput(events=mouse_events, name="CyberDeck Virtual Mouse")

            self._ui_keyboard = UInput(events={e.EV_KEY: key_codes}, name="CyberDeck Virtual Keyboard")
            self._e = e
            return True
        except Exception as error:
            log.warning("Wayland backend init failed (evdev): %s", error)
            self._ui_mouse = None
            self._ui_keyboard = None
            self._e = None
            return False

    def _tap(self, code: int, *, mouse: bool = False) -> bool:
        """Send a single tap event for the given key code."""
        if not self._ensure():
            return False
        ui = self._ui_mouse if mouse else self._ui_keyboard
        if ui is None:
            return False
        ui.write(self._e.EV_KEY, code, 1)
        ui.write(self._e.EV_KEY, code, 0)
        ui.syn()
        return True

    def _key_code(self, key: str) -> Optional[int]:
        """Map logical key names to wl-virtual-input key codes."""
        key = str(key or "").strip().lower()
        if not self._ensure():
            return None
        e = self._e
        key_map = {
            "enter": e.KEY_ENTER,
            "backspace": e.KEY_BACKSPACE,
            "space": e.KEY_SPACE,
            "win": e.KEY_LEFTMETA,
            "winleft": e.KEY_LEFTMETA,
            "ctrl": e.KEY_LEFTCTRL,
            "alt": e.KEY_LEFTALT,
            "shift": e.KEY_LEFTSHIFT,
            "tab": e.KEY_TAB,
            "esc": e.KEY_ESC,
            "delete": e.KEY_DELETE,
            "home": e.KEY_HOME,
            "end": e.KEY_END,
            "pageup": e.KEY_PAGEUP,
            "pagedown": e.KEY_PAGEDOWN,
            "up": e.KEY_UP,
            "down": e.KEY_DOWN,
            "left": e.KEY_LEFT,
            "right": e.KEY_RIGHT,
            "playpause": e.KEY_PLAYPAUSE,
            "nexttrack": e.KEY_NEXTSONG,
            "prevtrack": e.KEY_PREVIOUSSONG,
            "stop": e.KEY_STOPCD,
            "volumemute": e.KEY_MUTE,
            "volumeup": e.KEY_VOLUMEUP,
            "volumedown": e.KEY_VOLUMEDOWN,
        }
        if key in key_map:
            return key_map[key]
        if len(key) == 1:
            ch = key
            if "a" <= ch <= "z":
                return getattr(e, f"KEY_{ch.upper()}", None)
            if "0" <= ch <= "9":
                return getattr(e, f"KEY_{ch}", None)
            symbols = {
                "\n": e.KEY_ENTER,
                "\r": e.KEY_ENTER,
                "\t": e.KEY_TAB,
                "-": e.KEY_MINUS,
                "=": e.KEY_EQUAL,
                "[": e.KEY_LEFTBRACE,
                "]": e.KEY_RIGHTBRACE,
                ";": e.KEY_SEMICOLON,
                "'": e.KEY_APOSTROPHE,
                "`": e.KEY_GRAVE,
                "\\": e.KEY_BACKSLASH,
                ",": e.KEY_COMMA,
                ".": e.KEY_DOT,
                "/": e.KEY_SLASH,
                " ": e.KEY_SPACE,
            }
            return symbols.get(ch)
        return None

    def _write_text_wtype(self, text: str) -> bool:
        """Type text using wtype with shell-safe quoting."""
        cmd = shutil.which("wtype")
        if not cmd:
            return False
        payload = str(text or "")
        if not payload:
            return True
        try:
            proc = subprocess.run(
                [cmd, "--", payload],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(2.0, min(8.0, 0.04 * len(payload))),
                check=False,
            )
            return int(proc.returncode) == 0
        except Exception:
            return False

    def move_rel(self, dx: int, dy: int) -> bool:
        """Move the pointer by relative delta."""
        if not self._ensure():
            return False
        ui = self._ui_mouse
        if ui is None:
            return False
        mx = int(dx)
        my = int(dy)
        if not (mx or my):
            return True
        ui.write(self._e.EV_REL, self._e.REL_X, mx)
        ui.write(self._e.EV_REL, self._e.REL_Y, my)
        ui.syn()
        return True

    def click(self, button: str = "left", double: bool = False) -> bool:
        """Dispatch a mouse click through the active backend."""
        if not self._ensure():
            return False
        code = self._e.BTN_LEFT if button != "right" else self._e.BTN_RIGHT
        count = 2 if double else 1
        for _ in range(count):
            self._tap(code, mouse=True)
        return True

    def scroll(self, dy: int) -> bool:
        """Dispatch a mouse scroll event through the active backend."""
        if not self._ensure():
            return False
        ui = self._ui_mouse
        if ui is None:
            return False
        val = int(dy)
        if val == 0:
            return True
        ui.write(self._e.EV_REL, self._e.REL_WHEEL, val)
        ui.syn()
        return True

    def mouse_down(self, button: str = "left") -> bool:
        """Press and hold the requested mouse button."""
        if not self._ensure():
            return False
        ui = self._ui_mouse
        if ui is None:
            return False
        code = self._e.BTN_LEFT if button != "right" else self._e.BTN_RIGHT
        ui.write(self._e.EV_KEY, code, 1)
        ui.syn()
        return True

    def mouse_up(self, button: str = "left") -> bool:
        """Release the requested mouse button."""
        if not self._ensure():
            return False
        ui = self._ui_mouse
        if ui is None:
            return False
        code = self._e.BTN_LEFT if button != "right" else self._e.BTN_RIGHT
        ui.write(self._e.EV_KEY, code, 0)
        ui.syn()
        return True

    def write_text(self, text: str) -> bool:
        """Type text using the active input backend."""
        payload = str(text or "")
        if not payload:
            return True

        if self._write_text_wtype(payload):
            return True

        if not self._ensure():
            return False
        ui = self._ui_keyboard
        if ui is None:
            return False
        seq = []
        for ch in payload:
            need_shift = ch.isupper()
            base = ch.lower() if need_shift else ch
            code = self._key_code(base)
            if code is None:
                return False
            seq.append((code, need_shift))

        for code, need_shift in seq:
            if need_shift:
                ui.write(self._e.EV_KEY, self._e.KEY_LEFTSHIFT, 1)
            ui.write(self._e.EV_KEY, code, 1)
            ui.write(self._e.EV_KEY, code, 0)
            if need_shift:
                ui.write(self._e.EV_KEY, self._e.KEY_LEFTSHIFT, 0)
            ui.syn()
        return True

    def press(self, key: str) -> bool:
        """Send a single key press through the active backend."""
        code = self._key_code(key)
        if code is None:
            return False
        return self._tap(code, mouse=False)

    def hotkey(self, *keys: str) -> bool:
        """Send a key combination through the active backend."""
        if not self._ensure():
            return False
        ui = self._ui_keyboard
        if ui is None:
            return False
        seq = [self._key_code(k) for k in keys if str(k).strip()]
        seq = [x for x in seq if x is not None]
        if not seq:
            return False
        for code in seq:
            ui.write(self._e.EV_KEY, code, 1)
        ui.syn()
        for code in reversed(seq):
            ui.write(self._e.EV_KEY, code, 0)
        ui.syn()
        return True
