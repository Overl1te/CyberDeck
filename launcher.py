import os
import sys
import threading
import webbrowser
import socket
import uvicorn
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray

from main import app

# --- НАСТРОЙКИ ---
PORT = 8000
HOST = "0.0.0.0"

# Глобальные переменные для контроля сервера
server = None
server_thread = None
tray_icon = None

# --- 1. ПОЛУЧЕНИЕ ЛОКАЛЬНОГО IP ---
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

# --- 2. КЛАСС СЕРВЕРА ---
class UvicornServer(uvicorn.Server):
    def install_signal_handlers(self):
        pass # Переопределяем, чтобы uvicorn не воровал сигналы закрытия у Windows

    def run_in_thread(self):
        self.run()

def start_server():
    global server, server_thread
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="critical", log_config=None)
    
    server = UvicornServer(config=config)
    server_thread = threading.Thread(target=server.run_in_thread, daemon=True)
    server_thread.start()

# --- 3. ГРАФИЧЕСКИЙ ИНТЕРФЕЙС ---
def show_settings():
    root = tk.Tk()
    root.withdraw()
    
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    
    msg = (f"CyberDeck Server запущен!\n\n"
           f"IP адрес для телефона:\n{url}\n\n"
           f"1. Открой браузер на телефоне.\n"
           f"2. Введи этот адрес.\n"
           f"3. Управляй ПК")
    
    messagebox.showinfo("CyberDeck Info", msg)
    root.destroy()

# --- 4. СИСТЕМНЫЙ ТРЕЙ ---
def create_image():
    # Проверяем наличие иконки, учитывая временную папку PyInstaller
    if hasattr(sys, '_MEIPASS'):
        icon_path = os.path.join(sys._MEIPASS, "icon.png")
    else:
        icon_path = "icon.png"

    if os.path.exists(icon_path):
        return Image.open(icon_path)
    
    width = 64
    height = 64
    image = Image.new('RGB', (width, height), color=(0, 255, 157))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(0, 0, 0))
    return image

def on_exit(icon, item):
    icon.stop()
    if server:
        server.should_exit = True
    sys.exit(0)

def run_tray():
    global tray_icon
    image = create_image()
    
    menu = pystray.Menu(
        pystray.MenuItem("Информация / IP", show_settings),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выход", on_exit)
    )
    
    tray_icon = pystray.Icon("CyberDeck", image, "CyberDeck Control", menu)
    tray_icon.run()

if __name__ == "__main__":
    start_server()
    run_tray()