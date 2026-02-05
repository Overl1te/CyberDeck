import ctypes
import os
import subprocess

import pyautogui
from fastapi import APIRouter, HTTPException

from .auth import TokenDep, require_perm
from .logging_config import log


router = APIRouter()
_IS_WINDOWS = os.name == "nt"


def _run_first_ok(cmds: list[list[str]]) -> bool:
    for cmd in cmds:
        try:
            res = subprocess.run(
                cmd,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            if res.returncode == 0:
                return True
        except Exception:
            continue
    return False


@router.post("/system/shutdown")
def system_shutdown(token: str = TokenDep):
    require_perm(token, "perm_power")
    if _IS_WINDOWS:
        os.system("shutdown /s /t 1")
    else:
        ok = _run_first_ok([["systemctl", "poweroff"], ["shutdown", "-h", "now"], ["poweroff"]])
        if not ok:
            raise HTTPException(500, "shutdown_failed")
    return {"status": "shutdown"}


@router.post("/system/restart")
def system_restart(token: str = TokenDep):
    require_perm(token, "perm_power")
    if _IS_WINDOWS:
        os.system("shutdown /r /t 1")
    else:
        ok = _run_first_ok([["systemctl", "reboot"], ["shutdown", "-r", "now"], ["reboot"]])
        if not ok:
            raise HTTPException(500, "restart_failed")
    return {"status": "restart"}


@router.post("/system/logoff")
def system_logoff(token: str = TokenDep):
    require_perm(token, "perm_power")
    if not _IS_WINDOWS:
        raise HTTPException(400, "logoff_supported_only_on_windows")
    os.system("shutdown /l")
    return {"status": "logoff"}


@router.post("/system/lock")
def system_lock(token: str = TokenDep):
    require_perm(token, "perm_power")
    if _IS_WINDOWS:
        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            raise HTTPException(500, f"lock_failed: {e}")
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
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], close_fds=True)
        return {"status": "sleep"}
    except Exception as e:
        log.exception("Sleep failed")
        raise HTTPException(500, f"sleep_failed: {e}")


@router.post("/system/hibernate")
def system_hibernate(token: str = TokenDep):
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
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "1,1,0"], close_fds=True)
        return {"status": "hibernate"}
    except Exception as e:
        log.exception("Hibernate failed")
        raise HTTPException(500, f"hibernate_failed: {e}")


@router.post("/volume/{action}")
def volume_control(action: str, token: str = TokenDep):
    require_perm(token, "perm_keyboard")
    keys = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
    if action in keys:
        pyautogui.press(keys[action], _pause=False)
    return {"status": "ok"}
