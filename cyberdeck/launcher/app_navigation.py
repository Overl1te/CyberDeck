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

    def _inline_text(self, ru_text: str, en_text: str) -> str:
        """Return short inline text in active language without touching i18n payload."""
        lang = str(self.settings.get("language", "ru") or "ru").strip().lower()
        return str(en_text if lang == "en" else ru_text)

    def queue_settings_autosave(self, delay_ms: int = 450) -> Any:
        """Debounce automatic settings save requests from UI controls."""
        if bool(getattr(self, "_settings_ui_initializing", False)):
            return
        try:
            if getattr(self, "_settings_autosave_job", None) is not None:
                self.after_cancel(self._settings_autosave_job)
        except Exception:
            pass
        self._settings_autosave_job = None
        try:
            if hasattr(self, "lbl_settings_status"):
                self.lbl_settings_status.configure(
                    text=self._inline_text("Автосохранение...", "Autosaving..."),
                    text_color=COLOR_TEXT_DIM,
                )
        except Exception:
            pass

        def _run() -> None:
            """Execute delayed auto-save on UI thread."""
            self._settings_autosave_job = None
            self.save_settings_action(auto=True)

        try:
            self._settings_autosave_job = self.after(max(80, int(delay_ms)), _run)
        except Exception:
            self._settings_autosave_job = None

    def _set_settings_status(self, text: str, color: str = None) -> None:
        """Update settings status label if it exists."""
        if not hasattr(self, "lbl_settings_status"):
            return
        try:
            self.lbl_settings_status.configure(
                text=str(text or ""),
                text_color=color or COLOR_TEXT_DIM,
            )
        except Exception:
            pass

    def queue_server_restart(self, delay_ms: int = 1200) -> Any:
        """Debounce server restart requests triggered by settings changes."""
        self._server_restart_dirty = True
        try:
            if getattr(self, "_server_restart_job", None) is not None:
                self.after_cancel(self._server_restart_job)
        except Exception:
            pass
        self._server_restart_job = None
        self._set_settings_status(
            self._inline_text(
                "Настройки сохранены. Перезапуск сервера...",
                "Settings saved. Restarting server...",
            ),
            COLOR_WARN,
        )

        def _run() -> None:
            """Run delayed server restart once after burst of settings changes."""
            self._server_restart_job = None
            if not bool(getattr(self, "_server_restart_dirty", False)):
                return
            try:
                self.restart_server()
            finally:
                self._server_restart_dirty = False
            self._set_settings_status(
                self._inline_text("Сервер перезапущен", "Server restarted"),
                COLOR_ACCENT,
            )

        try:
            self._server_restart_job = self.after(max(120, int(delay_ms)), _run)
        except Exception:
            self._server_restart_job = None

    def _help_content(self) -> str:
        """Return user-readable help body for current locale."""
        if str(self.settings.get("language", "ru") or "ru").strip().lower() == "en":
            return (
                f"CyberDeck Launcher {LAUNCHER_VERSION}\n\n"
                "What this app does\n"
                "- Starts and monitors local CyberDeck server\n"
                "- Shows pairing PIN and QR for mobile connection\n"
                "- Manages trusted devices and permissions\n\n"
                "Quick start\n"
                "1. Open Home and make sure server status is Online.\n"
                "2. Scan QR from mobile app and confirm the new device.\n"
                "3. In Devices tab, choose permissions for this device.\n\n"
                "Important settings\n"
                "- TLS is enabled by default.\n"
                "- If TLS certificate/key fields are empty, launcher generates a self-signed certificate automatically.\n"
                "- Server settings are applied and restarted automatically when required.\n\n"
                "If connection fails\n"
                "- Restart server from Home.\n"
                "- Enable debug logs in Settings.\n"
                "- Run launcher with `-c` to mirror logs to console.\n"
                "- Open `docs/ERROR_MATRIX.md` for error codes and fixes."
            )
        return (
            f"CyberDeck Launcher {LAUNCHER_VERSION}\n\n"
            "Что делает лаунчер\n"
            "- Запускает и контролирует локальный сервер CyberDeck\n"
            "- Показывает PIN и QR для подключения телефона\n"
            "- Управляет доверенными устройствами и их правами\n\n"
            "Быстрый старт\n"
            "1. Откройте «Сводка» и убедитесь, что сервер в статусе «Онлайн».\n"
            "2. Отсканируйте QR в мобильном приложении и подтвердите новое устройство.\n"
            "3. На вкладке «Устройства» задайте права для этого устройства.\n\n"
            "Важные настройки\n"
            "- TLS включен по умолчанию.\n"
            "- Если поля сертификата/ключа TLS пустые, лаунчер автоматически создаст самоподписанный сертификат.\n"
            "- Серверные настройки применяются автоматически, при необходимости сервер перезапускается.\n\n"
            "Если подключение не работает\n"
            "- Перезапустите сервер на вкладке «Сводка».\n"
            "- Включите «Режим отладки логов сервера» в настройках.\n"
            "- Запустите лаунчер с флагом `-c`, чтобы видеть логи в консоли.\n"
            "- Откройте `docs/ERROR_MATRIX.md`: там список кодов ошибок и действия по исправлению."
        )

    def save_settings_action(self, auto: bool = False) -> Any:
        """Save settings action."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        if getattr(self, "_settings_autosave_job", None) is not None:
            try:
                self.after_cancel(self._settings_autosave_job)
            except Exception:
                pass
            self._settings_autosave_job = None

        def _show_settings_error(err_text: str) -> None:
            """Show save validation error in user-friendly way."""
            if auto:
                self._set_settings_status(err_text, COLOR_FAIL)
                return
            try:
                messagebox.showerror(self.tr("app_name"), err_text)
            except Exception:
                pass

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
        cloudflare_runtime_keys = (
            "cloudflare_enabled",
            "cloudflare_binary_path",
            "cloudflare_tunnel_token",
            "cloudflare_hostname",
            "cloudflare_auto_install",
        )
        app_restart_keys = (
            "pairing_single_use",
            "ignore_vpn",
            "upload_max_bytes",
            "upload_allowed_ext",
            "verbose_http_log",
            "verbose_ws_log",
            "verbose_stream_log",
            "mdns_enabled",
            "device_approval_required",
            "stream_profile",
            "stream_offer_fps",
            "stream_offer_max_w",
            "stream_offer_q",
            "stream_offer_gop",
            "stream_offer_preset",
            "h264_bitrate_k",
            "h265_bitrate_k",
            "offer_audio_default",
            "audio_bitrate_k",
            "audio_sample_rate",
            "audio_channels",
            "audio_fallback_silent",
            "stream_fast_resample_threshold",
            "stream_subsampling_threshold",
        )
        launcher_restart_keys = ("hotkey_enabled",)
        old_language = str(self.settings.get("language", "ru"))
        old_restart_values = {k: self.settings.get(k) for k in restart_keys}
        old_cloudflare_values = {k: self.settings.get(k) for k in cloudflare_runtime_keys}
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
        if hasattr(self, "sw_cloudflare_enabled"):
            self.settings["cloudflare_enabled"] = bool(self.sw_cloudflare_enabled.get())
        if hasattr(self, "ent_cloudflare_binary_path"):
            self.settings["cloudflare_binary_path"] = str(self.ent_cloudflare_binary_path.get()).strip()
        if hasattr(self, "ent_cloudflare_tunnel_token"):
            self.settings["cloudflare_tunnel_token"] = str(self.ent_cloudflare_tunnel_token.get()).strip()
        if hasattr(self, "ent_cloudflare_hostname"):
            cloudflare_hostname = str(self.ent_cloudflare_hostname.get()).strip()
            if cloudflare_hostname and ("://" not in cloudflare_hostname):
                cloudflare_hostname = f"https://{cloudflare_hostname}"
            self.settings["cloudflare_hostname"] = cloudflare_hostname
        self.settings["qr_mode"] = str(self.qr_mode_var.get() or DEFAULT_SETTINGS["qr_mode"]).strip().lower()
        if self.settings["qr_mode"] not in ("site", "app"):
            self.settings["qr_mode"] = DEFAULT_SETTINGS["qr_mode"]
        if hasattr(self, "opt_language"):
            self.settings["language"] = normalize_language(self.language_code_from_label(self.opt_language.get()))

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
        if hasattr(self, "opt_stream_profile"):
            profile = str(self.opt_stream_profile.get() or "balanced").strip().lower().replace("-", "_")
            if profile not in ("balanced", "quality", "low_latency"):
                profile = "balanced"
            self.app_config["stream_profile"] = profile
        if hasattr(self, "ent_stream_offer_fps"):
            self.app_config["stream_offer_fps"] = max(5, _get_int(self.ent_stream_offer_fps, 30))
        if hasattr(self, "ent_stream_offer_max_w"):
            self.app_config["stream_offer_max_w"] = max(640, _get_int(self.ent_stream_offer_max_w, 1920))
        if hasattr(self, "ent_stream_offer_q"):
            self.app_config["stream_offer_q"] = max(20, min(95, _get_int(self.ent_stream_offer_q, 55)))
        if hasattr(self, "ent_stream_offer_gop"):
            self.app_config["stream_offer_gop"] = max(10, _get_int(self.ent_stream_offer_gop, 60))
        if hasattr(self, "ent_stream_offer_preset"):
            preset = str(self.ent_stream_offer_preset.get() or "veryfast").strip()
            self.app_config["stream_offer_preset"] = preset or "veryfast"
        if hasattr(self, "ent_h264_bitrate_k"):
            self.app_config["h264_bitrate_k"] = max(500, _get_int(self.ent_h264_bitrate_k, 6000))
        if hasattr(self, "ent_h265_bitrate_k"):
            self.app_config["h265_bitrate_k"] = max(500, _get_int(self.ent_h265_bitrate_k, 4200))
        if hasattr(self, "sw_offer_audio_default"):
            self.app_config["offer_audio_default"] = bool(self.sw_offer_audio_default.get())
        if hasattr(self, "ent_audio_bitrate_k"):
            self.app_config["audio_bitrate_k"] = max(48, min(320, _get_int(self.ent_audio_bitrate_k, 128)))
        if hasattr(self, "ent_audio_sample_rate"):
            self.app_config["audio_sample_rate"] = max(8000, min(96000, _get_int(self.ent_audio_sample_rate, 48000)))
        if hasattr(self, "ent_audio_channels"):
            self.app_config["audio_channels"] = max(1, min(2, _get_int(self.ent_audio_channels, 2)))
        if hasattr(self, "sw_audio_fallback_silent"):
            self.app_config["audio_fallback_silent"] = bool(self.sw_audio_fallback_silent.get())
        if hasattr(self, "ent_stream_fast_resample_threshold"):
            self.app_config["stream_fast_resample_threshold"] = max(
                30, _get_int(self.ent_stream_fast_resample_threshold, 60)
            )
        if hasattr(self, "ent_stream_subsampling_threshold"):
            self.app_config["stream_subsampling_threshold"] = max(
                30, _get_int(self.ent_stream_subsampling_threshold, 60)
            )
        self._normalize_app_config()

        tls_auto_generated = False
        if self.settings["tls_enabled"]:
            cert_path = str(self.settings.get("tls_cert_path") or "").strip()
            key_path = str(self.settings.get("tls_key_path") or "").strip()
            cert_empty = cert_path == ""
            key_empty = key_path == ""
            if cert_empty != key_empty:
                err = self._inline_text(
                    "Для TLS укажите и сертификат, и ключ, либо оставьте оба поля пустыми для автогенерации.",
                    "For TLS, provide both certificate and key, or keep both fields empty for auto-generation.",
                )
                _show_settings_error(err)
                self.settings["tls_enabled"] = False
                try:
                    self.sw_tls.deselect()
                    if hasattr(self, "_refresh_tls_fields_visibility"):
                        self._refresh_tls_fields_visibility()
                except Exception:
                    pass
            elif cert_empty and key_empty:
                before_cert = cert_path
                before_key = key_path
                try:
                    self.tls_enabled = True
                    self.tls_cert_path = before_cert
                    self.tls_key_path = before_key
                    self._ensure_tls_material()
                    self.settings["tls_enabled"] = bool(self.tls_enabled)
                    self.settings["tls_cert_path"] = str(self.tls_cert_path or "")
                    self.settings["tls_key_path"] = str(self.tls_key_path or "")
                    tls_auto_generated = bool(self.settings["tls_cert_path"] and self.settings["tls_key_path"])
                except Exception:
                    pass
                if not tls_auto_generated:
                    err = self._inline_text(
                        "Не удалось сгенерировать TLS сертификат автоматически. TLS отключен.",
                        "Failed to generate TLS certificate automatically. TLS was disabled.",
                    )
                    _show_settings_error(err)
                    try:
                        self.sw_tls.deselect()
                        if hasattr(self, "_refresh_tls_fields_visibility"):
                            self._refresh_tls_fields_visibility()
                    except Exception:
                        pass
            else:
                cert_exists = os.path.exists(cert_path)
                key_exists = os.path.exists(key_path)
                if (not cert_exists) or (not key_exists):
                    missing = []
                    if not cert_exists:
                        missing.append(cert_path)
                    if not key_exists:
                        missing.append(key_path)
                    missing_msg = ", ".join([str(x) for x in missing if str(x).strip()]) or "TLS files"
                    err = self._inline_text(
                        f"TLS файлы не найдены: {missing_msg}",
                        f"TLS files were not found: {missing_msg}",
                    )
                    _show_settings_error(err)
                    self.settings["tls_enabled"] = False
                    try:
                        self.sw_tls.deselect()
                        if hasattr(self, "_refresh_tls_fields_visibility"):
                            self._refresh_tls_fields_visibility()
                    except Exception:
                        pass

        if tls_auto_generated:
            try:
                self.ent_tls_cert.delete(0, "end")
                self.ent_tls_cert.insert(0, str(self.settings.get("tls_cert_path") or ""))
                self.ent_tls_key.delete(0, "end")
                self.ent_tls_key.insert(0, str(self.settings.get("tls_key_path") or ""))
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
            if tls_auto_generated:
                text = self._inline_text(
                    "Настройки сохранены. Сгенерирован самоподписанный TLS сертификат.",
                    "Settings saved. Self-signed TLS certificate generated.",
                )
            elif auto:
                text = self._inline_text("Сохранено автоматически", "Saved automatically")
            else:
                text = self.tr("settings_applied")
            self.lbl_settings_status.configure(text=text, text_color=COLOR_ACCENT)

        cloudflare_runtime_changed = False
        try:
            cloudflare_runtime_changed = any(
                self.settings.get(k) != old_cloudflare_values.get(k) for k in cloudflare_runtime_keys
            )
        except Exception:
            cloudflare_runtime_changed = False
        if cloudflare_runtime_changed:
            try:
                self._apply_cloudflare_runtime()
            except Exception:
                pass
            try:
                self.request_sync(0)
            except Exception:
                pass

        restart_server_needed = False
        try:
            if any(self.settings.get(k) != old_restart_values.get(k) for k in restart_keys):
                restart_server_needed = True
            if any(self.app_config.get(k) != old_app_restart_values.get(k) for k in app_restart_keys):
                restart_server_needed = True
        except Exception:
            pass
        if restart_server_needed:
            self._server_restart_dirty = True
        if bool(getattr(self, "_server_restart_dirty", False)):
            self.queue_server_restart(delay_ms=(1400 if auto else 350))

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
        if cloudflare_runtime_changed:
            try:
                self.refresh_qr_code(force=True)
            except Exception:
                pass

    def toggle_remote_access_action(self) -> Any:
        """Toggle remote access without forcing a full server restart."""
        enabled = not bool(self.settings.get("cloudflare_enabled", False))
        self.settings["cloudflare_enabled"] = enabled
        try:
            save_json(self.settings_path, self.settings)
        except Exception as exc:
            try:
                self.show_toast(self.tr("toast_save_failed"), level="error")
            except Exception:
                pass
            try:
                self.append_log(f"[launcher] failed to save remote access setting: {exc}\n")
            except Exception:
                pass
            return

        try:
            if hasattr(self, "sw_cloudflare_enabled"):
                if enabled:
                    self.sw_cloudflare_enabled.select()
                else:
                    self.sw_cloudflare_enabled.deselect()
        except Exception:
            pass

        try:
            self._apply_cloudflare_runtime()
        except Exception as exc:
            try:
                self.append_log(f"[launcher] failed to apply remote access runtime: {exc}\n")
            except Exception:
                pass
        try:
            self.refresh_qr_code(force=True)
        except Exception:
            pass
        try:
            self.request_sync(0)
        except Exception:
            pass
        try:
            self._set_settings_status(
                self._inline_text(
                    "Удалённый доступ включён" if enabled else "Удалённый доступ выключен",
                    "Remote access enabled" if enabled else "Remote access disabled",
                ),
                COLOR_ACCENT if enabled else COLOR_TEXT_DIM,
            )
        except Exception:
            pass

    def select_frame(self, name: str) -> Any:
        """Select frame."""
        self.current_frame_name = str(name or "home")
        self.home_frame.grid_forget()
        self.devices_frame.grid_forget()
        self.settings_frame.grid_forget()

        for btn in (self.btn_home, self.btn_devices, self.btn_settings):
            btn.configure(
                text_color=COLOR_TEXT_DIM,
                fg_color="transparent",
                border_width=0,
                border_color=COLOR_BORDER,
                hover_color=COLOR_PANEL_ALT,
            )

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
                    self._schedule_capture_exclusion_refresh(40)
                    existing.focus_force()
                    return
            except Exception:
                pass

        text = str(self._help_content() or "").strip()
        commands_text = str(self.tr("help_commands") or "").strip()
        runtime_summary = self._help_runtime_summary()
        try:
            win = ctk.CTkToplevel(self)
            self._help_window = win
            win.title(self.tr("help_title"))
            win.geometry("1020x700")
            win.minsize(820, 560)
            win.configure(fg_color=COLOR_BG)
            win.transient(self)
            win.protocol("WM_DELETE_WINDOW", self._close_help_window)
            self._schedule_capture_exclusion_refresh(40)

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
            header.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                header,
                text=self.tr("help_title"),
                font=FONT_HEADER,
                text_color=COLOR_TEXT,
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))
            ctk.CTkLabel(
                header,
                text=self.tr("help_subtitle", version=LAUNCHER_VERSION),
                font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM,
            ).grid(row=1, column=0, sticky="w", padx=14, pady=(2, 10))
            CyberBtn(
                header,
                text=self.tr("help_close"),
                command=self._close_help_window,
                width=120,
                height=34,
            ).grid(row=0, column=1, rowspan=2, sticky="e", padx=14, pady=12)

            sidebar = ctk.CTkFrame(
                shell,
                width=285,
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
                text=self.tr("help_open_logs"),
                command=self._open_log_artifact,
                height=34,
            ).pack(fill="x", padx=12, pady=6)
            CyberBtn(
                sidebar,
                text=self.tr("help_check_server"),
                command=self._check_server_from_help,
                height=34,
            ).pack(fill="x", padx=12, pady=(6, 10))
            CyberBtn(
                sidebar,
                text=self.tr("help_export_diag"),
                command=self._export_help_diagnostics,
                height=34,
                fg_color=COLOR_ACCENT,
                text_color="#04110A",
                hover_color=COLOR_ACCENT_HOVER,
                border_color=COLOR_ACCENT,
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
            body.grid_rowconfigure(1, weight=1)
            body.grid_columnconfigure(0, weight=1)

            runtime_card = ctk.CTkFrame(
                body,
                fg_color=COLOR_PANEL_ALT,
                corner_radius=10,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            runtime_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
            ctk.CTkLabel(
                runtime_card,
                text=self._inline_text("Снимок окружения", "Runtime Snapshot"),
                font=FONT_UI_BOLD,
                text_color=COLOR_TEXT,
            ).pack(anchor="w", padx=14, pady=(12, 4))
            ctk.CTkLabel(
                runtime_card,
                text=self._inline_text(
                    "Текущие адреса доступа, режим сервера и состояние diagnostics.",
                    "Current access endpoints, server mode, and diagnostics state.",
                ),
                font=FONT_SMALL,
                text_color=COLOR_TEXT_DIM,
                justify="left",
                wraplength=640,
            ).pack(anchor="w", padx=14, pady=(0, 8))
            runtime_box = ctk.CTkTextbox(
                runtime_card,
                height=170,
                fg_color=COLOR_BG,
                border_width=1,
                border_color=COLOR_BORDER,
                corner_radius=8,
                text_color=COLOR_TEXT,
                font=FONT_SMALL,
                wrap="word",
            )
            runtime_box.pack(fill="x", padx=14, pady=(0, 14))
            runtime_box.insert("1.0", runtime_summary)
            runtime_box.configure(state="disabled")

            guide_card = ctk.CTkFrame(
                body,
                fg_color=COLOR_PANEL_ALT,
                corner_radius=10,
                border_width=1,
                border_color=COLOR_BORDER,
            )
            guide_card.grid(row=1, column=0, sticky="nsew")
            guide_card.grid_rowconfigure(1, weight=1)
            guide_card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                guide_card,
                text=self._inline_text("Памятка", "Guide"),
                font=FONT_UI_BOLD,
                text_color=COLOR_TEXT,
            ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))
            text_box = ctk.CTkTextbox(
                guide_card,
                fg_color=COLOR_BG,
                border_width=1,
                border_color=COLOR_BORDER,
                corner_radius=10,
                text_color=COLOR_TEXT,
                font=FONT_UI,
                wrap="word",
            )
            text_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 14))
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

    def _help_runtime_summary(self) -> str:
        """Build compact launcher/server snapshot shown in the help window."""
        local_origin = str(self._local_access_origin() or "").strip() or "-"
        public_origin = str(self._public_access_origin() or "").strip() or self._inline_text("не активен", "not active")
        remote_status = str(getattr(self, "cloudflare_status", "disabled") or "disabled")
        mode = "PUBLIC" if remote_status == "online" else "LAN"
        if not bool(getattr(self, "server_online", False)):
            mode = "OFFLINE"

        diag = self.server_diag if isinstance(getattr(self, "server_diag", None), dict) else {}
        uptime_text = self._format_uptime_short(diag.get("uptime_s", 0))
        cpu_text = f"{float(diag.get('cpu', 0.0) or 0.0):.0f}%"
        ram_text = f"{float(diag.get('ram', 0.0) or 0.0):.0f}%"
        last_sync = time.strftime("%H:%M:%S")
        lines = [
            f"{self._inline_text('Состояние', 'Status')}: {self.tr('server_online_state') if bool(getattr(self, 'server_online', False)) else self.tr('server_offline_state')}",
            f"{self._inline_text('Режим', 'Mode')}: {mode}",
            f"{self._inline_text('Локальный доступ', 'Local access')}: {local_origin}",
            f"{self._inline_text('Публичный доступ', 'Public access')}: {public_origin}",
            self.tr(
                "server_version_line",
                server=str(getattr(self, "server_version", self.tr("unknown_value")) or self.tr("unknown_value")),
                launcher=LAUNCHER_VERSION,
            ),
            f"{self._inline_text('Диагностика', 'Diagnostics')}: uptime {uptime_text} | CPU {cpu_text} | RAM {ram_text}",
            f"{self._inline_text('Лог-файл', 'Log file')}: {str(getattr(self, 'log_file', '') or '-')}",
            f"{self._inline_text('Последний sync', 'Last sync')}: {last_sync}",
        ]
        last_error = str(getattr(self, "cloudflare_last_error", "") or "").strip()
        if last_error:
            lines.append(f"{self._inline_text('Проблема публичного доступа', 'Public access issue')}: {last_error}")
        return "\n".join(lines)

    def _scrub_sensitive_payload(self, value: Any) -> Any:
        """Redact sensitive tokens/secrets from diagnostics exports."""
        markers = ("token", "secret", "password", "authorization", "cookie", "qr_token", "nonce")
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key or "")
                if any(marker in key_text.lower() for marker in markers):
                    cleaned[key_text] = "<redacted>"
                else:
                    cleaned[key_text] = self._scrub_sensitive_payload(item)
            return cleaned
        if isinstance(value, list):
            return [self._scrub_sensitive_payload(item) for item in value]
        if isinstance(value, tuple):
            return [self._scrub_sensitive_payload(item) for item in value]
        return value

    def _build_help_diag_payload(self) -> dict[str, Any]:
        """Build support-friendly diagnostics bundle for export."""
        diag = self.server_diag if isinstance(getattr(self, "server_diag", None), dict) else {}
        try:
            recent_logs = "".join(list(self._server_log_ring)[-120:])
        except Exception:
            recent_logs = ""
        return {
            "collected_at": int(time.time()),
            "launcher": {
                "version": LAUNCHER_VERSION,
                "language": str(self.settings.get("language", "ru") or "ru"),
                "server_online": bool(getattr(self, "server_online", False)),
                "server_ip": str(getattr(self, "server_ip", "") or ""),
                "server_port": int(getattr(self, "server_port", getattr(self, "port", DEFAULT_PORT)) or DEFAULT_PORT),
                "api_scheme": str(getattr(self, "api_scheme", "http") or "http"),
                "server_version": str(getattr(self, "server_version", "") or ""),
                "status_text": str(getattr(self, "status_text", "") or ""),
                "local_access": str(self._local_access_origin() or ""),
                "public_access": str(self._public_access_origin() or ""),
                "log_file": str(getattr(self, "log_file", "") or ""),
                "cloudflare": {
                    "status": str(getattr(self, "cloudflare_status", "") or ""),
                    "public_url": str(getattr(self, "cloudflare_public_url", "") or ""),
                    "last_error": str(getattr(self, "cloudflare_last_error", "") or ""),
                    "target_url": str(getattr(self, "cloudflare_target_url", "") or ""),
                    "binary_path": str(getattr(self, "cloudflare_binary_resolved", "") or ""),
                },
                "settings": {
                    "tls_enabled": bool(self.settings.get("tls_enabled", False)),
                    "preferred_port": int(self.settings.get("preferred_port", DEFAULT_PORT) or DEFAULT_PORT),
                    "cloudflare_enabled": bool(self.settings.get("cloudflare_enabled", False)),
                    "cloudflare_auto_install": bool(self.settings.get("cloudflare_auto_install", True)),
                    "cloudflare_hostname": str(self.settings.get("cloudflare_hostname", "") or ""),
                    "qr_mode": str(self.settings.get("qr_mode", "app") or "app"),
                    "devices_panel_visible": bool(self.settings.get("devices_panel_visible", True)),
                },
            },
            "server_diag": self._scrub_sensitive_payload(diag),
            "recent_logs_tail": recent_logs,
        }

    def _export_help_diagnostics(self) -> Any:
        """Export launcher/server diagnostics to Downloads without blocking the UI thread."""
        def _run() -> None:
            try:
                payload = self._build_help_diag_payload()
                if bool(getattr(self, "server_online", False)):
                    try:
                        response = self.api_client.get_diag_bundle(timeout=2.5)
                        if bool(getattr(response, "ok", False)):
                            payload["server_diag"] = self._scrub_sensitive_payload(self.api_client.json_dict(response))
                    except Exception:
                        pass

                export_dir = os.path.join(os.path.expanduser("~"), "Downloads", "CyberDeck")
                os.makedirs(export_dir, exist_ok=True)
                stamp = time.strftime("%Y%m%d-%H%M%S")
                path = os.path.join(export_dir, f"cyberdeck-diagnostics-{stamp}.json")
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                self.ui_call(lambda p=path: self.show_toast(self.tr("help_diag_exported", path=p), level="success"))
            except Exception as exc:
                self.ui_call(
                    lambda msg=str(exc or "").strip() or exc.__class__.__name__: self.show_toast(
                        self.tr("help_diag_export_failed", msg=msg),
                        level="error",
                    )
                )

        threading.Thread(target=_run, daemon=True).start()

    def _open_log_artifact(self) -> Any:
        """Open the real log file, or fall back to a saved recent-log snapshot."""
        path = str(getattr(self, "log_file", "") or "").strip()
        try:
            if (not path) or (not os.path.exists(path)):
                export_dir = os.path.join(os.path.expanduser("~"), "Downloads", "CyberDeck")
                os.makedirs(export_dir, exist_ok=True)
                path = os.path.join(export_dir, "cyberdeck-recent-logs.txt")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("".join(list(self._server_log_ring)[-160:]))

            if is_windows():
                os.startfile(path)
            elif sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", path], close_fds=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path], close_fds=True)
            self.show_toast(self.tr("help_logs_opened"), level="success")
        except Exception:
            try:
                self.show_toast(self.tr("open_file_failed", path=path), level="error")
            except Exception:
                pass

    def _check_server_from_help(self) -> Any:
        """Run a lightweight local API probe from the help window."""
        def _run() -> None:
            ok = False
            try:
                response = self.api_client.get_info(timeout=1.5)
                ok = bool(getattr(response, "ok", False))
            except Exception:
                ok = False

            def _finish() -> None:
                if ok:
                    try:
                        self.request_sync(0)
                    except Exception:
                        pass
                    self.show_toast(self.tr("help_server_ok"), level="success")
                else:
                    self.show_toast(self.tr("help_server_fail"), level="error")

            self.ui_call(_finish)

        threading.Thread(target=_run, daemon=True).start()

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
            urls = [str(SUPPORT_URL or "").strip(), *[str(x or "").strip() for x in SUPPORT_URLS]]
            opened = False
            seen: set[str] = set()
            for url in urls:
                if (not url) or (url in seen):
                    continue
                seen.add(url)
                if webbrowser.open(url, new=2):
                    opened = True
                    break
            if not opened:
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
            manager = getattr(self, "cloudflare_manager", None)
            if manager is not None:
                manager.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "tray"):
                self.tray.stop()
        except Exception:
            pass
        os._exit(0)

