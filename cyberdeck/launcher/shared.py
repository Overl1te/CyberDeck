import customtkinter as ctk
import threading
import sys
import os
import ctypes
import subprocess
import socket
import shlex
import pystray
import time
import json
import webbrowser
import uvicorn
import queue
import urllib.parse
from typing import Any
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk
from tkinter import filedialog, messagebox
from collections import deque
import qrcode
from cyberdeck import config as server_config
from cyberdeck.platform.wayland_setup import (
    check_wayland_requirements,
    ensure_wayland_ready,
    find_wayland_setup_script,
    format_wayland_issues,
    is_linux_wayland_session,
)
from cyberdeck.launcher.api_client import LauncherApiClient
from cyberdeck.launcher.ui.home import setup_home_ui
from cyberdeck.launcher.ui.devices import setup_devices_ui
from cyberdeck.launcher.ui.settings import setup_settings_ui
from cyberdeck.launcher.toasts import ToastManager
from cyberdeck.launcher.settings import (
    DEFAULT_PORT,
    SETTINGS_FILE_NAME,
    APP_CONFIG_FILE_NAME,
    DEFAULT_SETTINGS,
    DEFAULT_APP_CONFIG,
)
from cyberdeck.launcher.i18n import (
    tr as i18n_tr,
    normalize_language,
    language_options as i18n_language_options,
    language_label as i18n_language_label,
    language_code as i18n_language_code,
)


def _tr_any(owner: Any, key: str, **kwargs: Any) -> str:
    """Return localized string using owner translator with safe fallback."""
    fn = getattr(owner, "tr", None)
    if callable(fn):
        try:
            return str(fn(key, **kwargs))
        except Exception:
            pass
    return i18n_tr("ru", key, **kwargs)

SERVER_SCRIPT_NAME = "main.py"
SYNC_INTERVAL_MS = 1000

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

COLOR_BG = "#050805"
COLOR_PANEL = "#0A120D"
COLOR_PANEL_ALT = "#0D1711"
COLOR_BORDER = "#1D3A29"
COLOR_ACCENT = "#3CFF91"
COLOR_ACCENT_HOVER = "#69FFAD"
COLOR_WARN = "#FFC24B"
COLOR_FAIL = "#FF6B6B"
COLOR_TEXT = "#D9FFE8"
COLOR_TEXT_DIM = "#77A889"

FONT_UI = ("Consolas", 12)
FONT_UI_BOLD = ("Consolas", 12, "bold")
FONT_HEADER = ("Consolas", 22, "bold")
FONT_SMALL = ("Consolas", 10)
FONT_MONO = ("Consolas", 12)
FONT_CODE = ("Consolas", 44, "bold")
QR_IMAGE_SIZE = 240
PORT_PICK_SPAN = 40

DEFAULT_DEVICE_PRESETS = ["fast", "balanced", "safe", "ultra_safe"]
BOOT_OVERLAY_DISMISS_AFTER_S = 8.0
BOOT_OVERLAY_MIN_VISIBLE_S = 7.0
BOOT_PROGRESS_TICK_MS = 120
BOOT_PROGRESS_TARGET_STEP = 0.006
BOOT_PROGRESS_EXP_RATE = 0.42
BOOT_PROGRESS_EXP_MIN_STEP = 0.002
BOOT_PROGRESS_EXP_MAX_STEP = 0.08
BOOT_SPINNER_STEP_S = 0.34
BOOT_MEDIA_GIF_REL = os.path.join("static", "launcher_boot.gif")
BOOT_MEDIA_IMG_REL = os.path.join("static", "launcher_boot.png")
BOOT_MEDIA_GIF_FALLBACK_REL = "logo.gif"
BOOT_OVERLAY_EXIT_STEPS = 10
BOOT_OVERLAY_EXIT_STEP_MS = 18
BOOT_OVERLAY_EXIT_SHRINK = 0.14
BOOT_OVERLAY_EXIT_ALPHA_DROP = 0.08
SUPPORT_URL = "https://pay.cloudtips.ru/p/70ab5e1b"

LAUNCHER_VERSION = str(getattr(server_config, "VERSION", "unknown") or "unknown")

ABOUT_TEXT = (
    "CyberDeck\n\n"
    "Client for controlling a PC over local network.\n\n"
    "Author:\n"
    "Overl1te\n"
    "https://github.com/Overl1te\n\n"
    "Project repository:\n"
    "https://github.com/Overl1te/CyberDeck\n\n"
    "License GNU GPLv3\n"
    "https://github.com/Overl1te/CyberDeck/blob/main/LICENSE\n\n"
    "Terms of use\n"
    "https://github.com/Overl1te/CyberDeck/blob/main/TERMS_OF_USE.md\n\n"
    "CyberDeck Copyright (C) 2026  Overl1te"
)


def is_windows() -> bool:
    """Return True when current OS is Windows."""
    return os.name == "nt"


def is_packaged_runtime() -> bool:
    """Return True when launcher runs from packaged executable."""
    if bool(getattr(sys, "frozen", False)):
        return True
    if "__compiled__" in globals():
        return True
    try:
        if bool(getattr(server_config, "RUNTIME_PACKAGED", False)):
            return True
    except Exception:
        pass
    try:
        exe_path = str(getattr(sys, "executable", "") or "")
        exe_name = os.path.basename(exe_path).strip().lower()
        python_like = {"python", "python3", "python.exe", "pythonw.exe", "py.exe", "pypy", "pypy3"}
        if exe_name and (exe_name not in python_like) and ("python" not in exe_name) and ("pypy" not in exe_name):
            return True
    except Exception:
        pass
    try:
        main_mod = sys.modules.get("__main__")
        if main_mod is not None and hasattr(main_mod, "__compiled__"):
            return True
    except Exception:
        pass
    return False


def detect_resource_dir(default_dir: str) -> str:
    """Resolve runtime directory where bundled media/resources are available."""
    candidates: list[str] = []
    env_dir = str(os.environ.get("CYBERDECK_RESOURCE_DIR", "") or "").strip()
    if env_dir:
        candidates.append(env_dir)

    try:
        module_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates.append(module_root)
    except Exception:
        pass

    try:
        comp = globals().get("__compiled__", None)
        containing = None
        if isinstance(comp, dict):
            containing = comp.get("containing_dir")
        else:
            containing = getattr(comp, "containing_dir", None)
        if containing:
            candidates.append(str(containing))
    except Exception:
        pass

    try:
        candidates.append(os.path.dirname(sys.executable))
    except Exception:
        pass

    if default_dir:
        candidates.append(default_dir)

    seen: set[str] = set()
    for raw in candidates:
        path = os.path.abspath(str(raw or ""))
        if (not path) or (path in seen):
            continue
        seen.add(path)
        if os.path.exists(os.path.join(path, "icon.png")):
            return path
        if os.path.exists(os.path.join(path, "icon-qr-code.png")):
            return path
        if os.path.exists(os.path.join(path, "logo.gif")):
            return path
        if os.path.exists(os.path.join(path, "static")):
            return path

    return os.path.abspath(str(default_dir or "."))


def tray_unavailable_reason() -> str:
    """Explain why system tray is unavailable in current desktop session."""
    if not sys.platform.startswith("linux"):
        return ""
    xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    wayland_display = bool(os.environ.get("WAYLAND_DISPLAY"))
    x11_display = bool(os.environ.get("DISPLAY"))
    if xdg_type == "wayland" or (wayland_display and not x11_display):
        return "Wayland session"
    return ""


def ensure_console() -> None:
    """Attach console for GUI runtime on Windows when needed."""
    if not is_windows():
        return
    try:
        # Respect shell redirection: do not replace stdout/stderr with CONOUT$.
        if (sys.stdout is not None) and hasattr(sys.stdout, "isatty") and (not bool(sys.stdout.isatty())):
            return
        if (sys.stderr is not None) and hasattr(sys.stderr, "isatty") and (not bool(sys.stderr.isatty())):
            return
    except Exception:
        pass
    try:
        has_console = False
        try:
            has_console = bool(ctypes.windll.kernel32.GetConsoleWindow())
        except Exception:
            has_console = False
        if not has_console:
            ctypes.windll.kernel32.AllocConsole()
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        if sys.stdout is None:
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="ignore")
        if sys.stderr is None:
            sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass


def ensure_null_stdio() -> None:
    """Provide safe stdout/stderr sinks for `--noconsole` builds."""
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass
    try:
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass


def load_json(path: str, default: dict[str, Any]) -> dict[str, Any]:
    """Load JSON dictionary and merge with defaults."""
    # Read-path helpers should avoid mutating shared state where possible.
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = default.copy()
                    merged.update(data)
                    return merged
    except Exception:
        pass
    return default.copy()


def save_json(path: str, data: dict[str, Any]) -> None:
    """Persist dictionary to JSON file."""
    # Write-path helpers should keep side effects minimal and well-scoped.
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_autostart(enabled: bool, command: str) -> None:
    """Manage autostart registration in user scope."""
    # Write-path helpers should keep side effects minimal and well-scoped.
    if is_windows():
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, "CyberDeckLauncher", 0, winreg.REG_SZ, str(command))
                else:
                    try:
                        winreg.DeleteValue(key, "CyberDeckLauncher")
                    except FileNotFoundError:
                        pass
        except Exception:
            pass
        return

    # XDG autostart path for Linux.
    if sys.platform.startswith("linux"):
        try:
            autostart_dir = os.path.join(os.path.expanduser("~"), ".config", "autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            desktop_path = os.path.join(autostart_dir, "CyberDeck.desktop")

            if not enabled:
                try:
                    if os.path.exists(desktop_path):
                        os.remove(desktop_path)
                except Exception:
                    pass
                return

            if isinstance(command, (list, tuple)):
                cmd_str = " ".join(shlex.quote(str(x)) for x in command if str(x))
            else:
                cmd_str = str(command)

            # Exec field is not a shell command; wrap with sh -lc for safe quoting.
            exec_line = f"sh -lc {shlex.quote(cmd_str)}"

            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=CyberDeck\n"
                f"Exec={exec_line}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass


class CyberBtn(ctk.CTkButton):
    def __init__(self, master: Any, **kwargs: Any) -> None:
        """Create a themed launcher button."""
        defaults = dict(
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
            fg_color=COLOR_PANEL_ALT,
            text_color=COLOR_TEXT,
            hover_color="#163020",
            font=FONT_UI_BOLD,
            height=34,
        )
        defaults.update(kwargs)
        super().__init__(master, **defaults)

