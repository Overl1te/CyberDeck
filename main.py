import os
import uuid
import json
import time
import threading
import mss
import pyautogui
import psutil
import uvicorn
import socket
import ctypes
import asyncio
import sys
import subprocess
import http.server
import socketserver
import urllib.parse
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from io import BytesIO
from PIL import Image, ImageDraw
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional, Any

try:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
except Exception:
    pass
try:
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
except Exception:
    pass


VERSION = "v1.2.1"
HOST = "0.0.0.0"
PORT = int(os.environ.get("CYBERDECK_PORT", "8080"))
UDP_PORT = int(os.environ.get("CYBERDECK_UDP_PORT", "5555"))
CURSOR_STREAM = int(os.environ.get("CYBERDECK_CURSOR_STREAM", "1")) == 1
CURSOR_STREAM_FPS = int(os.environ.get("CYBERDECK_CURSOR_FPS", "30"))

DEBUG = os.environ.get("CYBERDECK_DEBUG", "1") == "1"
CONSOLE_LOG = os.environ.get("CYBERDECK_CONSOLE", "0") == "1"
LOG_ENABLED = os.environ.get("CYBERDECK_LOG", "0") == "1" or CONSOLE_LOG

running_loop = None

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FILES_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
SESSION_FILE = os.path.join(BASE_DIR, "cyberdeck_sessions.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOG_FILE = os.path.join(BASE_DIR, "cyberdeck.log")

if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR, exist_ok=True)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

PAIRING_CODE = str(uuid.uuid4().int)[:4]
SERVER_ID = str(uuid.uuid4())[:8]
HOSTNAME = os.environ.get("COMPUTERNAME", "CyberDeck PC")


def setup_logging() -> logging.Logger:
    os.makedirs(BASE_DIR, exist_ok=True)
    logger = logging.getLogger("cyberdeck")
    logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

    if not LOG_ENABLED:
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            ul = logging.getLogger(name)
            ul.handlers.clear()
            ul.propagate = False
            ul.setLevel(logging.CRITICAL)
        return logger

    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG if DEBUG else logging.INFO)
    logger.addHandler(file_handler)

    if CONSOLE_LOG:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        console.setLevel(logging.DEBUG if DEBUG else logging.INFO)
        logger.addHandler(console)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        ul = logging.getLogger(name)
        ul.handlers.clear()
        ul.propagate = False
        ul.setLevel(logging.DEBUG if DEBUG else logging.INFO)
        ul.addHandler(file_handler)
        if CONSOLE_LOG:
            ul.addHandler(console)

    return logger


log = setup_logging()

try:
    pyautogui.PAUSE = 0
except Exception:
    pass

_mouse_remainders_lock = threading.Lock()
_mouse_remainders = {}

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


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def udp_discovery_service():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", UDP_PORT))
        log.info(f"UDP discovery listening on {UDP_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                if b"CYBERDECK_DISCOVER" in data:
                    nonce = None
                    try:
                        if data.startswith(b"CYBERDECK_DISCOVER:"):
                            nonce = data.split(b":", 1)[1].decode("utf-8", "ignore")[:32]
                    except Exception:
                        nonce = None
                    resp_dict = {"cyberdeck": True, "proto": 2, "id": SERVER_ID, "name": HOSTNAME, "port": PORT, "version": VERSION}
                    if nonce:
                        resp_dict["nonce"] = nonce
                    resp = json.dumps(resp_dict)
                    sock.sendto(resp.encode("utf-8"), addr)
            except Exception:
                pass
    except Exception:
        log.exception("UDP discovery died")


threading.Thread(target=udp_discovery_service, daemon=True).start()

class DeviceSession:
    def __init__(self, device_id, device_name, ip, token=None, settings=None):
        self.device_id = device_id
        self.device_name = device_name
        self.ip = ip
        self.token = token if token else str(uuid.uuid4())
        self.websocket: Optional[WebSocket] = None
        self.settings: Dict[str, Any] = settings or {}


class DeviceManager:
    def __init__(self):
        self.sessions: Dict[str, DeviceSession] = {}

    def authorize(self, device_id, name, ip):
        for t, s in self.sessions.items():
            if s.device_id == device_id:
                s.ip = ip
                s.device_name = name
                self.save_sessions()
                return t
        s = DeviceSession(device_id, name, ip)
        self.sessions[s.token] = s
        self.save_sessions()
        return s.token

    def save_sessions(self):
        try:
            data = {
                t: {
                    "device_id": s.device_id,
                    "device_name": s.device_name,
                    "ip": s.ip,
                    "settings": s.settings,
                }
                for t, s in self.sessions.items()
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            log.exception("Failed to save sessions")

    def load_sessions(self):
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for t, i in data.items():
                        self.sessions[t] = DeviceSession(
                            i.get("device_id"),
                            i.get("device_name"),
                            i.get("ip"),
                            token=t,
                            settings=i.get("settings") or {},
                        )
        except Exception:
            log.exception("Failed to load sessions")

    def get_session(self, token: str):
        return self.sessions.get(token)

    def register_socket(self, token: str, ws: WebSocket):
        if token in self.sessions:
            self.sessions[token].websocket = ws

    def unregister_socket(self, token: str):
        if token in self.sessions:
            self.sessions[token].websocket = None

    def delete_session(self, token: str) -> bool:
        if token not in self.sessions:
            return False
        try:
            self.sessions.pop(token, None)
            self.save_sessions()
            return True
        except Exception:
            log.exception("Failed to delete session")
            return False

    def update_settings(self, token: str, patch: Dict[str, Any]):
        s = self.sessions.get(token)
        if not s:
            return False
        if not isinstance(patch, dict):
            return False
        for k, v in patch.items():
            if v is None:
                try:
                    s.settings.pop(k, None)
                except Exception:
                    pass
            else:
                s.settings[k] = v
        self.save_sessions()
        return True

    def get_all_devices(self):
        out = []
        for t, s in self.sessions.items():
            out.append(
                {
                    "name": s.device_name,
                    "ip": s.ip,
                    "token": t,
                    "online": bool(s.websocket),
                    "settings": s.settings,
                }
            )
        return out


device_manager = DeviceManager()
device_manager.load_sessions()

DEFAULT_PERMS = {
    "perm_mouse": True,
    "perm_keyboard": True,
    "perm_upload": True,
    "perm_file_send": True,
    "perm_stream": True,
    "perm_power": False,
}


def _get_perm(token: str, key: str) -> bool:
    s = device_manager.get_session(token)
    if not s:
        return False
    try:
        settings = s.settings or {}
        if key in settings:
            return bool(settings.get(key))
        return bool(DEFAULT_PERMS.get(key, False))
    except Exception:
        return bool(DEFAULT_PERMS.get(key, False))


def _require_perm(token: str, key: str):
    if not _get_perm(token, key):
        raise HTTPException(403, detail=f"permission_denied:{key}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global running_loop
    running_loop = asyncio.get_running_loop()
    log.info("Server startup complete")
    yield


app = FastAPI(title=f"CyberDeck {VERSION}", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


async def get_token(request: Request, token: Optional[str] = Query(None)):
    if token and device_manager.get_session(token):
        return token
    auth = request.headers.get("Authorization")
    if auth:
        t = auth.replace("Bearer ", "")
        if device_manager.get_session(t):
            return t
    ws_token = request.query_params.get("token")
    if ws_token and device_manager.get_session(ws_token):
        return ws_token
    raise HTTPException(403, detail="Unauthorized")


class HandshakeRequest(BaseModel):
    code: str
    device_id: str
    device_name: str


@app.post("/api/handshake")
def handshake(req: HandshakeRequest, request: Request):
    if req.code != PAIRING_CODE:
        raise HTTPException(403, detail="Invalid Code")
    token = device_manager.authorize(req.device_id, req.device_name, request.client.host)
    log.info(f"Handshake OK: {req.device_name} ({req.device_id}) -> {request.client.host}")
    return {"status": "ok", "token": token, "server_name": HOSTNAME}


@app.get("/api/stats")
def get_stats(token: str = Depends(get_token)):
    return {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent}


@app.post("/api/file/upload")
async def upload_file(file: UploadFile = File(...), token: str = Depends(get_token)):
    _require_perm(token, "perm_upload")
    try:
        file_path = os.path.join(FILES_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                buffer.write(chunk)
        return {"status": "ok"}
    except Exception as e:
        log.exception("Upload failed")
        return {"status": "error", "detail": str(e)}


def trigger_file_send_logic(device_token: str, file_path: str):
    if not _get_perm(device_token, "perm_file_send"):
        return False, "permission_denied:perm_file_send"
    session = device_manager.get_session(device_token)
    if not session or not session.websocket:
        return False, "Offline"

    if not os.path.exists(file_path):
        return False, "File missing"

    if running_loop is None:
        return False, "Server not ready"

    try:
        free_port = find_free_port()
        local_ip = get_local_ip()
        filename = os.path.basename(file_path)

        params = pick_transfer_params(session.settings or {})
        chunk = params["chunk"]
        sleep_s = params["sleep"]

        def start_transporter_inprocess(path: str, port: int, timeout_s: int, chunk_sz: int, sleep_each: float):
            served = threading.Event()
            target_name = os.path.basename(path)

            class OneFileHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    try:
                        req_name = urllib.parse.unquote(self.path.lstrip("/"))
                        if req_name != target_name:
                            self.send_response(404)
                            self.end_headers()
                            return
                        self.send_response(200)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Content-Length", str(os.path.getsize(path)))
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
            start_transporter_inprocess(file_path, free_port, 300, chunk, sleep_s)
        else:
            transporter_path = os.path.join(BASE_DIR, "transporter.py")
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
            ]

            proc = subprocess.Popen(
                cmd,
                cwd=BASE_DIR,
                stdout=subprocess.DEVNULL if not CONSOLE_LOG else None,
                stderr=subprocess.DEVNULL if not CONSOLE_LOG else None,
            )

            def killer(p):
                time.sleep(300)
                try:
                    p.terminate()
                except Exception:
                    pass

            threading.Thread(target=killer, args=(proc,), daemon=True).start()

        encoded_name = urllib.parse.quote(filename)
        download_url = f"http://{local_ip}:{free_port}/{encoded_name}"

        msg = {"type": "file_transfer", "filename": filename, "url": download_url, "size": os.path.getsize(file_path)}

        log.info(
            f"Transfer start -> {session.device_name} ({session.ip}) | preset={session.settings.get('transfer_preset','balanced')} "
            f"| chunk={chunk} sleep={sleep_s} | {filename} -> {download_url}"
        )

        asyncio.run_coroutine_threadsafe(session.websocket.send_json(msg), running_loop)
        return True, "Transporter started"
    except Exception as e:
        log.exception("Trigger transfer failed")
        return False, str(e)


class LocalFileRequest(BaseModel):
    token: str
    file_path: str


class LocalSettingsRequest(BaseModel):
    token: str
    settings: Dict[str, Any]

class LocalTokenRequest(BaseModel):
    token: str

class QrLoginRequest(BaseModel):
    nonce: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None


@app.post("/api/local/trigger_file")
def local_trigger_file(req: LocalFileRequest, request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    ok, msg = trigger_file_send_logic(req.token, req.file_path)
    return {"ok": ok, "msg": msg}


@app.get("/api/local/info")
def local_info(request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    return {
        "version": VERSION,
        "pairing_code": PAIRING_CODE,
        "ip": get_local_ip(),
        "port": PORT,
        "hostname": HOSTNAME,
        "log_file": LOG_FILE,
        "devices": device_manager.get_all_devices(),
    }

@app.get("/api/local/qr_payload")
def local_qr_payload(request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    payload = {
        "type": "cyberdeck_qr_v1",
        "server_id": SERVER_ID,
        "hostname": HOSTNAME,
        "version": VERSION,
        "ip": get_local_ip(),
        "port": PORT,
        "pairing_code": PAIRING_CODE,
        "ts": int(time.time()),
        "nonce": str(uuid.uuid4()),
    }
    return {"payload": payload}

@app.post("/api/qr/login")
def qr_login(req: QrLoginRequest):
    raise HTTPException(501, detail="qr_login_not_implemented")


@app.get("/api/local/stats")
def local_stats(request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "uptime_s": int(time.time() - psutil.boot_time()),
        "process_ram": psutil.Process(os.getpid()).memory_info().rss,
    }


@app.get("/api/local/device_settings")
def local_get_device_settings(token: str, request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    s = device_manager.get_session(token)
    if not s:
        raise HTTPException(404)
    return {"token": token, "settings": s.settings}


@app.post("/api/local/device_settings")
def local_set_device_settings(req: LocalSettingsRequest, request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    ok = device_manager.update_settings(req.token, req.settings)
    if not ok:
        raise HTTPException(404)
    return {"ok": True}


@app.post("/api/local/device_disconnect")
def local_device_disconnect(req: LocalTokenRequest, request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    s = device_manager.get_session(req.token)
    if not s:
        raise HTTPException(404)
    if not s.websocket or running_loop is None:
        device_manager.unregister_socket(req.token)
        return {"ok": True, "msg": "already_offline"}
    try:
        asyncio.run_coroutine_threadsafe(s.websocket.close(code=1000), running_loop)
    except Exception:
        pass
    device_manager.unregister_socket(req.token)
    return {"ok": True}


@app.post("/api/local/device_delete")
def local_device_delete(req: LocalTokenRequest, request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    s = device_manager.get_session(req.token)
    if not s:
        raise HTTPException(404)
    try:
        if s.websocket and running_loop is not None:
            asyncio.run_coroutine_threadsafe(s.websocket.close(code=1000), running_loop)
    except Exception:
        pass
    device_manager.unregister_socket(req.token)
    ok = device_manager.delete_session(req.token)
    if not ok:
        raise HTTPException(500)
    return {"ok": True}


@app.post("/api/local/regenerate_code")
def regenerate_code(request: Request):
    if request.client.host != "127.0.0.1":
        raise HTTPException(403)
    global PAIRING_CODE
    PAIRING_CODE = str(uuid.uuid4().int)[:4]
    log.info(f"Pairing code regenerated -> {PAIRING_CODE}")
    return {"new_code": PAIRING_CODE}


@app.post("/system/shutdown")
def system_shutdown(token: str = Depends(get_token)):
    _require_perm(token, "perm_power")
    os.system("shutdown /s /t 1")
    return {"status": "shutdown"}


@app.post("/system/lock")
def system_lock(token: str = Depends(get_token)):
    _require_perm(token, "perm_power")
    ctypes.windll.user32.LockWorkStation()
    return {"status": "locked"}

@app.post("/system/sleep")
def system_sleep(token: str = Depends(get_token)):
    _require_perm(token, "perm_power")
    if os.name != "nt":
        raise HTTPException(400, "sleep_supported_only_on_windows")
    try:
        try:
            ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        except Exception:
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], close_fds=True)
        return {"status": "sleep"}
    except Exception as e:
        log.exception("Sleep failed")
        raise HTTPException(500, f"sleep_failed: {e}")



@app.post("/volume/{action}")
def volume_control(action: str, token: str = Depends(get_token)):
    _require_perm(token, "perm_keyboard")
    keys = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
    if action in keys:
        pyautogui.press(keys[action], _pause=False)
    return {"status": "ok"}



class _VideoStreamer:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_raw = None
        self._raw_seq = 0
        self._latest_jpeg = None
        self._latest_jpeg_key = None
        self._latest_jpeg_seq = -1
        self._ts = 0.0
        self.base_w = int(os.environ.get("CYBERDECK_STREAM_W", "960"))
        self.base_q = int(os.environ.get("CYBERDECK_STREAM_Q", "25"))
        self.base_fps = int(os.environ.get("CYBERDECK_STREAM_FPS", "30"))
        self.base_cursor = int(os.environ.get("CYBERDECK_STREAM_CURSOR", "0")) == 1
        self._desired_key = (self.base_w, self.base_q, self.base_cursor)
        self._ema_encode_ms = None
        self._ema_grab_ms = None
        self._ema_loop_fps = None
        self._last_loop_t = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                min_dt = 1.0 / max(5, self.base_fps)
                while not self._stop.is_set():
                    t0 = time.perf_counter()
                    try:
                        g0 = time.perf_counter()
                        sct_img = sct.grab(monitor)
                        g_ms = (time.perf_counter() - g0) * 1000.0
                        raw = bytes(sct_img.bgra)
                        size = sct_img.size
                        with self._lock:
                            self._raw_seq += 1
                            raw_seq = self._raw_seq
                            self._latest_raw = (raw, size, monitor, raw_seq)
                            desired_w, desired_q, desired_cursor = self._desired_key

                        e0 = time.perf_counter()
                        jpeg = self._encode(raw, size, monitor, desired_w, desired_q, desired_cursor)
                        e_ms = (time.perf_counter() - e0) * 1000.0
                        with self._lock:
                            self._latest_jpeg = jpeg
                            self._latest_jpeg_key = (desired_w, desired_q, desired_cursor)
                            self._latest_jpeg_seq = raw_seq
                            self._ts = time.time()

                            a = 0.15
                            self._ema_encode_ms = e_ms if self._ema_encode_ms is None else (self._ema_encode_ms * (1 - a) + e_ms * a)
                            self._ema_grab_ms = g_ms if self._ema_grab_ms is None else (self._ema_grab_ms * (1 - a) + g_ms * a)
                            now = time.perf_counter()
                            if self._last_loop_t is not None:
                                dt = max(0.0001, now - self._last_loop_t)
                                fps_now = 1.0 / dt
                                self._ema_loop_fps = fps_now if self._ema_loop_fps is None else (self._ema_loop_fps * (1 - a) + fps_now * a)
                            self._last_loop_t = now
                    except Exception:
                        log.exception("Video grab/encode failed")
                        time.sleep(0.05)
                    dt = time.perf_counter() - t0
                    if dt < min_dt:
                        time.sleep(min_dt - dt)
        except Exception:
            log.exception("Video streamer died")

    def _encode(self, raw_bgra: bytes, size, monitor, w: int, q: int, cursor: bool) -> bytes:
        img = Image.frombytes("RGB", size, raw_bgra, "raw", "BGRX")
        if cursor:
            try:
                cx, cy = pyautogui.position()
                rx, ry = cx - monitor["left"], cy - monitor["top"]
                draw = ImageDraw.Draw(img)
                draw.ellipse((rx - 6, ry - 6, rx + 6, ry + 6), outline=(0, 255, 65), width=2)
                draw.line((rx, ry, rx + 18, ry + 18), fill=(0, 255, 65), width=2)
            except Exception:
                pass

        if w and img.width > w:
            h = int(img.height * (w / img.width))
            img = img.resize((w, max(1, h)), Image.Resampling.NEAREST)

        buf = BytesIO()
        q = max(10, min(95, int(q)))
        img.save(buf, format="JPEG", quality=q, subsampling=2, progressive=False, optimize=False)
        return buf.getvalue()

    def get_jpeg(self, w: int, q: int, cursor: bool) -> bytes:
        with self._lock:
            raw = self._latest_raw
            jpeg = self._latest_jpeg
            jpeg_key = self._latest_jpeg_key
            jpeg_seq = self._latest_jpeg_seq
        if raw is None:
            return b""

        key = (int(w), int(q), bool(cursor))
        raw_bgra, size, monitor, raw_seq = raw
        if jpeg is not None and jpeg_key == key and jpeg_seq == raw_seq:
            return jpeg

        try:
            with self._lock:
                self._desired_key = key
        except Exception:
            pass

        out = self._encode(raw_bgra, size, monitor, key[0], key[1], key[2])
        try:
            with self._lock:
                if self._latest_raw and self._latest_raw[3] == raw_seq:
                    self._latest_jpeg = out
                    self._latest_jpeg_key = key
                    self._latest_jpeg_seq = raw_seq
        except Exception:
            pass
        return out

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            desired = tuple(self._desired_key)
            return {
                "desired_w": int(desired[0]),
                "desired_q": int(desired[1]),
                "desired_cursor": bool(desired[2]),
                "base_fps": int(self.base_fps),
                "ema_encode_ms": float(self._ema_encode_ms) if self._ema_encode_ms is not None else None,
                "ema_grab_ms": float(self._ema_grab_ms) if self._ema_grab_ms is not None else None,
                "ema_loop_fps": float(self._ema_loop_fps) if self._ema_loop_fps is not None else None,
                "ts": float(self._ts),
            }


_video_streamer = _VideoStreamer()


def generate_video_stream(w: int, q: int, fps: int, cursor: bool):
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    min_dt = 1.0 / max(5, int(fps))
    while True:
        t0 = time.perf_counter()
        try:
            frame = _video_streamer.get_jpeg(w, q, cursor)
            if frame:
                yield boundary + frame + b"\r\n"
        except Exception:
            log.exception("Video stream generator error")
            time.sleep(0.05)
        dt = time.perf_counter() - t0
        if dt < min_dt:
            time.sleep(min_dt - dt)


@app.get("/video_feed")
def video_feed(
    token: str = Depends(get_token),
    w: Optional[int] = None,
    q: Optional[int] = None,
    max_w: Optional[int] = None,
    quality: Optional[int] = None,
    fps: int = 30,
    cursor: int = 0,
    low_latency: int = 0,
):
    _require_perm(token, "perm_stream")

    eff_w = int(max_w if max_w is not None else (w if w is not None else 960))
    eff_q = int(quality if quality is not None else (q if q is not None else 25))
    eff_fps = int(fps)

    if int(low_latency) == 1:
        eff_w = min(eff_w, 960)
        eff_q = min(eff_q, 35)
        eff_fps = min(eff_fps, 60)

    return StreamingResponse(
        generate_video_stream(eff_w, eff_q, eff_fps, bool(int(cursor))),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/stream_stats")
def stream_stats(token: str = Depends(get_token)):
    _require_perm(token, "perm_stream")
    return _video_streamer.get_stats()


async def _cursor_stream(websocket: WebSocket):
    min_dt = 1.0 / max(5, int(CURSOR_STREAM_FPS))
    last_pos = None
    while True:
        try:
            x, y = pyautogui.position()
            w, h = pyautogui.size()
            pos = (int(x), int(y), int(w), int(h))
            if pos != last_pos:
                await websocket.send_json({"type": "cursor", "x": pos[0], "y": pos[1], "w": pos[2], "h": pos[3]})
                last_pos = pos
        except asyncio.CancelledError:
            break
        except Exception:
            break
        await asyncio.sleep(min_dt)


@app.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket, token: str = Query(...)):
    if not device_manager.get_session(token):
        await websocket.close(code=4003)
        return
    if not (_get_perm(token, "perm_mouse") or _get_perm(token, "perm_keyboard")):
        await websocket.close(code=4003)
        return
    await websocket.accept()
    device_manager.register_socket(token, websocket)
    log.info(f"WS connected: {token}")
    cursor_task = asyncio.create_task(_cursor_stream(websocket)) if CURSOR_STREAM else None
    try:
        while True:
            data = await websocket.receive_json()
            t = (data.get("type") or "").lower()

            if t == "move":
                if not _get_perm(token, "perm_mouse"):
                    continue
                try:
                    dx = float(data.get("dx", 0) or 0)
                    dy = float(data.get("dy", 0) or 0)
                except Exception:
                    dx, dy = 0.0, 0.0

                with _mouse_remainders_lock:
                    rx, ry = _mouse_remainders.get(token, (0.0, 0.0))
                    dx += rx
                    dy += ry
                    mx = int(round(dx))
                    my = int(round(dy))
                    _mouse_remainders[token] = (dx - mx, dy - my)

                if mx or my:
                    pyautogui.moveRel(mx, my, _pause=False)

            elif t == "click":
                if not _get_perm(token, "perm_mouse"):
                    continue
                pyautogui.click(_pause=False)

            elif t == "rclick":
                if not _get_perm(token, "perm_mouse"):
                    continue
                pyautogui.click(button="right", _pause=False)

            elif t == "dclick":
                if not _get_perm(token, "perm_mouse"):
                    continue
                pyautogui.doubleClick(_pause=False)

            elif t == "scroll":
                if not _get_perm(token, "perm_mouse"):
                    continue
                pyautogui.scroll(int(data.get("dy", 0)), _pause=False)

            elif t == "drag_s":
                if not _get_perm(token, "perm_mouse"):
                    continue
                pyautogui.mouseDown(_pause=False)

            elif t == "drag_e":
                if not _get_perm(token, "perm_mouse"):
                    continue
                pyautogui.mouseUp(_pause=False)

            elif t == "text":
                if not _get_perm(token, "perm_keyboard"):
                    continue
                text = str(data.get("text", ""))
                if text:
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if hwnd:
                        for char in text:
                            ctypes.windll.user32.SendMessageW(hwnd, 0x0102, ord(char), 0)

            elif t == "key":
                if not _get_perm(token, "perm_keyboard"):
                    continue
                key_map = {"enter": 0x0D, "backspace": 0x08, "space": 0x20, "win": 0x5B}
                val = str(data.get("key", "")).lower()
                vk = key_map.get(val)
                if vk:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

            elif t == "hotkey":
                if not _get_perm(token, "perm_keyboard"):
                    continue
                keys = data.get("keys") or []
                if isinstance(keys, list) and keys:
                    keys = [str(k).lower() for k in keys]
                    pyautogui.hotkey(*keys, _pause=False)

            elif t == "media":
                if not _get_perm(token, "perm_keyboard"):
                    continue
                act = str(data.get("action", "")).lower()
                media_map = {
                    "play_pause": "playpause",
                    "next": "nexttrack",
                    "prev": "prevtrack",
                    "stop": "stop",
                    "mute": "volumemute",
                    "vol_up": "volumeup",
                    "vol_down": "volumedown",
                }
                key = media_map.get(act)
                if key:
                    pyautogui.press(key, _pause=False)

            elif t == "shortcut":
                if not _get_perm(token, "perm_keyboard"):
                    continue
                act = str(data.get("action", "")).lower()
                if act == "copy":
                    pyautogui.hotkey("ctrl", "c", _pause=False)
                elif act == "paste":
                    pyautogui.hotkey("ctrl", "v", _pause=False)
                elif act == "cut":
                    pyautogui.hotkey("ctrl", "x", _pause=False)
                elif act == "undo":
                    pyautogui.hotkey("ctrl", "z", _pause=False)
                elif act == "redo":
                    pyautogui.hotkey("ctrl", "y", _pause=False)

    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WS error")
    finally:
        if cursor_task:
            cursor_task.cancel()
        device_manager.unregister_socket(token)
        try:
            with _mouse_remainders_lock:
                _mouse_remainders.pop(token, None)
        except Exception:
            pass
        log.info(f"WS disconnected: {token}")


if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    log_level = "debug" if DEBUG else "info"
    access_log = DEBUG
    if not LOG_ENABLED:
        log_level = "critical"
        access_log = False
    uvicorn.run(app, host=HOST, port=PORT, log_level=log_level, access_log=access_log)
