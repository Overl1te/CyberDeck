import argparse
import http.server
import os
import socketserver
import sys
import time
import urllib.parse

class OneFileHandler(http.server.BaseHTTPRequestHandler):
    file_path: str = ""
    filename: str = ""
    chunk_size: int = 64 * 1024
    sleep_s: float = 0.002
    quiet: bool = True
    server_instance = None

    def log_message(self, format, *args):
        if not self.quiet:
            super().log_message(format, *args)

    def do_GET(self):
        try:
            if not self.file_path or not os.path.exists(self.file_path):
                self.send_error(404, "File not found")
                return

            req = urllib.parse.unquote(self.path.lstrip("/"))
            if req and req != self.filename:
                self.send_error(404, "Not found")
                return

            file_size = os.path.getsize(self.file_path)
            encoded_name = urllib.parse.quote(self.filename)

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
            self.end_headers()

            with open(self.file_path, "rb") as f:
                while True:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                        if self.sleep_s:
                            time.sleep(self.sleep_s)
                    except Exception:
                        break
        finally:
            try:
                if self.server_instance:
                    self.server_instance.shutdown()
                    self.server_instance.server_close()
            except Exception:
                pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("file_path")
    ap.add_argument("port", type=int)
    ap.add_argument("--chunk", type=int, default=64 * 1024)
    ap.add_argument("--sleep", type=float, default=0.002)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--quiet", action="store_true")
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

    socketserver.TCPServer.allow_reuse_address = True

    with socketserver.TCPServer(("0.0.0.0", args.port), Handler) as httpd:
        Handler.server_instance = httpd

        def watchdog():
            time.sleep(max(5, args.timeout))
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass

        import threading
        threading.Thread(target=watchdog, daemon=True).start()

        if not Handler.quiet:
            print(f"Serving {filename} on port {args.port} (chunk={Handler.chunk_size}, sleep={Handler.sleep_s})")
        httpd.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
