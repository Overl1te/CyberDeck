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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Optional
from io import BytesIO
from PIL import Image, ImageDraw

VERSION = "v1.1.1"
HOST = "0.0.0.0"
PORT = 8080
UDP_PORT = 5555
DEBUG = True 

running_loop = None 

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FILES_DIR = os.path.join(BASE_DIR, "CyberDeck_Files")
SESSION_FILE = os.path.join(BASE_DIR, "cyberdeck_sessions.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

if not os.path.exists(FILES_DIR): os.makedirs(FILES_DIR)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

PAIRING_CODE = str(uuid.uuid4().int)[:4]
SERVER_ID = str(uuid.uuid4())[:8]
HOSTNAME = os.environ.get('COMPUTERNAME', 'CyberDeck PC')

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
    """Захватываем цикл событий при старте сервера"""
    global running_loop
    running_loop = asyncio.get_running_loop()
    if DEBUG: print(f"Server Event Loop Captured: {running_loop}")

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
        print(f"Upload Error: {e}")
        return {"status": "error", "detail": str(e)}

@app.get("/api/file/download/{filename}")
def download_file(filename: str, token: str = Depends(get_token)):
    path = os.path.join(FILES_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, filename=filename)
    raise HTTPException(404, "File not found")

def trigger_file_send(device_token: str, file_path: str):
    global running_loop
    session = device_manager.get_session(device_token)
    
    if not session or not session.websocket: 
        return False, "Device offline"
    
    try:
        filename = os.path.basename(file_path)
        dest_path = os.path.join(FILES_DIR, filename)
        if file_path != dest_path:
            shutil.copy2(file_path, dest_path)
        
        msg = {
            "type": "file_transfer", 
            "filename": filename,
            "url": f"/api/file/download/{filename}?token={device_token}",
            "size": os.path.getsize(file_path)
        }

        if running_loop and running_loop.is_running():
            running_loop.call_soon_threadsafe(
                lambda: asyncio.create_task(session.websocket.send_json(msg))
            )
            return True, "Transfer init"
        else:
            return False, "Server loop not ready"
            
    except Exception as e: 
        return False, str(e)

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
                
                time.sleep(0.03)
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
                text_to_send = data.get('text', '')
                if text_to_send:
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    if hwnd:
                        for char in text_to_send:
                            ctypes.windll.user32.SendMessageW(hwnd, 0x0102, ord(char), 0)
            elif t == "key":
                key_map = {
                    "enter": 0x0D, "backspace": 0x08, "tab": 0x09, 
                    "esc": 0x1B, "space": 0x20, "win": 0x5B
                }
                val = data.get('key', '').lower()
                vk = key_map.get(val)
                if vk:
                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                
    except WebSocketDisconnect: pass

if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)