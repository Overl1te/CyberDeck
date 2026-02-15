from __future__ import annotations

from typing import Any

from .launcher_shared import *


class AppRuntimeMixin:
    """Runtime/server synchronization and device list rendering methods."""

    def start_server_inprocess(self) -> Any:
        """Manage lifecycle transition to start server inprocess."""
        # Lifecycle transitions are centralized here to prevent partial-state bugs.
        if self.server_thread and self.server_thread.is_alive():
            return
        try:
            try:
                import cyberdeck.config as cfg
                cfg.reload_from_env()
                import cyberdeck.logging_config as lc
                lc.reload_logging()
            except Exception:
                pass

            import main as cyberdeck_server

            log_level = "debug" if os.environ.get("CYBERDECK_DEBUG", "0") == "1" else "info"
            access_log = os.environ.get("CYBERDECK_DEBUG", "0") == "1"
            if os.environ.get("CYBERDECK_LOG", "0") != "1":
                log_level = "critical"
                access_log = False

            config = uvicorn.Config(
                cyberdeck_server.app,
                host="0.0.0.0",
                port=int(self.port),
                log_level=log_level,
                access_log=access_log,
                ssl_certfile=os.environ.get("CYBERDECK_TLS_CERT") if os.environ.get("CYBERDECK_TLS", "0") == "1" else None,
                ssl_keyfile=os.environ.get("CYBERDECK_TLS_KEY") if os.environ.get("CYBERDECK_TLS", "0") == "1" else None,
            )
            server = uvicorn.Server(config)
            self._uvicorn_server = server

            def _run() -> None:
                """Run uvicorn server in background thread."""
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

    def stop_server_process(self) -> Any:
        """Manage lifecycle transition to stop server process."""
        # Lifecycle transitions are centralized here to prevent partial-state bugs.
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

    def restart_server(self) -> Any:
        """Manage lifecycle transition to restart server."""
        # Lifecycle transitions are centralized here to prevent partial-state bugs.
        self.append_log("[launcher] перезапуск сервера...\n")
        self.stop_server_process()
        time.sleep(0.2)
        self.start_server_process()

    def server_stdout_loop(self) -> Any:
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

    def append_log(self, text: str) -> Any:
        """Append log."""
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

    def _safe_after(self, delay_ms: int, callback: Any) -> Any:
        """Schedule a Tk callback only if the root window is alive."""
        try:
            if not self.winfo_exists():
                return None
        except Exception:
            return None
        try:
            return self.after(int(delay_ms), callback)
        except Exception:
            return None

    def _schedule_sync(self, delay_ms: int) -> Any:
        """Schedule sync."""
        try:
            if self._sync_job is not None:
                self.after_cancel(self._sync_job)
        except Exception:
            pass
        self._sync_job = self._safe_after(max(0, int(delay_ms)), self.sync_loop)

    def request_sync(self, delay_ms: int = 0) -> Any:
        """Request a deferred GUI synchronization pass."""
        self._schedule_sync(delay_ms)

    def ui_call(self, fn: Any) -> Any:
        """Queue a callable that must run on the UI thread."""
        try:
            self._ui_queue.put(fn)
        except Exception:
            pass

    def tr(self, key: str, **kwargs: Any) -> str:
        """Translate a localization key using the active language."""
        return i18n_tr(self.settings.get("language", "ru"), key, **kwargs)

    def language_options(self) -> list[str]:
        """Return available language labels for the UI."""
        return i18n_language_options()

    def language_label(self, code: str = None) -> str:
        """Resolve a human-readable language label from a code."""
        return i18n_language_label(code or self.settings.get("language", "ru"))

    def language_code_from_label(self, label: str) -> str:
        """Resolve language code from the selected localized label."""
        return i18n_language_code(label)

    def _rebuild_ui_for_language(self) -> Any:
        """Refresh visible UI text after language switch."""
        active = str(getattr(self, "current_frame_name", "home") or "home")
        if active not in ("home", "devices", "settings"):
            active = "home"
        saved_token = self.selected_token
        for name in ("sidebar", "home_frame", "devices_frame", "settings_frame"):
            w = getattr(self, name, None)
            if not w:
                continue
            try:
                w.destroy()
            except Exception:
                pass
        self.setup_ui()
        self.select_frame(active)
        self.selected_token = saved_token
        try:
            self.update_gui_data()
            self.refresh_selected_panel()
        except Exception:
            pass
        need_tray = bool(self.settings.get("start_in_tray") or self.settings.get("close_to_tray"))
        if need_tray and getattr(self, "tray", None):
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None
            threading.Thread(target=self.setup_tray, daemon=True).start()

    def _ensure_window_visible(self) -> Any:
        """Ensure window visible."""
        try:
            self.deiconify()
            self.lift()
            self._apply_topmost(raise_window=False)
            self.focus_force()
        except Exception:
            pass

    def _apply_topmost(self, enabled: bool | None = None, raise_window: bool = False) -> Any:
        """Apply topmost."""
        target = bool(self.settings.get("always_on_top")) if enabled is None else bool(enabled)
        try:
            # Re-apply to force WM refresh after withdraw/deiconify.
            self.attributes("-topmost", False)
        except Exception:
            pass
        try:
            self.attributes("-topmost", target)
        except Exception:
            pass
        if raise_window:
            try:
                self.lift()
                self.focus_force()
            except Exception:
                pass

    def preview_topmost_toggle(self) -> Any:
        """Preview topmost toggle."""
        value = False
        try:
            value = bool(self.sw_topmost.get())
        except Exception:
            value = False
        self._apply_topmost(enabled=value, raise_window=True)

    def _process_ui_queue(self) -> Any:
        """Execute pending UI-thread callbacks from the queue."""
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

    def sync_loop(self) -> Any:
        """Synchronize loop."""
        self._sync_job = None
        if self._sync_inflight:
            self._schedule_sync(200)
            return
        self._sync_inflight = True

        def _fetch() -> None:
            """Fetch launcher status snapshot from local API."""
            try:
                resp = self.api_client.get_info(timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    self.server_online = True
                    try:
                        self.server_id = str(data.get("server_id") or "")
                    except Exception:
                        self.server_id = ""
                    self.pairing_code = data.get("pairing_code", "ERR")
                    self.server_ip = data.get("ip", "0.0.0.0")
                    try:
                        new_port = int(data.get("port", self.port))
                    except Exception:
                        new_port = int(self.port)
                    self.server_port = int(new_port)
                    if int(new_port) != int(self.port):
                        self.port = int(new_port)
                        self.api_url = f"{self.api_scheme}://127.0.0.1:{self.port}/api/local"
                        self.api_client.configure(self.api_url, self.requests_verify)
                    self.server_version = data.get("version", "unknown")
                    try:
                        self.server_hostname = str(data.get("hostname") or "")
                    except Exception:
                        self.server_hostname = ""
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
        """Build the display name shown for a connected device."""
        try:
            settings = d.get("settings") or {}
            alias = str(settings.get("alias") or "").strip()
            if alias:
                return alias
        except Exception:
            pass
        return d.get("name", "unknown")

    def _iter_visible_devices(self) -> Any:
        """Iterate over visible devices."""
        visible = []
        for d in self.devices_data or []:
            token = d.get("token")
            if not token:
                continue
            online = bool(d.get("online")) and self.server_online
            if (not self.show_offline.get()) and (not online):
                continue
            visible.append((token, d, online))
        return visible

    def _device_row_key(self, d: dict, online: bool, is_sel: bool) -> Any:
        """Build a stable key used to track a device row widget."""
        settings = d.get("settings") or {}
        return (
            self._device_display_name(d),
            d.get("ip", "?"),
            bool(online),
            settings.get("transfer_preset", "balanced"),
            bool(is_sel),
        )

    def _bind_device_select(self, widget: Any, token: str) -> Any:
        """Bind device select."""
        try:
            widget.bind("<Button-1>", lambda _e, t=token: self.select_device(t))
        except Exception:
            pass

    def _create_device_row(self, token: str) -> Any:
        """Create device row."""
        row = ctk.CTkFrame(
            self.device_list,
            fg_color=COLOR_PANEL_ALT,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )

        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(fill="x", expand=True, padx=8, pady=8)

        dot = ctk.CTkFrame(
            content,
            width=10,
            height=10,
            corner_radius=5,
            fg_color="#444",
        )
        dot.pack(side="left", padx=(2, 10), pady=6)
        dot.pack_propagate(False)

        info = ctk.CTkFrame(content, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)

        lbl_title = ctk.CTkLabel(
            info,
            text="...",
            font=FONT_UI_BOLD,
            text_color=COLOR_TEXT,
        )
        lbl_title.pack(anchor="w")
        lbl_sub = ctk.CTkLabel(
            info,
            text="...",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        )
        lbl_sub.pack(anchor="w")

        lbl_check = ctk.CTkLabel(content, text="✓", text_color=COLOR_ACCENT, font=FONT_UI_BOLD)

        for w in (row, dot, info, lbl_title, lbl_sub):
            self._bind_device_select(w, token)

        return {
            "row": row,
            "dot": dot,
            "lbl_title": lbl_title,
            "lbl_sub": lbl_sub,
            "lbl_check": lbl_check,
            "render_key": None,
        }

    def _update_device_row(self, entry: dict, d: dict, online: bool, is_sel: bool) -> Any:
        """Update device row."""
        row = entry["row"]
        dot = entry["dot"]
        lbl_title = entry["lbl_title"]
        lbl_sub = entry["lbl_sub"]
        lbl_check = entry["lbl_check"]

        row.configure(
            fg_color=COLOR_PANEL if is_sel else COLOR_PANEL_ALT,
            border_color=COLOR_ACCENT if is_sel else COLOR_BORDER,
        )
        dot.configure(fg_color=COLOR_ACCENT if online else "#444")

        name = self._device_display_name(d)
        ip = d.get("ip", "?")
        preset = (d.get("settings") or {}).get("transfer_preset", "balanced")
        status = self.tr("status_online") if online else self.tr("status_offline")

        lbl_title.configure(text=name)
        lbl_sub.configure(text=f"{ip} | {status} | {self.tr('profile')}: {preset}")

        try:
            if is_sel:
                if lbl_check.winfo_manager() != "pack":
                    lbl_check.pack(side="right", padx=(10, 0))
            elif lbl_check.winfo_manager() == "pack":
                lbl_check.pack_forget()
        except Exception:
            pass

        entry["render_key"] = self._device_row_key(d, online, is_sel)

    def _sync_device_list(self) -> Any:
        """Synchronize device list."""
        visible = self._iter_visible_devices()
        visible_tokens = [token for token, _d, _online in visible]
        visible_set = set(visible_tokens)

        for token in list(self._device_rows.keys()):
            if token in visible_set:
                continue
            entry = self._device_rows.pop(token, None)
            if not entry:
                continue
            try:
                entry["row"].destroy()
            except Exception:
                pass
        self._device_row_order = [t for t in self._device_row_order if t in visible_set]

        if not visible:
            if self._device_empty_label is None:
                self._device_empty_label = ctk.CTkLabel(
                    self.device_list,
                    text=self.tr("no_connections"),
                    text_color=COLOR_TEXT_DIM,
                    font=FONT_SMALL,
                )
            if self._device_empty_label.winfo_manager() != "pack":
                self._device_empty_label.pack(pady=20)
        elif self._device_empty_label is not None:
            try:
                self._device_empty_label.pack_forget()
            except Exception:
                pass

        for token, d, online in visible:
            is_sel = self.selected_token == token
            entry = self._device_rows.get(token)
            if entry is None:
                entry = self._create_device_row(token)
                self._device_rows[token] = entry
            key = self._device_row_key(d, online, is_sel)
            if entry.get("render_key") != key:
                self._update_device_row(entry, d, online, is_sel)

        if visible_tokens != self._device_row_order:
            for token in visible_tokens:
                entry = self._device_rows.get(token)
                if not entry:
                    continue
                row = entry["row"]
                try:
                    row.pack_forget()
                except Exception:
                    pass
                row.pack(fill="x", pady=4, padx=2)
            self._device_row_order = list(visible_tokens)

    def update_gui_data(self) -> Any:
        """Update GUI data."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        self.lbl_code.configure(text=self.pairing_code)
        self.lbl_server.configure(text=f"{self.server_ip}:{self.server_port}")
        self.lbl_version.configure(text=self.tr("server_version_line", server=self.server_version, launcher=LAUNCHER_VERSION))

        if self.server_online:
            self.lbl_header_status.configure(text=self.tr("server_online_state"), text_color=COLOR_ACCENT)
        else:
            self.lbl_header_status.configure(text=self.tr("server_offline_state"), text_color=COLOR_FAIL)

        total = len(self.devices_data)
        online_count = sum(1 for d in self.devices_data if d.get("online"))
        self.lbl_summary_devices.configure(text=self.tr("devices_ratio", online=online_count, total=total))
        self.lbl_summary_logs.configure(
            text=self.tr("logs_console") if self.logs_enabled else self.tr("logs_off")
        )
        self.lbl_summary_tray.configure(
            text=self.tr("tray_mode_main") if self.start_in_tray else self.tr("tray_mode_window")
        )

        self.lbl_logs_hint.configure(
            text=self.tr("logs_hint") if not self.logs_enabled else ""
        )
        self.lbl_devices_status.configure(
            text=self.tr("updated_at", time=time.strftime("%H:%M:%S")) if self.server_online else self.tr("updated_offline")
        )

        self.refresh_qr_code()

        all_tokens = {d.get("token") for d in self.devices_data if d.get("token")}
        if self.selected_token and self.selected_token not in all_tokens:
            self.selected_token = None
            self.selected_device_name = None
            self._selected_device_form_state = None
            self._set_device_settings_dirty(
                False,
                status_text=self.tr("choose_device"),
                status_color=COLOR_TEXT_DIM,
            )

        self._sync_device_list()

        self.refresh_selected_panel()
