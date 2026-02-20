"""System control endpoints (power/session/media) exposed by CyberDeck API."""

import ctypes
import os
import subprocess

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


@router.post("/volume/{action}")
def volume_control(action: str, token: str = TokenDep):
    """Send volume media key action via selected input backend."""
    require_perm(token, "perm_keyboard")
    keys = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
    if action not in keys:
        raise HTTPException(400, "unknown_action")
    if not INPUT_BACKEND.press(keys[action]):
        raise HTTPException(501, "keyboard_input_unavailable")
    return {"status": "ok"}

