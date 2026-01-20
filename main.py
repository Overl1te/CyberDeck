from fastapi import FastAPI, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import WebSocket
import pyautogui
import io
import os
import webbrowser
import psutil
from PIL import Image, ImageDraw
from mss import mss

app = FastAPI(title="PC Remote Control")

def generate_video_stream():
    # mss - самая быстрая библиотека для захвата
    with mss() as sct:
        # Берем первый монитор. Если у тебя их два и курсор на втором - может быть смещение.
        # Обычно monitors[1] - это основной.
        monitor = sct.monitors[1]
        
        while True:
            # 1. Захват экрана
            sct_img = sct.grab(monitor)
            
            # 2. Превращаем в картинку, на которой можно рисовать
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # 3. Узнаем, где сейчас мышка
            mouse_x, mouse_y = pyautogui.position()
            
            # 4. Рисуем курсор (Красный прицел)
            draw = ImageDraw.Draw(img)
            
            # Размер перекрестия
            r = 10 
            # Рисуем линии (Красный цвет #FF0000, толщина 3px)
            # Горизонтальная
            draw.line((mouse_x - r, mouse_y, mouse_x + r, mouse_y), fill="red", width=3)
            # Вертикальная
            draw.line((mouse_x, mouse_y - r, mouse_x, mouse_y + r), fill="red", width=3)

            # 5. Сохраняем в JPEG
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=45) # Качество 45 для скорости
            img_bytes = img_byte_arr.getvalue()

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + img_bytes + b'\r\n')
            
# 1. Получить скриншот экрана в реальном времени
@app.get("/screenshot")
def get_screenshot():
    # Делаем скрин
    screenshot = pyautogui.screenshot()
    
    # Сохраняем его в оперативную память
    img_byte_arr = io.BytesIO()
    screenshot.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    # Отдаем как картинку
    return StreamingResponse(img_byte_arr, media_type="image/png")

# 2. Открыть любую ссылку
@app.post("/open-url")
def open_url(url: str):
    webbrowser.open(url)
    return {"status": "opened", "url": url}

# 3. Управление громкостью
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

# 4. Выключить комп
@app.post("/system/shutdown")
def shutdown_pc():
    os.system("shutdown /s /t 1")
    return {"status": "Bye bye"}

# 5. Получить статистику по компу 
@app.get("/api/stats")
async def get_system_stats():
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    return {"cpu": cpu, "ram": ram}

# 6. Управление курсором
@app.websocket("/ws/mouse")
async def websocket_mouse(websocket: WebSocket):
    await websocket.accept()
    sensitivity = 1.5 
    scroll_speed = 5
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # --- КОМАНДЫ (КЛИКИ И СКРОЛЛ) ---
            if "type" in data:
                if data["type"] == "click":
                    pyautogui.click()
                elif data["type"] == "right_click":
                    pyautogui.rightClick()
                elif data["type"] == "double_click":
                    pyautogui.doubleClick()
                
                # ЛОГИКА СКРОЛЛА
                elif data["type"] == "scroll":
                    # Получаем смещение по вертикали
                    dy = data.get("dy", 0)
                    # pyautogui.scroll: Положительное число = вверх, Отрицательное = вниз.
                    # Умножаем на scroll_speed, чтобы крутилось бодрее.
                    pyautogui.scroll(int(dy * scroll_speed))

            # --- ОБЫЧНОЕ ДВИЖЕНИЕ КУРСОРА ---
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

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('static/index.html')