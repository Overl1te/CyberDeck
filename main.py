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

# Отключаем задержку pyautogui
pyautogui.PAUSE = 0

app = FastAPI(title="PC Remote Control")

# --- ФУНКЦИЯ ПОИСКА ПУТЕЙ ---
def get_resource_path(relative_path):
    """ Получает абсолютный путь к ресурсу, работает и для dev, и для PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- ВИДЕО ПОТОК ---
def generate_video_stream():
    with mss() as sct:
        # Обычно monitors[1] - это основной.
        monitor = sct.monitors[1]
        while True:
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            mouse_x, mouse_y = pyautogui.position()
            
            draw = ImageDraw.Draw(img)
            r = 10 
            draw.line((mouse_x - r, mouse_y, mouse_x + r, mouse_y), fill="red", width=3)
            draw.line((mouse_x, mouse_y - r, mouse_x, mouse_y + r), fill="red", width=3)

            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=45)
            img_bytes = img_byte_arr.getvalue()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')

# --- ЭНДПОИНТЫ ---            
@app.get("/screenshot")
def get_screenshot():
    screenshot = pyautogui.screenshot()
    img_byte_arr = io.BytesIO()
    screenshot.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return StreamingResponse(img_byte_arr, media_type="image/png")

@app.post("/open-url")
def open_url(url: str):
    webbrowser.open(url)
    return {"status": "opened", "url": url}

@app.post("/volume/{action}")
def volume_control(action: str):
    if action == "up":
        pyautogui.press("volumeup")
    elif action == "down":
        pyautogui.press("volumedown")
    elif action == "mute":
        pyautogui.press("volumemute")
    else:
        return {"error": "unknown action"}
    return {"status": "success", "action": action}

@app.post("/system/shutdown")
def shutdown_pc():
    os.system("shutdown /s /t 1")
    return {"status": "Bye bye"}

@app.get("/api/stats")
async def get_system_stats():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    return {"cpu": cpu, "ram": ram}

@app.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket):
    await websocket.accept()
    sensitivity = 1.5 
    scroll_speed = 5
    
    try:
        while True:
            data = await websocket.receive_json()
            if "type" in data:
                if data["type"] == "click":
                    pyautogui.click()
                elif data["type"] == "right_click":
                    pyautogui.rightClick()
                elif data["type"] == "double_click":
                    pyautogui.doubleClick()
                elif data["type"] == "scroll":
                    dy = data.get("dy", 0)
                    pyautogui.scroll(int(dy * scroll_speed))
            else:
                dx = data.get('dx', 0) * sensitivity
                dy = data.get('dy', 0) * sensitivity
                pyautogui.moveRel(dx, dy, _pause=False)
            
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        generate_video_stream(), 
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


static_path = get_resource_path("static")

if not os.path.exists(static_path):
    static_path = "static" 

app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def read_index():
    return FileResponse(os.path.join(static_path, 'index.html'))