import os
import shutil
import subprocess
import sys
from typing import Callable, List, Optional, Tuple

_CRITICAL_WAYLAND_ISSUES = {"stream_backend_missing_pipewire"}


def is_linux_wayland_session() -> bool:
    """Return whether current runtime is a Linux Wayland session."""
    if os.name == "nt" or not sys.platform.startswith("linux"):
        return False
    xdg_type = (os.environ.get("XDG_SESSION_TYPE") or "").strip().lower()
    if xdg_type == "wayland":
        return True
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _linux_pkg_manager() -> str:
    """Detect the Linux package manager available on this host."""
    if os.name == "nt" or not sys.platform.startswith("linux"):
        return "none"
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("pacman"):
        return "pacman"
    return "unknown"


def _wayland_setup_script_names() -> List[str]:
    """Return candidate Wayland setup script filenames."""
    manager = _linux_pkg_manager()
    if manager == "apt":
        return ["setup_ubuntu_wayland.sh", "setup_arch_wayland.sh"]
    if manager == "pacman":
        return ["setup_arch_wayland.sh", "setup_ubuntu_wayland.sh"]
    return ["setup_ubuntu_wayland.sh", "setup_arch_wayland.sh"]


def find_wayland_setup_script(base_dir: str) -> str:
    """Locate the first existing Wayland setup script in scripts/."""
    here = os.path.dirname(os.path.abspath(__file__))
    roots = [
        os.path.join(base_dir, "scripts"),
        os.path.join(os.path.dirname(base_dir), "scripts"),
        os.path.join(os.path.dirname(here), "scripts"),
    ]
    for scripts_dir in roots:
        for script_name in _wayland_setup_script_names():
            p = os.path.join(scripts_dir, script_name)
            if os.path.exists(p):
                return p
    return ""


def _ffmpeg_supports_pipewire() -> bool:
    """Check whether installed FFmpeg supports PipeWire capture."""
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


def _ffmpeg_supports_x11grab() -> bool:
    """Check whether installed FFmpeg supports X11 fallback capture."""
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
        return "x11grab" in str(proc.stdout or "").lower()
    except Exception:
        return False


def _gst_supports_pipewire() -> bool:
    """Check whether installed GStreamer supports PipeWire capture."""
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


def _wayland_allow_x11_fallback() -> bool:
    """Return whether X11 fallback should be treated as usable in current session."""
    if not is_linux_wayland_session():
        return False
    if not os.environ.get("DISPLAY"):
        return False
    return os.environ.get("CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK", "1") == "1"


def _wayland_screenshot_available() -> bool:
    """Check whether screenshot tools required for Wayland fallback are installed."""
    return bool(
        shutil.which("grim")
        or shutil.which("gnome-screenshot")
        or shutil.which("spectacle")
        or shutil.which("gdbus")
        or shutil.which("qdbus")
        or shutil.which("qdbus6")
    )


def _wayland_text_tools_available() -> bool:
    """Check whether text-input tools required on Wayland are installed."""
    return bool(shutil.which("wtype") or shutil.which("wl-copy"))


def _recommended_backend_order() -> str:
    """Build best-effort backend order for current Wayland runtime."""
    ffmpeg_present = bool(shutil.which("ffmpeg"))
    ffmpeg_pipewire_ok = ffmpeg_present and _ffmpeg_supports_pipewire()
    ffmpeg_x11_ok = ffmpeg_present and _ffmpeg_supports_x11grab() and _wayland_allow_x11_fallback()
    gst_ok = _gst_supports_pipewire()
    screenshot_ok = _wayland_screenshot_available()
    if ffmpeg_pipewire_ok:
        return "ffmpeg,gstreamer,screenshot,native"
    if ffmpeg_x11_ok:
        # On many Wayland sessions x11grab can produce unusable frames; keep it as a fallback.
        if screenshot_ok and gst_ok:
            return "screenshot,gstreamer,ffmpeg,native"
        if screenshot_ok:
            return "screenshot,ffmpeg,gstreamer,native"
        if gst_ok:
            return "gstreamer,screenshot,ffmpeg,native"
        return "ffmpeg,screenshot,gstreamer,native"
    if gst_ok:
        if screenshot_ok:
            return "screenshot,gstreamer,ffmpeg,native"
        return "gstreamer,screenshot,ffmpeg,native"
    if screenshot_ok:
        return "screenshot,ffmpeg,gstreamer,native"
    return ""


def _apply_runtime_wayland_policy(log: Optional[Callable[[str], None]] = None) -> List[str]:
    """Apply non-root runtime fallbacks so Wayland can run without installer in common cases."""
    if not is_linux_wayland_session():
        return []

    applied: List[str] = []

    if "CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK" not in os.environ and os.environ.get("DISPLAY"):
        os.environ["CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK"] = "1"
        applied.append("CYBERDECK_WAYLAND_ALLOW_X11_FALLBACK=1")

    if "CYBERDECK_MJPEG_BACKEND_ORDER" not in os.environ:
        order = _recommended_backend_order()
        if order:
            os.environ["CYBERDECK_MJPEG_BACKEND_ORDER"] = order
            applied.append(f"CYBERDECK_MJPEG_BACKEND_ORDER={order}")

    if "CYBERDECK_CURSOR_STREAM" not in os.environ:
        os.environ["CYBERDECK_CURSOR_STREAM"] = "0"
        applied.append("CYBERDECK_CURSOR_STREAM=0")

    if "CYBERDECK_FAST_RESIZE" not in os.environ:
        os.environ["CYBERDECK_FAST_RESIZE"] = "1"
        applied.append("CYBERDECK_FAST_RESIZE=1")

    if "CYBERDECK_PREFER_MJPEG_OFFER" not in os.environ:
        os.environ["CYBERDECK_PREFER_MJPEG_OFFER"] = "1"
        applied.append("CYBERDECK_PREFER_MJPEG_OFFER=1")

    if applied and log:
        log("applied runtime wayland policy: " + ", ".join(applied))

    return applied


def _critical_issues(issues: List[str]) -> List[str]:
    """Return blocking issues that prevent basic Wayland streaming startup."""
    return [x for x in (issues or []) if x in _CRITICAL_WAYLAND_ISSUES]


def check_wayland_requirements() -> List[str]:
    """Collect Wayland runtime requirements and missing dependencies."""
    if not is_linux_wayland_session():
        return []

    issues: List[str] = []

    ffmpeg_pipewire_ok = bool(shutil.which("ffmpeg")) and _ffmpeg_supports_pipewire()
    ffmpeg_x11_ok = bool(shutil.which("ffmpeg")) and _ffmpeg_supports_x11grab() and _wayland_allow_x11_fallback()
    gst_ok = _gst_supports_pipewire()
    screenshot_ok = _wayland_screenshot_available()
    if not (ffmpeg_pipewire_ok or ffmpeg_x11_ok or gst_ok or screenshot_ok):
        issues.append("stream_backend_missing_pipewire")

    if not os.path.exists("/dev/uinput"):
        issues.append("uinput_missing")
    elif not os.access("/dev/uinput", os.R_OK | os.W_OK):
        issues.append("uinput_no_access")

    try:
        import evdev  # type: ignore # noqa: F401, PLC0415
    except Exception:
        issues.append("python_evdev_missing")
    if not _wayland_text_tools_available():
        issues.append("wayland_text_tools_missing")

    return issues


def format_wayland_issues(issues: List[str]) -> str:
    """Normalize and transform values used to format wayland issues."""
    if not issues:
        return "ok"

    mapping = {
        "stream_backend_missing_pipewire": (
            "no working Wayland stream backend "
            "(need ffmpeg+pipewire, ffmpeg+x11grab fallback, gstreamer pipewiresrc, or screenshot tools)"
        ),
        "uinput_missing": "/dev/uinput is missing",
        "uinput_no_access": "no access to /dev/uinput",
        "python_evdev_missing": "python package evdev is not installed",
        "wayland_text_tools_missing": "wtype/wl-copy not found (text input may be limited)",
    }
    return ", ".join(mapping.get(x, x) for x in issues)


def _stream_process(
    cmd: List[str], cwd: str, log: Optional[Callable[[str], None]] = None
) -> int:
    """Start a short-lived test stream process and capture exit status."""
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
    """Manage lifecycle transition to run wayland setup installer."""
    script = find_wayland_setup_script(base_dir)
    if not os.path.exists(script):
        return False, "installer_not_found"

    bash = shutil.which("bash")
    if not bash:
        return False, "bash_not_found"

    # sudo inside the setup script usually requires an interactive TTY.
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
    """Ensure wayland ready."""
    _apply_runtime_wayland_policy(log=log)
    issues = check_wayland_requirements()
    critical = _critical_issues(issues)
    if not critical:
        if issues:
            return True, issues, False, "ready_with_warnings"
        return True, [], False, "already_ready"

    if not auto_install:
        return False, issues, False, "auto_install_disabled"

    ok, reason = run_wayland_setup_installer(base_dir, log=log)
    if not ok:
        _apply_runtime_wayland_policy(log=log)
        issues_after_fail = check_wayland_requirements()
        critical_after_fail = _critical_issues(issues_after_fail)
        if not critical_after_fail:
            return True, issues_after_fail, True, f"{reason}:ready_with_warnings"
        return False, (issues_after_fail or issues), True, reason

    issues_after = check_wayland_requirements()
    critical_after = _critical_issues(issues_after)
    if critical_after:
        return False, issues_after, True, "recheck_after_installer"
    return True, issues_after, True, "recheck_after_installer"
