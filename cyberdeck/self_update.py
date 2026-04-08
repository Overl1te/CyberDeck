"""Windows self-update helper for packaged CyberDeck installs."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from urllib import request

from . import config
from .update_checker import fetch_latest_release_tag, is_newer_version, normalize_version_tag


_INSTALL_LOCK = threading.Lock()
_UNINSTALLER_RE = re.compile(r"^unins\d+\.exe$", re.IGNORECASE)


def _launcher_pid() -> int:
    """Return launcher PID exported into the server environment."""
    try:
        return max(0, int(str(os.environ.get("CYBERDECK_LAUNCHER_PID", "0")).strip() or "0"))
    except Exception:
        return 0


def _has_uninstaller(base_dir: str) -> bool:
    """Return True when the current packaged directory looks like an installed build."""
    root = str(base_dir or "").strip()
    if not root or (not os.path.isdir(root)):
        return False
    try:
        for name in os.listdir(root):
            if _UNINSTALLER_RE.match(str(name or "").strip()):
                return True
    except Exception:
        return False
    return False


def self_update_supported() -> bool:
    """Return True when unattended Windows installer updates are supported."""
    if os.name != "nt":
        return False
    if not bool(getattr(config, "RUNTIME_PACKAGED", False)):
        return False
    if _launcher_pid() <= 0:
        return False
    return _has_uninstaller(str(getattr(config, "BASE_DIR", "") or ""))


def _updates_dir() -> str:
    """Return writable directory used for downloaded installers and helper scripts."""
    root = os.path.join(str(getattr(config, "DATA_DIR", "") or ""), "updates")
    os.makedirs(root, exist_ok=True)
    return root


def _safe_file_name(name: str, fallback: str) -> str:
    """Return a conservative file name safe for the local filesystem."""
    base = os.path.basename(str(name or "").strip())
    if not base:
        base = str(fallback or "").strip()
    if not base:
        base = "CyberDeck_Setup.exe"
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", base)


def _download_file(download_url: str, dest_path: str, *, timeout_s: float, expected_size: int = 0) -> int:
    """Download a release asset into `dest_path` and return written byte count."""
    req = request.Request(
        str(download_url or "").strip(),
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": "CyberDeck-Updater/1.3.2",
        },
    )
    written = 0
    tmp_path = f"{dest_path}.tmp"
    try:
        with request.urlopen(req, timeout=max(30.0, float(timeout_s))) as response:
            with open(tmp_path, "wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
        if expected_size > 0 and int(written) != int(expected_size):
            raise ValueError("size_mismatch")
        os.replace(tmp_path, dest_path)
        return int(written)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        raise


def _write_installer_script(*, installer_path: str, launcher_pid: int, latest_tag: str) -> tuple[str, str]:
    """Write detached helper script that waits for launcher shutdown and runs installer."""
    update_dir = _updates_dir()
    version = normalize_version_tag(latest_tag) or "latest"
    log_path = os.path.join(update_dir, f"install-{version}.log")
    script_path = os.path.join(update_dir, f"run-update-{version}.cmd")
    script = "\n".join(
        [
            "@echo off",
            "setlocal",
            f'set "LAUNCHER_PID={int(launcher_pid)}"',
            f'set "INSTALLER={installer_path}"',
            f'set "UPDATE_LOG={log_path}"',
            "for /L %%I in (1,1,180) do (",
            '  tasklist /FI "PID eq %LAUNCHER_PID%" 2>nul | find "%LAUNCHER_PID%" >nul',
            "  if errorlevel 1 goto launch",
            "  timeout /t 1 /nobreak >nul",
            ")",
            ":launch",
            '"%INSTALLER%" /SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS /LOG="%UPDATE_LOG%"',
            'del "%~f0"',
            "exit /b",
            "",
        ]
    )
    with open(script_path, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(script)
    return script_path, log_path


def _spawn_detached_script(script_path: str) -> None:
    """Launch detached Windows helper script in the background."""
    cmd = str(os.environ.get("ComSpec", "cmd.exe") or "cmd.exe").strip() or "cmd.exe"
    creationflags = 0
    for flag_name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS", "CREATE_NO_WINDOW"):
        try:
            creationflags |= int(getattr(subprocess, flag_name, 0) or 0)
        except Exception:
            pass
    subprocess.Popen(
        [cmd, "/c", script_path],
        cwd=os.path.dirname(os.path.abspath(script_path)),
        close_fds=True,
        creationflags=creationflags,
    )


def prepare_launcher_update_install(
    *,
    current_version: str,
    repo_slug: str,
    timeout_s: float = 2.5,
    ttl_s: int = 300,
    force_refresh: bool = True,
) -> dict[str, object]:
    """Download latest installer and stage a detached silent update for launcher/server."""
    if not self_update_supported():
        return {
            "ok": False,
            "status": "unsupported",
            "error": "unsupported_runtime",
            "shutdown_required": False,
        }

    if not _INSTALL_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "status": "busy",
            "error": "update_in_progress",
            "shutdown_required": False,
        }

    try:
        release = fetch_latest_release_tag(
            repo_slug,
            timeout_s=timeout_s,
            ttl_s=ttl_s,
            force_refresh=force_refresh,
        )
        if not bool(release.get("ok")):
            return {
                "ok": False,
                "status": "release_error",
                "error": str(release.get("error") or "release_lookup_failed"),
                "shutdown_required": False,
            }

        latest_tag = str(release.get("latest_tag") or "").strip()
        if not latest_tag or not is_newer_version(latest_tag, current_version):
            return {
                "ok": False,
                "status": "no_update",
                "error": "no_update",
                "shutdown_required": False,
                "latest_tag": latest_tag,
            }

        asset = release.get("preferred_asset") if isinstance(release.get("preferred_asset"), dict) else {}
        if str(asset.get("kind") or "") != "windows_installer":
            return {
                "ok": False,
                "status": "no_installer",
                "error": "installer_asset_missing",
                "shutdown_required": False,
                "latest_tag": latest_tag,
            }

        download_url = str(asset.get("download_url") or "").strip()
        if not download_url.lower().startswith("https://"):
            return {
                "ok": False,
                "status": "bad_asset",
                "error": "installer_download_url_invalid",
                "shutdown_required": False,
                "latest_tag": latest_tag,
            }

        installer_name = _safe_file_name(str(asset.get("name") or ""), f"CyberDeck_Setup_{latest_tag}.exe")
        installer_path = os.path.join(_updates_dir(), installer_name)
        expected_size = int(asset.get("size") or 0)
        if (not os.path.exists(installer_path)) or (expected_size > 0 and os.path.getsize(installer_path) != expected_size):
            _download_file(
                download_url,
                installer_path,
                timeout_s=float(getattr(config, "UPDATE_DOWNLOAD_TIMEOUT_S", 300.0) or 300.0),
                expected_size=expected_size,
            )

        launcher_pid = _launcher_pid()
        script_path, log_path = _write_installer_script(
            installer_path=installer_path,
            launcher_pid=launcher_pid,
            latest_tag=latest_tag,
        )
        _spawn_detached_script(script_path)
        return {
            "ok": True,
            "status": "scheduled",
            "latest_tag": latest_tag,
            "installer_path": installer_path,
            "script_path": script_path,
            "log_path": log_path,
            "launcher_pid": launcher_pid,
            "shutdown_required": True,
            "scheduled_at": int(time.time()),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "error",
            "error": str(exc.__class__.__name__).lower() or "update_install_failed",
            "shutdown_required": False,
        }
    finally:
        _INSTALL_LOCK.release()
