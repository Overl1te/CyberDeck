from fastapi import FastAPI, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import WebSocket
import pyautogui
import io
import os
import sys
import webbrowser
import psutil
from PIL import Image, ImageDraw
from mss import mss
import time
import ctypes

# Настройки PyAutoGUI
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False 

app = FastAPI(title="PC Remote Control")

# --- ГЛОБАЛЬНЫЕ ПРАВА ---
PERMISSIONS = {
    "mouse_move": True,
    "mouse_click": True,
    "keyboard": True,
    "screen": True,
    "system": True,
    "web": True
}

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def set_clipboard(text):
    try:
        # Открываем буфер
        ctypes.windll.user32.OpenClipboard(0)
        # Очищаем
        ctypes.windll.user32.EmptyClipboard()
        
        # Кодируем текст в UTF-16 (стандарт Windows)
        text_bytes = text.encode('utf-16le') + b'\x00\x00'
        
        # Выделяем память
        h_mem = ctypes.windll.kernel32.GlobalAlloc(0x0002, len(text_bytes))
        p_mem = ctypes.windll.kernel32.GlobalLock(h_mem)
        
        # Копируем байты в память
        ctypes.memmove(p_mem, text_bytes, len(text_bytes))
        
        # Разблокируем память и устанавливаем данные
        ctypes.windll.kernel32.GlobalUnlock(h_mem)
        # 13 = CF_UNICODETEXT
        ctypes.windll.user32.SetClipboardData(13, h_mem)
        
        # Закрываем буфер
        ctypes.windll.user32.CloseClipboard()
        return True
    except Exception as e:
        print(f"Clipboard Error: {e}")
        return False

# --- ВИДЕО ПОТОК ---
def generate_video_stream():
    if not PERMISSIONS["screen"]:
        yield (b'--frame\r\nContent-Type: text/plain\r\n\r\nACCESS DENIED\r\n')
        return

    with mss() as sct:
        monitor = sct.monitors[1]
        while True:
            if not PERMISSIONS["screen"]:
                time.sleep(1)
                continue

            try:
                start_time = time.time()
                
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                mouse_x, mouse_y = pyautogui.position()
                draw = ImageDraw.Draw(img)
                l = 10
                draw.line((mouse_x - l, mouse_y, mouse_x + l, mouse_y), fill="red", width=2)
                draw.line((mouse_x, mouse_y - l, mouse_x, mouse_y + l), fill="red", width=2)

                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=40) 
                img_bytes = img_byte_arr.getvalue()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')
                
                elapsed = time.time() - start_time
                wait = 0.033 - elapsed
                if wait > 0: time.sleep(wait)
                
            except Exception:
                break 

# --- API ---
@app.post("/open-url")
def open_url(url: str):
    if not PERMISSIONS["web"]: return {"status": "denied"}
    webbrowser.open(url)
    return {"status": "opened"}

@app.post("/volume/{action}")
def volume_control(action: str):
    if not PERMISSIONS["system"]: return {"status": "denied"}
    if action == "up": pyautogui.press("volumeup")
    elif action == "down": pyautogui.press("volumedown")
    elif action == "mute": pyautogui.press("volumemute")
    return {"status": "ok"}

@app.post("/system/shutdown")
def shutdown_pc():
    if not PERMISSIONS["system"]: return {"status": "denied"}
    os.system("shutdown /s /t 1")
    return {"status": "bye"}

@app.get("/api/stats")
async def get_system_stats():
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent
    }

# --- ВВОД ТЕКСТА ---
@app.post("/keyboard/type")
def type_text(payload: dict):
    if not PERMISSIONS["keyboard"]: return {"status": "denied"}
    
    text = payload.get("text", "")
    if text:
        success = set_clipboard(text)
        
        if success:
            time.sleep(0.1)
            
            pyautogui.keyDown('ctrl')
            pyautogui.press('v')
            pyautogui.keyUp('ctrl')
            
    return {"status": "typed"}

@app.post("/keyboard/key/{key_name}")
def press_key(key_name: str):
    if not PERMISSIONS["keyboard"]: return {"status": "denied"}
    
    valid_keys = ['enter', 'backspace', 'esc', 'space', 'tab', 'win', 'up', 'down', 'left', 'right']
    if key_name in valid_keys:
        pyautogui.press(key_name)
    return {"status": "pressed"}

@app.post("/keyboard/shortcut/{name}")
def hotkey(name: str):
    if not PERMISSIONS["keyboard"]: return {"status": "denied"}
    
    if name == "alt_tab": pyautogui.hotkey('alt', 'tab')
    elif name == "win_d": pyautogui.hotkey('win', 'd')
    elif name == "copy": pyautogui.hotkey('ctrl', 'c')
    elif name == "paste": pyautogui.hotkey('ctrl', 'v')
    elif name == "task_manager": pyautogui.hotkey('ctrl', 'shift', 'esc')
    return {"status": "executed"}

# --- МЫШЬ ---
@app.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket):
    await websocket.accept()
    
    sensitivity = 1.5  
    scroll_speed = 5

    try:
        while True:
            data = await websocket.receive_json()
            cmd_type = data.get("type")
            
            if not PERMISSIONS["mouse_click"] and cmd_type in ["click", "right_click", "double_click", "drag_start", "drag_end"]: continue
            if not PERMISSIONS["mouse_move"] and ("dx" in data or cmd_type == "scroll"): continue

            if cmd_type == "click": pyautogui.click()
            elif cmd_type == "right_click": pyautogui.rightClick()
            elif cmd_type == "double_click": pyautogui.doubleClick()
            elif cmd_type == "drag_start": pyautogui.mouseDown()
            elif cmd_type == "drag_end": pyautogui.mouseUp()
            
            elif cmd_type == "scroll":
                dy = data.get("dy", 0)
                pyautogui.scroll(int(dy * scroll_speed))
            
            elif "dx" in data:
                dx = data.get('dx', 0) * sensitivity
                dy = data.get('dy', 0) * sensitivity
                pyautogui.moveRel(int(dx), int(dy), _pause=False)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"Mouse Error: {e}")

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        generate_video_stream(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

static_path = get_resource_path("static")
if not os.path.exists(static_path): static_path = "static" 
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_path, 'index.html'))