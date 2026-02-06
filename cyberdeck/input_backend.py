import os
import subprocess
from typing import Optional, Tuple

from .logging_config import log


def _session_kind() -> str:
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
    name = "base"
    can_pointer = False
    can_keyboard = False
    can_position = False
    can_screen_size = False

    def configure(self) -> None:
        pass

    def position(self) -> Optional[Tuple[int, int]]:
        return None

    def screen_size(self) -> Optional[Tuple[int, int]]:
        return None

    def move_rel(self, dx: int, dy: int) -> bool:
        return False

    def click(self, button: str = "left", double: bool = False) -> bool:
        return False

    def scroll(self, dy: int) -> bool:
        return False

    def mouse_down(self, button: str = "left") -> bool:
        return False

    def mouse_up(self, button: str = "left") -> bool:
        return False

    def write_text(self, text: str) -> bool:
        return False

    def press(self, key: str) -> bool:
        return False

    def hotkey(self, *keys: str) -> bool:
        return False


class _NullBackend(_BaseInputBackend):
    name = "null"


class _PyAutoGuiBackend(_BaseInputBackend):
    name = "pyautogui"
    can_pointer = True
    can_keyboard = True
    can_position = True
    can_screen_size = True

    def __init__(self):
        self._pg = None
        self._loaded = False

    def _ensure(self) -> bool:
        if self._loaded:
            return self._pg is not None
        self._loaded = True
        try:
            import pyautogui  # noqa: PLC0415

            self._pg = pyautogui
            return True
        except Exception as e:
            log.warning("PyAutoGUI backend init failed: %s", e)
            self._pg = None
            return False

    def configure(self) -> None:
        if not self._ensure():
            return
        self._pg.FAILSAFE = False
        self._pg.PAUSE = 0

    def position(self) -> Optional[Tuple[int, int]]:
        if not self._ensure():
            return None
        x, y = self._pg.position()
        return int(x), int(y)

    def screen_size(self) -> Optional[Tuple[int, int]]:
        if not self._ensure():
            return None
        w, h = self._pg.size()
        return int(w), int(h)

    def move_rel(self, dx: int, dy: int) -> bool:
        if not self._ensure():
            return False
        self._pg.moveRel(int(dx), int(dy), _pause=False)
        return True

    def click(self, button: str = "left", double: bool = False) -> bool:
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
        if not self._ensure():
            return False
        self._pg.scroll(int(dy), _pause=False)
        return True

    def mouse_down(self, button: str = "left") -> bool:
        if not self._ensure():
            return False
        self._pg.mouseDown(button=button, _pause=False)
        return True

    def mouse_up(self, button: str = "left") -> bool:
        if not self._ensure():
            return False
        self._pg.mouseUp(button=button, _pause=False)
        return True

    def write_text(self, text: str) -> bool:
        if not self._ensure():
            return False
        self._pg.write(text, interval=0, _pause=False)
        return True

    def press(self, key: str) -> bool:
        if not self._ensure():
            return False
        self._pg.press(key, _pause=False)
        return True

    def hotkey(self, *keys: str) -> bool:
        if not self._ensure():
            return False
        self._pg.hotkey(*keys, _pause=False)
        return True


class _X11Backend(_BaseInputBackend):
    name = "linux_x11_pynput"
    can_pointer = True
    can_keyboard = True
    can_position = True
    can_screen_size = True

    def __init__(self):
        self._mouse = None
        self._keyboard = None
        self._button = None
        self._key = None
        self._loaded = False

    def _ensure(self) -> bool:
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
        except Exception as e:
            log.warning("X11 backend init failed (pynput): %s", e)
            self._mouse = None
            self._keyboard = None
            return False

    def _key_obj(self, key: str):
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
        if not self._ensure():
            return None
        pos = self._mouse.position
        return int(pos[0]), int(pos[1])

    def screen_size(self) -> Optional[Tuple[int, int]]:
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
        if not self._ensure():
            return False
        x, y = self._mouse.position
        self._mouse.position = (int(x) + int(dx), int(y) + int(dy))
        return True

    def click(self, button: str = "left", double: bool = False) -> bool:
        if not self._ensure():
            return False
        btn = self._button.left if button != "right" else self._button.right
        cnt = 2 if double else 1
        self._mouse.click(btn, cnt)
        return True

    def scroll(self, dy: int) -> bool:
        if not self._ensure():
            return False
        self._mouse.scroll(0, int(dy))
        return True

    def mouse_down(self, button: str = "left") -> bool:
        if not self._ensure():
            return False
        btn = self._button.left if button != "right" else self._button.right
        self._mouse.press(btn)
        return True

    def mouse_up(self, button: str = "left") -> bool:
        if not self._ensure():
            return False
        btn = self._button.left if button != "right" else self._button.right
        self._mouse.release(btn)
        return True

    def write_text(self, text: str) -> bool:
        if not self._ensure():
            return False
        self._keyboard.type(str(text))
        return True

    def press(self, key: str) -> bool:
        if not self._ensure():
            return False
        key_obj = self._key_obj(key)
        self._keyboard.press(key_obj)
        self._keyboard.release(key_obj)
        return True

    def hotkey(self, *keys: str) -> bool:
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
    name = "linux_wayland_evdev"
    can_pointer = True
    can_keyboard = True
    can_position = False
    can_screen_size = False

    def __init__(self):
        self._loaded = False
        self._ui_mouse = None
        self._ui_keyboard = None
        self._e = None

    def _ensure(self) -> bool:
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
        except Exception as e:
            log.warning("Wayland backend init failed (evdev): %s", e)
            self._ui_mouse = None
            self._ui_keyboard = None
            self._e = None
            return False

    def _tap(self, code: int, *, mouse: bool = False) -> bool:
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

    def move_rel(self, dx: int, dy: int) -> bool:
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
        if not self._ensure():
            return False
        code = self._e.BTN_LEFT if button != "right" else self._e.BTN_RIGHT
        count = 2 if double else 1
        for _ in range(count):
            self._tap(code, mouse=True)
        return True

    def scroll(self, dy: int) -> bool:
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
        if not self._ensure():
            return False
        ui = self._ui_keyboard
        if ui is None:
            return False
        for ch in str(text):
            need_shift = ch.isupper()
            base = ch.lower() if need_shift else ch
            code = self._key_code(base)
            if code is None:
                continue
            if need_shift:
                ui.write(self._e.EV_KEY, self._e.KEY_LEFTSHIFT, 1)
            ui.write(self._e.EV_KEY, code, 1)
            ui.write(self._e.EV_KEY, code, 0)
            if need_shift:
                ui.write(self._e.EV_KEY, self._e.KEY_LEFTSHIFT, 0)
            ui.syn()
        return True

    def press(self, key: str) -> bool:
        code = self._key_code(key)
        if code is None:
            return False
        return self._tap(code, mouse=False)

    def hotkey(self, *keys: str) -> bool:
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


def _build_backend() -> _BaseInputBackend:
    kind = _session_kind()
    if kind == "windows":
        backend = _PyAutoGuiBackend()
    elif kind == "x11":
        backend = _X11Backend()
    elif kind == "wayland":
        backend = _WaylandBackend()
    else:
        backend = _PyAutoGuiBackend()

    # Linux fallback if specialized backend cannot initialize.
    if os.name != "nt" and isinstance(backend, (_X11Backend, _WaylandBackend)):
        try:
            if not backend._ensure():
                backend = _PyAutoGuiBackend()
        except Exception:
            backend = _PyAutoGuiBackend()

    try:
        if isinstance(backend, _PyAutoGuiBackend) and not backend._ensure():
            backend = _NullBackend()
    except Exception:
        backend = _NullBackend()

    backend.configure()
    log.info("Input backend: %s (session=%s)", backend.name, kind)
    return backend


INPUT_BACKEND = _build_backend()
