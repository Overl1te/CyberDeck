import customtkinter as ctk
import threading
import sys
import os
import ctypes
import subprocess
import pystray
import psutil
import time
import requests
import json
import uvicorn
import queue
from PIL import Image
from tkinter import filedialog, messagebox
from collections import deque
import qrcode

SERVER_SCRIPT_NAME = "main.py"
PORT = 8080
API_URL = f"http://127.0.0.1:{PORT}/api/local"
SYNC_INTERVAL_MS = 1000

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

COLOR_BG = "#0B0F12"
COLOR_PANEL = "#151A1F"
COLOR_PANEL_ALT = "#0F1418"
COLOR_BORDER = "#242B33"
COLOR_ACCENT = "#31E6A1"
COLOR_ACCENT_HOVER = "#56F0BB"
COLOR_WARN = "#FFC857"
COLOR_FAIL = "#FF6B6B"
COLOR_TEXT = "#E6EEF3"
COLOR_TEXT_DIM = "#8A949E"

FONT_UI = ("Tahoma", 13)
FONT_UI_BOLD = ("Tahoma", 13, "bold")
FONT_HEADER = ("Tahoma", 22, "bold")
FONT_SMALL = ("Tahoma", 11)
FONT_MONO = ("Consolas", 12)
FONT_CODE = ("Consolas", 44, "bold")

DEFAULT_DEVICE_PRESETS = ["fast", "balanced", "safe", "ultra_safe"]

SETTINGS_FILE_NAME = "launcher_settings.json"
DEFAULT_SETTINGS = {
    "close_to_tray": True,
    "always_on_top": False,
    "autostart": False,
    "hotkey_enabled": False,
    "start_in_tray": True,
    "show_on_start": True,
}

ABOUT_TEXT = (
    "CyberDeck\n\n"
    "Клиент для управления ПК по локальной сети.\n\n"
    "Автор:\n"
    "Overl1te\n"
    "https://github.com/Overl1te\n\n"
    "Репозиторий проекта:\n"
    "https://github.com/Overl1te/CyberDeck\n\n"
    "Лицензия GNU GPLv3\n"
    "https://github.com/Overl1te/CyberDeck/blob/main/LICENSE\n\n"
    "Условия использования\n"
    "https://github.com/Overl1te/CyberDeck/blob/main/TERMS_OF_USE.md\n\n"
    "CyberDeck Copyright (C) 2026  Overl1te"
)


def is_windows() -> bool:
    return os.name == "nt"


def ensure_console():
    """Если запущено как GUI и консоли нет, создаем ее."""
    if not is_windows():
        return
    try:
        ctypes.windll.kernel32.AllocConsole()
        try:
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="ignore")
        sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass


def ensure_null_stdio():
    """In --noconsole builds sys.stdout/stderr can be None; make them safe sinks."""
    try:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass
    try:
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    except Exception:
        pass


def load_json(path: str, default: dict):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = default.copy()
                    merged.update(data)
                    return merged
    except Exception:
        pass
    return default.copy()


def save_json(path: str, data: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_autostart(enabled: bool, command: str):
    """HKCU Run. Без админа."""
    if not is_windows():
        return
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, "CyberDeckLauncher", 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, "CyberDeckLauncher")
                except FileNotFoundError:
                    pass
    except Exception:
        pass


class CyberBtn(ctk.CTkButton):
    def __init__(self, master, **kwargs):
        defaults = dict(
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
            fg_color=COLOR_PANEL_ALT,
            text_color=COLOR_TEXT,
            hover_color=COLOR_BORDER,
            font=FONT_UI_BOLD,
        )
        defaults.update(kwargs)
        super().__init__(master, **defaults)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.console_mode = ("-c" in sys.argv) or ("--console" in sys.argv)
        self.logs_enabled = self.console_mode
        if self.console_mode:
            ensure_console()
            print("[CyberDeck] Режим консоли включен (-c)")
        else:
            ensure_null_stdio()

        if not self.is_admin():
            self.run_as_admin()
            sys.exit()

        if getattr(sys, "frozen", False):
            self.base_dir = os.path.dirname(sys.executable)
            self.server_exe = os.path.join(self.base_dir, "main.exe")
            self.launch_cmd_for_autostart = f'"{sys.executable}"'
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self.server_exe = os.path.join(self.base_dir, SERVER_SCRIPT_NAME)
            self.launch_cmd_for_autostart = f'"{sys.executable}" "{os.path.abspath(__file__)}"'

        self.settings_path = os.path.join(self.base_dir, SETTINGS_FILE_NAME)
        self.settings = load_json(self.settings_path, DEFAULT_SETTINGS)
        self.start_in_tray = bool(self.settings.get("start_in_tray", True))
        self.show_on_start = bool(self.settings.get("show_on_start", True))

        self.icon_path_png = os.path.join(self.base_dir, "icon.png")
        self.icon_path_ico = os.path.join(self.base_dir, "icon.ico")
        self.log_file = os.path.join(self.base_dir, "cyberdeck.log")

        self.title("CyberDeck")
        self.geometry("1100x720")
        self.configure(fg_color=COLOR_BG)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        try:
            if os.path.exists(self.icon_path_ico):
                self.iconbitmap(self.icon_path_ico)
        except Exception:
            pass

        self.attributes("-topmost", bool(self.settings.get("always_on_top")))

        self.server_process = None
        self.server_thread = None
        self._uvicorn_server = None
        self._server_log_ring = deque(maxlen=400)
        self._qr_last_fetch_ts = 0.0
        self._qr_ctk_img = None
        self.devices_data = []
        self.show_offline = ctk.BooleanVar(value=False)
        self.selected_token = None
        self.selected_device_name = None
        self.pairing_code = "...."
        self.server_ip = "0.0.0.0"
        self.server_port = PORT
        self.server_version = "unknown"
        self.status_text = "> ОЖИДАНИЕ СЕРВЕРА"
        self.server_online = False

        self.var_transfer_preset = ctk.StringVar(value="balanced")
        self.var_device_alias = ctk.StringVar(value="")
        self.var_device_note = ctk.StringVar(value="")
        self.var_transfer_chunk_kb = ctk.StringVar(value="")
        self.var_transfer_sleep_ms = ctk.StringVar(value="")
        self.var_perm_mouse = ctk.BooleanVar(value=True)
        self.var_perm_keyboard = ctk.BooleanVar(value=True)
        self.var_perm_upload = ctk.BooleanVar(value=True)
        self.var_perm_file_send = ctk.BooleanVar(value=True)
        self.var_perm_stream = ctk.BooleanVar(value=True)
        self.var_perm_power = ctk.BooleanVar(value=False)

        self._sync_inflight = False
        self._sync_job = None
        self._devices_render_key = None
        self._ui_queue = queue.Queue()
        self._device_settings_dirty = False
        self._suppress_device_setting_trace = False

        self.setup_ui()
        self.start_server_process()

        self.after(50, self._process_ui_queue)
        self._schedule_sync(0)
        threading.Thread(target=self.setup_tray, daemon=True).start()

        if self.start_in_tray and (not self.show_on_start):
            self.withdraw()

        if self.settings.get("autostart"):
            set_autostart(True, self.launch_cmd_for_autostart)
        if self.settings.get("hotkey_enabled"):
            threading.Thread(target=self.hotkey_loop, daemon=True).start()

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    def run_as_admin(self):
        if getattr(sys, "frozen", False):
            executable = sys.executable
            args = " ".join(sys.argv[1:])
        else:
            executable = sys.executable
            args = f'"{os.path.abspath(__file__)}"'
            for a in sys.argv[1:]:
                args += f" {a}"
        ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, args, None, 1)

    def kill_old_server(self):
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                for conn in proc.net_connections(kind="inet"):
                    if conn.laddr and conn.laddr.port == PORT:
                        proc.kill()
            except Exception:
                continue

    def start_server_process(self):
        self.kill_old_server()

        env = os.environ.copy()
        env["CYBERDECK_CONSOLE"] = "1" if self.logs_enabled else "0"
        env["CYBERDECK_LOG"] = "1" if self.logs_enabled else "0"
        env["CYBERDECK_DEBUG"] = "1"
        env["CYBERDECK_PORT"] = str(PORT)

        os.environ.update(env)

        if getattr(sys, "frozen", False):
            if os.path.exists(self.server_exe):
                cmd = [self.server_exe]
            else:
                self.start_server_inprocess()
                self.append_log("[launcher] сервер запущен (в процессе)\n")
                return
        else:
            cmd = [sys.executable, self.server_exe]

        creationflags = 0
        startupinfo = None
        if is_windows() and not self.console_mode:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            stdout_target = subprocess.PIPE
            stderr_target = subprocess.STDOUT
            self.server_process = subprocess.Popen(
                cmd,
                cwd=self.base_dir,
                env=env,
                stdout=stdout_target,
                stderr=stderr_target,
                text=True,
                bufsize=1,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            threading.Thread(target=self.server_stdout_loop, daemon=True).start()
            self.append_log("[launcher] сервер запущен\n")
        except Exception as e:
            self.append_log(f"[launcher] ошибка запуска сервера: {e}\n")
            self._show_server_start_error(str(e))

    def _show_server_start_error(self, extra: str = ""):
        try:
            tail = "".join(list(self._server_log_ring)[-80:])
        except Exception:
            tail = ""

        msg = "Не удалось запустить сервер.\n\n"
        if extra:
            msg += f"Ошибка: {extra}\n\n"
        if tail.strip():
            msg += "Последние сообщения:\n" + tail[-4000:]
        else:
            msg += "Подсказка: запустите приложение с флагом -c, чтобы увидеть логи."

        try:
            self.ui_call(lambda: messagebox.showerror("CyberDeck", msg))
        except Exception:
            pass

    def start_server_inprocess(self):
        if self.server_thread and self.server_thread.is_alive():
            return
        try:
            import main as cyberdeck_server

            log_level = "debug" if os.environ.get("CYBERDECK_DEBUG", "1") == "1" else "info"
            access_log = os.environ.get("CYBERDECK_DEBUG", "1") == "1"
            if os.environ.get("CYBERDECK_LOG", "0") != "1":
                log_level = "critical"
                access_log = False

            config = uvicorn.Config(
                cyberdeck_server.app,
                host="0.0.0.0",
                port=PORT,
                log_level=log_level,
                access_log=access_log,
            )
            server = uvicorn.Server(config)
            self._uvicorn_server = server

            def _run():
                try:
                    server.run()
                except Exception as e:
                    self.append_log(f"[launcher] ошибка uvicorn: {e}\n")
                    self._show_server_start_error(str(e))

            self.server_thread = threading.Thread(target=_run, daemon=True)
            self.server_thread.start()
        except Exception as e:
            self.append_log(f"[launcher] ошибка запуска сервера (в процессе): {e}\n")
            self._show_server_start_error(str(e))

    def stop_server_process(self):
        try:
            if self.server_process and self.server_process.poll() is None:
                self.server_process.kill()
        except Exception:
            pass
        self.server_process = None
        try:
            if self._uvicorn_server:
                self._uvicorn_server.should_exit = True
        except Exception:
            pass
        self._uvicorn_server = None
        self.server_thread = None

    def restart_server(self):
        self.append_log("[launcher] перезапуск сервера...\n")
        self.stop_server_process()
        time.sleep(0.2)
        self.start_server_process()

    def server_stdout_loop(self):
        """Читает stdout сервера (если туда что-то попадает)."""
        try:
            if not self.server_process or not self.server_process.stdout:
                return
            for line in self.server_process.stdout:
                if not line:
                    continue
                self.append_log(line)
            try:
                rc = self.server_process.poll()
            except Exception:
                rc = None
            if rc not in (None, 0):
                self.append_log(f"[launcher] сервер завершился (code={rc})\n")
                self._show_server_start_error(f"server exited with code {rc}")
        except Exception:
            pass

    def append_log(self, text: str):
        try:
            self._server_log_ring.append(str(text))
        except Exception:
            pass

        if not self.logs_enabled:
            return

        try:
            print(text, end="")
        except Exception:
            pass

    def _safe_after(self, delay_ms: int, callback):
        try:
            if not self.winfo_exists():
                return None
        except Exception:
            return None
        try:
            return self.after(int(delay_ms), callback)
        except Exception:
            return None

    def _schedule_sync(self, delay_ms: int):
        try:
            if self._sync_job is not None:
                self.after_cancel(self._sync_job)
        except Exception:
            pass
        self._sync_job = self._safe_after(max(0, int(delay_ms)), self.sync_loop)

    def request_sync(self, delay_ms: int = 0):
        self._schedule_sync(delay_ms)

    def ui_call(self, fn):
        try:
            self._ui_queue.put(fn)
        except Exception:
            pass

    def _process_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.after(50, self._process_ui_queue)
        except Exception:
            pass

    def sync_loop(self):
        self._sync_job = None
        if self._sync_inflight:
            self._schedule_sync(200)
            return
        self._sync_inflight = True

        def _fetch():
            try:
                resp = requests.get(f"{API_URL}/info", timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    self.server_online = True
                    self.pairing_code = data.get("pairing_code", "ERR")
                    self.server_ip = data.get("ip", "0.0.0.0")
                    self.server_port = data.get("port", PORT)
                    self.server_version = data.get("version", "unknown")
                    self.log_file = data.get("log_file", self.log_file)
                    self.devices_data = data.get("devices", [])
                else:
                    self.server_online = False
            except Exception:
                self.server_online = False
            finally:
                self._sync_inflight = False
                self.ui_call(self.update_gui_data)
                self.ui_call(lambda: self._schedule_sync(SYNC_INTERVAL_MS))

        threading.Thread(target=_fetch, daemon=True).start()
    def _device_display_name(self, d: dict) -> str:
        try:
            settings = d.get("settings") or {}
            alias = str(settings.get("alias") or "").strip()
            if alias:
                return alias
        except Exception:
            pass
        return d.get("name", "unknown")

    def _compute_devices_render_key(self):
        items = []
        for d in self.devices_data or []:
            online = bool(d.get("online")) and self.server_online
            if (not self.show_offline.get()) and (not online):
                continue
            settings = d.get("settings") or {}
            items.append(
                (
                    d.get("token"),
                    self._device_display_name(d),
                    d.get("ip"),
                    bool(online),
                    settings.get("transfer_preset"),
                    settings.get("transfer_chunk"),
                    settings.get("transfer_sleep"),
                    settings.get("note"),
                )
            )
        return (bool(self.server_online), bool(self.show_offline.get()), self.selected_token, tuple(items))

    def update_gui_data(self):
        self.lbl_code.configure(text=self.pairing_code)
        self.lbl_server.configure(text=f"{self.server_ip}:{self.server_port}")
        self.lbl_version.configure(text=self.server_version)

        if self.server_online:
            self.lbl_header_status.configure(text="Сервер: онлайн", text_color=COLOR_ACCENT)
        else:
            self.lbl_header_status.configure(text="Сервер: нет связи", text_color=COLOR_FAIL)

        total = len(self.devices_data)
        online_count = sum(1 for d in self.devices_data if d.get("online"))
        self.lbl_summary_devices.configure(text=f"Устройства: {online_count}/{total}")
        self.lbl_summary_logs.configure(
            text="Логи: консоль" if self.logs_enabled else "Логи: выключены"
        )
        self.lbl_summary_tray.configure(
            text="Трей: основной режим" if self.start_in_tray else "Трей: окно"
        )

        self.lbl_logs_hint.configure(
            text="Подсказка: запустите с -c для вывода логов" if not self.logs_enabled else ""
        )
        self.lbl_devices_status.configure(
            text=f"Обновление: {time.strftime('%H:%M:%S')}" if self.server_online else "Обновление: нет связи"
        )

        self.refresh_qr_code()

        try:
            devices_key = self._compute_devices_render_key()
        except Exception:
            devices_key = object()
        if devices_key == self._devices_render_key:
            self.refresh_selected_panel()
            return
        self._devices_render_key = devices_key

        for w in self.device_list.winfo_children():
            w.destroy()

        if not self.devices_data:
            ctk.CTkLabel(
                self.device_list,
                text="Подключений нет",
                text_color=COLOR_TEXT_DIM,
                font=FONT_SMALL,
            ).pack(pady=20)
        else:
            for d in self.devices_data:
                online = bool(d.get("online")) and self.server_online
                if (not self.show_offline.get()) and (not online):
                    continue

                token = d.get("token")
                is_sel = self.selected_token == token

                row = ctk.CTkFrame(
                    self.device_list,
                    fg_color=COLOR_PANEL if is_sel else COLOR_PANEL_ALT,
                    corner_radius=10,
                    border_width=1,
                    border_color=COLOR_ACCENT if is_sel else COLOR_BORDER,
                )
                row.pack(fill="x", pady=4, padx=2)

                content = ctk.CTkFrame(row, fg_color="transparent")
                content.pack(fill="x", expand=True, padx=8, pady=8)

                dot = ctk.CTkFrame(
                    content,
                    width=10,
                    height=10,
                    corner_radius=5,
                    fg_color=COLOR_ACCENT if online else "#444",
                )
                dot.pack(side="left", padx=(2, 10), pady=6)
                dot.pack_propagate(False)

                name = self._device_display_name(d)
                ip = d.get("ip", "?")
                preset = (d.get("settings") or {}).get("transfer_preset", "balanced")
                status = "Онлайн" if online else "Офлайн"

                info = ctk.CTkFrame(content, fg_color="transparent")
                info.pack(side="left", fill="x", expand=True)

                lbl_title = ctk.CTkLabel(
                    info,
                    text=name,
                    font=FONT_UI_BOLD,
                    text_color=COLOR_TEXT,
                )
                lbl_title.pack(anchor="w")
                lbl_sub = ctk.CTkLabel(
                    info,
                    text=f"{ip} | {status} | профиль: {preset}",
                    font=FONT_SMALL,
                    text_color=COLOR_TEXT_DIM,
                )
                lbl_sub.pack(anchor="w")

                def _bind_select(w):
                    try:
                        w.bind("<Button-1>", lambda _e, t=token: self.select_device(t))
                    except Exception:
                        pass

                _bind_select(row)
                _bind_select(dot)
                _bind_select(info)
                _bind_select(lbl_title)
                _bind_select(lbl_sub)

                actions = ctk.CTkFrame(content, fg_color="transparent")
                actions.pack(side="right", padx=(10, 2))

                if is_sel:
                    ctk.CTkLabel(actions, text="✓", text_color=COLOR_ACCENT, font=FONT_UI_BOLD).pack(side="right", padx=(10, 0))

                dis_btn = CyberBtn(
                    actions,
                    text="Отключить",
                    width=110,
                    height=30,
                    corner_radius=10,
                    fg_color="transparent",
                    border_width=1,
                    border_color=COLOR_BORDER,
                    text_color=COLOR_TEXT,
                    hover_color=COLOR_PANEL,
                    font=FONT_SMALL,
                    command=lambda t=token: self.disconnect_device(t),
                )
                if not online:
                    try:
                        dis_btn.configure(state="disabled", text_color=COLOR_TEXT_DIM, border_color=COLOR_BORDER)
                    except Exception:
                        pass
                dis_btn.pack(side="right", padx=(10, 0))

                CyberBtn(
                    actions,
                    text="Удалить",
                    width=96,
                    height=30,
                    corner_radius=10,
                    fg_color="transparent",
                    border_width=1,
                    border_color=COLOR_FAIL,
                    text_color=COLOR_FAIL,
                    hover_color=COLOR_PANEL,
                    font=FONT_SMALL,
                    command=lambda t=token, n=self._device_display_name(d): self.delete_device(t, n),
                ).pack(side="right")

        self.refresh_selected_panel()

    def _set_qr_placeholder(self, text: str):
        try:
            if hasattr(self, "lbl_qr") and self.lbl_qr:
                self.lbl_qr.configure(text=text, image=None)
        except Exception:
            pass

    def refresh_qr_code(self, force: bool = False):
        if not hasattr(self, "lbl_qr"):
            return

        if not self.server_online:
            self._set_qr_placeholder("QR недоступен")
            return

        now = time.time()
        if (not force) and (now - float(self._qr_last_fetch_ts) < 30.0):
            return
        self._qr_last_fetch_ts = now

        def _bg():
            try:
                resp = requests.get(f"{API_URL}/qr_payload", timeout=1)
                if resp.status_code != 200:
                    raise RuntimeError(f"http {resp.status_code}")
                payload = (resp.json() or {}).get("payload") or {}
                qr_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

                img = qrcode.make(qr_text).convert("RGB").resize((220, 220), Image.NEAREST)

                def _ui():
                    self._qr_ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(220, 220))
                    self.lbl_qr.configure(image=self._qr_ctk_img, text="")

                self.ui_call(_ui)
            except Exception as e:
                self.append_log(f"[launcher] qr error: {e}\n")
                self.ui_call(lambda: self._set_qr_placeholder("QR ошибка"))

        threading.Thread(target=_bg, daemon=True).start()

    def _get_selected_device(self):
        if not self.selected_token:
            return None
        for d in self.devices_data:
            if d.get("token") == self.selected_token:
                return d
        return None

    def _translate_transfer_msg(self, msg: str) -> str:
        if not msg:
            return "Ошибка"
        mapping = {
            "Offline": "Устройство не в сети",
            "File missing": "Файл не найден",
            "Server not ready": "Сервер еще не готов",
            "transporter.py missing": "Не найден transporter.py",
            "Transporter started": "Передача запущена",
        }
        return mapping.get(msg, msg)

    
    def select_device(self, token: str):
        self.selected_token = token
        self.selected_device_name = None
        for d in self.devices_data:
            if d.get("token") == token:
                self.selected_device_name = self._device_display_name(d)
                settings = d.get("settings") or {}
                self._suppress_device_setting_trace = True
                self.var_transfer_preset.set(settings.get("transfer_preset", "balanced"))
                self.var_device_alias.set((settings.get("alias") or "").strip())
                self.var_device_note.set((settings.get("note") or "").strip())
                try:
                    chunk = settings.get("transfer_chunk")
                    self.var_transfer_chunk_kb.set("" if chunk in (None, "", 0) else str(int(chunk) // 1024))
                except Exception:
                    self.var_transfer_chunk_kb.set("")
                try:
                    sleep = settings.get("transfer_sleep")
                    self.var_transfer_sleep_ms.set("" if sleep in (None, "", 0) else str(int(float(sleep) * 1000)))
                except Exception:
                    self.var_transfer_sleep_ms.set("")

                self.var_perm_mouse.set(bool(settings.get("perm_mouse", True)))
                self.var_perm_keyboard.set(bool(settings.get("perm_keyboard", True)))
                self.var_perm_upload.set(bool(settings.get("perm_upload", True)))
                self.var_perm_file_send.set(bool(settings.get("perm_file_send", True)))
                self.var_perm_stream.set(bool(settings.get("perm_stream", True)))
                self.var_perm_power.set(bool(settings.get("perm_power", False)))
                self._suppress_device_setting_trace = False
                self._device_settings_dirty = False
                break
        self.lbl_status.configure(text="> Устройство выбрано", text_color=COLOR_ACCENT)
        self.update_gui_data()

    def refresh_selected_panel(self):
        if not self.selected_token:
            self.lbl_target.configure(text="Нет")
            self.lbl_target_status.configure(text="Цель не выбрана", text_color=COLOR_TEXT_DIM)
            return

        d = self._get_selected_device()
        name = (d.get("name") if d else None) or self.selected_device_name or "Устройство"
        name = (self._device_display_name(d) if d else None) or name
        ip = (d.get("ip") if d else None) or "-"
        online = bool(d.get("online")) and self.server_online if d else False
        status = "Онлайн" if online else "Офлайн"

        self.lbl_target.configure(text=f"{name}\n{self.selected_token[:8]}...")
        self.lbl_target_status.configure(
            text=f"{status} • {ip}",
            text_color=COLOR_ACCENT if online else COLOR_TEXT_DIM,
        )

    def disconnect_device(self, token: str):
        if not token:
            return

        def _bg():
            try:
                requests.post(f"{API_URL}/device_disconnect", json={"token": token}, timeout=2)
            except Exception as e:
                self.ui_call(lambda: messagebox.showerror("CyberDeck", f"Не удалось отключить устройство.\n\n{e}"))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

    def delete_device(self, token: str, name: str = "Устройство"):
        if not token:
            return
        try:
            ok = messagebox.askyesno("CyberDeck", f"Удалить устройство \"{name}\"?\n\nОно исчезнет из списка.")
        except Exception:
            ok = False
        if not ok:
            return

        def _bg():
            try:
                requests.post(f"{API_URL}/device_delete", json={"token": token}, timeout=3)
                if self.selected_token == token:
                    self.selected_token = None
                    self.selected_device_name = None
            except Exception as e:
                self.ui_call(lambda: messagebox.showerror("CyberDeck", f"Не удалось удалить устройство.\n\n{e}"))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

    def save_device_settings(self):
        if not self.selected_token:
            self.lbl_status.configure(text="> Устройство не выбрано", text_color=COLOR_FAIL)
            return

        preset = self.var_transfer_preset.get().strip().lower()
        if preset not in DEFAULT_DEVICE_PRESETS:
            preset = "balanced"

        alias = self.var_device_alias.get().strip()
        note = self.var_device_note.get().strip()
        chunk_kb_raw = self.var_transfer_chunk_kb.get().strip()
        sleep_ms_raw = self.var_transfer_sleep_ms.get().strip()

        patch = {"transfer_preset": preset}
        patch["alias"] = alias if alias else None
        patch["note"] = note if note else None

        if chunk_kb_raw == "":
            patch["transfer_chunk"] = None
        else:
            try:
                patch["transfer_chunk"] = max(1, int(chunk_kb_raw)) * 1024
            except Exception:
                patch["transfer_chunk"] = None

        if sleep_ms_raw == "":
            patch["transfer_sleep"] = None
        else:
            try:
                patch["transfer_sleep"] = max(0.0, float(sleep_ms_raw) / 1000.0)
            except Exception:
                patch["transfer_sleep"] = None

        patch["perm_mouse"] = bool(self.var_perm_mouse.get())
        patch["perm_keyboard"] = bool(self.var_perm_keyboard.get())
        patch["perm_upload"] = bool(self.var_perm_upload.get())
        patch["perm_file_send"] = bool(self.var_perm_file_send.get())
        patch["perm_stream"] = bool(self.var_perm_stream.get())
        patch["perm_power"] = bool(self.var_perm_power.get())

        def _bg():
            try:
                payload = {"token": self.selected_token, "settings": patch}
                resp = requests.post(f"{API_URL}/device_settings", json=payload, timeout=2)
                if resp.status_code == 200:
                    self.ui_call(lambda: self._mark_device_settings_saved())
                else:
                    self.ui_call(lambda: self.lbl_status.configure(text="> Ошибка сохранения", text_color=COLOR_FAIL))
            except Exception as e:
                self.ui_call(lambda: self.lbl_status.configure(text=f"> Ошибка: {e}", text_color=COLOR_FAIL))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

    def _mark_device_settings_saved(self):
        self._device_settings_dirty = False
        try:
            self.lbl_status.configure(text="> Настройки сохранены", text_color=COLOR_ACCENT)
        except Exception:
            pass

    def _on_device_setting_changed(self, *_args):
        if self._suppress_device_setting_trace:
            return
        if not self.selected_token:
            return
        self._device_settings_dirty = True
        try:
            if hasattr(self, "lbl_status"):
                self.lbl_status.configure(text="> Есть несохранённые настройки (нажмите «Сохранить настройки»)", text_color=COLOR_WARN)
        except Exception:
            pass

    def send_file(self):
        if not self.selected_token:
            self.lbl_status.configure(text="> Устройство не выбрано", text_color=COLOR_FAIL)
            return

        path = filedialog.askopenfilename(title="Выберите файл")
        if not path:
            return

        def _bg_send():
            self.ui_call(lambda: self.lbl_status.configure(text="> Запрос передачи...", text_color=COLOR_WARN))
            try:
                payload = {"token": self.selected_token, "file_path": path}
                resp = requests.post(f"{API_URL}/trigger_file", json=payload, timeout=4)

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        self.ui_call(lambda: self.lbl_status.configure(text="> Передача началась", text_color=COLOR_ACCENT))
                    else:
                        msg = self._translate_transfer_msg(data.get("msg"))
                        self.ui_call(lambda: self.lbl_status.configure(text=f"> Ошибка: {msg}", text_color=COLOR_FAIL))
                else:
                    self.ui_call(lambda: self.lbl_status.configure(text="> Ошибка API", text_color=COLOR_FAIL))
            except Exception as e:
                self.ui_call(lambda: self.lbl_status.configure(text=f"> Ошибка: {e}", text_color=COLOR_FAIL))

        threading.Thread(target=_bg_send, daemon=True).start()

    def regenerate_code_action(self):
        def _req():
            try:
                requests.post(f"{API_URL}/regenerate_code", timeout=2)
            except Exception:
                pass

        threading.Thread(target=_req, daemon=True).start()

    def copy_pairing_code(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self.pairing_code)
            self.lbl_status.configure(text="> Код скопирован", text_color=COLOR_ACCENT)
        except Exception:
            pass

    def apply_settings(self):
        self.attributes("-topmost", bool(self.settings.get("always_on_top")))
        set_autostart(bool(self.settings.get("autostart")), self.launch_cmd_for_autostart)
        save_json(self.settings_path, self.settings)

    def hotkey_loop(self):
        """Ctrl+Alt+D: показать/скрыть окно."""
        if not is_windows():
            return
        try:
            import ctypes.wintypes as wintypes

            user32 = ctypes.windll.user32
            MOD_ALT = 0x0001
            MOD_CONTROL = 0x0002
            WM_HOTKEY = 0x0312
            HOTKEY_ID = 1

            if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT | MOD_CONTROL, ord("D")):
                self.append_log("[launcher] не удалось зарегистрировать хоткей\n")
                return

            msg = wintypes.MSG()
            while True:
                r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r == 0:
                    break
                if msg.message == WM_HOTKEY:
                    self.ui_call(self.toggle_window)

        except Exception:
            pass

    def toggle_window(self):
        if self.state() in ("withdrawn", "iconic"):
            self.deiconify()
            self.lift()
            self.focus_force()
        else:
            self.withdraw()

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=COLOR_PANEL)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            self.sidebar, text="CyberDeck", font=("Tahoma", 26, "bold"), text_color=COLOR_TEXT
        ).grid(row=0, column=0, padx=20, pady=(28, 0), sticky="w")
        ctk.CTkLabel(
            self.sidebar, text="Панель управления", font=FONT_SMALL, text_color=COLOR_TEXT_DIM
        ).grid(row=1, column=0, padx=20, pady=(2, 20), sticky="w")

        self.btn_home = self.create_nav_btn("Сводка", "home", 2)
        self.btn_devices = self.create_nav_btn("Устройства", "devices", 3)
        self.btn_settings = self.create_nav_btn("Настройки", "settings", 4)

        self.home_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.devices_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.settings_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")

        self.setup_home()
        self.setup_devices()
        self.setup_settings()

        self.select_frame("devices")

    def create_nav_btn(self, text, name, row):
        cmd = lambda: self.select_frame(name)
        btn = ctk.CTkButton(
            self.sidebar,
            text=text,
            fg_color="transparent",
            text_color=COLOR_TEXT_DIM,
            hover_color=COLOR_PANEL,
            anchor="w",
            font=FONT_UI_BOLD,
            corner_radius=8,
            height=36,
            command=cmd,
        )
        btn.grid(row=row, column=0, sticky="ew", padx=12, pady=6)
        return btn

    def setup_home(self):
        header = ctk.CTkFrame(self.home_frame, fg_color=COLOR_PANEL, corner_radius=12, height=70)
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="Состояние системы", font=FONT_HEADER, text_color=COLOR_TEXT).pack(
            side="left", padx=20, pady=18
        )
        self.lbl_header_status = ctk.CTkLabel(header, text="Сервер: ...", font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM)
        self.lbl_header_status.pack(side="right", padx=20)

        grid = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        grid.pack(fill="x", padx=20)

        card = ctk.CTkFrame(grid, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ctk.CTkLabel(card, text="Код доступа", font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(pady=(12, 4))
        self.lbl_code = ctk.CTkLabel(card, text="....", font=FONT_CODE, text_color=COLOR_TEXT)
        self.lbl_code.pack(pady=2)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=18, pady=(6, 14))
        CyberBtn(
            btn_row,
            text="Копировать",
            command=self.copy_pairing_code,
            height=34,
            fg_color=COLOR_ACCENT,
            text_color="#0B0F12",
            hover_color=COLOR_ACCENT_HOVER,
            border_color=COLOR_ACCENT,
        ).pack(side="left", expand=True, fill="x", padx=(0, 8))
        CyberBtn(btn_row, text="Обновить", command=self.regenerate_code_action, height=34).pack(
            side="left", expand=True, fill="x"
        )

        qr_card = ctk.CTkFrame(grid, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        qr_card.pack(side="left", fill="both", expand=False, padx=(10, 10))
        ctk.CTkLabel(qr_card, text="Вход по QR", font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(pady=(12, 6))
        self.lbl_qr = ctk.CTkLabel(qr_card, text="QR недоступен", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
        self.lbl_qr.pack(padx=14, pady=(0, 8))
        CyberBtn(qr_card, text="Обновить QR", command=lambda: self.refresh_qr_code(force=True), height=34).pack(
            padx=14, pady=(0, 14), fill="x"
        )

        info = ctk.CTkFrame(grid, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        info.pack(side="left", fill="both", expand=True, padx=(10, 0))

        ctk.CTkLabel(info, text="Сервер", font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(pady=(12, 6))
        self.lbl_server = ctk.CTkLabel(info, text="0.0.0.0:8080", font=FONT_UI_BOLD, text_color=COLOR_TEXT)
        self.lbl_server.pack(pady=2)
        self.lbl_version = ctk.CTkLabel(info, text="version", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
        self.lbl_version.pack(pady=(0, 10))

        CyberBtn(
            info,
            text="Перезапустить сервер",
            command=self.restart_server,
            height=34,
            fg_color=COLOR_ACCENT,
            text_color="#0B0F12",
            hover_color=COLOR_ACCENT_HOVER,
            border_color=COLOR_ACCENT,
        ).pack(padx=18, pady=(0, 14), fill="x")

        summary = ctk.CTkFrame(self.home_frame, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        summary.pack(fill="x", padx=20, pady=(12, 20))

        ctk.CTkLabel(summary, text="Сводка", font=FONT_UI_BOLD, text_color=COLOR_TEXT).pack(anchor="w", padx=18, pady=(12, 6))
        self.lbl_summary_devices = ctk.CTkLabel(summary, text="Устройства: 0/0", font=FONT_SMALL, text_color=COLOR_TEXT)
        self.lbl_summary_devices.pack(anchor="w", padx=18)
        self.lbl_summary_logs = ctk.CTkLabel(summary, text="Логи: выключены", font=FONT_SMALL, text_color=COLOR_TEXT)
        self.lbl_summary_logs.pack(anchor="w", padx=18, pady=(4, 0))
        self.lbl_summary_tray = ctk.CTkLabel(summary, text="Трей: основной режим", font=FONT_SMALL, text_color=COLOR_TEXT)
        self.lbl_summary_tray.pack(anchor="w", padx=18, pady=(4, 0))
        self.lbl_logs_hint = ctk.CTkLabel(summary, text="", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
        self.lbl_logs_hint.pack(anchor="w", padx=18, pady=(6, 12))

    def setup_devices(self):
        header = ctk.CTkFrame(self.devices_frame, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="Устройства", font=FONT_HEADER, text_color=COLOR_TEXT).pack(side="left")

        self.lbl_devices_status = ctk.CTkLabel(header, text="Обновление: ...", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
        self.lbl_devices_status.pack(side="right", padx=8)

        self.sw_show_offline = ctk.CTkSwitch(
            header,
            text="Показывать оффлайн",
            text_color=COLOR_TEXT,
            variable=self.show_offline,
            command=self.update_gui_data,
        )
        self.sw_show_offline.pack(side="right", padx=8)

        split = ctk.CTkFrame(self.devices_frame, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        split.grid_columnconfigure(0, weight=2)
        split.grid_columnconfigure(1, weight=1)
        split.grid_rowconfigure(0, weight=1)

        self.device_list = ctk.CTkScrollableFrame(split, fg_color=COLOR_BG, corner_radius=10)
        self.device_list.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        panel = ctk.CTkFrame(split, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        panel.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(panel, text="Цель", font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM).pack(pady=(18, 4))
        self.lbl_target = ctk.CTkLabel(panel, text="Нет", font=FONT_UI_BOLD, text_color=COLOR_TEXT)
        self.lbl_target.pack(pady=(0, 4))
        self.lbl_target_status = ctk.CTkLabel(panel, text="Цель не выбрана", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
        self.lbl_target_status.pack(pady=(0, 10))

        ctk.CTkLabel(panel, text="Псевдоним", font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM).pack(pady=(8, 4))
        self.ent_alias = ctk.CTkEntry(
            panel,
            textvariable=self.var_device_alias,
            height=32,
            corner_radius=8,
            fg_color=COLOR_PANEL_ALT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
        )
        self.ent_alias.pack(padx=18, fill="x")

        ctk.CTkLabel(panel, text="Примечание", font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM).pack(pady=(8, 4))
        self.ent_note = ctk.CTkEntry(
            panel,
            textvariable=self.var_device_note,
            height=32,
            corner_radius=8,
            fg_color=COLOR_PANEL_ALT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
        )
        self.ent_note.pack(padx=18, fill="x")

        ctk.CTkLabel(panel, text="Профиль передачи", font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM).pack(pady=(8, 4))
        self.opt_preset = ctk.CTkOptionMenu(
            panel,
            values=DEFAULT_DEVICE_PRESETS,
            variable=self.var_transfer_preset,
            corner_radius=8,
            fg_color=COLOR_PANEL_ALT,
            button_color=COLOR_BORDER,
            button_hover_color=COLOR_PANEL,
            text_color=COLOR_TEXT,
            dropdown_fg_color=COLOR_PANEL,
            dropdown_hover_color=COLOR_PANEL_ALT,
            dropdown_text_color=COLOR_TEXT,
        )
        self.opt_preset.pack(padx=18, fill="x")

        adv = ctk.CTkFrame(panel, fg_color="transparent")
        adv.pack(padx=18, pady=(10, 0), fill="x")
        adv.grid_columnconfigure(0, weight=1)
        adv.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(adv, text="Chunk (KB)", font=FONT_SMALL, text_color=COLOR_TEXT_DIM).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(adv, text="Sleep (ms)", font=FONT_SMALL, text_color=COLOR_TEXT_DIM).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.ent_chunk_kb = ctk.CTkEntry(
            adv,
            textvariable=self.var_transfer_chunk_kb,
            height=30,
            corner_radius=8,
            fg_color=COLOR_PANEL_ALT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
        )
        self.ent_chunk_kb.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.ent_sleep_ms = ctk.CTkEntry(
            adv,
            textvariable=self.var_transfer_sleep_ms,
            height=30,
            corner_radius=8,
            fg_color=COLOR_PANEL_ALT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
        )
        self.ent_sleep_ms.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))

        ctk.CTkLabel(panel, text="Права", font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM).pack(pady=(14, 4))
        perms = ctk.CTkFrame(panel, fg_color=COLOR_PANEL_ALT, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
        perms.pack(padx=18, fill="x")

        ctk.CTkSwitch(perms, text="Управление курсором", text_color=COLOR_TEXT, variable=self.var_perm_mouse).pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        ctk.CTkSwitch(perms, text="Клавиатура / медиа", text_color=COLOR_TEXT, variable=self.var_perm_keyboard).pack(
            anchor="w", padx=14, pady=6
        )
        ctk.CTkSwitch(perms, text="Видеопоток (экран)", text_color=COLOR_TEXT, variable=self.var_perm_stream).pack(
            anchor="w", padx=14, pady=6
        )
        ctk.CTkSwitch(perms, text="Файлы на ПК (Upload)", text_color=COLOR_TEXT, variable=self.var_perm_upload).pack(
            anchor="w", padx=14, pady=6
        )
        ctk.CTkSwitch(perms, text="Файлы на устройство (Send)", text_color=COLOR_TEXT, variable=self.var_perm_file_send).pack(
            anchor="w", padx=14, pady=6
        )
        ctk.CTkSwitch(perms, text="Питание / блокировка", text_color=COLOR_TEXT, variable=self.var_perm_power).pack(
            anchor="w", padx=14, pady=(6, 12)
        )

        for v in (
            self.var_device_alias,
            self.var_device_note,
            self.var_transfer_preset,
            self.var_transfer_chunk_kb,
            self.var_transfer_sleep_ms,
            self.var_perm_mouse,
            self.var_perm_keyboard,
            self.var_perm_upload,
            self.var_perm_file_send,
            self.var_perm_stream,
            self.var_perm_power,
        ):
            try:
                v.trace_add("write", self._on_device_setting_changed)
            except Exception:
                pass

        CyberBtn(
            panel,
            text="Сохранить настройки",
            command=self.save_device_settings,
            height=34,
            fg_color=COLOR_ACCENT,
            text_color="#0B0F12",
            hover_color=COLOR_ACCENT_HOVER,
            border_color=COLOR_ACCENT,
        ).pack(padx=18, pady=(12, 6), fill="x")
        CyberBtn(panel, text="Отправить файл", command=self.send_file, height=38).pack(
            padx=18, pady=(6, 14), fill="x"
        )

        self.lbl_status = ctk.CTkLabel(panel, text="> Выберите устройство", text_color=COLOR_TEXT_DIM, font=FONT_SMALL)
        self.lbl_status.pack(pady=(0, 16))

    def setup_settings(self):
        header = ctk.CTkFrame(self.settings_frame, fg_color=COLOR_PANEL, corner_radius=12, height=70)
        header.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(header, text="Настройки", font=FONT_HEADER, text_color=COLOR_TEXT).pack(
            side="left", padx=20, pady=18
        )

        box = ctk.CTkFrame(self.settings_frame, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        box.pack(fill="x", padx=20, pady=10)

        self.sw_start_in_tray = ctk.CTkSwitch(box, text="Запускать в трее", text_color=COLOR_TEXT)
        self.sw_start_in_tray.pack(anchor="w", padx=18, pady=(14, 6))
        self.sw_start_in_tray.select() if self.settings.get("start_in_tray") else self.sw_start_in_tray.deselect()

        self.sw_show_on_start = ctk.CTkSwitch(box, text="Открывать окно при запуске", text_color=COLOR_TEXT)
        self.sw_show_on_start.pack(anchor="w", padx=18, pady=6)
        self.sw_show_on_start.select() if self.settings.get("show_on_start", True) else self.sw_show_on_start.deselect()

        self.sw_close_to_tray = ctk.CTkSwitch(box, text="Закрывать в трей", text_color=COLOR_TEXT)
        self.sw_close_to_tray.pack(anchor="w", padx=18, pady=6)
        self.sw_close_to_tray.select() if self.settings.get("close_to_tray") else self.sw_close_to_tray.deselect()

        self.sw_topmost = ctk.CTkSwitch(box, text="Поверх окон", text_color=COLOR_TEXT)
        self.sw_topmost.pack(anchor="w", padx=18, pady=6)
        self.sw_topmost.select() if self.settings.get("always_on_top") else self.sw_topmost.deselect()

        self.sw_autostart = ctk.CTkSwitch(box, text="Автозапуск с Windows", text_color=COLOR_TEXT)
        self.sw_autostart.pack(anchor="w", padx=18, pady=6)
        self.sw_autostart.select() if self.settings.get("autostart") else self.sw_autostart.deselect()

        self.sw_hotkey = ctk.CTkSwitch(box, text="Горячая клавиша Ctrl+Alt+D (показ/скрытие)", text_color=COLOR_TEXT)
        self.sw_hotkey.pack(anchor="w", padx=18, pady=(6, 14))
        self.sw_hotkey.select() if self.settings.get("hotkey_enabled") else self.sw_hotkey.deselect()

        CyberBtn(box, text="Применить", command=self.save_settings_action, height=34).pack(
            padx=18, pady=(0, 14), fill="x"
        )

        self.lbl_settings_status = ctk.CTkLabel(box, text="", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
        self.lbl_settings_status.pack(anchor="w", padx=18, pady=(0, 12))

        CyberBtn(box, text="О приложении", command=self.show_about, height=34).pack(
            padx=18, pady=(0, 14), fill="x"
        )

    def save_settings_action(self):
        self.settings["start_in_tray"] = bool(self.sw_start_in_tray.get())
        self.settings["show_on_start"] = bool(self.sw_show_on_start.get())
        self.settings["close_to_tray"] = bool(self.sw_close_to_tray.get())
        self.settings["always_on_top"] = bool(self.sw_topmost.get())
        self.settings["autostart"] = bool(self.sw_autostart.get())
        self.settings["hotkey_enabled"] = bool(self.sw_hotkey.get())
        self.start_in_tray = bool(self.settings.get("start_in_tray"))
        self.show_on_start = bool(self.settings.get("show_on_start", True))
        self.apply_settings()
        self.append_log("[launcher] настройки применены\n")
        if hasattr(self, "lbl_settings_status"):
            self.lbl_settings_status.configure(text="Настройки применены", text_color=COLOR_ACCENT)

    def select_frame(self, name):
        self.home_frame.grid_forget()
        self.devices_frame.grid_forget()
        self.settings_frame.grid_forget()

        for btn in (self.btn_home, self.btn_devices, self.btn_settings):
            btn.configure(text_color=COLOR_TEXT_DIM, fg_color="transparent")

        if name == "home":
            self.home_frame.grid(row=0, column=1, sticky="nsew")
            self.btn_home.configure(text_color=COLOR_ACCENT, fg_color=COLOR_PANEL_ALT)
        elif name == "devices":
            self.devices_frame.grid(row=0, column=1, sticky="nsew")
            self.btn_devices.configure(text_color=COLOR_ACCENT, fg_color=COLOR_PANEL_ALT)
        else:
            self.settings_frame.grid(row=0, column=1, sticky="nsew")
            self.btn_settings.configure(text_color=COLOR_ACCENT, fg_color=COLOR_PANEL_ALT)

    def setup_tray(self):
        try:
            image = Image.open(self.icon_path_png)
        except Exception:
            image = Image.new("RGB", (64, 64), color="green")

        menu = pystray.Menu(
            pystray.MenuItem("Показать/скрыть", self.toggle_window),
            pystray.MenuItem("Перезапустить сервер", self.tray_restart_server),
            pystray.MenuItem("Открыть Загрузки", self.open_downloads),
            pystray.MenuItem("О приложении", self.tray_show_about),
            pystray.MenuItem("Выход", self.quit_app),
        )
        self.tray = pystray.Icon("CyberDeck", image, "CyberDeck", menu)
        self.tray.run()

    def tray_restart_server(self, icon=None, item=None):
        self.ui_call(self.restart_server)

    def open_downloads(self, icon=None, item=None):
        try:
            if is_windows():
                os.startfile(os.path.join(os.path.expanduser("~"), "Downloads"))
        except Exception:
            pass

    def show_about(self):
        try:
            messagebox.showinfo("О приложении", ABOUT_TEXT)
        except Exception:
            pass

    def tray_show_about(self, icon=None, item=None):
        try:
            self.ui_call(self.show_about)
        except Exception:
            pass

    def on_close(self):
        if self.settings.get("close_to_tray"):
            self.withdraw()
            self.append_log("[launcher] скрыто в трей\n")
        else:
            self.quit_app()

    def quit_app(self, icon=None, item=None):
        self.stop_server_process()
        try:
            if hasattr(self, "tray"):
                self.tray.stop()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    app = App()
    app.mainloop()
