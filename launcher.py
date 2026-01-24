import customtkinter as ctk
import threading
import sys
import os
import socket
import ctypes
import subprocess
import pystray
import asyncio
import psutil
from PIL import Image
from tkinter import filedialog
import main

main.DEBUG = True

SHOW_CONSOLE = "-c" in sys.argv
if sys.platform == "win32" and not SHOW_CONSOLE:
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)
    except: pass

COLOR_BG = "#050505"
COLOR_PANEL = "#111111"
COLOR_ACCENT = "#00FF41" 
COLOR_FAIL = "#FF3333"
COLOR_TEXT_DIM = "#555555"
FONT_MAIN = ("Consolas", 14)
FONT_BOLD = ("Consolas", 14, "bold")
FONT_HEADER = ("Consolas", 24, "bold")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def run_as_admin():
    if getattr(sys, 'frozen', False): executable = sys.executable; args = ""
    else: executable = sys.executable; args = f'"{__file__}"'
    if len(sys.argv) > 1: args += " " + " ".join(sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, args, None, 1)

def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except: return "127.0.0.1"

def kill_port_owner(port):
    """Убивает процесс, занимающий порт, используя API psutil"""
    print(f"Checking port {port}...")
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.net_connections(kind='inet'):
                    if conn.laddr.port == port:
                        print(f"Killing {proc.name()} (PID: {proc.pid}) on port {port}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        print(f"Error cleaning port: {e}")

class CyberBtn(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        super().__init__(master, corner_radius=0, border_width=1, border_color=COLOR_ACCENT, 
                         fg_color="transparent", text_color=COLOR_ACCENT, hover_color=COLOR_ACCENT,
                         font=FONT_BOLD, **kwargs)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
    def on_enter(self, e): self.configure(text_color=COLOR_BG)
    def on_leave(self, e): self.configure(text_color=COLOR_ACCENT)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        if not is_admin():
            run_as_admin()
            sys.exit()

        self.title(f"CYBERDECK")
        self.geometry("950x650")
        self.configure(fg_color=COLOR_BG)
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        if getattr(sys, 'frozen', False): base_dir = os.path.dirname(sys.executable)
        else: base_dir = os.path.dirname(os.path.abspath(__file__))
        self.icon_path = os.path.join(base_dir, "icon.png")
        if os.path.exists(self.icon_path):
            try: self.iconbitmap(self.icon_path)
            except: pass

        self.setup_ui()
        self.setup_firewall_rules()
        
        self.server_thread = threading.Thread(target=self.start_server_raw, daemon=True)
        self.server_thread.start()
        
        threading.Thread(target=self.setup_tray, daemon=True).start()
        self.after(2000, self.update_status_loop)

    def start_server_raw(self):
        """
        Запуск сервера в изолированном цикле событий.
        """
        try:
            import uvicorn
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            config = uvicorn.Config(
                main.app, 
                host="0.0.0.0", 
                port=main.PORT, 
                log_level="info" if main.DEBUG else "critical",
            )
            server = uvicorn.Server(config)
            
            server.install_signal_handlers = False
            
            loop.run_until_complete(server.serve())
        except Exception as e:
            print(f"CRITICAL SERVER ERROR: {e}")

    def setup_firewall_rules(self):
        try:
            subprocess.run(f'netsh advfirewall firewall delete rule name="CyberDeck TCP"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(f'netsh advfirewall firewall add rule name="CyberDeck TCP" dir=in action=allow protocol=TCP localport={main.PORT} profile=any', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            subprocess.run(f'netsh advfirewall firewall delete rule name="CyberDeck UDP"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(f'netsh advfirewall firewall add rule name="CyberDeck UDP" dir=in action=allow protocol=UDP localport={main.UDP_PORT} profile=any', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass

    def safe_update_status(self, text, color=None):
        """Обновляет статус из любого потока, не вешая GUI"""
        def _update():
            self.lbl_status.configure(text=text)
            if color:
                self.lbl_status.configure(text_color=color)
        self.after(0, _update)

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
        
        self.lbl_cpu = ctk.CTkLabel(self.sidebar, text="CPU: 0% | MEM: 0%", font=("Consolas", 11), text_color="gray")
        self.lbl_cpu.grid(row=5, column=0, padx=20, pady=5, sticky="w")
        ctk.CTkLabel(self.sidebar, text=f"BUILD: {main.VERSION}", font=("Consolas", 10), text_color=COLOR_TEXT_DIM).grid(row=6, column=0, padx=20, pady=20, sticky="sw")

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
        header = ctk.CTkFrame(self.home_frame, fg_color=COLOR_PANEL, corner_radius=0, height=60)
        header.pack(fill="x", padx=20, pady=20)
        ctk.CTkLabel(header, text="SYSTEM STATUS :: ONLINE", font=FONT_HEADER, text_color=COLOR_ACCENT).pack(side="left", padx=20, pady=15)
        
        grid = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20)
        
        left = ctk.CTkFrame(grid, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0,10))
        
        card = ctk.CTkFrame(left, fg_color=COLOR_PANEL, corner_radius=0, border_width=1, border_color="#333")
        card.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(card, text="ACCESS KEY", font=("Consolas", 12), text_color="gray").pack(pady=(15,5))
        self.lbl_code = ctk.CTkLabel(card, text=main.PAIRING_CODE, font=("Consolas", 50, "bold"), text_color="white")
        self.lbl_code.pack(pady=5)
        self.lbl_ip = ctk.CTkLabel(card, text=f"{get_lan_ip()}:{main.PORT}", font=("Consolas", 16), text_color=COLOR_ACCENT)
        self.lbl_ip.pack(pady=(0, 15))
        
        CyberBtn(card, text="REGENERATE", command=self.restart_server, height=30).pack(pady=(0,15), padx=40, fill="x")

        right = ctk.CTkFrame(grid, fg_color="transparent")
        right.pack(side="right", fill="both", expand=True, padx=(10,0))
        
        act = ctk.CTkFrame(right, fg_color=COLOR_PANEL, corner_radius=0, border_width=1, border_color="#333")
        act.pack(fill="x")
        ctk.CTkLabel(act, text="QUICK ACTIONS", font=("Consolas", 12), text_color="gray").pack(pady=(15,10))
        CyberBtn(act, text="OPEN FILES", command=lambda: os.startfile(main.FILES_DIR)).pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(act, text="", height=10).pack()
        
        if SHOW_CONSOLE:
            ctk.CTkLabel(self.home_frame, text="LOGS ARE DISPLAYED IN CONSOLE WINDOW", font=("Consolas", 12), text_color="gray").pack(pady=50)

    def setup_devices(self):
        ctk.CTkLabel(self.devices_frame, text="CONNECTED NODES", font=FONT_HEADER, text_color="white").pack(pady=20, padx=20, anchor="w")
        self.device_list = ctk.CTkScrollableFrame(self.devices_frame, height=300, fg_color="black", corner_radius=0)
        self.device_list.pack(pady=10, padx=20, fill="x")
        
        box = ctk.CTkFrame(self.devices_frame, fg_color=COLOR_PANEL, corner_radius=0)
        box.pack(pady=20, padx=20, fill="x")
        self.lbl_status = ctk.CTkLabel(box, text="> SELECT TARGET", text_color="gray", font=("Consolas", 12))
        self.lbl_status.pack(pady=10)
        CyberBtn(box, text="UPLOAD PAYLOAD", command=self.send_file).pack(pady=10)
        self.selected_token = None

    def update_status_loop(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.lbl_cpu.configure(text=f"CPU: {cpu}% | RAM: {ram}%")
            
            devs = main.device_manager.get_all_devices()
            for w in self.device_list.winfo_children(): w.destroy()
            
            if not devs:
                ctk.CTkLabel(self.device_list, text="[SCANNING... NO SIGNAL]", text_color="#333", font=("Consolas", 12)).pack(pady=20)
            else:
                for d in devs:
                    row = ctk.CTkFrame(self.device_list, fg_color="#111", corner_radius=0)
                    row.pack(fill="x", pady=2)
                    is_sel = (self.selected_token == d['token'])
                    col = COLOR_ACCENT if is_sel else "#333"
                    ctk.CTkCanvas(row, width=5, height=40, bg=col, highlightthickness=0).pack(side="left")
                    ctk.CTkLabel(row, text=f"{d['name']} :: {d['ip']}", font=("Consolas", 12), text_color="white").pack(side="left", padx=10)
                    btn_txt = "LINKED" if is_sel else "CONNECT"
                    btn_fg = COLOR_ACCENT if is_sel else "transparent"
                    btn_txt_col = "black" if is_sel else COLOR_ACCENT
                    ctk.CTkButton(row, text=btn_txt, width=80, corner_radius=0, fg_color=btn_fg, 
                                  border_width=1, border_color=COLOR_ACCENT, text_color=btn_txt_col,
                                  command=lambda t=d['token']: self.sel_dev(t)).pack(side="right", padx=10, pady=5)
        except Exception as e: 
            print(f"Status Loop Error: {e}")
        
        self.after(2000, self.update_status_loop)

    def select_frame(self, name):
        self.home_frame.grid_forget(); self.devices_frame.grid_forget()
        self.btn_home.configure(text_color="gray"); self.btn_devices.configure(text_color="gray")
        if name == "home": self.home_frame.grid(row=0, column=1, sticky="nsew"); self.btn_home.configure(text_color=COLOR_ACCENT)
        else: self.devices_frame.grid(row=0, column=1, sticky="nsew"); self.btn_devices.configure(text_color=COLOR_ACCENT)

    def sel_dev(self, t):
        self.selected_token = t
        self.lbl_status.configure(text="> TARGET LOCKED", text_color=COLOR_ACCENT)
        self.after(10, self.update_status_loop)

    def send_file(self):
        if not self.selected_token: return
        path = filedialog.askopenfilename()
        if not path: return

        def _bg_send():
            self.safe_update_status("> UPLOADING...", "yellow")
            try:
                ok, msg = main.trigger_file_send(self.selected_token, path)
                if ok:
                    self.safe_update_status(f"> SENT: {msg.upper()}", COLOR_ACCENT)
                else:
                    self.safe_update_status(f"> ERROR: {msg.upper()}", COLOR_FAIL)
            except Exception as e:
                self.safe_update_status(f"> CRASH: {str(e)}", COLOR_FAIL)

        threading.Thread(target=_bg_send, daemon=True).start()

    def restart_server(self):
        main.PAIRING_CODE = str(main.uuid.uuid4().int)[:4]
        self.lbl_code.configure(text=main.PAIRING_CODE)

    def setup_tray(self):
        try: image = Image.open(self.icon_path)
        except: image = Image.new('RGB', (64, 64), color='green')
        menu = pystray.Menu(pystray.MenuItem("Show", self.show_window), pystray.MenuItem("Exit", self.quit_app))
        self.tray = pystray.Icon("CyberDeck", image, "CyberDeck", menu)
        self.tray.run()

    def show_window(self, icon=None, item=None): self.after(0, self.deiconify)
    def hide_window(self): self.withdraw()
    def quit_app(self, icon=None, item=None):
        if hasattr(self, 'tray'): self.tray.stop()
        os._exit(0)

if __name__ == "__main__":
    kill_port_owner(main.PORT)
    
    app = App()
    app.mainloop()