from __future__ import annotations

from typing import Any

from .shared import *

ELEVATION_ATTEMPT_ENV = "CYBERDECK_ELEVATION_ATTEMPTED"
ELEVATION_MARKER_ARG = "--cyberdeck-elevated"

class AppStartupMixin:
    """Startup/bootstrap methods for launcher application."""

    def __init__(self) -> Any:
        """Initialize AppStartupMixin state and collaborator references."""
        self.console_mode = ("-c" in sys.argv) or ("--console" in sys.argv)
        self.logs_enabled = self.console_mode
        self._enforce_admin_rights()

        super().__init__()

        packaged_runtime = is_packaged_runtime()
        if self.console_mode:
            ensure_console()
            print("[CyberDeck] console mode enabled (-c)")
        else:
            ensure_null_stdio()

        if packaged_runtime:
            self.base_dir = os.path.dirname(sys.executable)
            self.server_exe = os.path.join(self.base_dir, "main.exe" if is_windows() else "main")
            self.launcher_script = sys.executable
            if is_windows():
                self.launch_cmd_for_autostart = f'"{sys.executable}"'
            else:
                self.launch_cmd_for_autostart = [sys.executable]
        else:
            self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.launcher_script = os.path.join(self.base_dir, "launcher.py")
            self.server_exe = os.path.join(self.base_dir, SERVER_SCRIPT_NAME)
            if is_windows():
                self.launch_cmd_for_autostart = f'"{sys.executable}" "{self.launcher_script}"'
            else:
                self.launch_cmd_for_autostart = [sys.executable, self.launcher_script]

        self.resource_dir = detect_resource_dir(self.base_dir)

        self.settings_path = os.path.join(self.base_dir, SETTINGS_FILE_NAME)
        self.settings = load_json(self.settings_path, DEFAULT_SETTINGS)
        self.settings["language"] = normalize_language(self.settings.get("language", DEFAULT_SETTINGS["language"]))
        qr_mode = str(self.settings.get("qr_mode", DEFAULT_SETTINGS["qr_mode"]) or DEFAULT_SETTINGS["qr_mode"]).strip().lower()
        if qr_mode not in ("site", "app"):
            qr_mode = DEFAULT_SETTINGS["qr_mode"]
        self.settings["qr_mode"] = qr_mode
        self.app_config_path = os.path.join(self.base_dir, APP_CONFIG_FILE_NAME)
        self.app_config = load_json(self.app_config_path, DEFAULT_APP_CONFIG)
        self._normalize_app_config()
        save_json(self.app_config_path, self.app_config)
        try:
            self.settings["devices_panel_width"] = max(
                320, int(self.settings.get("devices_panel_width", DEFAULT_SETTINGS["devices_panel_width"]))
            )
        except Exception:
            self.settings["devices_panel_width"] = int(DEFAULT_SETTINGS["devices_panel_width"])
        self.settings["devices_panel_visible"] = bool(
            self.settings.get("devices_panel_visible", DEFAULT_SETTINGS["devices_panel_visible"])
        )
        self.start_in_tray = bool(self.settings.get("start_in_tray", True))
        self.show_on_start = bool(self.settings.get("show_on_start", True))
        self.tls_enabled = bool(self.settings.get("tls_enabled"))
        self.tls_cert_path = str(self.settings.get("tls_cert_path") or "").strip()
        self.tls_key_path = str(self.settings.get("tls_key_path") or "").strip()
        self.tls_ca_path = str(self.settings.get("tls_ca_path") or "").strip()

        self.icon_path_png = os.path.join(self.resource_dir, "icon.png")
        self.icon_path_qr_png = os.path.join(self.resource_dir, "icon-qr-code.png")
        self.icon_path_ico = os.path.join(self.resource_dir, "icon.ico")
        if not os.path.exists(self.icon_path_ico):
            self.icon_path_ico = os.path.join(self.base_dir, "icon.ico")
        self.log_file = str(getattr(server_config, "LOG_FILE", os.path.join(self.base_dir, "cyberdeck.log")))

        self.title("CyberDeck")
        self.geometry("1100x720")
        self._center_window(1100, 720)
        self.configure(fg_color=COLOR_BG)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        try:
            if os.path.exists(self.icon_path_ico):
                self.iconbitmap(self.icon_path_ico)
        except Exception:
            pass

        self._apply_topmost()

        self.server_process = None
        self.server_thread = None
        self._uvicorn_server = None
        self._hotkey_thread_started = False
        self.tray = None
        self._server_log_ring = deque(maxlen=400)
        self._qr_last_fetch_ts = 0.0
        self._qr_ctk_img = None
        self.devices_data = []
        self.show_offline = ctk.BooleanVar(value=False)
        self.selected_token = None
        self.selected_device_name = None
        self.pairing_code = "...."
        self.server_id = ""
        self.server_hostname = ""
        self.server_ip = "0.0.0.0"
        self.port = int(DEFAULT_PORT)
        self.server_port = int(self.port)
        self.api_scheme = "https" if self.tls_enabled else "http"
        if self.tls_enabled:
            self.requests_verify = self.tls_ca_path if self.tls_ca_path else False
        else:
            self.requests_verify = True
        self.api_url = f"{self.api_scheme}://127.0.0.1:{self.port}/api/local"
        self.api_client = LauncherApiClient(self.api_url, verify=self.requests_verify)
        self.server_version = "unknown"
        self.status_text = self.tr("server_placeholder")
        self.server_online = False
        self.update_state = {
            "checked_at": 0,
            "server": {"has_update": False, "latest_tag": "", "error": ""},
            "launcher": {"has_update": False, "latest_tag": "", "error": ""},
            "mobile": {"has_update": False, "latest_tag": "", "error": ""},
        }
        self._seen_update_popup_keys = set()
        self._next_update_pull_ts = 0.0
        self._update_status_line = "Updates: not checked"
        self.current_frame_name = "home"

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
        self._device_rows = {}
        self._device_row_order = []
        self._device_empty_label = None
        self._ui_queue = queue.Queue()
        self._device_settings_dirty = False
        self._selected_device_form_state = None
        self._suppress_device_setting_trace = False
        self._wayland_auto_setup_attempted = False
        self._wayland_warning_shown = False
        self._devices_panel_resizing = False
        self._devices_panel_resize_start_x = 0
        self._devices_panel_resize_start_width = 0
        self._boot_overlay = None
        self._boot_status_label = None
        self._boot_hint_label = None
        self._boot_progress = None
        self._boot_skip_btn = None
        self._boot_media_label = None
        self._boot_media_text_label = None
        self._boot_signature_label = None
        self._boot_media_job = None
        self._boot_media_frame_idx = 0
        self._boot_media_frames = []
        self._boot_media_frame_delays = []
        self._boot_phase = 0
        self._boot_timer_job = None
        self._boot_overlay_visible = False
        self._boot_started_ts = 0.0
        self._boot_exit_job = None
        self._boot_exit_progress = 0
        self._boot_exiting = False

        self.setup_ui()
        self._build_boot_overlay()
        self.toast_manager = ToastManager(
            self,
            color_panel=COLOR_PANEL,
            color_border=COLOR_BORDER,
            color_accent=COLOR_ACCENT,
            color_fail=COLOR_FAIL,
            color_text=COLOR_TEXT,
            font_small=FONT_SMALL,
        )
        self.start_server_process()

        self.after(50, self._process_ui_queue)
        self._schedule_sync(0)
        tray_reason = tray_unavailable_reason()
        if self.settings.get("start_in_tray") or self.settings.get("close_to_tray"):
            if tray_reason:
                self.append_log(f"[launcher] tray disabled: {tray_reason}\n")
            else:
                threading.Thread(target=self.setup_tray, daemon=True).start()

        if self.start_in_tray and (not self.show_on_start) and not tray_reason:
            self.withdraw()

        if self.settings.get("autostart"):
            set_autostart(True, self.launch_cmd_for_autostart)
        if self.settings.get("hotkey_enabled"):
            threading.Thread(target=self.hotkey_loop, daemon=True).start()
            self._hotkey_thread_started = True

    def is_admin(self) -> Any:
        """Return whether admin."""
        if not is_windows():
            return True
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False

    def _enforce_admin_rights(self) -> None:
        """Ensure launcher runs elevated on Windows or terminate startup."""
        if not is_windows():
            return
        if self.is_admin():
            return

        marker_present = ELEVATION_MARKER_ARG in {str(x) for x in sys.argv}
        attempted = marker_present or (str(os.environ.get(ELEVATION_ATTEMPT_ENV, "")).strip() == "1")

        if self.console_mode:
            try:
                ensure_console()
                print("[CyberDeck] admin rights required; requesting elevation...")
            except Exception:
                pass

        if (not attempted) and self.run_as_admin():
            raise SystemExit(0)

        msg = (
            "CyberDeck requires administrator privileges.\n\n"
            "Relaunch was cancelled or failed.\n"
            "Start launcher as Administrator."
        )
        if self.console_mode:
            try:
                print("[CyberDeck] elevation failed or cancelled")
            except Exception:
                pass
        try:
            messagebox.showerror("CyberDeck", msg)
        except Exception:
            pass
        raise SystemExit(1)

    def run_as_admin(self) -> Any:
        """Manage lifecycle transition to run as admin."""
        # Lifecycle transitions are centralized here to prevent partial-state bugs.
        if not is_windows():
            return False
        try:
            os.environ[ELEVATION_ATTEMPT_ENV] = "1"
        except Exception:
            pass
        argv_tail = [str(x) for x in sys.argv[1:] if str(x) != ELEVATION_MARKER_ARG]
        argv_tail = [ELEVATION_MARKER_ARG, *argv_tail]
        if is_packaged_runtime():
            executable = sys.executable
            args = subprocess.list2cmdline(argv_tail)
        else:
            executable = sys.executable
            entry = ""
            try:
                if sys.argv and str(sys.argv[0]).strip():
                    entry = os.path.abspath(str(sys.argv[0]))
            except Exception:
                entry = ""
            if not entry:
                entry = os.path.abspath(
                    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "launcher.py")
                )
            args = subprocess.list2cmdline([entry, *argv_tail])
        try:
            rc = int(ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, args, None, 1))
        except Exception:
            return False
        # ShellExecuteW returns value > 32 on success.
        return rc > 32

    def kill_old_server(self) -> Any:
        """Terminate old server."""
        # Legacy no-op kept for API compatibility.
        return

    def _is_port_free(self, port: int) -> bool:
        """Return whether port free."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", int(port)))
                return True
        except Exception:
            return False

    def _pick_port(self, preferred: int) -> int:
        """Pick port."""
        try:
            preferred = int(preferred)
        except Exception:
            preferred = int(DEFAULT_PORT)

        candidates: list[int] = []

        def _push_port(p: int) -> None:
            """Add a unique valid port candidate."""
            try:
                pi = int(p)
            except Exception:
                return
            if 1 <= pi <= 65535 and pi not in candidates:
                candidates.append(pi)

        if preferred > 0:
            _push_port(preferred)
            for i in range(1, PORT_PICK_SPAN + 1):
                _push_port(preferred + i)
                _push_port(preferred - i)

        _push_port(DEFAULT_PORT)
        for i in range(1, PORT_PICK_SPAN + 1):
            _push_port(DEFAULT_PORT + i)
            _push_port(DEFAULT_PORT - i)

        for p in range(9000, 9051):
            _push_port(p)

        for p in candidates:
            if self._is_port_free(p):
                return int(p)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", 0))
                return int(s.getsockname()[1])
        except Exception:
            return int(DEFAULT_PORT)

    def _center_window(self, width: int = None, height: int = None) -> Any:
        """Center the launcher window on the current monitor."""
        try:
            self.update_idletasks()
            if width is None or height is None:
                g = str(self.geometry() or "1100x720").split("+", 1)[0]
                w_str, h_str = g.split("x", 1)
                width = int(w_str)
                height = int(h_str)
            sw = int(self.winfo_screenwidth())
            sh = int(self.winfo_screenheight())
            x = max(0, int((sw - int(width)) / 2))
            y = max(0, int((sh - int(height)) / 2))
            self.geometry(f"{int(width)}x{int(height)}+{x}+{y}")
        except Exception:
            pass

    def _select_port_for_launch(self) -> None:
        """Select port for launch."""
        self.port = self._pick_port(self.settings.get("preferred_port", DEFAULT_PORT))
        self.server_port = int(self.port)
        self.api_url = f"{self.api_scheme}://127.0.0.1:{self.port}/api/local"
        self.api_client.configure(self.api_url, self.requests_verify)

    @staticmethod
    def _normalize_ext_csv(raw: str) -> str:
        """Normalize ext CSV."""
        out = []
        for x in str(raw or "").split(","):
            token = str(x or "").strip().lower()
            if not token:
                continue
            if not token.startswith("."):
                token = f".{token}"
            if token not in out:
                out.append(token)
        return ",".join(out)

    def _normalize_app_config(self) -> None:
        """Normalize app config."""
        cfg = dict(DEFAULT_APP_CONFIG)
        try:
            if isinstance(self.app_config, dict):
                cfg.update(self.app_config)
        except Exception:
            pass
        cfg["allow_query_token"] = bool(cfg.get("allow_query_token"))
        try:
            cfg["upload_max_bytes"] = max(0, int(cfg.get("upload_max_bytes", 0)))
        except Exception:
            cfg["upload_max_bytes"] = 0
        cfg["upload_allowed_ext"] = self._normalize_ext_csv(str(cfg.get("upload_allowed_ext", "") or ""))
        cfg["verbose_http_log"] = bool(cfg.get("verbose_http_log", True))
        cfg["verbose_ws_log"] = bool(cfg.get("verbose_ws_log", True))
        cfg["verbose_stream_log"] = bool(cfg.get("verbose_stream_log", True))
        cfg["mdns_enabled"] = bool(cfg.get("mdns_enabled", True))
        self.app_config = cfg

    def start_server_process(self) -> Any:
        """Manage lifecycle transition to start server process."""
        # Lifecycle transitions are centralized here to prevent partial-state bugs.
        self._show_boot_overlay("Starting server...")
        self._ensure_wayland_setup()
        self._select_port_for_launch()

        env = os.environ.copy()
        env["CYBERDECK_CONSOLE"] = "1" if self.logs_enabled else "0"
        env["CYBERDECK_LOG"] = "1" if self.logs_enabled else "0"
        env["CYBERDECK_DEBUG"] = "1" if bool(self.settings.get("debug")) else "0"
        env["CYBERDECK_PORT"] = str(int(self.port))
        env["CYBERDECK_PORT_AUTO"] = "0"

        try:
            env["CYBERDECK_PAIRING_TTL_S"] = str(max(0, int(self.settings.get("pairing_ttl_min", 0))) * 60)
        except Exception:
            env["CYBERDECK_PAIRING_TTL_S"] = "0"

        try:
            env["CYBERDECK_SESSION_TTL_S"] = str(max(0, int(self.settings.get("session_ttl_days", 0))) * 86400)
        except Exception:
            env["CYBERDECK_SESSION_TTL_S"] = "0"

        try:
            env["CYBERDECK_SESSION_IDLE_TTL_S"] = str(max(0, int(self.settings.get("session_idle_ttl_min", 0))) * 60)
        except Exception:
            env["CYBERDECK_SESSION_IDLE_TTL_S"] = "0"

        try:
            env["CYBERDECK_MAX_SESSIONS"] = str(max(0, int(self.settings.get("max_sessions", 0))))
        except Exception:
            env["CYBERDECK_MAX_SESSIONS"] = "0"

        try:
            env["CYBERDECK_PIN_WINDOW_S"] = str(max(1, int(self.settings.get("pin_window_s", 60))))
        except Exception:
            env["CYBERDECK_PIN_WINDOW_S"] = "60"

        try:
            env["CYBERDECK_PIN_MAX_FAILS"] = str(max(1, int(self.settings.get("pin_max_fails", 8))))
        except Exception:
            env["CYBERDECK_PIN_MAX_FAILS"] = "8"

        try:
            env["CYBERDECK_PIN_BLOCK_S"] = str(max(1, int(self.settings.get("pin_block_s", 300))))
        except Exception:
            env["CYBERDECK_PIN_BLOCK_S"] = "300"

        env["CYBERDECK_CONFIG_FILE"] = str(self.app_config_path)
        env["CYBERDECK_ALLOW_QUERY_TOKEN"] = "1" if bool(self.app_config.get("allow_query_token")) else "0"
        env["CYBERDECK_UPLOAD_MAX_BYTES"] = str(max(0, int(self.app_config.get("upload_max_bytes", 0) or 0)))
        env["CYBERDECK_UPLOAD_ALLOWED_EXT"] = str(self.app_config.get("upload_allowed_ext", "") or "")
        env["CYBERDECK_VERBOSE_HTTP_LOG"] = "1" if bool(self.app_config.get("verbose_http_log", True)) else "0"
        env["CYBERDECK_VERBOSE_WS_LOG"] = "1" if bool(self.app_config.get("verbose_ws_log", True)) else "0"
        env["CYBERDECK_VERBOSE_STREAM_LOG"] = "1" if bool(self.app_config.get("verbose_stream_log", True)) else "0"
        env["CYBERDECK_MDNS"] = "1" if bool(self.app_config.get("mdns_enabled", True)) else "0"

        if self.tls_enabled and self.tls_cert_path and self.tls_key_path:
            env["CYBERDECK_TLS"] = "1"
            env["CYBERDECK_TLS_CERT"] = self.tls_cert_path
            env["CYBERDECK_TLS_KEY"] = self.tls_key_path
        else:
            env["CYBERDECK_TLS"] = "0"
            env["CYBERDECK_TLS_CERT"] = ""
            env["CYBERDECK_TLS_KEY"] = ""

        os.environ.update(env)
        if is_packaged_runtime():
            # In packaged builds we always run server in-process to avoid
            # accidental recursive launches via stale external binaries.
            self.start_server_inprocess()
            self.append_log("[launcher] server started (in-process)\n")
            return
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
            self.append_log("[launcher] server process started\n")
        except Exception as e:
            self.append_log(f"[launcher] failed to start server process: {e}\n")
            self._show_server_start_error(str(e))

    def _ensure_wayland_setup(self) -> Any:
        """Ensure wayland setup."""
        if not is_linux_wayland_session():
            return

        auto_install = not self._wayland_auto_setup_attempted
        if auto_install:
            self.append_log("[launcher] Wayland detected: checking screen-stream setup...\n")
        else:
            self.append_log("[launcher] Wayland detected: re-checking stream setup...\n")

        ok, issues, attempted, reason = ensure_wayland_ready(
            self.base_dir,
            auto_install=auto_install,
            log=lambda line: self.append_log(f"[wayland-setup] {line}\n"),
        )
        if attempted:
            self._wayland_auto_setup_attempted = True

        if ok:
            if issues:
                issue_text = format_wayland_issues(issues)
                self.append_log(f"[launcher] Wayland setup is usable with warnings: {issue_text} ({reason})\n")
            else:
                self.append_log("[launcher] Wayland setup is ready.\n")
            return

        issue_text = format_wayland_issues(issues)
        self.append_log(f"[launcher] Wayland setup is not ready: {issue_text} ({reason})\n")

        if self._wayland_warning_shown:
            return
        self._wayland_warning_shown = True

        setup_script = find_wayland_setup_script(self.base_dir)
        manual_hint = f"  bash {setup_script}" if setup_script else (
            "  bash ./scripts/setup_ubuntu_wayland.sh\n"
            "  # or\n"
            "  bash ./scripts/setup_arch_wayland.sh"
        )

        msg = (
            "Wayland stream backend is not ready.\n\n"
            f"Issue: {issue_text}\n\n"
            "Run setup script manually:\n"
            f"{manual_hint}\n\n"
            "Then restart launcher and restart CyberDeck server."
        )
        try:
            messagebox.showwarning("CyberDeck", msg)
        except Exception:
            pass

    def _show_server_start_error(self, extra: str = "") -> Any:
        """Show server start error."""
        try:
            tail = "".join(list(self._server_log_ring)[-80:])
        except Exception:
            tail = ""

        msg = "Failed to start server.\n\n"
        if extra:
            msg += f"Details: {extra}\n\n"
        if tail.strip():
            msg += "Recent logs:\n" + tail[-4000:]
        else:
            msg += "No logs available. Run launcher with -c for console output."

        try:
            self.ui_call(lambda: messagebox.showerror("CyberDeck", msg))
        except Exception:
            pass

