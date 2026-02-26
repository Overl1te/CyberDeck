from __future__ import annotations

from typing import Any

from .shared import *


class AppNavigationMixin:
    """Navigation, settings save flow, tray/menu, and app shutdown methods."""

    def create_nav_btn(self, text: str, name: str, row: int) -> Any:
        """Create nav btn."""
        def cmd() -> None:
            """Switch to selected frame."""
            self.select_frame(name)

        btn = CyberBtn(
            self.sidebar,
            text=str(text or ""),
            fg_color="transparent",
            text_color=COLOR_TEXT_DIM,
            border_width=0,
            border_color=COLOR_BORDER,
            hover_color=COLOR_PANEL_ALT,
            anchor="w",
            font=FONT_UI_BOLD,
            corner_radius=8,
            height=40,
            command=cmd,
        )
        btn.grid(row=row, column=0, sticky="ew", padx=14, pady=5)
        return btn

    def _ui_theme(self) -> Any:
        """Return color palette used by navigation controls."""
        return {
            "CyberBtn": CyberBtn,
            "COLOR_BG": COLOR_BG,
            "COLOR_PANEL": COLOR_PANEL,
            "COLOR_PANEL_ALT": COLOR_PANEL_ALT,
            "COLOR_BORDER": COLOR_BORDER,
            "COLOR_ACCENT": COLOR_ACCENT,
            "COLOR_ACCENT_HOVER": COLOR_ACCENT_HOVER,
            "COLOR_WARN": COLOR_WARN,
            "COLOR_FAIL": COLOR_FAIL,
            "COLOR_TEXT": COLOR_TEXT,
            "COLOR_TEXT_DIM": COLOR_TEXT_DIM,
            "FONT_UI_BOLD": FONT_UI_BOLD,
            "FONT_HEADER": FONT_HEADER,
            "FONT_SMALL": FONT_SMALL,
            "FONT_CODE": FONT_CODE,
            "DEFAULT_PORT": DEFAULT_PORT,
            "DEFAULT_SETTINGS": DEFAULT_SETTINGS,
            "APP_CONFIG_FILE_NAME": APP_CONFIG_FILE_NAME,
            "DEFAULT_DEVICE_PRESETS": DEFAULT_DEVICE_PRESETS,
        }

    def setup_home(self) -> Any:
        """Build and attach widgets for the Home tab."""
        setup_home_ui(self, self._ui_theme())

    def setup_devices(self) -> Any:
        """Build and attach widgets for the Devices tab."""
        setup_devices_ui(self, self._ui_theme())

    def setup_settings(self) -> Any:
        """Build and attach widgets for the Settings tab."""
        setup_settings_ui(self, self._ui_theme())

    def save_settings_action(self) -> Any:
        """Save settings action."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        restart_keys = (
            "debug",
            "preferred_port",
            "pairing_ttl_min",
            "session_ttl_days",
            "session_idle_ttl_min",
            "max_sessions",
            "pin_window_s",
            "pin_max_fails",
            "pin_block_s",
            "tls_enabled",
            "tls_cert_path",
            "tls_key_path",
            "tls_ca_path",
            "qr_mode",
        )
        app_restart_keys = (
            "allow_query_token",
            "pairing_single_use",
            "ignore_vpn",
            "upload_max_bytes",
            "upload_allowed_ext",
            "verbose_http_log",
            "verbose_ws_log",
            "verbose_stream_log",
            "mdns_enabled",
            "device_approval_required",
        )
        launcher_restart_keys = ("hotkey_enabled",)
        old_language = str(self.settings.get("language", "ru"))
        old_restart_values = {k: self.settings.get(k) for k in restart_keys}
        old_app_restart_values = {k: self.app_config.get(k) for k in app_restart_keys}
        old_launcher_values = {k: self.settings.get(k) for k in launcher_restart_keys}

        def _get_int(entry: Any, default: int) -> int:
            """Parse integer from entry with fallback."""
            try:
                v = str(entry.get()).strip()
                if v == "":
                    return int(default)
                return int(float(v))
            except Exception:
                return int(default)

        self.settings["start_in_tray"] = bool(self.sw_start_in_tray.get())
        self.settings["show_on_start"] = bool(self.sw_show_on_start.get())
        self.settings["close_to_tray"] = bool(self.sw_close_to_tray.get())
        self.settings["always_on_top"] = bool(self.sw_topmost.get())
        self.settings["autostart"] = bool(self.sw_autostart.get())
        self.settings["hotkey_enabled"] = bool(self.sw_hotkey.get())
        self.settings["debug"] = bool(self.sw_debug.get())
        if hasattr(self, "sw_system_notifications"):
            self.settings["system_notifications"] = bool(self.sw_system_notifications.get())

        self.settings["preferred_port"] = max(1, _get_int(self.ent_preferred_port, DEFAULT_PORT))
        self.settings["pairing_ttl_min"] = max(0, _get_int(self.ent_pairing_ttl, 0))
        self.settings["session_ttl_days"] = max(0, _get_int(self.ent_session_ttl_days, 0))
        self.settings["session_idle_ttl_min"] = max(0, _get_int(self.ent_session_idle_min, 0))
        self.settings["max_sessions"] = max(0, _get_int(self.ent_max_sessions, 0))
        self.settings["pin_window_s"] = max(1, _get_int(self.ent_pin_window_s, 60))
        self.settings["pin_max_fails"] = max(1, _get_int(self.ent_pin_max_fails, 8))
        self.settings["pin_block_s"] = max(1, _get_int(self.ent_pin_block_s, 300))

        self.settings["tls_enabled"] = bool(self.sw_tls.get())
        self.settings["tls_cert_path"] = str(self.ent_tls_cert.get()).strip()
        self.settings["tls_key_path"] = str(self.ent_tls_key.get()).strip()
        self.settings["tls_ca_path"] = str(self.ent_tls_ca.get()).strip()
        self.settings["qr_mode"] = str(self.qr_mode_var.get() or DEFAULT_SETTINGS["qr_mode"]).strip().lower()
        if self.settings["qr_mode"] not in ("site", "app"):
            self.settings["qr_mode"] = DEFAULT_SETTINGS["qr_mode"]
        if hasattr(self, "opt_language"):
            self.settings["language"] = normalize_language(self.language_code_from_label(self.opt_language.get()))

        if hasattr(self, "sw_allow_query_token"):
            self.app_config["allow_query_token"] = bool(self.sw_allow_query_token.get())
        if hasattr(self, "sw_pairing_single_use"):
            self.app_config["pairing_single_use"] = bool(self.sw_pairing_single_use.get())
        if hasattr(self, "sw_ignore_vpn"):
            self.app_config["ignore_vpn"] = bool(self.sw_ignore_vpn.get())
        if hasattr(self, "ent_upload_max_bytes"):
            self.app_config["upload_max_bytes"] = max(0, _get_int(self.ent_upload_max_bytes, 0))
        if hasattr(self, "ent_upload_allowed_ext"):
            self.app_config["upload_allowed_ext"] = self._normalize_ext_csv(self.ent_upload_allowed_ext.get())
        if hasattr(self, "sw_verbose_http_log"):
            self.app_config["verbose_http_log"] = bool(self.sw_verbose_http_log.get())
        if hasattr(self, "sw_verbose_ws_log"):
            self.app_config["verbose_ws_log"] = bool(self.sw_verbose_ws_log.get())
        if hasattr(self, "sw_verbose_stream_log"):
            self.app_config["verbose_stream_log"] = bool(self.sw_verbose_stream_log.get())
        if hasattr(self, "sw_mdns_enabled"):
            self.app_config["mdns_enabled"] = bool(self.sw_mdns_enabled.get())
        if hasattr(self, "sw_device_approval_required"):
            self.app_config["device_approval_required"] = bool(self.sw_device_approval_required.get())
        self._normalize_app_config()

        if self.settings["tls_enabled"] and (not self.settings["tls_cert_path"] or not self.settings["tls_key_path"]):
            try:
                self.tls_enabled = True
                self.tls_cert_path = str(self.settings.get("tls_cert_path") or "").strip()
                self.tls_key_path = str(self.settings.get("tls_key_path") or "").strip()
                self._ensure_tls_material()
                self.settings["tls_enabled"] = bool(self.tls_enabled)
                self.settings["tls_cert_path"] = str(self.tls_cert_path or "")
                self.settings["tls_key_path"] = str(self.tls_key_path or "")
            except Exception:
                pass
            if self.settings["tls_enabled"] and self.settings["tls_cert_path"] and self.settings["tls_key_path"]:
                try:
                    self.ent_tls_cert.delete(0, "end")
                    self.ent_tls_cert.insert(0, self.settings["tls_cert_path"])
                    self.ent_tls_key.delete(0, "end")
                    self.ent_tls_key.insert(0, self.settings["tls_key_path"])
                except Exception:
                    pass
            else:
                try:
                    messagebox.showerror(self.tr("app_name"), self.tr("tls_invalid"))
                except Exception:
                    pass
                self.settings["tls_enabled"] = False
                try:
                    self.sw_tls.deselect()
                except Exception:
                    pass

        self.start_in_tray = bool(self.settings.get("start_in_tray"))
        self.show_on_start = bool(self.settings.get("show_on_start", True))
        self.tls_enabled = bool(self.settings.get("tls_enabled"))
        self.tls_cert_path = str(self.settings.get("tls_cert_path") or "").strip()
        self.tls_key_path = str(self.settings.get("tls_key_path") or "").strip()
        self.tls_ca_path = str(self.settings.get("tls_ca_path") or "").strip()
        if hasattr(self, "_refresh_api_transport"):
            self._refresh_api_transport()
        else:
            self.api_scheme = "https" if self.tls_enabled else "http"
            if self.tls_enabled:
                self.requests_verify = self.tls_ca_path if self.tls_ca_path else False
            else:
                self.requests_verify = True
        self.api_url = f"{self.api_scheme}://127.0.0.1:{self.port}/api/local"
        self.api_client.configure(self.api_url, self.requests_verify)
        self.apply_settings()
        self.append_log("[launcher] settings applied\n")
        language_changed = str(self.settings.get("language", "ru")) != str(old_language)
        if language_changed:
            self._rebuild_ui_for_language()
        if hasattr(self, "lbl_settings_status"):
            self.lbl_settings_status.configure(text=self.tr("settings_applied"), text_color=COLOR_ACCENT)

        restart_server_needed = False
        try:
            if any(self.settings.get(k) != old_restart_values.get(k) for k in restart_keys):
                restart_server_needed = True
            if any(self.app_config.get(k) != old_app_restart_values.get(k) for k in app_restart_keys):
                restart_server_needed = True
        except Exception:
            pass
        if restart_server_needed:
            self.restart_server()

        launcher_restart_needed = False
        try:
            if any(self.settings.get(k) != old_launcher_values.get(k) for k in launcher_restart_keys):
                if (not bool(self.settings.get("hotkey_enabled"))) and bool(old_launcher_values.get("hotkey_enabled")):
                    launcher_restart_needed = True
        except Exception:
            pass

        if launcher_restart_needed and hasattr(self, "lbl_settings_status"):
            self.lbl_settings_status.configure(
                text=self.tr("settings_restart_launcher"),
                text_color=COLOR_WARN,
            )

        try:
            if self.settings.get("qr_mode") != old_restart_values.get("qr_mode"):
                self.refresh_qr_code(force=True)
        except Exception:
            pass

    def select_frame(self, name: str) -> Any:
        """Select frame."""
        self.current_frame_name = str(name or "home")
        self.home_frame.grid_forget()
        self.devices_frame.grid_forget()
        self.settings_frame.grid_forget()

        for btn in (self.btn_home, self.btn_devices, self.btn_settings):
            btn.configure(text_color=COLOR_TEXT_DIM, fg_color="transparent", border_width=0, border_color=COLOR_BORDER)

        if name == "home":
            self.home_frame.grid(row=0, column=1, sticky="nsew")
            self.btn_home.configure(
                text_color=COLOR_TEXT,
                fg_color=COLOR_PANEL_ALT,
                border_width=1,
                border_color=COLOR_ACCENT,
            )
        elif name == "devices":
            self.devices_frame.grid(row=0, column=1, sticky="nsew")
            self.btn_devices.configure(
                text_color=COLOR_TEXT,
                fg_color=COLOR_PANEL_ALT,
                border_width=1,
                border_color=COLOR_ACCENT,
            )
        else:
            self.settings_frame.grid(row=0, column=1, sticky="nsew")
            self.btn_settings.configure(
                text_color=COLOR_TEXT,
                fg_color=COLOR_PANEL_ALT,
                border_width=1,
                border_color=COLOR_ACCENT,
            )

    def setup_tray(self) -> Any:
        """Initialize system tray menu actions and icon behavior."""
        reason = tray_unavailable_reason()
        if reason:
            self.append_log(f"[launcher] tray disabled: {reason}\n")
            self.ui_call(self._ensure_window_visible)
            return

        try:
            image = Image.open(self.icon_path_png)
        except Exception:
            image = Image.new("RGB", (64, 64), color="green")

        menu = pystray.Menu(
            pystray.MenuItem(self.tr("tray_toggle"), self.toggle_window),
            pystray.MenuItem(self.tr("tray_restart"), self.tray_restart_server),
            pystray.MenuItem(self.tr("tray_downloads"), self.open_downloads),
            pystray.MenuItem(self.tr("tray_help"), self.tray_show_help),
            pystray.MenuItem(self.tr("tray_about"), self.tray_show_about),
            pystray.MenuItem(self.tr("tray_exit"), self.quit_app),
        )
        self.tray = pystray.Icon("CyberDeck", image, "CyberDeck", menu)
        try:
            self.tray.run()
        except Exception as e:
            self.append_log(f"[launcher] tray unavailable: {e}\n")
            try:
                if hasattr(self, "tray") and self.tray:
                    self.tray.stop()
            except Exception:
                pass
            self.tray = None
            self.ui_call(self._ensure_window_visible)

    def tray_restart_server(self, icon: Any = None, item: Any = None) -> Any:
        """Restart the embedded server process from tray menu action."""
        self.ui_call(self.restart_server)

    def open_downloads(self, icon: Any = None, item: Any = None) -> Any:
        """Open or close resources required to open downloads."""
        try:
            path = os.path.join(os.path.expanduser("~"), "Downloads")
            if is_windows():
                os.startfile(path)
            elif sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", path], close_fds=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path], close_fds=True)
        except Exception:
            pass

    def show_help(self) -> Any:
        """Show help."""
        existing = getattr(self, "_help_window", None)
        if existing:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass

        text = str(self.tr("help_text", version=LAUNCHER_VERSION) or "").strip()
        commands_text = str(self.tr("help_commands") or "").strip()
        try:
            win = ctk.CTkToplevel(self)
            self._help_window = win
            win.title(self.tr("help_title"))
            win.geometry("920x620")
            win.minsize(760, 500)
            win.configure(fg_color=COLOR_BG)
            win.transient(self)
            win.protocol("WM_DELETE_WINDOW", self._close_help_window)

            try:
                self.update_idletasks()
                win.update_idletasks()
                w = int(win.winfo_width() or 920)
                h = int(win.winfo_height() or 620)
                x = int(self.winfo_x() + max(0, (self.winfo_width() - w) / 2))
                y = int(self.winfo_y() + max(0, (self.winfo_height() - h) / 2))
                win.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                pass

            shell = ctk.CTkFrame(
                win,
                fg_color=COLOR_PANEL,
                corner_radius=12,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            shell.pack(fill="both", expand=True, padx=14, pady=14)
            shell.grid_columnconfigure(1, weight=1)
            shell.grid_rowconfigure(1, weight=1)

            header = ctk.CTkFrame(shell, fg_color=COLOR_PANEL_ALT, corner_radius=10, border_width=1, border_color=COLOR_BORDER)
            header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 10))
            ctk.CTkLabel(
                header,
                text=self.tr("help_title"),
                font=FONT_HEADER,
                text_color=COLOR_TEXT,
            ).pack(anchor="w", padx=14, pady=(10, 0))
            ctk.CTkLabel(
                header,
                text=self.tr("help_subtitle", version=LAUNCHER_VERSION),
                font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM,
            ).pack(anchor="w", padx=14, pady=(2, 10))

            sidebar = ctk.CTkFrame(
                shell,
                width=245,
                fg_color=COLOR_PANEL_ALT,
                corner_radius=10,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            sidebar.grid(row=1, column=0, sticky="nsew", padx=(12, 8), pady=(0, 12))
            sidebar.grid_propagate(False)
            ctk.CTkLabel(
                sidebar,
                text=self.tr("help_quick_actions"),
                font=FONT_UI_BOLD,
                text_color=COLOR_TEXT,
            ).pack(anchor="w", padx=12, pady=(12, 8))

            CyberBtn(
                sidebar,
                text=self.tr("nav_support"),
                command=self.open_support_page,
                height=34,
            ).pack(fill="x", padx=12, pady=(0, 6))
            CyberBtn(
                sidebar,
                text=self.tr("open_app_config"),
                command=self.open_app_config_file,
                height=34,
            ).pack(fill="x", padx=12, pady=6)
            CyberBtn(
                sidebar,
                text=self.tr("help_copy_commands"),
                command=self._copy_help_commands,
                height=34,
                fg_color=COLOR_PANEL,
                hover_color=COLOR_PANEL_ALT,
            ).pack(fill="x", padx=12, pady=(6, 10))

            ctk.CTkLabel(
                sidebar,
                text=self.tr("help_commands_title"),
                font=FONT_UI_BOLD,
                text_color=COLOR_TEXT_DIM,
            ).pack(anchor="w", padx=12, pady=(4, 6))

            cmd_box = ctk.CTkTextbox(
                sidebar,
                height=130,
                fg_color=COLOR_BG,
                border_width=1,
                border_color=COLOR_BORDER,
                corner_radius=8,
                text_color=COLOR_TEXT,
                font=FONT_SMALL,
                wrap="word",
            )
            cmd_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            cmd_box.insert("1.0", commands_text)
            cmd_box.configure(state="disabled")

            body = ctk.CTkFrame(shell, fg_color="transparent")
            body.grid(row=1, column=1, sticky="nsew", padx=(8, 12), pady=(0, 12))
            body.grid_rowconfigure(0, weight=1)
            body.grid_columnconfigure(0, weight=1)

            text_box = ctk.CTkTextbox(
                body,
                fg_color=COLOR_PANEL_ALT,
                border_width=1,
                border_color=COLOR_BORDER,
                corner_radius=10,
                text_color=COLOR_TEXT,
                font=FONT_UI,
                wrap="word",
            )
            text_box.grid(row=0, column=0, sticky="nsew")
            text_box.insert("1.0", text)
            text_box.configure(state="disabled")

            actions = ctk.CTkFrame(shell, fg_color="transparent")
            actions.grid(row=2, column=0, columnspan=2, sticky="e", padx=12, pady=(0, 12))
            CyberBtn(
                actions,
                text=self.tr("help_close"),
                command=self._close_help_window,
                width=140,
                height=34,
            ).pack(side="right")

            win.focus_force()
            win.lift()
        except Exception:
            try:
                messagebox.showinfo(self.tr("help_title"), text)
            except Exception:
                pass

    def _close_help_window(self) -> Any:
        """Close help window if it exists."""
        win = getattr(self, "_help_window", None)
        self._help_window = None
        if not win:
            return
        try:
            win.destroy()
        except Exception:
            pass

    def _copy_help_commands(self) -> Any:
        """Copy diagnostics/test commands from help sidebar."""
        payload = str(self.tr("help_commands") or "").strip()
        if not payload:
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(payload)
            self.update_idletasks()
            self.show_toast(self.tr("help_commands_copied"), level="success")
        except Exception:
            pass

    def open_app_config_file(self) -> Any:
        """Open or close resources required to open app config file."""
        path = str(self.app_config_path)
        try:
            if is_windows():
                os.startfile(path)
            elif sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", path], close_fds=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path], close_fds=True)
        except Exception:
            try:
                self.show_toast(self.tr("open_file_failed", path=path), level="error")
            except Exception:
                pass

    def open_support_page(self) -> Any:
        """Open or close resources required to open support page."""
        try:
            if not webbrowser.open(SUPPORT_URL, new=2):
                raise RuntimeError("browser_open_failed")
        except Exception:
            try:
                self.show_toast(self.tr("support_open_failed"), level="error")
            except Exception:
                pass

    def show_about(self) -> Any:
        """Show about."""
        about_text = self.tr("about_text", version=LAUNCHER_VERSION)
        try:
            messagebox.showinfo(self.tr("about_title"), about_text)
        except Exception:
            pass

    def tray_show_about(self, icon: Any = None, item: Any = None) -> Any:
        """Open the About dialog from tray menu action."""
        try:
            self.ui_call(self.show_about)
        except Exception:
            pass

    def tray_show_help(self, icon: Any = None, item: Any = None) -> Any:
        """Open help links from tray menu action."""
        try:
            self.ui_call(self.show_help)
        except Exception:
            pass

    def on_close(self) -> Any:
        """Apply close behavior: hide to tray or fully terminate the app."""
        if self.settings.get("close_to_tray") and getattr(self, "tray", None):
            self.withdraw()
            self.append_log("[launcher] minimized to tray\n")
        else:
            self.quit_app()

    def quit_app(self, icon: Any = None, item: Any = None) -> Any:
        """Stop background services and exit the launcher process."""
        self.stop_server_process()
        try:
            if hasattr(self, "tray"):
                self.tray.stop()
        except Exception:
            pass
        os._exit(0)

