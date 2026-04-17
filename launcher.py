#!/usr/bin/env python3
"""CyberDeck launcher entry point (GUI + server orchestration).

Catches unhandled exceptions and writes a crash log before re-raising.
"""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

from cyberdeck.launcher.app import App


def _crash_log_paths() -> list[str]:
    paths: list[str] = []

    explicit = str(os.environ.get("CYBERDECK_CRASH_LOG", "") or "").strip()
    if explicit:
        paths.append(explicit)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    paths.append(os.path.join(base_dir, "launcher_crash.log"))

    user_profile = str(os.environ.get("USERPROFILE", "") or "").strip()
    if user_profile:
        paths.append(
            os.path.join(
                user_profile,
                "AppData",
                "LocalLow",
                "CyberDeck",
                "launcher_crash.log",
            )
        )

    seen: set[str] = set()
    out: list[str] = []
    for raw in paths:
        normalized = os.path.abspath(str(raw))
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _write_crash_log(header: str) -> None:
    payload = (
        f"[{datetime.now().isoformat(timespec='seconds')}] {header}\n"
        f"{traceback.format_exc()}\n"
    )
    for path in _crash_log_paths():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(payload)
        except Exception:
            pass


if __name__ == "__main__":
    # On Windows, python.exe always opens a console window.  When the user
    # doesn't need it (no -c / --console flag), silently re-launch via
    # pythonw.exe so only the GUI is visible.
    if (
        os.name == "nt"
        and "-c" not in sys.argv
        and "--console" not in sys.argv
    ):
        exe = sys.executable
        exe_name = os.path.basename(exe).lower()
        if exe_name in ("python.exe", "python3.exe"):
            pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.isfile(pythonw):
                import subprocess

                subprocess.Popen(
                    [pythonw] + sys.argv,
                    creationflags=subprocess.DETACHED_PROCESS
                    | subprocess.CREATE_NO_WINDOW,
                )
                raise SystemExit(0)

    try:
        app = App()
        app.mainloop()
    except BaseException:
        _write_crash_log("Unhandled exception in launcher entrypoint")
        raise
