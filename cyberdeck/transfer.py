import asyncio
import hashlib
import http.server
import os
import socketserver
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from typing import Any, Dict, Tuple

from . import config
from .auth import get_perm
from .context import device_manager
from .logging_config import log
from .net import find_free_port, get_local_ip


TRANSFER_PRESETS = {
    "fast": {"chunk": 1024 * 1024, "sleep": 0.0},
    "balanced": {"chunk": 256 * 1024, "sleep": 0.001},
    "safe": {"chunk": 64 * 1024, "sleep": 0.002},
    "ultra_safe": {"chunk": 32 * 1024, "sleep": 0.005},
}


def pick_transfer_params(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Pick transfer params."""
    preset = str(settings.get("transfer_preset", "balanced")).lower()
    base = TRANSFER_PRESETS.get(preset, TRANSFER_PRESETS["balanced"]).copy()

    if "transfer_chunk" in settings:
        try:
            base["chunk"] = max(1024, int(settings["transfer_chunk"]))
        except Exception:
            pass
    if "transfer_sleep" in settings:
        try:
            base["sleep"] = max(0.0, float(settings["transfer_sleep"]))
        except Exception:
            pass
    return base


def _sha256_file(path: str) -> str:
    """Compute SHA-256 digest for a file on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _resolve_transfer_scheme() -> str:
    """Resolve transfer scheme."""
    mode = str(getattr(config, "TRANSFER_SCHEME", "auto") or "auto").strip().lower()
    if mode in ("http", "https"):
        return mode
    scheme = str(getattr(config, "SCHEME", "http") or "http").strip().lower()
    return scheme if scheme in ("http", "https") else "http"


def trigger_file_send_logic(device_token: str, file_path: str) -> Tuple[bool, str]:
    """Trigger file send logic."""
    if not get_perm(device_token, "perm_file_send"):
        return False, "permission_denied:perm_file_send"
    session = device_manager.get_session(device_token)
    if not session or not session.websocket:
        return False, "Offline"

    if not os.path.exists(file_path):
        return False, "File missing"

    import cyberdeck.context as ctx
    if ctx.running_loop is None:
        return False, "Server not ready"

    try:
        free_port = find_free_port()
        local_ip = get_local_ip()
        filename = os.path.basename(file_path)
        dl_token = uuid.uuid4().hex
        allow_ip = str(getattr(session, "ip", "") or "")
        transfer_scheme = _resolve_transfer_scheme()
        tls_enabled = transfer_scheme == "https"
        tls_cert = str(getattr(config, "TLS_CERT", "") or "").strip()
        tls_key = str(getattr(config, "TLS_KEY", "") or "").strip()
        if tls_enabled and not (tls_cert and tls_key and os.path.exists(tls_cert) and os.path.exists(tls_key)):
            log.warning("Transfer TLS requested but cert/key are unavailable, falling back to HTTP")
            tls_enabled = False
            transfer_scheme = "http"

        params = pick_transfer_params(session.settings or {})
        chunk = params["chunk"]
        sleep_s = params["sleep"]
        file_size = int(os.path.getsize(file_path))
        file_sha256 = _sha256_file(file_path)

        def start_transporter_inprocess(
            path: str,
            port: int,
            timeout_s: int,
            chunk_sz: int,
            sleep_each: float,
            token: str,
            only_ip: str,
            use_tls: bool,
            cert_path: str,
            key_path: str,
        ):
            """Manage lifecycle transition to start transporter inprocess."""
            # Lifecycle transitions are centralized here to prevent partial-state bugs.
            target_name = os.path.basename(path)

            class OneFileHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    """Serve transfer status and file download endpoints."""
                    try:
                        parsed = urllib.parse.urlparse(self.path)
                        req_name = urllib.parse.unquote(parsed.path.lstrip("/"))
                        if req_name != target_name:
                            self.send_response(404)
                            self.end_headers()
                            return

                        if only_ip:
                            try:
                                ip = (self.client_address[0] if self.client_address else "") or ""
                                if ip != only_ip:
                                    self.send_response(403)
                                    self.end_headers()
                                    return
                            except Exception:
                                self.send_response(403)
                                self.end_headers()
                                return

                        if token:
                            try:
                                qs = urllib.parse.parse_qs(parsed.query or "")
                                got = (qs.get("t") or [""])[0]
                                if got != token:
                                    self.send_response(403)
                                    self.end_headers()
                                    return
                            except Exception:
                                self.send_response(403)
                                self.end_headers()
                                return

                        file_size_local = int(os.path.getsize(path))
                        range_header = str(self.headers.get("Range") or "").strip()
                        start = 0
                        end = max(0, file_size_local - 1)
                        status_code = 200
                        if range_header.lower().startswith("bytes="):
                            try:
                                raw = range_header[6:].split(",", 1)[0].strip()
                                left, right = raw.split("-", 1)
                                if left:
                                    start = max(0, int(left))
                                if right:
                                    end = int(right)
                                if start >= file_size_local or end < start:
                                    self.send_response(416)
                                    self.send_header("Content-Range", f"bytes */{file_size_local}")
                                    self.end_headers()
                                    return
                                end = min(end, file_size_local - 1)
                                status_code = 206
                            except Exception:
                                self.send_response(416)
                                self.send_header("Content-Range", f"bytes */{file_size_local}")
                                self.end_headers()
                                return

                        send_len = max(0, end - start + 1)
                        self.send_response(status_code)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Content-Length", str(send_len))
                        if status_code == 206:
                            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size_local}")
                        enc = urllib.parse.quote(target_name)
                        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{enc}")
                        self.end_headers()
                        with open(path, "rb") as f:
                            f.seek(start)
                            left_to_send = send_len
                            while left_to_send > 0:
                                data = f.read(min(chunk_sz, left_to_send))
                                if not data:
                                    break
                                self.wfile.write(data)
                                left_to_send -= len(data)
                                if sleep_each:
                                    time.sleep(sleep_each)
                    except Exception:
                        pass

                def log_message(self, format, *args):
                    """Silence default HTTP server logs for cleaner console output."""
                    return

            def _run():
                """Execute an internal helper callback used by the surrounding control flow."""
                try:
                    with socketserver.TCPServer(("", port), OneFileHandler) as httpd:
                        if use_tls:
                            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
                            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
                        httpd.timeout = 0.5

                        def _shutdown_later():
                            """Stop the temporary HTTP server after timeout or completion."""
                            end_t = time.time() + timeout_s
                            while time.time() < end_t:
                                time.sleep(0.2)
                            try:
                                httpd.shutdown()
                            except Exception:
                                pass

                        threading.Thread(target=_shutdown_later, daemon=True).start()
                        httpd.serve_forever()
                except Exception:
                    log.exception("In-process transporter failed")

            threading.Thread(target=_run, daemon=True).start()

        if bool(getattr(config, "RUNTIME_PACKAGED", False)):
            start_transporter_inprocess(
                file_path,
                free_port,
                300,
                chunk,
                sleep_s,
                dl_token,
                allow_ip,
                tls_enabled,
                tls_cert,
                tls_key,
            )
        else:
            transporter_path = os.path.join(config.BASE_DIR, "transporter.py")
            if not os.path.exists(transporter_path):
                return False, "transporter.py missing"

            cmd = [
                sys.executable,
                transporter_path,
                file_path,
                str(free_port),
                "--chunk",
                str(chunk),
                "--sleep",
                str(sleep_s),
                "--timeout",
                "300",
                "--quiet",
                "--token",
                dl_token,
                "--allow-ip",
                allow_ip,
            ]
            if tls_enabled:
                cmd.extend(["--tls", "--cert", tls_cert, "--key", tls_key])

            proc = subprocess.Popen(
                cmd,
                cwd=config.BASE_DIR,
                stdout=subprocess.DEVNULL if not config.CONSOLE_LOG else None,
                stderr=subprocess.DEVNULL if not config.CONSOLE_LOG else None,
            )

            def killer(p):
                """Force-terminate stale transfer process after hard timeout."""
                time.sleep(300)
                try:
                    p.terminate()
                except Exception:
                    pass

            threading.Thread(target=killer, args=(proc,), daemon=True).start()

        encoded_name = urllib.parse.quote(filename)
        download_url = f"{transfer_scheme}://{local_ip}:{free_port}/{encoded_name}?t={dl_token}"
        expires_at = int(time.time() + 300)

        msg = {
            "type": "file_transfer",
            "transfer_id": uuid.uuid4().hex,
            "filename": filename,
            "url": download_url,
            "scheme": transfer_scheme,
            "tls": bool(tls_enabled),
            "size": file_size,
            "sha256": file_sha256,
            "accept_ranges": True,
            "expires_at": expires_at,
        }

        log.info(
            f"Transfer start -> {session.device_name} ({session.ip}) | preset={session.settings.get('transfer_preset','balanced')} "
            f"| chunk={chunk} sleep={sleep_s} | {filename} -> {download_url}"
        )

        asyncio.run_coroutine_threadsafe(session.websocket.send_json(msg), ctx.running_loop)
        return True, "Transporter started"
    except Exception as e:
        log.exception("Trigger transfer failed")
        return False, str(e)


