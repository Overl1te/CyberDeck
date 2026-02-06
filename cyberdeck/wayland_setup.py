import os
import shutil
import subprocess
import sys
from typing import Callable, List, Optional, Tuple


def is_linux_wayland_session() -> bool:
    if os.name == "nt" or not sys.platform.startswith("linux"):
        return False
    xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    if xdg_type == "wayland":
        return True
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def find_wayland_setup_script(base_dir: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "scripts", "setup_arch_wayland.sh"),
        os.path.join(os.path.dirname(base_dir), "scripts", "setup_arch_wayland.sh"),
        os.path.join(os.path.dirname(here), "scripts", "setup_arch_wayland.sh"),
    ]
    return next((p for p in candidates if os.path.exists(p)), "")


def _ffmpeg_supports_pipewire() -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-formats"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
        return "pipewire" in str(proc.stdout or "").lower()
    except Exception:
        return False


def _gst_supports_pipewire() -> bool:
    gst = shutil.which("gst-inspect-1.0")
    if not gst:
        return False
    try:
        proc = subprocess.run(
            [gst, "pipewiresrc"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        return int(proc.returncode) == 0
    except Exception:
        return False


def check_wayland_requirements() -> List[str]:
    if not is_linux_wayland_session():
        return []

    issues: List[str] = []

    ffmpeg_ok = bool(shutil.which("ffmpeg")) and _ffmpeg_supports_pipewire()
    gst_ok = _gst_supports_pipewire()
    if not (ffmpeg_ok or gst_ok):
        issues.append("stream_backend_missing_pipewire")

    if not os.path.exists("/dev/uinput"):
        issues.append("uinput_missing")
    elif not os.access("/dev/uinput", os.R_OK | os.W_OK):
        issues.append("uinput_no_access")

    try:
        import evdev  # noqa: F401, PLC0415
    except Exception:
        issues.append("python_evdev_missing")

    return issues


def format_wayland_issues(issues: List[str]) -> str:
    if not issues:
        return "ok"

    mapping = {
        "stream_backend_missing_pipewire": "нет рабочего backend для стрима Wayland (нужен ffmpeg+pipewire или gstreamer pipewiresrc)",
        "uinput_missing": "/dev/uinput отсутствует",
        "uinput_no_access": "нет прав на /dev/uinput",
        "python_evdev_missing": "python-пакет evdev не установлен",
    }
    return ", ".join(mapping.get(x, x) for x in issues)


def _stream_process(
    cmd: List[str], cwd: str, log: Optional[Callable[[str], None]] = None
) -> int:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        if proc.stdout:
            for line in proc.stdout:
                if log:
                    log(line.rstrip())
    finally:
        return int(proc.wait())


def run_wayland_setup_installer(
    base_dir: str, log: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str]:
    script = find_wayland_setup_script(base_dir)
    if not os.path.exists(script):
        return False, "installer_not_found"

    bash = shutil.which("bash")
    if not bash:
        return False, "bash_not_found"

    # sudo внутри установочного скрипта обычно требует интерактивный TTY.
    stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
    if not stdin_tty:
        return False, "no_tty_for_sudo"

    try:
        rc = _stream_process([bash, script], cwd=base_dir, log=log)
        return rc == 0, f"installer_exit_code:{rc}"
    except Exception as e:
        return False, f"installer_failed:{type(e).__name__}:{e}"


def ensure_wayland_ready(
    base_dir: str,
    auto_install: bool = True,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, List[str], bool, str]:
    issues = check_wayland_requirements()
    if not issues:
        return True, [], False, "already_ready"

    if not auto_install:
        return False, issues, False, "auto_install_disabled"

    ok, reason = run_wayland_setup_installer(base_dir, log=log)
    if not ok:
        return False, issues, True, reason

    issues_after = check_wayland_requirements()
    return len(issues_after) == 0, issues_after, True, "recheck_after_installer"
