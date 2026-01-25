import os
import uuid
import json
import time
import shutil
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
from io import BytesIO
from PIL import Image, ImageDraw
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional

# --- CONFIG ---
VERSION = "v1.5.0 (Process-Separated)"
HOST = "0.0.0.0"
PORT = 8080
UDP_PORT = 5555
DEBUG = True 

# Глобальный Event Loop
running_loop = None 

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FILES_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
SESSION_FILE = os.path.join(BASE_DIR, "cyberdeck_sessions.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

if not os.path.exists(FILES_DIR): os.makedirs(FILES_DIR)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# Генерируем код при старте, но позволяем его менять через API (для регенерации из GUI)
PAIRING_CODE = str(uuid.uuid4().int)[:4]
SERVER_ID = str(uuid.uuid4())[:8]
HOSTNAME = os.environ.get('COMPUTERNAME', 'CyberDeck PC')

# --- NETWORKING UTILS ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

# --- THROTTLED FILE SERVER ---
class ThrottledFileHandler(http.server.BaseHTTPRequestHandler):
    target_file = None
    server_instance = None 

    def log_message(self, format, *args): return 

    def do_GET(self):
        try:
            if not self.target_file or not os.path.exists(self.target_file):
                self.send_error(404, "File not found")
                return

            file_size = os.path.getsize(self.target_file)
            filename = os.path.basename(self.target_file)
            encoded_name = urllib.parse.quote(filename)

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(file_size))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{encoded_name}")
            self.end_headers()

            chunk_size = 64 * 1024 
            with open(self.target_file, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk: break
                    try:
                        self.wfile.write(chunk)
                        time.sleep(0.002) 
                    except Exception:
                        break
        except Exception as e:
            if DEBUG: print(f"Transfer Error: {e}")
        finally:
            threading.Thread(target=self.kill_server, daemon=True).start()

    def kill_server(self):
        if self.server_instance:
            try:
                self.server_instance.shutdown()
                self.server_instance.server_close()
            except: pass

def start_throttled_server(file_path, port):
    httpd = None
    try:
        handler = ThrottledFileHandler
        handler.target_file = file_path
        socketserver.TCPServer.allow_reuse_address = True
        httpd = socketserver.TCPServer(("0.0.0.0", port), handler)
        handler.server_instance = httpd
        
        def watchdog():
            time.sleep(60)
            if httpd: 
                try: httpd.shutdown(); httpd.server_close()
                except: pass
        
        threading.Thread(target=watchdog, daemon=True).start()
        httpd.serve_forever()
    except Exception: pass
    finally:
        if httpd: 
            try: httpd.server_close()
            except: pass

# --- UDP DISCOVERY ---
def udp_discovery_service():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', UDP_PORT))
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                if b"CYBERDECK_DISCOVER" in data:
                    resp = json.dumps({"id": SERVER_ID, "name": HOSTNAME, "port": PORT, "version": VERSION})
                    sock.sendto(resp.encode('utf-8'), addr)
            except: pass
    except: pass

threading.Thread(target=udp_discovery_service, daemon=True).start()

# --- SESSIONS ---
class DeviceSession:
    def __init__(self, device_id, device_name, ip, token=None):
        self.device_id = device_id
        self.device_name = device_name
        self.ip = ip
        self.token = token if token else str(uuid.uuid4())
        self.websocket: Optional[WebSocket] = None

class DeviceManager:
    def __init__(self): self.sessions: Dict[str, DeviceSession] = {} 
    
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
            data = {t: {'device_id': s.device_id, 'device_name': s.device_name, 'ip': s.ip} for t, s in self.sessions.items()}
            with open(SESSION_FILE, 'w') as f: json.dump(data, f)
        except: pass

    def load_sessions(self):
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, 'r') as f:
                    data = json.load(f)
                    for t, i in data.items():
                        self.sessions[t] = DeviceSession(i['device_id'], i['device_name'], i['ip'], token=t)
        except: pass

    def get_session(self, token: str): return self.sessions.get(token)
    def register_socket(self, token: str, ws: WebSocket):
        if token in self.sessions: self.sessions[token].websocket = ws
    def get_all_devices(self):
        return [{"name": s.device_name, "ip": s.ip, "token": t} for t, s in self.sessions.items()]

device_manager = DeviceManager()
device_manager.load_sessions()

app = FastAPI(title=f"CyberDeck {VERSION}")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup_event():
    global running_loop
    running_loop = asyncio.get_running_loop()

# --- API ---
async def get_token(request: Request, token: Optional[str] = Query(None)):
    if token and device_manager.get_session(token): return token
    auth = request.headers.get("Authorization")
    if auth:
        t = auth.replace("Bearer ", "")
        if device_manager.get_session(t): return t
    ws_token = request.query_params.get("token")
    if ws_token and device_manager.get_session(ws_token): return ws_token
    raise HTTPException(403, detail="Unauthorized")

class HandshakeRequest(BaseModel):
    code: str
    device_id: str
    device_name: str

@app.post("/api/handshake")
def handshake(req: HandshakeRequest, request: Request):
    if req.code != PAIRING_CODE: raise HTTPException(403, detail="Invalid Code")
    token = device_manager.authorize(req.device_id, req.device_name, request.client.host)
    return {"status": "ok", "token": token, "server_name": HOSTNAME}

@app.get("/api/stats") 
def get_stats(token: str = Depends(get_token)):
    return {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent}

@app.post("/api/file/upload")
async def upload_file(file: UploadFile = File(...), token: str = Depends(get_token)):
    try:
        file_path = os.path.join(FILES_DIR, file.filename)
        with open(file_path, "wb") as buffer:
             while True:
                chunk = await file.read(1024 * 1024)
                if not chunk: break
                buffer.write(chunk)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# --- ЛОГИКА ТРИГГЕРА ---
def trigger_file_send_logic(device_token, file_path):
    session = device_manager.get_session(device_token)
    if not session or not session.websocket: return False, "Offline"

    try:
        if not os.path.exists(file_path): return False, "File missing"

        free_port = find_free_port()
        local_ip = get_local_ip()
        filename = os.path.basename(file_path)
        
        # ЗАПУСК TRANSPORTER (HTTP режим)
        # Запускаем в отдельном процессе, чтобы не блочить видео
        proc = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "transporter.py"), file_path, str(free_port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Убийца процесса через 5 минут (на случай если забыли скачать)
        def killer(p):
            time.sleep(300) 
            try: p.terminate()
            except: pass
        threading.Thread(target=killer, args=(proc,), daemon=True).start()

        # ФОРМИРУЕМ HTTP ССЫЛКУ (теперь браузер ее поймет)
        # Важно: используем urllib.parse.quote для пробелов в именах
        encoded_name = urllib.parse.quote(filename)
        download_url = f"http://{local_ip}:{free_port}/{encoded_name}"
        
        msg = {
            "type": "file_transfer", 
            "filename": filename,
            "url": download_url,
            "size": os.path.getsize(file_path)
        }
    
    except:
        pass
    
    # Отправляем через существующий вебсокет
    asyncio.run_coroutine_threadsafe(session.websocket.send_json(msg), running_loop)
    return True, "Transporter started"

# --- LOCAL API ДЛЯ GUI (LAUNCHER) ---
# Launcher будет дергать эти ручки, чтобы управлять сервером
class LocalFileRequest(BaseModel):
    token: str
    file_path: str

@app.post("/api/local/trigger_file")
def local_trigger_file(req: LocalFileRequest, request: Request):
    # Простейшая защита: разрешаем только с локалхоста
    if request.client.host != "127.0.0.1": raise HTTPException(403)
    ok, msg = trigger_file_send_logic(req.token, req.file_path)
    return {"ok": ok, "msg": msg}

@app.get("/api/local/info")
def local_info(request: Request):
    if request.client.host != "127.0.0.1": raise HTTPException(403)
    return {
        "pairing_code": PAIRING_CODE,
        "ip": get_local_ip(),
        "port": PORT,
        "devices": device_manager.get_all_devices()
    }

@app.post("/api/local/regenerate_code")
def regenerate_code(request: Request):
    if request.client.host != "127.0.0.1": raise HTTPException(403)
    global PAIRING_CODE
    PAIRING_CODE = str(uuid.uuid4().int)[:4]
    return {"new_code": PAIRING_CODE}

@app.post("/system/shutdown")
def system_shutdown(token: str = Depends(get_token)):
    os.system("shutdown /s /t 1")
    return {"status": "shutdown"}

@app.post("/system/lock")
def system_lock(token: str = Depends(get_token)):
    ctypes.windll.user32.LockWorkStation()
    return {"status": "locked"}

@app.post("/volume/{action}")
def volume_control(action: str, token: str = Depends(get_token)):
    keys = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
    if action in keys: pyautogui.press(keys[action])
    return {"status": "ok"}

def generate_video_stream():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            try:
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                cx, cy = pyautogui.position()
                rx, ry = cx - monitor["left"], cy - monitor["top"]
                draw = ImageDraw.Draw(img)
                draw.ellipse((rx-6, ry-6, rx+6, ry+6), fill="#00FF9D", outline="black")
                if img.width > 1280: img.thumbnail((1280, 720), Image.Resampling.NEAREST)
                buf = BytesIO()
                img.save(buf, format='JPEG', quality=30, optimize=False) 
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buf.getvalue() + b'\r\n')
                time.sleep(0.033) 
            except: pass

@app.get("/video_feed")
def video_feed(token: str = Depends(get_token)):
    return StreamingResponse(generate_video_stream(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket, token: str = Query(...)):
    if not device_manager.get_session(token):
        await websocket.close(code=4003); return
    await websocket.accept()
    device_manager.register_socket(token, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            t = data.get("type")
            if t == "move": pyautogui.moveRel(int(data['dx']), int(data['dy']), _pause=False)
            elif t == "click": pyautogui.click()
            elif t == "rclick": pyautogui.click(button='right')
            elif t == "dclick": pyautogui.doubleClick()
            elif t == "scroll": pyautogui.scroll(int(data['dy']))
            elif t == "drag_s": pyautogui.mouseDown()
            elif t == "drag_e": pyautogui.mouseUp()
            elif t == "text":
                text = data.get('text', '')
                if text:
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if hwnd:
                        for char in text:
                            ctypes.windll.user32.SendMessageW(hwnd, 0x0102, ord(char), 0)
            elif t == "key":
                key_map = { "enter": 0x0D, "backspace": 0x08, "space": 0x20, "win": 0x5B }
                val = data.get('key', '').lower()
                vk = key_map.get(val)
                if vk:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            elif t == "shortcut":
                act = data.get('action')
                if act == 'copy': pyautogui.hotkey('ctrl', 'c')
                elif act == 'paste': pyautogui.hotkey('ctrl', 'v')
    except WebSocketDisconnect: pass

if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)