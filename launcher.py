import customtkinter as ctk
import threading
import sys
import os
import socket
import ctypes
import subprocess
import pystray
import psutil
import time
import requests
from PIL import Image
from tkinter import filedialog

# --- КОНФИГ ---
SERVER_SCRIPT_NAME = "main.py"
PORT = 8080
API_URL = f"http://127.0.0.1:{PORT}/api/local"

# --- GUI СТИЛЬ ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

COLOR_BG = "#050505"
COLOR_PANEL = "#111111"
COLOR_ACCENT = "#00FF41" 
COLOR_FAIL = "#FF3333"
COLOR_TEXT_DIM = "#555555"
FONT_MAIN = ("Consolas", 14)
FONT_BOLD = ("Consolas", 14, "bold")
FONT_HEADER = ("Consolas", 24, "bold")

class CyberBtn(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=0, border_width=1, border_color=COLOR_ACCENT, 
                         fg_color="transparent", text_color=COLOR_ACCENT, hover_color=COLOR_ACCENT,
                         font=FONT_BOLD, **kwargs)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        if not self.is_admin():
            self.run_as_admin()
            sys.exit()

        self.title("CYBERDECK")
        self.geometry("950x650")
        self.configure(fg_color=COLOR_BG)
        self.protocol("WM_DELETE_WINDOW", self.quit_app)

        if getattr(sys, 'frozen', False): 
            self.base_dir = os.path.dirname(sys.executable)
            self.server_exe = os.path.join(self.base_dir, "main.exe")
        else: 
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self.server_exe = os.path.join(self.base_dir, "main.py")

        self.icon_path = os.path.join(self.base_dir, "icon.png")
        if os.path.exists(self.icon_path):
            try: self.iconbitmap(self.icon_path)
            except: pass

        self.server_process = None
        self.devices_data = [] # Список устройств с сервера
        self.selected_token = None
        self.pairing_code = "...."
        
        self.setup_ui()
        self.start_server_process()
        
        # Запускаем цикл обновления данных с сервера (каждые 2 сек)
        self.after(2000, self.sync_loop)
        
        threading.Thread(target=self.setup_tray, daemon=True).start()

    def is_admin(self):
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False

    def run_as_admin(self):
        if getattr(sys, 'frozen', False): executable = sys.executable; args = ""
        else: executable = sys.executable; args = f'"{__file__}"'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, args, None, 1)

    def start_server_process(self):
        self.kill_old_server()
        cmd = [sys.executable, self.server_exe] if not getattr(sys, 'frozen', False) else [self.server_exe]
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        try:
            self.server_process = subprocess.Popen(
                cmd, cwd=self.base_dir, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            print(f"Error starting server: {e}")

    def kill_old_server(self):
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.net_connections(kind='inet'):
                    if conn.laddr.port == PORT:
                        proc.kill()
            except: continue

    # --- СИНХРОНИЗАЦИЯ С СЕРВЕРОМ ---
    def sync_loop(self):
        """Опрашивает локальный API сервера и обновляет GUI"""
        def _fetch():
            try:
                resp = requests.get(f"{API_URL}/info", timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    self.pairing_code = data.get("pairing_code", "ERR")
                    self.devices_data = data.get("devices", [])
                    # Обновляем GUI в главном потоке
                    self.after(0, self.update_gui_data)
            except: pass # Сервер еще грузится или упал
            
        threading.Thread(target=_fetch, daemon=True).start()
        self.after(2000, self.sync_loop)

    def update_gui_data(self):
        # 1. Обновляем код
        self.lbl_code.configure(text=self.pairing_code)
        
        # 2. Обновляем список устройств
        for w in self.device_list.winfo_children(): w.destroy()
        
        if not self.devices_data:
            ctk.CTkLabel(self.device_list, text="[NO CONNECTIONS]", text_color="#333", font=("Consolas", 12)).pack(pady=20)
        else:
            for d in self.devices_data:
                row = ctk.CTkFrame(self.device_list, fg_color="#111", corner_radius=0)
                row.pack(fill="x", pady=2)
                
                is_sel = (self.selected_token == d['token'])
                col = COLOR_ACCENT if is_sel else "#333"
                
                ctk.CTkCanvas(row, width=5, height=40, bg=col, highlightthickness=0).pack(side="left")
                ctk.CTkLabel(row, text=f"{d['name']} :: {d['ip']}", font=("Consolas", 12), text_color="white").pack(side="left", padx=10)
                
                btn_txt = "LINKED" if is_sel else "SELECT"
                btn_fg = COLOR_ACCENT if is_sel else "transparent"
                btn_txt_col = "black" if is_sel else COLOR_ACCENT
                
                ctk.CTkButton(row, text=btn_txt, width=80, corner_radius=0, fg_color=btn_fg, 
                              border_width=1, border_color=COLOR_ACCENT, text_color=btn_txt_col,
                              command=lambda t=d['token']: self.select_device(t)).pack(side="right", padx=10, pady=5)

    def select_device(self, token):
        self.selected_token = token
        self.lbl_status.configure(text="> TARGET LOCKED", text_color=COLOR_ACCENT)
        # Принудительно обновляем список, чтобы перерисовать кнопки
        self.update_gui_data()

    def send_file(self):
        if not self.selected_token:
            self.lbl_status.configure(text="> NO TARGET SELECTED", text_color=COLOR_FAIL)
            return
            
        path = filedialog.askopenfilename()
        if not path: return

        def _bg_send():
            self.lbl_status.configure(text="> REQUESTING TRANSFER...", text_color="yellow")
            try:
                # Шлем запрос на наш же сервер через локальный API
                payload = {"token": self.selected_token, "file_path": path}
                resp = requests.post(f"{API_URL}/trigger_file", json=payload)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        self.lbl_status.configure(text="> TRANSFER STARTED", text_color=COLOR_ACCENT)
                    else:
                        self.lbl_status.configure(text=f"> ERROR: {data.get('msg')}", text_color=COLOR_FAIL)
                else:
                    self.lbl_status.configure(text="> API ERROR", text_color=COLOR_FAIL)
            except Exception as e:
                self.lbl_status.configure(text=f"> CRASH: {e}", text_color=COLOR_FAIL)

        threading.Thread(target=_bg_send, daemon=True).start()

    def regenerate_code_action(self):
        def _req():
            try: requests.post(f"{API_URL}/regenerate_code")
            except: pass
        threading.Thread(target=_req, daemon=True).start()

    # --- UI SETUP ---
    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=COLOR_PANEL)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        ctk.CTkLabel(self.sidebar, text="CYBER", font=("Impact", 32), text_color="white").grid(row=0, column=0, padx=20, pady=(30, 0), sticky="w")
        ctk.CTkLabel(self.sidebar, text="DECK_CONTROL", font=("Consolas", 14), text_color=COLOR_ACCENT).grid(row=1, column=0, padx=22, pady=(0, 30), sticky="w")

        self.btn_home = self.create_nav_btn("TERMINAL", "home", 2)
        self.btn_devices = self.create_nav_btn("UPLINK", "devices", 3)
        
        # Frames
        self.home_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.devices_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        
        self.setup_home()
        self.setup_devices()
        self.select_frame("home")

    def create_nav_btn(self, text, name, row):
        cmd = lambda: self.select_frame(name)
        btn = ctk.CTkButton(self.sidebar, text=f"> {text}", fg_color="transparent", text_color="gray",
                            hover_color="#1a1a1a", anchor="w", font=FONT_MAIN, corner_radius=0, command=cmd)
        btn.grid(row=row, column=0, sticky="ew", padx=10, pady=5)
        return btn

    def setup_home(self):
        # HEADER
        header = ctk.CTkFrame(self.home_frame, fg_color=COLOR_PANEL, corner_radius=0, height=60)
        header.pack(fill="x", padx=20, pady=20)
        ctk.CTkLabel(header, text="SYSTEM STATUS :: ONLINE", font=FONT_HEADER, text_color=COLOR_ACCENT).pack(side="left", padx=20, pady=15)
        
        # GRID
        grid = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20)
        
        left = ctk.CTkFrame(grid, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0,10))
        
        # CODE CARD
        card = ctk.CTkFrame(left, fg_color=COLOR_PANEL, corner_radius=0, border_width=1, border_color="#333")
        card.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(card, text="ACCESS KEY", font=("Consolas", 12), text_color="gray").pack(pady=(15,5))
        self.lbl_code = ctk.CTkLabel(card, text="....", font=("Consolas", 50, "bold"), text_color="white")
        self.lbl_code.pack(pady=5)
        
        CyberBtn(card, text="REGENERATE", command=self.regenerate_code_action, height=30).pack(pady=(0,15), padx=40, fill="x")

    def setup_devices(self):
        ctk.CTkLabel(self.devices_frame, text="CONNECTED NODES", font=FONT_HEADER, text_color="white").pack(pady=20, padx=20, anchor="w")
        self.device_list = ctk.CTkScrollableFrame(self.devices_frame, height=300, fg_color="black", corner_radius=0)
        self.device_list.pack(pady=10, padx=20, fill="x")
        
        box = ctk.CTkFrame(self.devices_frame, fg_color=COLOR_PANEL, corner_radius=0)
        box.pack(pady=20, padx=20, fill="x")
        self.lbl_status = ctk.CTkLabel(box, text="> SELECT TARGET", text_color="gray", font=("Consolas", 12))
        self.lbl_status.pack(pady=10)
        CyberBtn(box, text="UPLOAD PAYLOAD", command=self.send_file).pack(pady=10)

    def select_frame(self, name):
        self.home_frame.grid_forget(); self.devices_frame.grid_forget()
        self.btn_home.configure(text_color="gray"); self.btn_devices.configure(text_color="gray")
        if name == "home": self.home_frame.grid(row=0, column=1, sticky="nsew"); self.btn_home.configure(text_color=COLOR_ACCENT)
        else: self.devices_frame.grid(row=0, column=1, sticky="nsew"); self.btn_devices.configure(text_color=COLOR_ACCENT)

    def setup_tray(self):
        try: image = Image.open(self.icon_path)
        except: image = Image.new('RGB', (64, 64), color='green')
        menu = pystray.Menu(pystray.MenuItem("Show", self.show_window), pystray.MenuItem("Exit", self.quit_app))
        self.tray = pystray.Icon("CyberDeck", image, "CyberDeck", menu)
        self.tray.run()

    def show_window(self, icon=None, item=None): self.after(0, self.deiconify)
    def hide_window(self): self.withdraw() # Свернуть в трей при закрытии
    def quit_app(self, icon=None, item=None):
        if self.server_process:
            self.server_process.kill()
        if hasattr(self, 'tray'): self.tray.stop()
        os._exit(0)

if __name__ == "__main__":
    app = App()
    app.mainloop()