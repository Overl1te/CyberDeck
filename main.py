import random as rnd_module
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pyautogui
import io
import os
import sys
import webbrowser
import psutil
from mss import mss
from PIL import Image
import base64
import subprocess
import time
import ctypes
import threading 

# --- НАСТРОЙКИ ---

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False 

app = FastAPI(title="CyberDeck v1.0.3")


# 1. Разрешаем cors
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Генерируем код
SESSION_CODE = str(rnd_module.randint(1000, 9999))
print(f" --- PAIRING CODE: {SESSION_CODE} --- ")

# Модель для приема кода
class HandshakeRequest(BaseModel):
    code: str

# 3. Проверка кода на вшивость)
@app.post("/api/handshake")
def handshake(req: HandshakeRequest):
    if req.code == SESSION_CODE:
        return {"status": "ok", "device": os.environ.get('COMPUTERNAME', 'Unknown PC')}
    else:
        raise HTTPException(status_code=403, detail="Invalid Code")

PERMISSIONS = {
    "mouse_move": True, "mouse_click": True, "keyboard": True,
    "screen": True, "system": True, "web": True
}

DEBUG_MODE = False
INPUT_LOCK = threading.Lock() 

def debug_log(category: str, message: str):
    if DEBUG_MODE:
        print(f"[{category.upper()}] {message}")

def get_resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def send_ctrl_v_robust():
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(0x11, 0, 0, 0) 
        time.sleep(0.05)
        user32.keybd_event(0x56, 0, 0, 0) 
        time.sleep(0.05)
        user32.keybd_event(0x56, 0, 2, 0) 
        user32.keybd_event(0x11, 0, 2, 0) 
    except Exception as e:
        debug_log("INPUT", f"Native input failed: {e}")

def set_clipboard(text):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]

    try:
        try: user32.CloseClipboard()
        except: pass

        success = False
        for _ in range(5):
            if user32.OpenClipboard(None):
                user32.EmptyClipboard()
                text_bytes = text.encode('utf-16le') + b'\x00\x00'
                h_mem = kernel32.GlobalAlloc(0x0002, len(text_bytes))
                
                if h_mem:
                    p_mem = kernel32.GlobalLock(h_mem)
                    if p_mem:
                        ctypes.memmove(p_mem, text_bytes, len(text_bytes))
                        kernel32.GlobalUnlock(h_mem)
                        if user32.SetClipboardData(13, h_mem):
                            success = True
                user32.CloseClipboard()
                if success: return True
                break
            time.sleep(0.05)
    except Exception as e:
        debug_log("CLIPBOARD", f"Ctypes Crash: {e}")

    debug_log("CLIPBOARD", "Using PowerShell fallback...")
    try:
        b64_text = base64.b64encode(text.encode('utf-16le')).decode()
        ps_cmd = f"$t = [System.Text.Encoding]::Unicode.GetString([System.Convert]::FromBase64String('{b64_text}')); Set-Clipboard -Value $t"
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            timeout=5, startupinfo=startupinfo, creationflags=0x08000000
        )
        time.sleep(0.5) 
        return True
    except Exception as e:
        debug_log("CLIPBOARD", f"PowerShell failed: {e}")
        return False


def generate_video_stream():
    if not PERMISSIONS["screen"]:
        yield (b'--frame\r\nContent-Type: text/plain\r\n\r\nACCESS DENIED\r\n')
        return

    while True:
        try:
            with mss() as sct:
                monitor = sct.monitors[1]
                
                while True:
                    if not PERMISSIONS["screen"]: 
                        time.sleep(1)
                        continue

                    sct_img = sct.grab(monitor)
                    
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    
                    img.thumbnail((1280, 720), Image.Resampling.NEAREST) 

                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG', quality=25, optimize=True) 
                    
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + img_byte_arr.getvalue() + b'\r\n')
                    
        except GeneratorExit:
            debug_log("STREAM", "Client disconnected")
            break
        except Exception as e:
            debug_log("STREAM_ERR", f"MSS Crash: {e} -> Reinitializing...")
            time.sleep(0.5)
            
@app.post("/open-url")
def open_url(url: str):
    debug_log("WEB", f"Opening URL: {url}")
    if PERMISSIONS["web"]: webbrowser.open(url)

@app.post("/volume/{action}")
def volume_control(action: str):
    debug_log("SYSTEM", f"Volume: {action}")
    if not PERMISSIONS["system"]: return
    
    with INPUT_LOCK:
        keys = {"up": "volumeup", "down": "volumedown", "mute": "volumemute"}
        if action in keys: pyautogui.press(keys[action])

@app.post("/system/shutdown")
def shutdown_pc():
    debug_log("SYSTEM", "Shutdown initiated")
    if PERMISSIONS["system"]: os.system("shutdown /s /t 1")

@app.get("/api/stats")
async def get_system_stats():
    return {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent}

class TextInput(BaseModel):
    text: str

@app.post("/keyboard/type")
def type_text(payload: TextInput):
    if not PERMISSIONS["keyboard"]: return {"status": "denied"}
    
    content = payload.text
    debug_log("KEYBOARD", f"Received: '{content}'")
    if not content: return {"status": "empty"}

    with INPUT_LOCK:
        if set_clipboard(content):
            debug_log("KEYBOARD", "Clipboard SET. Pasting...")
            time.sleep(0.3) 
            send_ctrl_v_robust()
            debug_log("KEYBOARD", "Paste command sent.")
            return {"status": "pasted", "length": len(content)}
        
    debug_log("KEYBOARD", "FAIL: Clipboard could not be set")
    return {"status": "clipboard_error"}

@app.post("/keyboard/key/{key_name}")
def press_key(key_name: str):
    if not PERMISSIONS["keyboard"]: return {"status": "denied"}
    debug_log("KEYBOARD", f"Pressing Key: {key_name}")
    
    valid = ['enter', 'backspace', 'esc', 'space', 'tab', 'win', 'up', 'down', 'left', 'right']
    
    if key_name in valid:
        with INPUT_LOCK: 
            pyautogui.keyDown(key_name)
            time.sleep(0.05)
            pyautogui.keyUp(key_name)
        return {"status": "pressed", "key": key_name}
        
    return {"status": "invalid_key"}

@app.post("/keyboard/shortcut/{name}")
def hotkey(name: str):
    if not PERMISSIONS["keyboard"]: return {"status": "denied"}
    debug_log("SHORTCUT", f"Action: {name}")
    
    with INPUT_LOCK: 
        time.sleep(0.05)
        if name == "alt_tab": pyautogui.hotkey('alt', 'tab')
        elif name == "win_d": pyautogui.hotkey('win', 'd')
        elif name == "copy": 
            ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
            ctypes.windll.user32.keybd_event(0x43, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x43, 0, 2, 0)
            ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
        elif name == "paste": 
            send_ctrl_v_robust()
        elif name == "task_manager": pyautogui.hotkey('ctrl', 'shift', 'esc')
        else: return {"status": "unknown"}
        
    return {"status": "executed", "action": name}

@app.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket):
    await websocket.accept()
    sensitivity = 1.8  
    scroll_speed = 3
    debug_log("MOUSE", "Client Connected")

    try:
        while True:
            data = await websocket.receive_json()
            
            if not PERMISSIONS["mouse_move"] and "dx" in data: continue
            if not PERMISSIONS["mouse_click"] and "type" in data: continue

            t = data.get("type")
            
            if t in ["click", "right_click", "double_click", "drag_start", "drag_end", "scroll"]:
                with INPUT_LOCK:
                    if t == "click": 
                        pyautogui.mouseDown()
                        time.sleep(0.02)
                        pyautogui.mouseUp()
                    elif t == "right_click": 
                        pyautogui.mouseDown(button='right')
                        time.sleep(0.02)
                        pyautogui.mouseUp(button='right')
                    elif t == "double_click": 
                        pyautogui.doubleClick()
                    elif t == "drag_start": pyautogui.mouseDown()
                    elif t == "drag_end": pyautogui.mouseUp()
                    elif t == "scroll": pyautogui.scroll(int(data.get("dy", 0) * scroll_speed))
            
            elif "dx" in data:
                dx = int(data.get('dx', 0) * sensitivity)
                dy = int(data.get('dy', 0) * sensitivity)
                if dx != 0 or dy != 0: pyautogui.moveRel(dx, dy, _pause=False)
            
    except WebSocketDisconnect: debug_log("MOUSE", "Client Disconnected")

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        generate_video_stream(), 
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"} 
    )

static_path = get_resource_path("static")
if not os.path.exists(static_path): static_path = "static" 
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_path, 'index.html'))