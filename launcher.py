import os
import sys
import threading
import socket
import uvicorn
import tkinter as tk
from tkinter import messagebox
from PIL import Image
import pystray
import main 

from main import app, PERMISSIONS

PORT = 8000
HOST = "0.0.0.0"
VERSION = "v1.0.3"

server = None
server_thread = None
tray_icon = None

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: 
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except: IP = '127.0.0.1'
    finally: s.close()
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

COLORS = {
    "bg": "#121212",
    "fg": "#00ff9d",
    "btn": "#1e1e1e",
    "btn_hover": "#333333",
    "accent": "#00ff9d"
}

def apply_dark_theme(root):
    root.configure(bg=COLORS["bg"])

def on_close_window(root):
    root.destroy()

def show_about(parent):
    ab = tk.Toplevel(parent)
    ab.title("About")
    ab.geometry("300x200")
    ab.configure(bg=COLORS["bg"])
    
    tk.Label(ab, text=f"CyberDeck {VERSION}", font=("Courier New", 14, "bold"), 
             bg=COLORS["bg"], fg=COLORS["fg"]).pack(pady=20)
    
    tk.Label(ab, text="Created by: Overl1te\nStack: Python, FastAPI, JS\nLicense: GPLv3", 
             font=("Consolas", 10), bg=COLORS["bg"], fg="#888").pack(pady=10)
    
    tk.Button(ab, text="OK", command=ab.destroy, 
              bg=COLORS["btn"], fg="white", bd=0, padx=20).pack(pady=10)

def open_settings_window():
    root = tk.Tk()
    root.title(f"CyberDeck {VERSION}")
    root.geometry("400x550")
    apply_dark_theme(root)
    root.protocol("WM_DELETE_WINDOW", lambda: on_close_window(root))
    
    tk.Label(root, text="SERVER CONTROL", bg=COLORS["bg"], fg=COLORS["fg"], 
             font=("Courier New", 16, "bold")).pack(pady=20)
    
    ip = get_local_ip()
    link = f"http://{ip}:{PORT}"
    tk.Label(root, text=f"Connect via: {link}", bg=COLORS["bg"], fg="#fff", font=("Consolas", 10)).pack(pady=5)
    
    frame = tk.Frame(root, bg=COLORS["bg"], bd=2, relief="flat")
    frame.pack(fill="both", expand=True, padx=40, pady=20)
    
    def add_check(key, label_text):
        val = PERMISSIONS[key]
        var = tk.BooleanVar(value=val)
        def change(): PERMISSIONS[key] = var.get()
        
        cb = tk.Checkbutton(frame, text=label_text, variable=var, command=change,
                            bg=COLORS["bg"], fg=COLORS["fg"], selectcolor=COLORS["btn"],
                            activebackground=COLORS["bg"], activeforeground=COLORS["fg"],
                            font=("Consolas", 11), bd=0, highlightthickness=0)
        cb.pack(anchor="w", pady=8)

    add_check("screen", " [X] SCREEN SHARE")
    add_check("mouse_move", " [X] MOUSE MOVE")
    add_check("mouse_click", " [X] MOUSE CLICKS")
    add_check("keyboard", " [X] KEYBOARD INPUT")
    add_check("system", " [X] SYSTEM (OFF/VOL)")
    add_check("web", " [X] OPEN LINKS")
    
    btn_frame = tk.Frame(root, bg=COLORS["bg"])
    btn_frame.pack(side="bottom", pady=20)

    tk.Button(btn_frame, text="ABOUT", command=lambda: show_about(root),
              bg=COLORS["btn"], fg="#aaa", bd=0, padx=15, pady=5).pack(side="left", padx=10)
              
    tk.Button(btn_frame, text="HIDE", command=lambda: on_close_window(root),
              bg=COLORS["btn"], fg="white", bd=0, padx=20, pady=5).pack(side="left", padx=10)

    root.mainloop()

def show_ip_popup():
    root = tk.Tk()
    root.withdraw()
    ip = get_local_ip()
    messagebox.showinfo("IP Address", f"http://{ip}:{PORT}")
    root.destroy()

def create_image():
    if hasattr(sys, '_MEIPASS'): p = os.path.join(sys._MEIPASS, "icon.png")
    else: p = "icon.png"
    if os.path.exists(p): return Image.open(p)
    return Image.new('RGB', (64, 64), color=(0, 255, 157))

def on_exit(icon, item):
    icon.stop()
    if server: server.should_exit = True
    sys.exit(0)

def run_tray():
    global tray_icon
    image = create_image()
    menu = pystray.Menu(
        pystray.MenuItem("Settings", open_settings_window),
        pystray.MenuItem("Show IP", show_ip_popup),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", on_exit)
    )
    tray_icon = pystray.Icon("CyberDeck", image, "CyberDeck", menu)
    tray_icon.run()

if __name__ == "__main__":
    if "-c" in sys.argv:
        main.DEBUG_MODE = True
        
        if sys.platform == "win32":
            import ctypes
            try:
                ctypes.windll.kernel32.AllocConsole()
                sys.stdout = open("CONOUT$", "w", encoding="utf-8")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8")
            except Exception as e:
                pass

        print("==========================================")
        print("   CYBERDECK DEBUG MODE ENABLED (-c)      ")
        print("   Debug window allocated.                ")
        print("==========================================")

    try:
        start_server()
        run_tray()
    except Exception as e:
        if "-c" in sys.argv:
            print(f"\n[CRITICAL ERROR] Failed to start: {e}")
            import traceback
            traceback.print_exc()
            print("\nPress Enter to exit...")
            input() 
        else:
            try:
                messagebox.showerror("Critical Error", f"Failed to start:\n{e}")
            except: pass
        sys.exit(1)