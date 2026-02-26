from __future__ import annotations

import os
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
    try:
        app = App()
        app.mainloop()
    except BaseException:
        _write_crash_log("Unhandled exception in launcher entrypoint")
        raise
