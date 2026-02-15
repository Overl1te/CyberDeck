from __future__ import annotations

from typing import Any

from .launcher_shared import *
from .launcher_shared import _tr_any


class AppDevicesMixin:
    """Device detail/actions/settings and QR handling methods."""

    def _set_qr_placeholder(self, text: str) -> Any:
        """Set QR placeholder."""
        try:
            if hasattr(self, "lbl_qr") and self.lbl_qr:
                self.lbl_qr.configure(text=text, image=None)
        except Exception:
            pass

    def _build_qr_image(self, qr_text: str, size: int = QR_IMAGE_SIZE) -> Any:
        """Build QR image."""
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=3,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)
        # Strict flat style: single solid color, no gradients/shadows.
        qr_img = qr.make_image(fill_color="#111111", back_color="white").convert("RGBA")

        out = Image.new("RGBA", (size, size), (255, 255, 255, 255))
        outer_margin = max(2, int(size * 0.01))
        qr_size = size - outer_margin * 2
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
        out.alpha_composite(qr_img, (outer_margin, outer_margin))

        try:
            logo_path = self.icon_path_qr_png if os.path.exists(self.icon_path_qr_png) else self.icon_path_png
            if os.path.exists(logo_path):
                logo_size = max(58, int(size * 0.27))
                logo = Image.open(logo_path).convert("RGBA")
                bbox = logo.getbbox()
                if bbox:
                    logo = logo.crop(bbox)
                logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
                quiet_size = int(max(logo_size + 4, logo_size * 1.12))
                quiet_x = (size - quiet_size) // 2
                quiet_y = (size - quiet_size) // 2

                # Keep quiet zone around icon so scanner reads center area reliably.
                quiet = Image.new("RGBA", (quiet_size, quiet_size), (255, 255, 255, 255))
                qmask = Image.new("L", (quiet_size, quiet_size), 0)
                qdraw = ImageDraw.Draw(qmask)
                qdraw.rounded_rectangle(
                    [0, 0, quiet_size - 1, quiet_size - 1],
                    radius=max(4, int(quiet_size * 0.1)),
                    fill=255,
                )
                quiet.putalpha(qmask)
                out.alpha_composite(quiet, (quiet_x, quiet_y))

                logo_x = (size - logo_size) // 2
                logo_y = (size - logo_size) // 2
                out.alpha_composite(logo, (logo_x, logo_y))
        except Exception:
            pass

        return out.convert("RGB")

    def refresh_qr_code(self, force: bool = False) -> Any:
        """Refresh QR code."""
        if not hasattr(self, "lbl_qr"):
            return

        if not self.server_online:
            self._set_qr_placeholder(self.tr("qr_unavailable"))
            return

        now = time.time()
        if (not force) and (now - float(self._qr_last_fetch_ts) < 30.0):
            return
        self._qr_last_fetch_ts = now

        def _bg() -> None:
            """Fetch and render QR image on worker thread."""
            try:
                resp = self.api_client.get_qr_payload(timeout=1)
                if resp.status_code != 200:
                    raise RuntimeError(f"http {resp.status_code}")
                data = resp.json() or {}
                payload = data.get("payload") or {}

                mode = str(self.settings.get("qr_mode", DEFAULT_SETTINGS["qr_mode"]) or DEFAULT_SETTINGS["qr_mode"]).strip().lower()
                if mode not in ("site", "app"):
                    mode = DEFAULT_SETTINGS["qr_mode"]

                if mode == "app":
                    try:
                        qs = urllib.parse.urlencode(
                            {
                                "type": payload.get("type", "cyberdeck_qr_v1"),
                                "server_id": payload.get("server_id", ""),
                                "hostname": payload.get("hostname", ""),
                                "version": payload.get("version", ""),
                                "ip": payload.get("ip", ""),
                                "port": payload.get("port", ""),
                                "code": payload.get("pairing_code", ""),
                                "scheme": payload.get("scheme", ""),
                                "ts": payload.get("ts", ""),
                                "nonce": payload.get("nonce", ""),
                                "qr_token": payload.get("qr_token", ""),
                            },
                            doseq=False,
                        )
                        qr_text = f"cyberdeck://pair?{qs}"
                    except Exception:
                        url = str(data.get("url") or "").strip()
                        qr_text = url if url else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                else:
                    url = str(data.get("url") or "").strip()
                    qr_text = url if url else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

                img = self._build_qr_image(qr_text, size=QR_IMAGE_SIZE)

                def _ui() -> None:
                    """Apply prepared QR image on UI thread."""
                    self._qr_ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(QR_IMAGE_SIZE, QR_IMAGE_SIZE))
                    self.lbl_qr.configure(image=self._qr_ctk_img, text="")

                self.ui_call(_ui)
            except Exception as e:
                self.append_log(f"[launcher] qr error: {e}\n")
                self.ui_call(lambda: self._set_qr_placeholder(self.tr("qr_error")))

        threading.Thread(target=_bg, daemon=True).start()

    def _get_selected_device(self) -> Any:
        """Return selected device."""
        if not self.selected_token:
            return None
        for d in self.devices_data:
            if d.get("token") == self.selected_token:
                return d
        return None

    def _translate_transfer_msg(self, msg: str) -> str:
        """Translate transfer msg."""
        if not msg:
            return self.tr("api_error")
        mapping = {
            "Offline": self.tr("transfer_msg_offline"),
            "File missing": self.tr("transfer_msg_file_missing"),
            "Server not ready": self.tr("transfer_msg_server_not_ready"),
            "transporter.py missing": self.tr("transfer_msg_transporter_missing"),
            "Transporter started": self.tr("transfer_msg_started"),
        }
        return mapping.get(msg, msg)

    def select_device(self, token: str) -> Any:
        """Select device."""
        self.selected_token = token
        self.selected_device_name = None
        loaded = False
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
                loaded = True
                break
        self._selected_device_form_state = self._capture_device_form_state() if loaded else None
        self._set_device_settings_dirty(False, status_text=self.tr("choose_device"), status_color=COLOR_ACCENT)
        self.update_gui_data()

    def refresh_selected_panel(self) -> Any:
        """Refresh selected panel."""
        if not self.selected_token:
            self.lbl_target.configure(text=self.tr("none"))
            self.lbl_target_status.configure(text=self.tr("target_not_selected"), text_color=COLOR_TEXT_DIM)
            self._selected_device_form_state = None
            self._set_device_settings_dirty(False)
            try:
                self.btn_disconnect_selected.configure(state="disabled", text_color=COLOR_TEXT_DIM)
                self.btn_delete_selected.configure(state="disabled", text_color=COLOR_TEXT_DIM)
            except Exception:
                pass
            return

        d = self._get_selected_device()
        name = (d.get("name") if d else None) or self.selected_device_name or self.tr("none")
        name = (self._device_display_name(d) if d else None) or name
        ip = (d.get("ip") if d else None) or "-"
        online = bool(d.get("online")) and self.server_online if d else False
        status = self.tr("status_online") if online else self.tr("status_offline")

        self.lbl_target.configure(text=f"{name}\n{self.selected_token[:8]}...")
        self.lbl_target_status.configure(
            text=f"{status} • {ip}",
            text_color=COLOR_ACCENT if online else COLOR_TEXT_DIM,
        )
        try:
            self.btn_delete_selected.configure(state="normal", text_color=COLOR_FAIL)
            if online:
                self.btn_disconnect_selected.configure(state="normal", text_color=COLOR_TEXT)
            else:
                self.btn_disconnect_selected.configure(state="disabled", text_color=COLOR_TEXT_DIM)
        except Exception:
            pass

    def disconnect_selected_device(self) -> Any:
        """Disconnect selected device."""
        if not self.selected_token:
            return
        self.disconnect_device(self.selected_token)

    def delete_selected_device(self) -> Any:
        """Delete selected device."""
        if not self.selected_token:
            return
        d = self._get_selected_device()
        name = self._device_display_name(d) if d else (self.selected_device_name or self.tr("none"))
        self.delete_device(self.selected_token, name)

    def disconnect_device(self, token: str) -> Any:
        """Disconnect device."""
        if not token:
            return

        def _bg() -> None:
            """Run device disconnect request."""
            try:
                self.api_client.device_disconnect(token, timeout=2)
                self.ui_call(lambda: self.show_toast(self.tr("disconnect"), level="success"))
            except Exception as e:
                self.ui_call(lambda e=e: self.show_toast(self.tr("error_prefix", msg=e), level="error"))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

    def delete_device(self, token: str, name: str = "") -> Any:
        """Delete device."""
        if not token:
            return
        try:
            ok = messagebox.askyesno(
                "CyberDeck",
                self.tr("delete_confirm", name=name),
            )
        except Exception:
            ok = False
        if not ok:
            return

        def _bg() -> None:
            """Run device delete request."""
            try:
                self.api_client.device_delete(token, timeout=3)
                if self.selected_token == token:
                    self.selected_token = None
                    self.selected_device_name = None
                self.ui_call(lambda: self.show_toast(self.tr("delete"), level="success"))
            except Exception as e:
                self.ui_call(lambda e=e: self.show_toast(self.tr("error_prefix", msg=e), level="error"))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

    def _normalize_chunk_kb_text(self, value: str) -> str:
        """Normalize chunk KB text."""
        text = str(value or "").strip()
        if text == "":
            return ""
        try:
            return str(max(1, int(float(text))))
        except Exception:
            return ""

    def _normalize_sleep_ms_text(self, value: str) -> str:
        """Normalize sleep ms text."""
        text = str(value or "").strip()
        if text == "":
            return ""
        try:
            v = max(0.0, float(text))
        except Exception:
            return ""
        if abs(v - round(v)) < 1e-6:
            return str(int(round(v)))
        return f"{v:.3f}".rstrip("0").rstrip(".")

    def _capture_device_form_state(self) -> Any:
        """Capture device form state."""
        preset = str(self.var_transfer_preset.get() or "").strip().lower()
        if preset not in DEFAULT_DEVICE_PRESETS:
            preset = "balanced"
        return {
            "transfer_preset": preset,
            "alias": str(self.var_device_alias.get() or "").strip(),
            "note": str(self.var_device_note.get() or "").strip(),
            "chunk_kb": self._normalize_chunk_kb_text(self.var_transfer_chunk_kb.get()),
            "sleep_ms": self._normalize_sleep_ms_text(self.var_transfer_sleep_ms.get()),
            "perm_mouse": bool(self.var_perm_mouse.get()),
            "perm_keyboard": bool(self.var_perm_keyboard.get()),
            "perm_upload": bool(self.var_perm_upload.get()),
            "perm_file_send": bool(self.var_perm_file_send.get()),
            "perm_stream": bool(self.var_perm_stream.get()),
            "perm_power": bool(self.var_perm_power.get()),
        }

    def _apply_device_form_state(self, state: dict) -> Any:
        """Apply device form state."""
        if not isinstance(state, dict):
            return
        self._suppress_device_setting_trace = True
        try:
            self.var_transfer_preset.set(state.get("transfer_preset", "balanced"))
            self.var_device_alias.set(state.get("alias", ""))
            self.var_device_note.set(state.get("note", ""))
            self.var_transfer_chunk_kb.set(state.get("chunk_kb", ""))
            self.var_transfer_sleep_ms.set(state.get("sleep_ms", ""))
            self.var_perm_mouse.set(bool(state.get("perm_mouse", True)))
            self.var_perm_keyboard.set(bool(state.get("perm_keyboard", True)))
            self.var_perm_upload.set(bool(state.get("perm_upload", True)))
            self.var_perm_file_send.set(bool(state.get("perm_file_send", True)))
            self.var_perm_stream.set(bool(state.get("perm_stream", True)))
            self.var_perm_power.set(bool(state.get("perm_power", False)))
        finally:
            self._suppress_device_setting_trace = False

    def _set_device_settings_dirty(self, dirty: bool, status_text: str = None, status_color: Any = None) -> Any:
        """Set device settings dirty."""
        dirty = bool(dirty) and bool(self.selected_token)
        self._device_settings_dirty = dirty
        tr = lambda k, **kw: _tr_any(self, k, **kw)

        can_edit = bool(self.selected_token and dirty)
        try:
            self.btn_save_device_settings.configure(state="normal" if can_edit else "disabled")
            self.btn_reset_device_settings.configure(state="normal" if can_edit else "disabled")
        except Exception:
            pass
        try:
            self.lbl_device_dirty.configure(text=tr("unsaved_changes") if dirty else "")
        except Exception:
            pass
        if status_text is not None:
            try:
                self.lbl_status.configure(
                    text=status_text,
                    text_color=status_color if status_color is not None else (COLOR_WARN if dirty else COLOR_TEXT_DIM),
                )
            except Exception:
                pass

    def _build_device_settings_patch(self) -> Any:
        """Build device settings patch."""
        state = self._capture_device_form_state()
        patch = {"transfer_preset": state["transfer_preset"]}
        patch["alias"] = state["alias"] if state["alias"] else None
        patch["note"] = state["note"] if state["note"] else None
        patch["transfer_chunk"] = None if state["chunk_kb"] == "" else (int(state["chunk_kb"]) * 1024)
        patch["transfer_sleep"] = None if state["sleep_ms"] == "" else (float(state["sleep_ms"]) / 1000.0)
        patch["perm_mouse"] = bool(state["perm_mouse"])
        patch["perm_keyboard"] = bool(state["perm_keyboard"])
        patch["perm_upload"] = bool(state["perm_upload"])
        patch["perm_file_send"] = bool(state["perm_file_send"])
        patch["perm_stream"] = bool(state["perm_stream"])
        patch["perm_power"] = bool(state["perm_power"])
        return patch

    def reset_device_settings(self) -> Any:
        """Reset device settings."""
        if not self.selected_token:
            self._set_device_settings_dirty(False, status_text=self.tr("device_not_selected"), status_color=COLOR_FAIL)
            return
        if not isinstance(self._selected_device_form_state, dict):
            return
        self._apply_device_form_state(self._selected_device_form_state)
        self._set_device_settings_dirty(False, status_text=self.tr("device_settings_no_changes"), status_color=COLOR_TEXT_DIM)
        self.show_toast(self.tr("device_settings_no_changes"), level="info")

    def save_device_settings(self) -> Any:
        """Save device settings."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        if not self.selected_token:
            self._set_device_settings_dirty(False, status_text=self.tr("device_not_selected"), status_color=COLOR_FAIL)
            return
        if not self._device_settings_dirty:
            self.show_toast(self.tr("device_settings_no_changes"), level="info")
            return
        patch = self._build_device_settings_patch()

        def _bg() -> None:
            """Send device settings patch and update UI state."""
            try:
                payload = {"token": self.selected_token, "settings": patch}
                resp = self.api_client.device_settings(payload, timeout=2)
                if resp.status_code == 200:
                    self.ui_call(lambda: self._mark_device_settings_saved())
                else:
                    self.ui_call(
                        lambda: self._set_device_settings_dirty(
                            True,
                            status_text=self.tr("save_error"),
                            status_color=COLOR_FAIL,
                        )
                    )
                    self.ui_call(lambda: self.show_toast(self.tr("toast_save_failed"), level="error"))
            except Exception as e:
                self.ui_call(
                    lambda e=e: self._set_device_settings_dirty(
                        True,
                        status_text=self.tr("error_prefix", msg=e),
                        status_color=COLOR_FAIL,
                    )
                )
                self.ui_call(lambda e=e: self.show_toast(self.tr("toast_saving_error", msg=e), level="error"))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

    def _mark_device_settings_saved(self) -> Any:
        """Mark device settings saved."""
        self._selected_device_form_state = self._capture_device_form_state()
        self._set_device_settings_dirty(False, status_text=self.tr("device_settings_saved"), status_color=COLOR_ACCENT)
        self.show_toast(self.tr("toast_device_settings_saved"), level="success")

    def _on_device_setting_changed(self, *_args: Any) -> Any:
        """Mark device settings as dirty after a form edit."""
        if self._suppress_device_setting_trace:
            return
        if not self.selected_token:
            return
        current = self._capture_device_form_state()
        dirty = current != (self._selected_device_form_state or {})
        self._set_device_settings_dirty(
            dirty,
            status_text=(
                self.tr("device_settings_dirty")
                if dirty
                else self.tr("device_settings_no_changes")
            ),
            status_color=COLOR_WARN if dirty else COLOR_TEXT_DIM,
        )

    def send_file(self) -> Any:
        """Send file."""
        if not self.selected_token:
            self.lbl_status.configure(text=self.tr("device_not_selected"), text_color=COLOR_FAIL)
            return

        path = filedialog.askopenfilename(title=self.tr("choose_file"))
        if not path:
            return

        def _bg_send() -> None:
            """Send file transfer trigger request."""
            self.ui_call(lambda: self.lbl_status.configure(text=self.tr("transfer_request"), text_color=COLOR_WARN))
            try:
                payload = {"token": self.selected_token, "file_path": path}
                resp = self.api_client.trigger_file(payload, timeout=4)

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        self.ui_call(lambda: self.lbl_status.configure(text=self.tr("transfer_started"), text_color=COLOR_ACCENT))
                        self.ui_call(lambda: self.show_toast(self.tr("toast_transfer_started"), level="success"))
                    else:
                        msg = self._translate_transfer_msg(data.get("msg"))
                        self.ui_call(lambda: self.lbl_status.configure(text=self.tr("error_prefix", msg=msg), text_color=COLOR_FAIL))
                        self.ui_call(lambda: self.show_toast(self.tr("toast_transfer_error", msg=msg), level="error"))
                else:
                    self.ui_call(lambda: self.lbl_status.configure(text=self.tr("api_error"), text_color=COLOR_FAIL))
                    self.ui_call(lambda: self.show_toast(self.tr("toast_api_error_transfer"), level="error"))
            except Exception as e:
                self.ui_call(lambda e=e: self.lbl_status.configure(text=self.tr("error_prefix", msg=e), text_color=COLOR_FAIL))
                self.ui_call(lambda e=e: self.show_toast(self.tr("toast_transfer_error", msg=e), level="error"))

        threading.Thread(target=_bg_send, daemon=True).start()

    def regenerate_code_action(self) -> Any:
        """Regenerate code action."""
        def _req() -> None:
            """Request pairing code regeneration."""
            try:
                self.api_client.regenerate_code(timeout=2)
                self.ui_call(lambda: self.show_toast(self.tr("toast_code_refreshing"), level="info"))
            except Exception:
                self.ui_call(lambda: self.show_toast(self.tr("toast_code_refresh_failed"), level="error"))

        threading.Thread(target=_req, daemon=True).start()

    def copy_pairing_code(self) -> Any:
        """Copy pairing code."""
        try:
            self.clipboard_clear()
            self.clipboard_append(self.pairing_code)
            self.lbl_status.configure(text=self.tr("code_copied"), text_color=COLOR_ACCENT)
            self.show_toast(self.tr("toast_code_copied"), level="success")
        except Exception:
            pass
