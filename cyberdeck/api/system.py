"""System control endpoints (power/session/media) exposed by CyberDeck API."""

import ctypes
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from ..auth import TokenDep, require_perm
from ..input import INPUT_BACKEND
from ..logging_config import log


router = APIRouter()
_IS_WINDOWS = os.name == "nt"
_WINDOWS_SYSTEM32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


def _env_float(name: str, default: float) -> float:
    """Read float env var and fall back to default for malformed values."""
    raw = os.environ.get(name, None)
    if raw is None:
        return float(default)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return float(default)


_COMMAND_TIMEOUT_S = max(0.2, min(30.0, _env_float("CYBERDECK_SYSTEM_CMD_TIMEOUT_S", 3.0)))
_VOLUME_PERCENT_RE = re.compile(r"(\d{1,3})(?:\.\d+)?%")
_WPCTL_VOLUME_RE = re.compile(r"volume:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
_WINDOWS_WAVEOUT_DEVICE = 0xFFFFFFFF
_WINDOWS_WAVEOUT_MAX = 0xFFFF
_WINDOWS_LAST_NONZERO_VOLUME = 50


def _run_first_ok(cmds: list[list[str]]) -> bool:
    """Run commands sequentially and return True for the first zero exit code."""
    for cmd in cmds:
        try:
            res = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                timeout=_COMMAND_TIMEOUT_S,
            )
            if res.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _run_background_ok(cmd: list[str]) -> bool:
    """Start detached process and return whether spawn succeeded."""
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True
    except Exception:
        return False


def _run_text_cmd(cmd: list[str], timeout_s: Optional[float] = None) -> tuple[bool, str]:
    """Run command and return `(ok, stdout)` preserving text output for parsing."""
    try:
        res = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
            timeout=float(timeout_s if timeout_s is not None else _COMMAND_TIMEOUT_S),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return bool(res.returncode == 0), str(res.stdout or "")
    except Exception:
        return False, ""


def _linux_session_id() -> str:
    """Return current Linux session id if available."""
    return str(os.environ.get("XDG_SESSION_ID") or "").strip()


def _linux_logoff_cmds() -> list[list[str]]:
    """Build Linux desktop/session specific logout command candidates."""
    session_id = _linux_session_id()
    cmds: list[list[str]] = []
    if session_id:
        cmds.append(["loginctl", "terminate-session", session_id])
    cmds.extend(
        [
            ["gnome-session-quit", "--logout", "--no-prompt"],
            ["cinnamon-session-quit", "--logout", "--no-prompt"],
            ["xfce4-session-logout", "--logout", "--fast"],
            ["mate-session-save", "--logout-dialog"],
            ["qdbus", "org.kde.Shutdown", "/Shutdown", "logout"],
            ["systemctl", "--user", "exit"],
        ]
    )
    return cmds


def _parse_first_int(text: str) -> Optional[int]:
    """Extract first integer from text payload."""
    m = re.search(r"-?\d+", str(text or ""))
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def _parse_bool_text(text: str) -> Optional[bool]:
    """Parse yes/no style text into boolean value."""
    normalized = str(text or "").strip().lower()
    if normalized in ("true", "yes", "on", "1", "muted"):
        return True
    if normalized in ("false", "no", "off", "0", "unmuted"):
        return False
    return None


def _clamp_percent(value: int) -> int:
    """Clamp integer volume percentage into [0, 100] range."""
    return max(0, min(100, int(value)))


def _windows_waveout_volume_state() -> Optional[dict[str, Any]]:
    """Read current Windows master-like waveOut volume percentage."""
    if not _IS_WINDOWS:
        return None
    try:
        raw = ctypes.c_uint32(0)
        mm_res = ctypes.windll.winmm.waveOutGetVolume(
            _WINDOWS_WAVEOUT_DEVICE,
            ctypes.byref(raw),
        )
        if int(mm_res) != 0:
            return None
        low = int(raw.value & _WINDOWS_WAVEOUT_MAX)
        high = int((raw.value >> 16) & _WINDOWS_WAVEOUT_MAX)
        avg = int(round(((low + high) * 0.5) * 100.0 / float(_WINDOWS_WAVEOUT_MAX)))
        pct = _clamp_percent(avg)
        return {
            "supported": True,
            "volume_percent": pct,
            "muted": bool(pct <= 0),
            "backend": "winmm",
        }
    except Exception:
        return None


def _windows_waveout_set_volume(percent: int) -> bool:
    """Set Windows waveOut volume in percentage for both channels."""
    global _WINDOWS_LAST_NONZERO_VOLUME
    if not _IS_WINDOWS:
        return False
    pct = _clamp_percent(percent)
    try:
        level = int(round((pct / 100.0) * float(_WINDOWS_WAVEOUT_MAX)))
        level = max(0, min(_WINDOWS_WAVEOUT_MAX, level))
        raw = int((level << 16) | level)
        mm_res = ctypes.windll.winmm.waveOutSetVolume(_WINDOWS_WAVEOUT_DEVICE, raw)
        if int(mm_res) != 0:
            return False
        if pct > 0:
            _WINDOWS_LAST_NONZERO_VOLUME = pct
        return True
    except Exception:
        return False


def _windows_waveout_toggle_mute() -> bool:
    """Toggle Windows mute state by zeroing/restoring waveOut volume."""
    state = _windows_waveout_volume_state()
    if not state:
        return False
    current = _clamp_percent(int(state.get("volume_percent", 0)))
    if current <= 0:
        restore = _clamp_percent(int(_WINDOWS_LAST_NONZERO_VOLUME or 50))
        if restore <= 0:
            restore = 50
        return _windows_waveout_set_volume(restore)
    return _windows_waveout_set_volume(0)


def _linux_volume_state() -> Optional[dict[str, Any]]:
    """Read Linux desktop output volume using wpctl/pactl."""
    wpctl = shutil.which("wpctl")
    if wpctl:
        ok, out = _run_text_cmd([wpctl, "get-volume", "@DEFAULT_AUDIO_SINK@"])
        if ok:
            m = _WPCTL_VOLUME_RE.search(out)
            if m:
                try:
                    raw = float(m.group(1))
                    pct = int(round(raw * 100.0 if raw <= 1.5 else raw))
                    pct = _clamp_percent(pct)
                    muted = "[MUTED]" in str(out or "").upper()
                    return {
                        "supported": True,
                        "volume_percent": pct,
                        "muted": bool(muted or pct <= 0),
                        "backend": "wpctl",
                    }
                except Exception:
                    pass

    pactl = shutil.which("pactl")
    if pactl:
        ok_vol, out_vol = _run_text_cmd([pactl, "get-sink-volume", "@DEFAULT_SINK@"])
        if ok_vol:
            values = [int(m.group(1)) for m in _VOLUME_PERCENT_RE.finditer(out_vol)]
            if values:
                pct = _clamp_percent(int(round(sum(values) / float(len(values)))))
                muted = None
                ok_mute, out_mute = _run_text_cmd([pactl, "get-sink-mute", "@DEFAULT_SINK@"])
                if ok_mute:
                    muted = _parse_bool_text(str(out_mute or "").split(":")[-1].strip())
                return {
                    "supported": True,
                    "volume_percent": pct,
                    "muted": bool(pct <= 0 if muted is None else muted),
                    "backend": "pactl",
                }
    return None


def _linux_set_volume_percent(percent: int) -> bool:
    """Set Linux output volume to exact percentage."""
    pct = _clamp_percent(percent)
    wpctl = shutil.which("wpctl")
    if wpctl:
        level = f"{pct / 100.0:.4f}"
        ok, _ = _run_text_cmd([wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", level])
        if ok:
            return True
    pactl = shutil.which("pactl")
    if pactl:
        ok, _ = _run_text_cmd([pactl, "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"])
        if ok:
            return True
    return False


def _linux_toggle_mute() -> bool:
    """Toggle Linux output mute status."""
    wpctl = shutil.which("wpctl")
    if wpctl:
        ok, _ = _run_text_cmd([wpctl, "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        if ok:
            return True
    pactl = shutil.which("pactl")
    if pactl:
        ok, _ = _run_text_cmd([pactl, "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        if ok:
            return True
    return False


def _mac_volume_state() -> Optional[dict[str, Any]]:
    """Read macOS output volume and mute state via AppleScript."""
    ok_vol, out_vol = _run_text_cmd(["osascript", "-e", "output volume of (get volume settings)"])
    if not ok_vol:
        return None
    pct_raw = _parse_first_int(out_vol)
    if pct_raw is None:
        return None
    pct = _clamp_percent(pct_raw)
    muted = None
    ok_mute, out_mute = _run_text_cmd(["osascript", "-e", "output muted of (get volume settings)"])
    if ok_mute:
        muted = _parse_bool_text(out_mute.strip())
    return {
        "supported": True,
        "volume_percent": pct,
        "muted": bool(pct <= 0 if muted is None else muted),
        "backend": "osascript",
    }


def _mac_set_volume_percent(percent: int) -> bool:
    """Set macOS output volume percentage."""
    pct = _clamp_percent(percent)
    ok, _ = _run_text_cmd(["osascript", "-e", f"set volume output volume {pct}"])
    return ok


def _mac_toggle_mute() -> bool:
    """Toggle macOS output mute state."""
    state = _mac_volume_state()
    if not state:
        return False
    currently_muted = bool(state.get("muted", False))
    if currently_muted:
        ok, _ = _run_text_cmd(["osascript", "-e", "set volume without output muted"])
        return ok
    ok, _ = _run_text_cmd(["osascript", "-e", "set volume with output muted"])
    return ok


def _raw_volume_state() -> Optional[dict[str, Any]]:
    """Read current host output volume state from OS-specific backend."""
    if _IS_WINDOWS:
        return _windows_waveout_volume_state()
    if sys.platform == "darwin":
        return _mac_volume_state()
    return _linux_volume_state()


def _set_volume_percent(percent: int) -> bool:
    """Set host output volume using OS-specific backend."""
    if _IS_WINDOWS:
        return _windows_waveout_set_volume(percent)
    if sys.platform == "darwin":
        return _mac_set_volume_percent(percent)
    return _linux_set_volume_percent(percent)


def _toggle_system_mute() -> bool:
    """Toggle host output mute using OS-specific backend."""
    if _IS_WINDOWS:
        return _windows_waveout_toggle_mute()
    if sys.platform == "darwin":
        return _mac_toggle_mute()
    return _linux_toggle_mute()


def get_volume_state_payload() -> dict[str, Any]:
    """Return normalized volume state payload for API responses."""
    state = _raw_volume_state() or {}
    supported = bool(state.get("supported", False))
    vol_raw = state.get("volume_percent", None)
    muted_raw = state.get("muted", None)
    volume_percent = None if vol_raw is None else _clamp_percent(int(vol_raw))
    muted = None if muted_raw is None else bool(muted_raw)
    if muted is None and volume_percent is not None:
        muted = bool(volume_percent <= 0)
    return {
        "supported": supported,
        "volume_percent": volume_percent,
        "muted": muted,
        "backend": str(state.get("backend", "") or ""),
    }


@router.post("/system/shutdown")
def system_shutdown(token: str = TokenDep):
    """Shutdown host machine."""
    require_perm(token, "perm_power")
    if _IS_WINDOWS:
        ok = _run_first_ok([["shutdown", "/s", "/t", "1"]])
        if not ok:
            raise HTTPException(500, "shutdown_failed")
    else:
        ok = _run_first_ok([["systemctl", "poweroff"], ["shutdown", "-h", "now"], ["poweroff"]])
        if not ok:
            raise HTTPException(500, "shutdown_failed")
    return {"status": "shutdown"}


@router.post("/system/restart")
def system_restart(token: str = TokenDep):
    """Restart host machine."""
    require_perm(token, "perm_power")
    if _IS_WINDOWS:
        ok = _run_first_ok([["shutdown", "/r", "/t", "1"]])
        if not ok:
            raise HTTPException(500, "restart_failed")
    else:
        ok = _run_first_ok([["systemctl", "reboot"], ["shutdown", "-r", "now"], ["reboot"]])
        if not ok:
            raise HTTPException(500, "restart_failed")
    return {"status": "restart"}


@router.post("/system/logoff")
def system_logoff(token: str = TokenDep):
    """Log out current desktop session."""
    require_perm(token, "perm_power")
    if _IS_WINDOWS:
        ok = _run_first_ok([["shutdown", "/l"]])
        if not ok:
            raise HTTPException(500, "logoff_failed")
        return {"status": "logoff"}
    ok = _run_first_ok(_linux_logoff_cmds())
    if not ok:
        raise HTTPException(400, "logoff_not_supported_on_this_system")
    return {"status": "logoff"}


@router.post("/system/lock")
def system_lock(token: str = TokenDep):
    """Lock current user session."""
    require_perm(token, "perm_power")
    if _IS_WINDOWS:
        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            raise HTTPException(500, f"lock_failed: {e}") from e
    else:
        ok = _run_first_ok(
            [
                ["loginctl", "lock-sessions"],
                ["xdg-screensaver", "lock"],
                ["gnome-screensaver-command", "-l"],
                ["dm-tool", "lock"],
            ]
        )
        if not ok:
            raise HTTPException(400, "lock_not_supported_on_this_system")
    return {"status": "locked"}


@router.post("/system/sleep")
def system_sleep(token: str = TokenDep):
    """Put machine into sleep/suspend mode."""
    require_perm(token, "perm_power")
    if not _IS_WINDOWS:
        ok = _run_first_ok([["systemctl", "suspend"]])
        if not ok:
            raise HTTPException(500, "sleep_failed")
        return {"status": "sleep"}
    try:
        try:
            ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        except Exception:
            cmd = [os.path.join(_WINDOWS_SYSTEM32, "rundll32.exe"), "powrprof.dll,SetSuspendState", "0,1,0"]
            if not _run_background_ok(cmd):
                raise RuntimeError("rundll32_start_failed")
        return {"status": "sleep"}
    except Exception as e:
        log.exception("Sleep failed")
        raise HTTPException(500, f"sleep_failed: {e}") from e


@router.post("/system/hibernate")
def system_hibernate(token: str = TokenDep):
    """Put machine into hibernate mode."""
    require_perm(token, "perm_power")
    if not _IS_WINDOWS:
        ok = _run_first_ok([["systemctl", "hibernate"]])
        if not ok:
            raise HTTPException(500, "hibernate_failed")
        return {"status": "hibernate"}
    try:
        try:
            ctypes.windll.powrprof.SetSuspendState(1, 1, 0)
        except Exception:
            cmd = [os.path.join(_WINDOWS_SYSTEM32, "rundll32.exe"), "powrprof.dll,SetSuspendState", "1,1,0"]
            if not _run_background_ok(cmd):
                raise RuntimeError("rundll32_start_failed")
        return {"status": "hibernate"}
    except Exception as e:
        log.exception("Hibernate failed")
        raise HTTPException(500, f"hibernate_failed: {e}") from e


@router.get("/volume/state")
def volume_state(token: str = TokenDep):
    """Return current host output volume state when backend support is available."""
    require_perm(token, "perm_keyboard")
    return {"status": "ok", **get_volume_state_payload()}


@router.post("/volume/set/{percent}")
def volume_set(percent: int, token: str = TokenDep):
    """Set host output volume to the requested percentage."""
    require_perm(token, "perm_keyboard")
    target = _clamp_percent(int(percent))
    if not _set_volume_percent(target):
        raise HTTPException(501, "volume_control_unavailable")
    return {"status": "ok", **get_volume_state_payload()}


@router.post("/volume/{action}")
def volume_control(action: str, token: str = TokenDep):
    """Send volume media key action via selected input backend."""
    require_perm(token, "perm_keyboard")
    keys = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
    if action not in keys:
        raise HTTPException(400, "unknown_action")
    if action == "mute":
        if (not _toggle_system_mute()) and (not INPUT_BACKEND.press(keys[action])):
            raise HTTPException(501, "keyboard_input_unavailable")
    else:
        if not INPUT_BACKEND.press(keys[action]):
            raise HTTPException(501, "keyboard_input_unavailable")
    return {"status": "ok", **get_volume_state_payload()}

