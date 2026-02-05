import asyncio
import http.server
import os
import socketserver
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


def trigger_file_send_logic(device_token: str, file_path: str) -> Tuple[bool, str]:
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

        params = pick_transfer_params(session.settings or {})
        chunk = params["chunk"]
        sleep_s = params["sleep"]

        def start_transporter_inprocess(path: str, port: int, timeout_s: int, chunk_sz: int, sleep_each: float, token: str, only_ip: str):
            served = threading.Event()
            target_name = os.path.basename(path)

            class OneFileHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
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

                        self.send_response(200)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Content-Length", str(os.path.getsize(path)))
                        enc = urllib.parse.quote(target_name)
                        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{enc}")
                        self.end_headers()
                        with open(path, "rb") as f:
                            while True:
                                data = f.read(chunk_sz)
                                if not data:
                                    break
                                self.wfile.write(data)
                                if sleep_each:
                                    time.sleep(sleep_each)
                        served.set()
                    except Exception:
                        pass

                def log_message(self, format, *args):
                    return

            def _run():
                try:
                    with socketserver.TCPServer(("", port), OneFileHandler) as httpd:
                        httpd.timeout = 0.5

                        def _shutdown_later():
                            end_t = time.time() + timeout_s
                            while time.time() < end_t and not served.is_set():
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

        if getattr(sys, "frozen", False):
            start_transporter_inprocess(file_path, free_port, 300, chunk, sleep_s, dl_token, allow_ip)
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

            proc = subprocess.Popen(
                cmd,
                cwd=config.BASE_DIR,
                stdout=subprocess.DEVNULL if not config.CONSOLE_LOG else None,
                stderr=subprocess.DEVNULL if not config.CONSOLE_LOG else None,
            )

            def killer(p):
                time.sleep(300)
                try:
                    p.terminate()
                except Exception:
                    pass

            threading.Thread(target=killer, args=(proc,), daemon=True).start()

        encoded_name = urllib.parse.quote(filename)
        download_url = f"http://{local_ip}:{free_port}/{encoded_name}?t={dl_token}"

        msg = {"type": "file_transfer", "filename": filename, "url": download_url, "size": os.path.getsize(file_path)}

        log.info(
            f"Transfer start -> {session.device_name} ({session.ip}) | preset={session.settings.get('transfer_preset','balanced')} "
            f"| chunk={chunk} sleep={sleep_s} | {filename} -> {download_url}"
        )

        asyncio.run_coroutine_threadsafe(session.websocket.send_json(msg), ctx.running_loop)
        return True, "Transporter started"
    except Exception as e:
        log.exception("Trigger transfer failed")
        return False, str(e)
