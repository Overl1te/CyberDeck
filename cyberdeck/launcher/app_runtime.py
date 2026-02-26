from __future__ import annotations

from typing import Any

from .shared import *


def _env_bool(name: str, default: bool) -> bool:
    """Read bool env var supporting common truthy/falsy forms."""
    raw = os.environ.get(name, None)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on", "y", "t"}:
        return True
    if value in {"0", "false", "no", "off", "n", "f"}:
        return False
    return bool(default)


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

            debug_enabled = _env_bool("CYBERDECK_DEBUG", False)
            log_enabled = _env_bool("CYBERDECK_LOG", False)
            tls_enabled = _env_bool("CYBERDECK_TLS", False)

            log_level = "debug" if debug_enabled else "info"
            access_log = bool(debug_enabled)
            if not log_enabled:
                log_level = "critical"
                access_log = False

            config = uvicorn.Config(
                cyberdeck_server.app,
                host="0.0.0.0",
                port=int(self.port),
                log_level=log_level,
                access_log=access_log,
                ssl_certfile=os.environ.get("CYBERDECK_TLS_CERT") if tls_enabled else None,
                ssl_keyfile=os.environ.get("CYBERDECK_TLS_KEY") if tls_enabled else None,
            )
            server = uvicorn.Server(config)
            self._uvicorn_server = server

            def _run() -> None:
                """Run uvicorn server in background thread."""
                try:
                    server.run()
                except Exception as e:
                    self.append_log(f"[launcher] uvicorn error: {e}\n")
                    self._show_server_start_error(str(e))

            self.server_thread = threading.Thread(target=_run, daemon=True)
            self.server_thread.start()
        except Exception as e:
            self.append_log(f"[launcher] in-process server start error: {e}\n")
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
        self.append_log("[launcher] restarting server...\n")
        self.stop_server_process()
        time.sleep(0.2)
        self.start_server_process()

    def server_stdout_loop(self) -> Any:
        """Read server stdout stream if subprocess writes into it."""
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
                self.append_log(f"[launcher] server exited (code={rc})\n")
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

    def _boot_mark_waiting(self) -> Any:
        """Update boot overlay while local API is still unavailable."""
        if not bool(getattr(self, "_boot_overlay_visible", False)):
            return
        if bool(getattr(self, "_boot_server_ready_announced", False)):
            return
        try:
            self._set_boot_stage(
                "server_wait",
                progress=0.96,
                detail=self.tr("boot_detail_server_wait"),
                visual_key="server",
            )
        except Exception:
            pass

    def _boot_mark_ready(self) -> Any:
        """Finalize boot overlay when local API responds successfully."""
        if not bool(getattr(self, "_boot_overlay_visible", False)):
            return
        if bool(getattr(self, "_boot_server_ready_announced", False)):
            return
        self._boot_server_ready_announced = True
        try:
            self._set_boot_stage(
                "server_wait",
                progress=1.0,
                detail=self.tr("boot_detail_finalizing"),
                visual_key="server",
            )
        except Exception:
            pass
        elapsed = max(0.0, time.time() - float(getattr(self, "_boot_started_ts", 0.0) or 0.0))
        min_visible = max(0.0, float(BOOT_OVERLAY_MIN_VISIBLE_S or 0.0))
        current = max(
            float(getattr(self, "_boot_progress_value", 0.0) or 0.0),
            float(getattr(self, "_boot_progress_target", 0.0) or 0.0),
        )
        remaining = max(0.0, 1.0 - min(1.0, current))
        fill_wait = 0.0
        try:
            tick_s = max(0.001, float(int(BOOT_PROGRESS_TICK_MS)) / 1000.0)
            exp_rate = max(0.01, float(BOOT_PROGRESS_EXP_RATE))
            exp_min = max(0.0001, float(BOOT_PROGRESS_EXP_MIN_STEP))
            exp_max = max(exp_min, float(BOOT_PROGRESS_EXP_MAX_STEP))
            step = max(exp_min, remaining * exp_rate)
            step = max(float(BOOT_PROGRESS_TARGET_STEP), min(exp_max, step))
            fill_wait = (remaining / max(0.0001, step)) * tick_s
        except Exception:
            fill_wait = 0.0
        wait_s = max(0.36, (min_visible - elapsed), fill_wait + 0.12)
        def _finish_boot() -> Any:
            try:
                self._set_boot_stage(
                    "server_ready",
                    progress=1.0,
                    detail=self.tr("boot_detail_server_ready"),
                    visual_key="ready",
                )
            except Exception:
                pass
            self._hide_boot_overlay()

        self._safe_after(int(wait_s * 1000), _finish_boot)

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

    def _notify_system(self, title: str, message: str) -> Any:
        """Best-effort system notification with tray/OS fallback."""
        if not bool(self.settings.get("system_notifications", True)):
            return
        app_name = self.tr("app_name")
        ttl = str(title or app_name).strip() or app_name
        msg = str(message or "").strip()
        if not msg:
            return
        try:
            if getattr(self, "tray", None):
                self.tray.notify(msg, ttl)
                return
        except Exception:
            pass
        try:
            from plyer import notification as plyer_notification  # type: ignore

            plyer_notification.notify(title=ttl, message=msg, app_name=app_name, timeout=4)
            return
        except Exception:
            pass
        try:
            if sys.platform.startswith("linux"):
                subprocess.Popen(["notify-send", ttl, msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            if sys.platform == "darwin":
                safe_t = ttl.replace('"', "'")
                safe_m = msg.replace('"', "'")
                script = f'display notification "{safe_m}" with title "{safe_t}"'
                subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _handle_local_event(self, event: dict[str, Any]) -> Any:
        """Handle one local server event and route toast/system notifications."""
        if not isinstance(event, dict):
            return
        et = str(event.get("type") or "").strip().lower()
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_id = int(event.get("id") or 0)
        if et == "device_connected":
            token = str(payload.get("token") or "")
            if token and token in self._notified_device_tokens:
                return
            if token:
                self._notified_device_tokens.add(token)
            name = str(payload.get("name") or payload.get("device_name") or self.tr("unknown_device"))
            text = self.tr("notify_device_connected", name=name)
            self.show_toast(text, level="success")
            self._notify_system(self.tr("app_name"), text)
            return
        if et == "device_disconnected":
            name = str(payload.get("name") or payload.get("device_name") or self.tr("unknown_device"))
            self.show_toast(self.tr("notify_device_disconnected", name=name), level="info")
            return
        if et == "file_received":
            if event_id in self._notified_upload_events:
                return
            self._notified_upload_events.add(event_id)
            filename = str(payload.get("filename") or "file")
            text = self.tr("notify_file_received", filename=filename)
            self.show_toast(text, level="info")
            self._notify_system(self.tr("app_name"), text)
            return
        if et == "input_lock_changed":
            sec = payload.get("security") if isinstance(payload.get("security"), dict) else {}
            self.security_state = {
                "locked": bool(sec.get("locked", False)),
                "reason": str(sec.get("reason", "") or ""),
                "actor": str(sec.get("actor", "system") or "system"),
                "updated_ts": float(sec.get("updated_ts", 0.0) or 0.0),
            }
            self.show_toast(self.tr("notify_input_lock_changed"), level="info")
            return
        if et == "panic_mode":
            revoked = int(payload.get("revoked", 0) or 0)
            sec = payload.get("security") if isinstance(payload.get("security"), dict) else {}
            self.security_state = {
                "locked": bool(sec.get("locked", True)),
                "reason": str(sec.get("reason", "panic_mode") or "panic_mode"),
                "actor": str(sec.get("actor", "panic_mode") or "panic_mode"),
                "updated_ts": float(sec.get("updated_ts", 0.0) or 0.0),
            }
            msg = self.tr("notify_panic_mode_revoked", count=revoked)
            self.show_toast(msg, level="warning")
            self._notify_system(self.tr("app_name"), msg)
            return
        if et == "device_pending":
            self._notify_system(
                self.tr("app_name"),
                str(event.get("message") or self.tr("notify_device_approval_required")),
            )
            self._prompt_pending_approval()

    def _approve_device_async(self, token: str, allow: bool) -> Any:
        """Call local approval API and refresh launcher state."""
        def _bg() -> None:
            try:
                resp = self.api_client.device_approve(token, allow=allow, timeout=3.0)
                if int(getattr(resp, "status_code", 0) or 0) != 200:
                    raise RuntimeError(f"http {getattr(resp, 'status_code', '?')}")
                if allow:
                    self.ui_call(lambda: self.show_toast(self.tr("device_approved"), level="success"))
                else:
                    self.ui_call(lambda: self.show_toast(self.tr("device_denied"), level="info"))
            except Exception as e:
                self._pending_prompted_tokens.discard(str(token or ""))
                self.ui_call(lambda e=e: self.show_toast(self.tr("approval_error", msg=e), level="error"))
            finally:
                self._approval_dialog_active = False
                self.ui_call(lambda: self.request_sync(150))
                self.ui_call(self._prompt_pending_approval)

        threading.Thread(target=_bg, daemon=True).start()

    def _approval_button_labels(self) -> tuple[str, str]:
        """Return localized labels for approval dialog actions."""
        return self.tr("approval_allow"), self.tr("approval_deny")

    def _approval_dialog_copy(self) -> dict[str, str]:
        """Return localized copy used by the custom approval dialog."""
        return {
            "title": self.tr("approval_prompt_title"),
            "subtitle": self.tr("approval_subtitle"),
            "device_label": self.tr("approval_device_label"),
            "ip_label": self.tr("approval_ip_label"),
            "session_label": self.tr("approval_session_label"),
            "hint": self.tr("approval_hint"),
        }

    def _close_approval_dialog(self) -> Any:
        """Close and forget active custom approval dialog window."""
        win = getattr(self, "_approval_dialog_window", None)
        self._approval_dialog_window = None
        if not win:
            return
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    def _show_approval_dialog(self, token: str, name: str, ip: str) -> bool:
        """Show themed approval dialog. Return True if custom dialog was created."""
        try:
            self._close_approval_dialog()
            copy = self._approval_dialog_copy()
            allow_text, deny_text = self._approval_button_labels()

            win = ctk.CTkToplevel(self)
            self._approval_dialog_window = win
            width = 640
            height = 350
            win.title(copy["title"])
            win.geometry(f"{width}x{height}")
            win.resizable(False, False)
            win.transient(self)
            win.configure(fg_color=COLOR_BG)
            win.lift()

            try:
                win.grab_set()
            except Exception:
                pass

            try:
                self.update_idletasks()
                win.update_idletasks()
                x = int(self.winfo_x() + max(0, (self.winfo_width() - width) / 2))
                y = int(self.winfo_y() + max(0, (self.winfo_height() - height) / 2))
                win.geometry(f"{width}x{height}+{x}+{y}")
            except Exception:
                pass

            panel = ctk.CTkFrame(
                win,
                fg_color=COLOR_PANEL,
                corner_radius=14,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            panel.pack(fill="both", expand=True, padx=12, pady=12)

            top = ctk.CTkFrame(panel, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(14, 8))

            badge = ctk.CTkLabel(
                top,
                text="NEW",
                width=54,
                height=30,
                corner_radius=8,
                fg_color=COLOR_WARN,
                text_color="#04110A",
                font=("Consolas", 12, "bold"),
            )
            badge.pack(side="left", padx=(0, 12))

            title_col = ctk.CTkFrame(top, fg_color="transparent")
            title_col.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                title_col,
                text=copy["title"],
                font=("Consolas", 17, "bold"),
                text_color=COLOR_TEXT,
            ).pack(anchor="w")
            ctk.CTkLabel(
                title_col,
                text=copy["subtitle"],
                justify="left",
                font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM,
            ).pack(anchor="w", pady=(2, 0))

            details = ctk.CTkFrame(
                panel,
                fg_color=COLOR_PANEL_ALT,
                corner_radius=10,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            details.pack(fill="x", padx=16, pady=(2, 12))

            row_dev = ctk.CTkFrame(details, fg_color="transparent")
            row_dev.pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(
                row_dev,
                text=copy["device_label"],
                font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM,
            ).pack(side="left")
            ctk.CTkLabel(
                row_dev,
                text=name,
                font=FONT_UI_BOLD,
                text_color=COLOR_TEXT,
            ).pack(side="right")

            row_ip = ctk.CTkFrame(details, fg_color="transparent")
            row_ip.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkLabel(
                row_ip,
                text=copy["ip_label"],
                font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM,
            ).pack(side="left")
            ctk.CTkLabel(
                row_ip,
                text=ip,
                font=FONT_UI_BOLD,
                text_color=COLOR_TEXT,
            ).pack(side="right")

            row_session = ctk.CTkFrame(details, fg_color="transparent")
            row_session.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkLabel(
                row_session,
                text=copy["session_label"],
                font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM,
            ).pack(side="left")
            ctk.CTkLabel(
                row_session,
                text=f"{token[:8]}...",
                font=("Consolas", 13, "bold"),
                text_color=COLOR_ACCENT,
            ).pack(side="right")

            ctk.CTkLabel(
                panel,
                text=copy["hint"],
                font=FONT_UI,
                text_color=COLOR_TEXT,
            ).pack(anchor="w", padx=16, pady=(0, 8))

            btn_row = ctk.CTkFrame(panel, fg_color="transparent")
            btn_row.pack(fill="x", padx=16, pady=(0, 14))
            btn_row.grid_columnconfigure(0, weight=1)
            btn_row.grid_columnconfigure(1, weight=1)

            def _decide(allow: bool) -> None:
                self._close_approval_dialog()
                self._approve_device_async(token, allow=allow)

            CyberBtn(
                btn_row,
                text=allow_text,
                command=lambda: _decide(True),
                height=36,
                fg_color=COLOR_ACCENT,
                text_color="#04110A",
                hover_color=COLOR_ACCENT_HOVER,
                border_color=COLOR_ACCENT,
            ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

            CyberBtn(
                btn_row,
                text=deny_text,
                command=lambda: _decide(False),
                height=36,
                fg_color="transparent",
                border_color=COLOR_FAIL,
                text_color=COLOR_FAIL,
                hover_color=COLOR_PANEL_ALT,
            ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

            win.bind("<Escape>", lambda _e: _decide(False))
            win.bind("<Return>", lambda _e: _decide(True))
            win.protocol("WM_DELETE_WINDOW", lambda: _decide(False))
            return True
        except Exception:
            self._close_approval_dialog()
            return False

    def _prompt_pending_approval(self) -> Any:
        """Show one approval dialog for the oldest unseen pending device."""
        if self._approval_dialog_active:
            return
        pending = self.pending_devices if isinstance(self.pending_devices, list) else []
        for row in pending:
            if not isinstance(row, dict):
                continue
            token = str(row.get("token") or "").strip()
            if not token:
                continue
            if token in self._pending_prompted_tokens:
                continue
            self._pending_prompted_tokens.add(token)
            self._approval_dialog_active = True
            name = str(row.get("name") or row.get("device_id") or self.tr("unknown_device"))
            ip = str(row.get("ip") or "-")
            shown = self._show_approval_dialog(token, name, ip)
            if shown:
                return
            try:
                allow = bool(
                    messagebox.askyesno(
                        self.tr("approval_prompt_title"),
                        self.tr("approval_prompt_text", name=name, ip=ip),
                    )
                )
            except Exception:
                allow = False
            self._approve_device_async(token, allow=allow)
            return

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
                except Exception as e:
                    try:
                        self.append_log(f"[launcher] ui callback error: {e}\n")
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
            was_online = bool(getattr(self, "server_online", False))
            try:
                resp = self.api_client.get_info(timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    self.server_online = True
                    self.ui_call(self._boot_mark_ready)
                    if not was_online:
                        # Server recovered/restarted: force immediate QR rebuild.
                        self._qr_last_fetch_ts = 0.0
                        self._qr_next_fetch_ts = 0.0
                        self._qr_last_state_signature = None
                    try:
                        self.server_id = str(data.get("server_id") or "")
                    except Exception:
                        self.server_id = ""
                    self.pairing_code = data.get("pairing_code", "ERR")
                    try:
                        raw_exp = data.get("pairing_expires_in_s", None)
                        self.pairing_expires_in_s = int(raw_exp) if raw_exp is not None else None
                    except Exception:
                        self.pairing_expires_in_s = None
                    try:
                        self.pairing_ttl_s = int(data.get("pairing_ttl_s", 0) or 0)
                    except Exception:
                        self.pairing_ttl_s = 0
                    self.pairing_single_use = bool(data.get("pairing_single_use", False))
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
                    self.server_version = data.get("version", self.tr("unknown_value"))
                    try:
                        self.server_hostname = str(data.get("hostname") or "")
                    except Exception:
                        self.server_hostname = ""
                    self.log_file = data.get("log_file", self.log_file)
                    self.devices_data = data.get("devices", [])
                    self.pending_devices = data.get("pending_devices", [])
                    sec = data.get("security") if isinstance(data.get("security"), dict) else {}
                    self.security_state = {
                        "locked": bool(sec.get("locked", False)),
                        "reason": str(sec.get("reason", "") or ""),
                        "actor": str(sec.get("actor", "system") or "system"),
                        "updated_ts": float(sec.get("updated_ts", 0.0) or 0.0),
                    }
                    now_mono = time.monotonic()
                    if now_mono >= float(getattr(self, "_next_update_pull_ts", 0.0) or 0.0):
                        try:
                            updates_resp = self.api_client.get_updates(timeout=2.5, force_refresh=False)
                            if updates_resp.status_code == 200:
                                self.update_state = updates_resp.json()
                                self._next_update_pull_ts = now_mono + 300.0
                            else:
                                self._next_update_pull_ts = now_mono + 60.0
                        except Exception:
                            self._next_update_pull_ts = now_mono + 45.0
                    self._update_status_line = self._build_update_status_line()
                    try:
                        events_resp = self.api_client.get_events(since_id=self._last_local_event_id, limit=80, timeout=1.3)
                        if events_resp.status_code == 200:
                            payload = events_resp.json() or {}
                            events = payload.get("events") if isinstance(payload.get("events"), list) else []
                            try:
                                latest_id = int(payload.get("latest_id") or self._last_local_event_id)
                            except Exception:
                                latest_id = self._last_local_event_id
                            if self._last_local_event_id < 0:
                                self._last_local_event_id = latest_id
                                events = []
                            for evt in events:
                                self.ui_call(lambda evt=evt: self._handle_local_event(evt))
                            if latest_id > self._last_local_event_id:
                                self._last_local_event_id = latest_id
                    except Exception:
                        pass
                    self.ui_call(self._maybe_show_update_popup)
                    self.ui_call(self._prompt_pending_approval)
                else:
                    self.server_online = False
                    self.ui_call(self._boot_mark_waiting)
            except Exception:
                self.server_online = False
                self.ui_call(self._boot_mark_waiting)
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
        return d.get("name", self.tr("unknown_device"))

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
        try:
            last_seen_ts = float(d.get("last_seen_ts") or 0.0)
            if last_seen_ts > 0:
                age_bucket = int(max(0.0, time.time() - last_seen_ts) // 60)
            else:
                age_bucket = -1
        except Exception:
            age_bucket = -1
        return (
            self._device_display_name(d),
            d.get("ip", "?"),
            bool(online),
            bool(d.get("approved", True)),
            settings.get("transfer_preset", "balanced"),
            int(age_bucket),
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
            corner_radius=12,
            border_width=1,
            border_color=COLOR_BORDER,
        )

        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(fill="x", expand=True, padx=10, pady=9)

        dot = ctk.CTkFrame(
            content,
            width=12,
            height=12,
            corner_radius=6,
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

        lbl_check = ctk.CTkLabel(content, text=self.tr("device_active"), text_color=COLOR_ACCENT, font=FONT_SMALL)

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
        approved = bool(d.get("approved", True))
        if not approved:
            dot.configure(fg_color=COLOR_WARN)
        else:
            dot.configure(fg_color=COLOR_ACCENT if online else "#444")

        name = self._device_display_name(d)
        ip = d.get("ip", "?")
        preset = (d.get("settings") or {}).get("transfer_preset", "balanced")
        try:
            last_seen_ts = float(d.get("last_seen_ts") or 0.0)
        except Exception:
            last_seen_ts = 0.0
        if last_seen_ts > 0:
            age_s = int(max(0.0, time.time() - last_seen_ts))
            if age_s < 60:
                last_seen_text = self.tr("last_seen_seconds", value=age_s)
            elif age_s < 3600:
                last_seen_text = self.tr("last_seen_minutes", value=max(1, age_s // 60))
            else:
                last_seen_text = self.tr("last_seen_hours", value=max(1, age_s // 3600))
        else:
            last_seen_text = self.tr("last_seen_never")
        if not approved:
            status = self.tr("status_pending")
        else:
            status = self.tr("status_online") if online else self.tr("status_offline")

        lbl_title.configure(text=name)
        lbl_sub.configure(
            text=self.tr(
                "last_seen_format",
                ip=ip,
                status=status,
                profile_label=self.tr("profile"),
                preset=preset,
                last_label=self.tr("last_seen_label"),
                last_seen=last_seen_text,
            )
        )

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

    @staticmethod
    def _channel_has_update(channel: dict[str, Any]) -> bool:
        """Return True when a release channel payload reports an available update."""
        try:
            return bool(channel.get("has_update"))
        except Exception:
            return False

    @staticmethod
    def _channel_latest_tag(channel: dict[str, Any]) -> str:
        """Return latest tag string from a release channel payload."""
        try:
            return str(channel.get("latest_tag") or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _channel_error(channel: dict[str, Any]) -> str:
        """Return normalized error from a release channel payload."""
        try:
            return str(channel.get("error") or "").strip()
        except Exception:
            return ""

    def _build_update_status_line(self) -> str:
        """Build one-line update status summary for launcher home screen."""
        state = self.update_state if isinstance(self.update_state, dict) else {}
        server = state.get("server") if isinstance(state.get("server"), dict) else {}
        launcher = state.get("launcher") if isinstance(state.get("launcher"), dict) else {}
        mobile = state.get("mobile") if isinstance(state.get("mobile"), dict) else {}

        server_upd = self._channel_has_update(server)
        launcher_upd = self._channel_has_update(launcher)
        mobile_upd = self._channel_has_update(mobile)
        self._update_status_has_updates = bool(server_upd or launcher_upd or mobile_upd)
        if server_upd or launcher_upd or mobile_upd:
            parts = []
            if server_upd:
                parts.append(f"{self.tr('updates_channel_server')} {self._channel_latest_tag(server) or '?'}")
            if launcher_upd:
                parts.append(f"{self.tr('updates_channel_launcher')} {self._channel_latest_tag(launcher) or '?'}")
            if mobile_upd:
                parts.append(f"{self.tr('updates_channel_mobile')} {self._channel_latest_tag(mobile) or '?'}")
            return self.tr("updates_available", items=", ".join(parts))

        errors = [
            x
            for x in (
                self._channel_error(server),
                self._channel_error(launcher),
                self._channel_error(mobile),
            )
            if x
        ]
        if errors:
            return self.tr("updates_check_error", error=errors[0])

        checked_at = int(state.get("checked_at") or 0)
        if checked_at > 0:
            try:
                stamp = time.strftime("%H:%M:%S", time.localtime(float(checked_at)))
            except Exception:
                stamp = self.tr("updates_recently")
            return self.tr("updates_up_to_date", time=stamp)
        return self.tr("updates_not_checked")

    def _collect_available_updates(self) -> list[tuple[str, str, str, str]]:
        """Collect channels that have updates as tuples `(name, current, latest, release_url)`."""
        state = self.update_state if isinstance(self.update_state, dict) else {}
        channels = (
            (self.tr("updates_channel_server"), state.get("server")),
            (self.tr("updates_channel_launcher"), state.get("launcher")),
            (self.tr("updates_channel_mobile"), state.get("mobile")),
        )
        out: list[tuple[str, str, str, str]] = []
        for name, raw in channels:
            payload = raw if isinstance(raw, dict) else {}
            if not self._channel_has_update(payload):
                continue
            out.append(
                (
                    name,
                    str(payload.get("current_version") or ""),
                    str(payload.get("latest_tag") or ""),
                    str(payload.get("release_url") or ""),
                )
            )
        return out

    def _build_update_popup_key(self, updates: list[tuple[str, str, str, str]]) -> str:
        """Build stable popup de-duplication key for a concrete update set."""
        parts = [f"{name}:{latest}" for name, _current, latest, _url in updates]
        return "|".join(parts)

    def _maybe_show_update_popup(self) -> Any:
        """Show one-time popup when a newer release is detected."""
        if not bool(getattr(self, "server_online", False)):
            return
        updates = self._collect_available_updates()
        if not updates:
            return

        key = self._build_update_popup_key(updates)
        seen = getattr(self, "_seen_update_popup_keys", None)
        if not isinstance(seen, set):
            seen = set()
            self._seen_update_popup_keys = seen
        if key in seen:
            return
        seen.add(key)

        lines = [
            self.tr("updates_dialog_header"),
            "",
        ]
        for name, current, latest, url in updates:
            if current:
                lines.append(f"- {name}: {current} -> {latest}")
            else:
                lines.append(f"- {name}: {latest}")
            if url:
                lines.append(f"  {url}")
        lines.append("")
        lines.append(self.tr("updates_dialog_open_releases"))
        try:
            messagebox.showinfo(self.tr("updates_dialog_title"), "\n".join(lines))
        except Exception:
            pass

    def update_gui_data(self) -> Any:
        """Update GUI data."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        self.lbl_code.configure(text=self.pairing_code)
        if hasattr(self, "lbl_pairing_ttl"):
            ttl_left = getattr(self, "pairing_expires_in_s", None)
            if ttl_left is None:
                ttl_text = self.tr("pairing_ttl_unlimited")
            elif int(ttl_left) <= 0:
                ttl_text = self.tr("pairing_ttl_expired")
            else:
                ttl_text = self.tr("pairing_ttl_seconds", seconds=int(ttl_left))
            if bool(getattr(self, "pairing_single_use", False)):
                ttl_text += f" | {self.tr('pairing_single_use_suffix')}"
            self.lbl_pairing_ttl.configure(text=ttl_text, text_color=(COLOR_WARN if ttl_left == 0 else COLOR_TEXT_DIM))

        if hasattr(self, "lbl_security_state"):
            locked = bool((self.security_state or {}).get("locked", False))
            reason = str((self.security_state or {}).get("reason", "") or "").strip()
            msg = self.tr("security_locked") if locked else self.tr("security_unlocked")
            if reason:
                msg += f" ({reason})"
            self.lbl_security_state.configure(text=msg, text_color=(COLOR_WARN if locked else COLOR_TEXT_DIM))
        if hasattr(self, "btn_toggle_input_lock"):
            locked = bool((self.security_state or {}).get("locked", False))
            self.btn_toggle_input_lock.configure(text=(self.tr("security_unlock_btn") if locked else self.tr("security_lock_btn")))

        self.lbl_server.configure(text=f"{self.server_ip}:{self.server_port}")
        self.lbl_version.configure(text=self.tr("server_version_line", server=self.server_version, launcher=LAUNCHER_VERSION))
        if hasattr(self, "lbl_updates"):
            default_line = self.tr("updates_not_checked")
            text = str(getattr(self, "_update_status_line", default_line) or default_line)
            color = COLOR_WARN if bool(getattr(self, "_update_status_has_updates", False)) else COLOR_TEXT_DIM
            self.lbl_updates.configure(text=text, text_color=color)

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

