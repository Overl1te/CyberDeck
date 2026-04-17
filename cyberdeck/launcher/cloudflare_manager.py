from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional
from urllib.parse import urlsplit

import requests


_WINDOWS_AMD64_DOWNLOAD_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
)
_TRYCLOUDFLARE_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
_HTTPS_URL_RE = re.compile(r"https://[a-z0-9][a-z0-9.-]*", re.IGNORECASE)
_NAMED_TUNNEL_READY_RE = re.compile(
    r"(registered tunnel connection|connection [^\n]* registered|connection registered)",
    re.IGNORECASE,
)
_QUICK_TUNNEL_PROBE_INTERVAL_S = 5.0
_QUICK_TUNNEL_BOOT_TIMEOUT_S = 30.0
_QUICK_TUNNEL_UNHEALTHY_MARKERS = (
    "cloudflare tunnel error",
    "origin has been unregistered from argo tunnel",
    "unable to resolve it",
)


@dataclass
class CloudflareSnapshot:
    """Serializable launcher view of current Cloudflare Tunnel runtime state."""

    enabled: bool = False
    running: bool = False
    status: str = "disabled"
    public_url: str = ""
    last_error: str = ""
    binary_path: str = ""
    target_url: str = ""
    configured_hostname: str = ""
    mode: str = "quick"
    pid: int = 0
    updated_ts: float = 0.0


class CloudflareManager:
    """Manage a local cloudflared child process and expose its current public origin."""

    def __init__(
        self,
        *,
        log: Optional[Callable[[str], None]] = None,
        install_dir: str = "",
        auto_install: bool = True,
        search_roots: Optional[list[str]] = None,
    ) -> None:
        self._log = log or (lambda _line: None)
        self._lock = threading.RLock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._install_thread: Optional[threading.Thread] = None
        self._last_lines: deque[str] = deque(maxlen=80)
        self._snapshot = CloudflareSnapshot()
        self._settings_signature: tuple[str, ...] = ("", "", "", "", "", "", "")
        self._binary_raw = ""
        self._tunnel_token = ""
        self._configured_hostname = ""
        self._target_url = ""
        self._enabled = False
        self._auto_install = bool(auto_install)
        self._install_dir = str(install_dir or self._default_install_dir()).strip()
        self._search_roots = [str(x or "").strip() for x in (search_roots or []) if str(x or "").strip()]
        self._download_url_override = ""
        self._last_install_attempt_ts = 0.0
        self._install_cooldown_s = 45.0
        self._next_restart_ts = 0.0
        self._restart_backoff_s = 0.0
        self._process_started_ts = 0.0
        self._named_tunnel_ready = False
        self._candidate_public_url = ""
        self._candidate_public_url_ts = 0.0
        self._last_public_url_probe_url = ""
        self._last_public_url_probe_ts = 0.0
        self._last_public_url_probe_ok = False
        self._public_url_confirmed = False

    def configure(
        self,
        *,
        enabled: bool,
        binary_path: str,
        tunnel_token: str,
        configured_hostname: str,
        target_url: str,
        auto_install: bool = True,
        download_url: str = "",
    ) -> None:
        """Update desired runtime configuration and restart process if needed."""
        with self._lock:
            next_sig = (
                "1" if bool(enabled) else "0",
                str(binary_path or "").strip(),
                str(tunnel_token or "").strip(),
                str(configured_hostname or "").strip(),
                str(target_url or "").strip(),
                "1" if bool(auto_install) else "0",
                str(download_url or "").strip(),
            )
            changed = next_sig != self._settings_signature
            self._settings_signature = next_sig
            self._enabled = bool(enabled)
            self._binary_raw = next_sig[1]
            self._tunnel_token = next_sig[2]
            self._configured_hostname = next_sig[3]
            self._target_url = next_sig[4]
            self._auto_install = bool(auto_install)
            self._download_url_override = next_sig[6]
            if changed:
                self._named_tunnel_ready = False
                self._reset_public_url_tracking()
                self.stop()
                if self._enabled:
                    self._set_snapshot(
                        status="starting",
                        enabled=True,
                        running=False,
                        public_url="",
                        last_error="",
                        binary_path=str(self._binary_raw or ""),
                        target_url=self._target_url,
                        configured_hostname=self._configured_hostname,
                        mode=("named" if self._tunnel_token else "quick"),
                        pid=0,
                    )
                else:
                    self._set_snapshot(
                        status="disabled",
                        enabled=False,
                        running=False,
                        public_url="",
                        last_error="",
                        binary_path="",
                        target_url="",
                        configured_hostname="",
                        mode="quick",
                        pid=0,
                    )

    def snapshot(self) -> CloudflareSnapshot:
        """Return immutable current runtime snapshot."""
        with self._lock:
            snap = self._snapshot
            return CloudflareSnapshot(
                enabled=bool(snap.enabled),
                running=bool(snap.running),
                status=str(snap.status or ""),
                public_url=str(snap.public_url or ""),
                last_error=str(snap.last_error or ""),
                binary_path=str(snap.binary_path or ""),
                target_url=str(snap.target_url or ""),
                configured_hostname=str(snap.configured_hostname or ""),
                mode=str(snap.mode or "quick"),
                pid=int(snap.pid or 0),
                updated_ts=float(snap.updated_ts or 0.0),
            )

    def ensure_running(self) -> CloudflareSnapshot:
        """Ensure the desired cloudflared child process is running when enabled."""
        with self._lock:
            if not self._enabled:
                self.stop()
                self._set_snapshot(status="disabled", enabled=False, running=False, public_url="", last_error="")
                return self.snapshot()

            exe = self._resolve_binary(self._binary_raw)
            if not exe:
                exe = self._ensure_managed_binary()
            if not exe:
                current_status = str(self._snapshot.status or "").strip().lower()
                if current_status == "installing":
                    return self.snapshot()
                self.stop()
                detail = str(self._snapshot.last_error or "").strip() or "cloudflared binary not found"
                self._set_snapshot(
                    status="missing_binary",
                    enabled=True,
                    running=False,
                    public_url="",
                    last_error=detail,
                    binary_path=str(self._binary_raw or ""),
                    configured_hostname=self._configured_hostname,
                    target_url=self._target_url,
                    mode=("named" if self._tunnel_token else "quick"),
                )
                return self.snapshot()

            if self._process is not None:
                rc = self._process.poll()
                if rc is None:
                    self._refresh_public_url_from_logs()
                    self._set_snapshot(
                        status=self._effective_running_status(),
                        enabled=True,
                        running=True,
                        binary_path=exe,
                        target_url=self._target_url,
                        configured_hostname=self._configured_hostname,
                        mode=("named" if self._tunnel_token else "quick"),
                        pid=int(getattr(self._process, "pid", 0) or 0),
                    )
                    return self.snapshot()
                self._record_process_exit(rc)
                self._process = None

            if self._next_restart_ts > time.time():
                return self.snapshot()

            cmd = self._build_command(exe)
            creationflags = 0
            startupinfo = None
            try:
                if os.name == "nt":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    creationflags = subprocess.CREATE_NO_WINDOW
            except Exception:
                startupinfo = None
                creationflags = 0

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=self._build_process_env(),
                    startupinfo=startupinfo,
                    creationflags=creationflags,
                )
            except Exception as exc:
                self._set_snapshot(
                    status="error",
                    enabled=True,
                    running=False,
                    public_url="",
                    last_error=f"cloudflared start failed: {exc}",
                    binary_path=exe,
                    configured_hostname=self._configured_hostname,
                    target_url=self._target_url,
                    mode=("named" if self._tunnel_token else "quick"),
                )
                return self.snapshot()

            self._last_lines.clear()
            self._process = proc
            self._process_started_ts = time.time()
            self._named_tunnel_ready = False
            self._reset_public_url_tracking()
            self._start_stdout_reader(proc)
            self._set_snapshot(
                status="starting",
                enabled=True,
                running=True,
                public_url="",
                last_error="",
                binary_path=exe,
                configured_hostname=self._configured_hostname,
                target_url=self._target_url,
                mode=("named" if self._tunnel_token else "quick"),
                pid=int(proc.pid or 0),
            )
            self._next_restart_ts = 0.0
            self._restart_backoff_s = 0.0
            self._log("[cloudflare] tunnel process started\n")
            return self.snapshot()

    def poll(self) -> CloudflareSnapshot:
        """Refresh local tunnel status by probing child process state/log-derived public URL."""
        with self._lock:
            if not self._enabled:
                return self.ensure_running()

            snap = self.ensure_running()
            proc = self._process
            if proc is None or proc.poll() is not None:
                return self.snapshot()

            self._refresh_public_url_from_logs()
            self._set_snapshot(
                status=self._effective_running_status(),
                enabled=True,
                running=True,
                binary_path=snap.binary_path,
                target_url=self._target_url,
                configured_hostname=self._configured_hostname,
                mode=("named" if self._tunnel_token else "quick"),
                pid=int(getattr(proc, "pid", 0) or 0),
            )
            return self.snapshot()

    def stop(self) -> None:
        """Stop a running cloudflared process, if any."""
        with self._lock:
            proc = self._process
            self._process = None
            self._process_started_ts = 0.0
            self._named_tunnel_ready = False
            self._reset_public_url_tracking()
            if proc is None:
                return
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1.5)
                    except Exception:
                        proc.kill()
            except Exception:
                pass
            finally:
                self._set_snapshot(
                    status="disabled" if not self._enabled else "offline",
                    running=False,
                    public_url="",
                    pid=0,
                )

    def _build_command(self, exe: str) -> list[str]:
        """Build cloudflared command line for quick or named tunnel mode."""
        target = str(self._target_url or "").strip()
        cmd = [exe, "tunnel", "--no-autoupdate"]
        if self._tunnel_token:
            cmd.extend(["run", "--token", self._tunnel_token])
            return cmd
        if os.name == "nt":
            cmd.extend(["--protocol", "http2", "--edge-ip-version", "4"])
        cmd.extend(["--url", target])
        if self._origin_requires_tls_skip_verify(target):
            cmd.append("--no-tls-verify")
        return cmd

    @staticmethod
    def _origin_requires_tls_skip_verify(target_url: str) -> bool:
        """Return True when cloudflared should ignore self-signed TLS on the local origin."""
        raw = str(target_url or "").strip()
        if not raw:
            return False
        try:
            parsed = urlsplit(raw)
        except Exception:
            return False
        scheme = str(parsed.scheme or "").strip().lower()
        host = str(parsed.hostname or "").strip().lower()
        if scheme != "https" or not host:
            return False
        return host in {"127.0.0.1", "localhost", "::1"}

    def _build_process_env(self) -> dict[str, str]:
        """Isolate cloudflared runtime state from any user-global tunnel config."""
        env = dict(os.environ)
        runtime_home = os.path.join(str(self._install_dir or self._default_install_dir()), "runtime-home")
        try:
            os.makedirs(runtime_home, exist_ok=True)
        except Exception:
            return env
        env["HOME"] = runtime_home
        if os.name == "nt":
            env["USERPROFILE"] = runtime_home
        return env

    def _effective_running_status(self) -> str:
        """Return current high-level status while child process is alive."""
        public_url = str(self._snapshot.public_url or "").strip()
        if public_url:
            return "online"
        if self._tunnel_token and self._named_tunnel_ready:
            return "online"
        return "starting"

    def _normalized_configured_hostname(self) -> str:
        """Return configured Cloudflare hostname as normalized absolute URL."""
        host = str(self._configured_hostname or "").strip()
        if not host:
            return ""
        if "://" not in host:
            host = f"https://{host}"
        return host.rstrip("/")

    def _ingest_log_line(self, line: str) -> None:
        """Parse cloudflared stdout and update readiness/public URL snapshot."""
        text = str(line or "").strip()
        if not text:
            return
        self._last_lines.append(text)

        match = _TRYCLOUDFLARE_RE.search(text)
        if match:
            self._remember_candidate_public_url(str(match.group(0)).rstrip("/"))
            self._set_snapshot(last_error="")
            return

        if self._tunnel_token and _NAMED_TUNNEL_READY_RE.search(text):
            self._named_tunnel_ready = True
            public_url = self._normalized_configured_hostname()
            if public_url:
                self._set_snapshot(public_url=public_url, last_error="")
            else:
                self._set_snapshot(last_error="")

    def _refresh_public_url_from_logs(self) -> None:
        """Promote snapshot to online once a public URL is known."""
        public_url = self._discover_public_url()
        if not public_url:
            return
        if self._tunnel_token:
            self._set_snapshot(public_url=public_url, last_error="")
            return
        probe = self._probe_quick_tunnel_public_url(public_url)
        if probe is None:
            return
        ok, detail = probe
        if ok:
            self._public_url_confirmed = True
            self._set_snapshot(public_url=public_url, last_error="")
            return
        self._set_snapshot(public_url="", last_error=str(detail or ""))
        if not ok:
            now = time.time()
            if self._public_url_confirmed:
                self._restart_unhealthy_quick_tunnel("quick tunnel public URL became unreachable")
                return
            if self._candidate_public_url_ts > 0.0 and (now - self._candidate_public_url_ts) >= _QUICK_TUNNEL_BOOT_TIMEOUT_S:
                self._restart_unhealthy_quick_tunnel("quick tunnel public URL did not become reachable")
                return

    def _discover_public_url(self) -> str:
        """Return best-known public URL for the current tunnel."""
        existing = str(self._snapshot.public_url or "").strip()
        if existing:
            return existing
        candidate = str(self._candidate_public_url or "").strip()
        if candidate:
            return candidate
        if self._tunnel_token and self._named_tunnel_ready:
            host = self._normalized_configured_hostname()
            if host:
                return host
        try:
            lines = list(self._last_lines)
        except Exception:
            lines = []
        for raw in reversed(lines):
            match = _TRYCLOUDFLARE_RE.search(str(raw or ""))
            if match:
                public_url = str(match.group(0)).rstrip("/")
                self._remember_candidate_public_url(public_url)
                return public_url
        return ""

    def _reset_public_url_tracking(self) -> None:
        """Clear cached Quick Tunnel URL and its health probe state."""
        self._candidate_public_url = ""
        self._candidate_public_url_ts = 0.0
        self._last_public_url_probe_url = ""
        self._last_public_url_probe_ts = 0.0
        self._last_public_url_probe_ok = False
        self._public_url_confirmed = False

    def _remember_candidate_public_url(self, public_url: str) -> None:
        """Store the current Quick Tunnel URL until a live probe confirms it."""
        text = str(public_url or "").strip().rstrip("/")
        if not text:
            return
        if text != self._candidate_public_url:
            self._candidate_public_url_ts = time.time()
            self._last_public_url_probe_url = ""
            self._last_public_url_probe_ts = 0.0
            self._last_public_url_probe_ok = False
            self._public_url_confirmed = False
        self._candidate_public_url = text

    def _probe_quick_tunnel_public_url(self, public_url: str) -> Optional[tuple[bool, str]]:
        """Rate-limit public URL probes so the launcher can detect dead links without spamming requests."""
        url = str(public_url or "").strip()
        if not url:
            return False, ""
        now = time.time()
        if (
            url == self._last_public_url_probe_url
            and self._last_public_url_probe_ts > 0.0
            and (now - self._last_public_url_probe_ts) < _QUICK_TUNNEL_PROBE_INTERVAL_S
        ):
            return None
        ok, detail = self._probe_public_url_live(url)
        self._last_public_url_probe_url = url
        self._last_public_url_probe_ts = now
        self._last_public_url_probe_ok = ok
        return ok, detail

    @staticmethod
    def _probe_public_url_live(public_url: str) -> tuple[bool, str]:
        """Return True only when the published origin serves a real HTTP response instead of a tunnel error page."""
        url = str(public_url or "").strip()
        if not url:
            return False, ""
        try:
            resp = requests.get(
                url,
                timeout=(2.5, 4.0),
                allow_redirects=True,
                headers={"User-Agent": "CyberDeck-Launcher/1"},
            )
        except requests.RequestException as exc:
            return False, str(exc or "").strip()
        code = int(getattr(resp, "status_code", 0) or 0)
        if 200 <= code < 400:
            return True, ""
        if code == 530:
            return False, str(getattr(resp, "text", "") or "").strip() or "The origin has been unregistered from Argo Tunnel"
        text = str(getattr(resp, "text", "") or "").strip().lower()
        if any(marker in text for marker in _QUICK_TUNNEL_UNHEALTHY_MARKERS):
            return False, str(getattr(resp, "text", "") or "").strip()
        return False, f"public URL probe failed with HTTP {code}"

    def _restart_unhealthy_quick_tunnel(self, detail: str) -> None:
        """Restart Quick Tunnel when Cloudflare publishes a dead or stale public URL."""
        if self._tunnel_token:
            return
        proc = self._process
        if proc is None:
            return
        self._process = None
        self._process_started_ts = 0.0
        self._named_tunnel_ready = False
        self._reset_public_url_tracking()
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except Exception:
                    proc.kill()
        except Exception:
            pass
        if self._restart_backoff_s <= 0.0:
            self._restart_backoff_s = 5.0
        else:
            self._restart_backoff_s = min(30.0, self._restart_backoff_s * 2.0)
        self._next_restart_ts = time.time() + self._restart_backoff_s
        self._set_snapshot(
            status="error",
            enabled=bool(self._enabled),
            running=False,
            public_url="",
            last_error=f"{detail}; retrying",
            configured_hostname=self._configured_hostname,
            target_url=self._target_url,
            mode=("named" if self._tunnel_token else "quick"),
            pid=0,
        )
        self._log(f"[cloudflare] {detail}\n")
        self._log(f"[cloudflare] retry in {int(max(1.0, self._restart_backoff_s))}s\n")

    def _resolve_binary(self, raw_path: str) -> str:
        """Return absolute executable path or empty string when unavailable."""
        text = str(raw_path or "").strip()
        if text:
            try:
                if os.path.isfile(text):
                    return os.path.abspath(text)
            except Exception:
                pass
            found = shutil.which(text)
            return str(found or "")

        for candidate in self._bundled_binary_candidates():
            try:
                if os.path.isfile(candidate):
                    return os.path.abspath(candidate)
            except Exception:
                pass

        managed = self._managed_binary_path()
        if managed and os.path.isfile(managed):
            return os.path.abspath(managed)

        found = shutil.which("cloudflared")
        return str(found or "")

    def _bundled_binary_candidates(self) -> list[str]:
        """Return bundled cloudflared paths relative to known runtime roots."""
        name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
        rel_paths = [
            os.path.join("tools", "cloudflared", name),
            os.path.join("vendor", "cloudflared", "windows-amd64", name),
            os.path.join("third_party", "cloudflared", "windows-amd64", name),
            name,
        ]
        seen: set[str] = set()
        out: list[str] = []
        for root in self._search_roots:
            base = os.path.abspath(str(root or "").strip())
            if not base:
                continue
            for rel in rel_paths:
                path = os.path.abspath(os.path.join(base, rel))
                if path not in seen:
                    seen.add(path)
                    out.append(path)
        return out

    def _default_install_dir(self) -> str:
        """Return default writable directory for the app-managed cloudflared binary."""
        if os.name == "nt":
            root = str(os.environ.get("LOCALAPPDATA", "") or "").strip()
            if root:
                return os.path.join(root, "CyberDeck", "tools", "cloudflared")
        return os.path.join(os.path.expanduser("~"), ".cyberdeck", "tools", "cloudflared")

    def _managed_binary_path(self) -> str:
        """Return expected location of the app-managed cloudflared executable."""
        base = str(self._install_dir or "").strip()
        if not base:
            return ""
        name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
        return os.path.join(base, name)

    def _ensure_managed_binary(self) -> str:
        """Download cloudflared into the app-managed tools directory when allowed."""
        managed = self._managed_binary_path()
        if managed and os.path.isfile(managed):
            return os.path.abspath(managed)
        if not self._auto_install:
            return ""
        if self._install_inflight():
            self._set_snapshot(
                status="installing",
                enabled=True,
                running=False,
                public_url="",
                binary_path=managed,
                configured_hostname=self._configured_hostname,
                target_url=self._target_url,
                mode=("named" if self._tunnel_token else "quick"),
            )
            return ""

        now = time.time()
        if self._last_install_attempt_ts > 0 and (now - self._last_install_attempt_ts) < self._install_cooldown_s:
            return ""
        self._last_install_attempt_ts = now
        self._set_snapshot(
            status="installing",
            enabled=True,
            running=False,
            public_url="",
            last_error="",
            binary_path=managed,
            configured_hostname=self._configured_hostname,
            target_url=self._target_url,
            mode=("named" if self._tunnel_token else "quick"),
        )
        self._start_install_thread()
        return ""

    def _download_binary(self) -> str:
        """Download cloudflared executable into the managed path."""
        url = self._download_url()
        if not url:
            raise RuntimeError("automatic cloudflared install is unsupported on this platform")
        self._validate_download_url(url)

        target = self._managed_binary_path()
        parent = os.path.dirname(target)
        os.makedirs(parent, exist_ok=True)
        with requests.get(url, stream=True, timeout=(5.0, 25.0)) as resp:
            resp.raise_for_status()
            with open(target, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        fh.write(chunk)
        try:
            self._verify_downloaded_binary(target)
        except Exception:
            try:
                os.remove(target)
            except Exception:
                pass
            raise
        try:
            os.chmod(target, 0o755)
        except Exception:
            pass
        return os.path.abspath(target)

    @staticmethod
    def _validate_download_url(url: str) -> None:
        """Reject malformed or non-HTTPS cloudflared download URLs."""
        parsed = urlsplit(str(url or "").strip())
        if str(parsed.scheme or "").strip().lower() != "https" or not str(parsed.netloc or "").strip():
            raise RuntimeError("cloudflared download URL must use https")

    def _verify_downloaded_binary(self, path: str) -> None:
        """Perform post-download verification before executing a managed binary."""
        text = os.path.abspath(str(path or "").strip())
        if not text or (not os.path.isfile(text)):
            raise RuntimeError("downloaded cloudflared binary is missing")
        if os.name != "nt":
            return
        if str(os.environ.get("CYBERDECK_CLOUDFLARED_SKIP_SIGNATURE_VERIFY") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return
        self._verify_windows_signature(text)

    @staticmethod
    def _verify_windows_signature(path: str) -> None:
        """Require a valid Cloudflare Authenticode signature for downloaded Windows binaries."""
        command = (
            "$sig = Get-AuthenticodeSignature -LiteralPath $args[0]; "
            "$out = @{ Status = [string]$sig.Status; "
            "Subject = [string]($sig.SignerCertificate.Subject); "
            "Issuer = [string]($sig.SignerCertificate.Issuer) }; "
            "$out | ConvertTo-Json -Compress"
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20.0,
            check=False,
        )
        if int(getattr(proc, "returncode", 0) or 0) != 0:
            detail = str(getattr(proc, "stderr", "") or getattr(proc, "stdout", "") or "").strip()
            raise RuntimeError(f"cloudflared signature check failed: {detail or 'powershell_error'}")
        try:
            payload = json.loads(str(getattr(proc, "stdout", "") or "").strip() or "{}")
        except Exception as exc:
            raise RuntimeError("cloudflared signature check failed: invalid output") from exc
        status = str(payload.get("Status") or "").strip().lower()
        subject = str(payload.get("Subject") or "").strip()
        issuer = str(payload.get("Issuer") or "").strip()
        if status != "valid":
            raise RuntimeError(f"cloudflared signature is not valid ({status or 'unknown'})")
        joined = f"{subject}\n{issuer}".lower()
        if "cloudflare" not in joined:
            raise RuntimeError("cloudflared signature signer mismatch")

    def _download_url(self) -> str:
        """Return official download URL for the current platform when known."""
        text = str(self._download_url_override or "").strip()
        if text:
            return text
        if os.name == "nt":
            machine = str(platform.machine() or "").strip().lower()
            if machine in {"amd64", "x86_64"}:
                return _WINDOWS_AMD64_DOWNLOAD_URL
        return ""

    def _install_inflight(self) -> bool:
        """Return True while a managed-binary install worker is active."""
        worker = self._install_thread
        return bool(worker is not None and worker.is_alive())

    def _start_install_thread(self) -> None:
        """Start asynchronous cloudflared download so launcher startup never blocks on it."""
        if self._install_inflight():
            return

        def _worker() -> None:
            managed = self._managed_binary_path()
            try:
                out = self._download_binary()
                self._log("[cloudflare] cloudflared auto-installed\n")
                with self._lock:
                    enabled = bool(self._enabled)
                    self._set_snapshot(
                        status="starting" if enabled else "disabled",
                        enabled=enabled,
                        running=False,
                        public_url="",
                        last_error="",
                        binary_path=out or managed,
                        configured_hostname=(self._configured_hostname if enabled else ""),
                        target_url=(self._target_url if enabled else ""),
                        mode=("named" if self._tunnel_token else "quick"),
                    )
            except Exception as exc:
                detail = self._format_install_error(exc)
                with self._lock:
                    enabled = bool(self._enabled)
                    self._set_snapshot(
                        status="error" if enabled else "disabled",
                        enabled=enabled,
                        running=False,
                        public_url="",
                        last_error=(detail if enabled else ""),
                        binary_path=managed,
                        configured_hostname=(self._configured_hostname if enabled else ""),
                        target_url=(self._target_url if enabled else ""),
                        mode=("named" if self._tunnel_token else "quick"),
                    )
            finally:
                with self._lock:
                    self._install_thread = None

        self._install_thread = threading.Thread(target=_worker, daemon=True)
        self._install_thread.start()

    def _format_install_error(self, exc: BaseException) -> str:
        """Return short human-readable install error without raw requests internals."""
        if isinstance(exc, requests.exceptions.Timeout):
            return "cloudflared download timed out"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "cloudflared download failed: connection error"
        if isinstance(exc, requests.exceptions.HTTPError):
            response = getattr(exc, "response", None)
            code = int(getattr(response, "status_code", 0) or 0)
            if code > 0:
                return f"cloudflared download failed: HTTP {code}"
            return "cloudflared download failed"
        text = str(exc or "").strip()
        if "read timed out" in text.lower():
            return "cloudflared download timed out"
        return f"cloudflared install failed: {text}" if text else "cloudflared install failed"

    def _start_stdout_reader(self, proc: subprocess.Popen[str]) -> None:
        """Drain child stdout so cloudflared never blocks on a full pipe."""

        def _worker() -> None:
            stream = getattr(proc, "stdout", None)
            if stream is None:
                return
            try:
                for raw in stream:
                    line = str(raw or "").strip()
                    if not line:
                        continue
                    with self._lock:
                        self._ingest_log_line(line)
            except Exception:
                pass

        self._stdout_thread = threading.Thread(target=_worker, daemon=True)
        self._stdout_thread.start()

    @staticmethod
    def _summarize_error_text(text: str) -> str:
        """Collapse verbose cloudflared output into one concise reason."""
        raw = str(text or "").strip()
        if not raw:
            return ""
        candidates: list[str] = []
        for line in raw.replace("\\r", "\n").replace("\\n", "\n").splitlines():
            item = str(line or "").strip()
            if not item:
                continue
            lower = item.lower()
            if "trycloudflare.com" in lower:
                continue
            if lower.startswith("error:"):
                item = item.split(":", 1)[1].strip()
            elif lower.startswith("error "):
                item = item.split(None, 1)[1].strip()
            elif lower.startswith("err "):
                item = item.split(None, 1)[1].strip()
            if not item:
                continue
            candidates.append(item)
        if not candidates:
            return ""
        return candidates[-1]

    @classmethod
    def _extract_process_exit_detail(cls, lines: list[str], return_code: int) -> str:
        """Extract the best user-facing exit reason from recent cloudflared output."""
        for raw in reversed(lines):
            summary = cls._summarize_error_text(raw)
            if summary:
                return summary
        summary = cls._summarize_error_text("\n".join(lines))
        if summary:
            return summary
        return f"cloudflared exited with code {int(return_code)}"

    def _record_process_exit(self, return_code: int) -> None:
        """Capture child process termination details for diagnostics."""
        try:
            lines = list(self._last_lines)
        except Exception:
            lines = []
        detail = self._extract_process_exit_detail(lines, return_code)
        if bool(self._enabled):
            if self._restart_backoff_s <= 0.0:
                self._restart_backoff_s = 5.0
            else:
                self._restart_backoff_s = min(30.0, self._restart_backoff_s * 2.0)
            self._next_restart_ts = time.time() + self._restart_backoff_s
        else:
            self._next_restart_ts = 0.0
            self._restart_backoff_s = 0.0
        self._named_tunnel_ready = False
        self._reset_public_url_tracking()
        self._set_snapshot(
            status="error",
            enabled=bool(self._enabled),
            running=False,
            public_url="",
            last_error=detail,
            configured_hostname=self._configured_hostname,
            target_url=self._target_url,
            mode=("named" if self._tunnel_token else "quick"),
            pid=0,
        )
        self._log(f"[cloudflare] tunnel stopped: {detail}\n")
        if bool(self._enabled) and self._next_restart_ts > 0.0:
            self._log(f"[cloudflare] retry in {int(max(1.0, self._restart_backoff_s))}s\n")

    def _set_snapshot(self, **changes: object) -> None:
        """Update snapshot fields with a fresh timestamp."""
        snap = self._snapshot
        data = {
            "enabled": bool(changes.get("enabled", snap.enabled)),
            "running": bool(changes.get("running", snap.running)),
            "status": str(changes.get("status", snap.status) or ""),
            "public_url": str(changes.get("public_url", snap.public_url) or ""),
            "last_error": str(changes.get("last_error", snap.last_error) or ""),
            "binary_path": str(changes.get("binary_path", snap.binary_path) or ""),
            "target_url": str(changes.get("target_url", snap.target_url) or ""),
            "configured_hostname": str(changes.get("configured_hostname", snap.configured_hostname) or ""),
            "mode": str(changes.get("mode", snap.mode) or "quick"),
            "pid": int(changes.get("pid", snap.pid) or 0),
            "updated_ts": float(time.time()),
        }
        self._snapshot = CloudflareSnapshot(**data)
