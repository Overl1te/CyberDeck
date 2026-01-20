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

from main import app, PERMISSIONS

PORT = 8000
HOST = "0.0.0.0"

server = None
server_thread = None
tray_icon = None

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

class UvicornServer(uvicorn.Server):
    def install_signal_handlers(self): pass
    def run_in_thread(self): self.run()

def start_server():
    global server, server_thread
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="critical", log_config=None)
    server = UvicornServer(config=config)
    server_thread = threading.Thread(target=server.run_in_thread, daemon=True)
    server_thread.start()

# --- GUI ---
def on_close_window(root):
    root.destroy()

def open_settings_window():
    root = tk.Tk()
    root.title("CyberDeck Settings")
    root.geometry("350x500")
    root.configure(bg="#050505")
    root.protocol("WM_DELETE_WINDOW", lambda: on_close_window(root))
    
    STYLE_FG = "#00ff9d"
    STYLE_BG = "#050505"
    FONT_HEADER = ("Courier New", 14, "bold")
    FONT_BODY = ("Consolas", 10)

    tk.Label(root, text="ACCESS CONTROL", bg=STYLE_BG, fg=STYLE_FG, font=FONT_HEADER).pack(pady=20)
    
    frame = tk.Frame(root, bg=STYLE_BG)
    frame.pack(fill="both", expand=True, padx=40)

    def add_check(key, text):
        # Читаем текущее значение
        current_val = PERMISSIONS[key]
        var = tk.BooleanVar(value=current_val)
        
        def on_change():
            PERMISSIONS[key] = var.get()
            print(f"[DEBUG] '{key}' -> {var.get()}")

        cb = tk.Checkbutton(frame, text=text, variable=var, command=on_change,
                            bg=STYLE_BG, fg=STYLE_FG, selectcolor="#1a1a1a",
                            activebackground=STYLE_BG, activeforeground=STYLE_FG,
                            font=FONT_BODY, highlightthickness=0, bd=0)
        cb.pack(anchor="w", pady=5)
    
    add_check("screen", "[ ] SCREEN SHARE")
    add_check("mouse_move", "[ ] MOUSE MOVEMENT")
    add_check("mouse_click", "[ ] MOUSE CLICKS")
    add_check("keyboard", "[ ] KEYBOARD INPUT")
    add_check("system", "[ ] POWER & VOLUME")
    add_check("web", "[ ] OPEN URLS")
    
    ip = get_local_ip()
    tk.Label(root, text=f"HOST: {ip}:{PORT}", bg=STYLE_BG, fg="#555", font=("Consolas", 8)).pack(side="bottom", pady=5)
    tk.Button(root, text="CLOSE", command=lambda: on_close_window(root), bg="#1a1a1a", fg="white", bd=0, padx=20, pady=5).pack(side="bottom", pady=10)

    root.mainloop()

def show_info_popup():
    root = tk.Tk()
    root.title("Info")
    root.protocol("WM_DELETE_WINDOW", lambda: on_close_window(root))
    root.withdraw()
    
    ip = get_local_ip()
    msg = f"Web Interface: http://{ip}:{PORT}"
    messagebox.showinfo("CyberDeck", msg)
    
    root.destroy()

def create_image():
    if hasattr(sys, '_MEIPASS'):
        icon_path = os.path.join(sys._MEIPASS, "icon.png")
    else:
        icon_path = "icon.png"
    if os.path.exists(icon_path): return Image.open(icon_path)
    return Image.new('RGB', (64, 64), color=(0, 255, 157))

def on_exit(icon, item):
    icon.stop()
    if server: server.should_exit = True
    sys.exit(0)

def run_tray():
    global tray_icon
    image = create_image()
    menu = pystray.Menu(
        pystray.MenuItem("Settings / Access", open_settings_window),
        pystray.MenuItem("Show IP", show_info_popup),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit)
    )
    tray_icon = pystray.Icon("CyberDeck", image, "CyberDeck", menu)
    tray_icon.run()

if __name__ == "__main__":
    start_server()
    run_tray()