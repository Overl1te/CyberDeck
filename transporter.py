import argparse
import http.server
import os
import socketserver
import ssl
import sys
import time
import urllib.parse
from urllib.parse import parse_qs, urlparse

class OneFileHandler(http.server.BaseHTTPRequestHandler):
    file_path: str = ""
    filename: str = ""
    chunk_size: int = 64 * 1024
    sleep_s: float = 0.002
    quiet: bool = True
    token: str = ""
    allow_ip: str = ""
    server_instance = None

    def log_message(self, format, *args):
        """Log message."""
        if not self.quiet:
            super().log_message(format, *args)

    def do_GET(self):
        """Serve an HTTP GET request."""
        try:
            if not self.file_path or not os.path.exists(self.file_path):
                self.send_error(404, "File not found")
                return

            parsed = urlparse(self.path)
            req = urllib.parse.unquote(parsed.path.lstrip("/"))
            if req and req != self.filename:
                self.send_error(404, "Not found")
                return

            if self.allow_ip:
                try:
                    ip = (self.client_address[0] if self.client_address else "") or ""
                    if ip != self.allow_ip:
                        self.send_error(403, "Forbidden")
                        return
                except Exception:
                    self.send_error(403, "Forbidden")
                    return

            if self.token:
                try:
                    qs = parse_qs(parsed.query or "")
                    got = (qs.get("t") or [""])[0]
                    if got != self.token:
                        self.send_error(403, "Forbidden")
                        return
                except Exception:
                    self.send_error(403, "Forbidden")
                    return

            file_size = os.path.getsize(self.file_path)
            encoded_name = urllib.parse.quote(self.filename)
            range_header = str(self.headers.get("Range") or "").strip()
            start = 0
            end = max(0, int(file_size) - 1)
            status_code = 200
            if range_header.lower().startswith("bytes="):
                try:
                    raw = range_header[6:].split(",", 1)[0].strip()
                    left, right = raw.split("-", 1)
                    if left:
                        start = max(0, int(left))
                    if right:
                        end = int(right)
                    if start >= file_size or end < start:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{file_size}")
                        self.end_headers()
                        return
                    end = min(end, int(file_size) - 1)
                    status_code = 206
                except Exception:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.end_headers()
                    return
            send_len = max(0, end - start + 1)

            self.send_response(status_code)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(send_len))
            if status_code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
            self.end_headers()

            with open(self.file_path, "rb") as f:
                f.seek(start)
                left_to_send = send_len
                while left_to_send > 0:
                    chunk = f.read(min(self.chunk_size, left_to_send))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                        left_to_send -= len(chunk)
                        if self.sleep_s:
                            time.sleep(self.sleep_s)
                    except Exception:
                        break
        finally:
            pass


def main(argv: list[str]) -> int:
    """Run the module entrypoint and start the main application flow."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("file_path")
    ap.add_argument("port", type=int)
    ap.add_argument("--chunk", type=int, default=64 * 1024)
    ap.add_argument("--sleep", type=float, default=0.002)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--token", type=str, default="")
    ap.add_argument("--allow-ip", type=str, default="")
    ap.add_argument("--tls", action="store_true")
    ap.add_argument("--cert", type=str, default="")
    ap.add_argument("--key", type=str, default="")
    args = ap.parse_args(argv)

    file_path = os.path.abspath(args.file_path)
    if not os.path.exists(file_path):
        print("Transporter Error: file not found")
        return 2

    directory = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    os.chdir(directory)

    Handler = OneFileHandler
    Handler.file_path = file_path
    Handler.filename = filename
    Handler.chunk_size = max(1024, int(args.chunk))
    Handler.sleep_s = max(0.0, float(args.sleep))
    Handler.quiet = bool(args.quiet)
    Handler.token = str(args.token or "")
    Handler.allow_ip = str(args.allow_ip or "")

    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(("0.0.0.0", args.port), Handler) as httpd:
        if bool(args.tls):
            cert_path = os.path.abspath(str(args.cert or "").strip())
            key_path = os.path.abspath(str(args.key or "").strip())
            if not (cert_path and key_path and os.path.exists(cert_path) and os.path.exists(key_path)):
                print("Transporter Error: TLS requested but cert/key not found")
                return 2
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        Handler.server_instance = httpd

        def watchdog():
            """Monitor transfer inactivity and stop the HTTP server on timeout."""
            time.sleep(max(5, args.timeout))
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass

        import threading
        threading.Thread(target=watchdog, daemon=True).start()

        if not Handler.quiet:
            proto = "https" if bool(args.tls) else "http"
            print(f"Serving {filename} via {proto} on port {args.port} (chunk={Handler.chunk_size}, sleep={Handler.sleep_s})")
        httpd.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
