from __future__ import annotations

from typing import Any

from .shared import *
from .shared import _tr_any


class AppDevicesMixin:
    """Device detail/actions/settings and QR handling methods."""

    @staticmethod
    def _build_app_qr_deep_link(payload: dict[str, Any]) -> str:
        """Build `cyberdeck://pair` deep link for app-mode QR payload."""
        if not isinstance(payload, dict):
            return ""

        qr_token = str(payload.get("qr_token") or payload.get("nonce") or "").strip()
        if not qr_token:
            return ""

        code = str(payload.get("pairing_code") or "").strip()
        ip = str(payload.get("ip") or "").strip()
        port = str(payload.get("port") or "").strip()
        if (not code) or (not ip) or (not port):
            return ""

        # Keep the deep link compact for better QR readability.
        params: dict[str, str] = {
            "type": str(payload.get("type") or "cyberdeck_qr_v1").strip(),
            "ip": ip,
            "port": port,
            "code": code,
            "scheme": str(payload.get("scheme") or "").strip(),
            "qr_token": qr_token,
        }

        try:
            expires_at = payload.get("pairing_expires_at")
            if expires_at not in (None, ""):
                params["exp"] = str(int(float(expires_at)))
        except Exception:
            pass

        encoded = urllib.parse.urlencode({k: v for k, v in params.items() if str(v).strip()}, doseq=False)
        if not encoded:
            return ""
        return f"cyberdeck://pair?{encoded}"

    @staticmethod
    def _build_app_fallback_url(payload: dict[str, Any], base_url: str = "") -> str:
        """Build compact web fallback URL for app-mode QR."""
        if not isinstance(payload, dict):
            return ""
        code = str(payload.get("pairing_code") or "").strip()
        ip = str(payload.get("ip") or "").strip()
        port = str(payload.get("port") or "").strip()
        qr_token = str(payload.get("qr_token") or payload.get("nonce") or "").strip()
        scheme = str(payload.get("scheme") or "http").strip().lower() or "http"
        if (not code) or (not ip) or (not port) or (not qr_token):
            return ""

        base = str(base_url or "").strip()
        parsed = urllib.parse.urlsplit(base) if base else None
        if parsed and parsed.scheme and parsed.netloc:
            out_scheme = parsed.scheme
            out_netloc = parsed.netloc
        else:
            out_scheme = scheme
            out_netloc = f"{ip}:{port}"

        params: dict[str, str] = {
            "type": str(payload.get("type") or "cyberdeck_qr_v1").strip(),
            "app_pkg": str(payload.get("app_pkg") or "").strip(),
            "ip": ip,
            "port": port,
            "code": code,
            "scheme": scheme,
            "qr_token": qr_token,
            "open": "app",
        }
        try:
            expires_at = payload.get("pairing_expires_at")
            if expires_at not in (None, ""):
                params["exp"] = str(int(float(expires_at)))
        except Exception:
            pass

        query = urllib.parse.urlencode({k: v for k, v in params.items() if str(v).strip()}, doseq=False)
        return urllib.parse.urlunsplit((out_scheme, out_netloc, "/", query, ""))

    @staticmethod
    def _append_open_mode_app(url: str) -> str:
        """Ensure fallback URL contains `open=app` query parameter."""
        raw = str(url or "").strip()
        if not raw:
            return ""
        try:
            parsed = urllib.parse.urlsplit(raw)
            query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            out = []
            has_open = False
            for k, v in query:
                if str(k) == "open":
                    has_open = True
                    out.append(("open", "app"))
                else:
                    out.append((k, v))
            if not has_open:
                out.append(("open", "app"))
            return urllib.parse.urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urllib.parse.urlencode(out, doseq=True),
                    parsed.fragment,
                )
            )
        except Exception:
            return raw

    @staticmethod
    def _build_android_intent_qr_link(deep_link: str, fallback_url: str = "") -> str:
        """Wrap deep-link into Android `intent://` URI with browser fallback."""
        deep = str(deep_link or "").strip()
        if not deep:
            return ""
        try:
            parsed = urllib.parse.urlsplit(deep)
            if parsed.scheme.lower() != "cyberdeck":
                return deep
            authority = str(parsed.netloc or "pair").strip().strip("/")
            path = str(parsed.path or "").lstrip("/")
            target = authority if (not path) else f"{authority}/{path}"
            intent = f"intent://{target}"
            if parsed.query:
                intent += f"?{parsed.query}"

            fallback = AppDevicesMixin._append_open_mode_app(fallback_url)
            tail = "Intent;scheme=cyberdeck;action=android.intent.action.VIEW;"
            if fallback:
                tail += f"S.browser_fallback_url={urllib.parse.quote(fallback, safe='')};"
            tail += "end"
            return f"{intent}#{tail}"
        except Exception:
            return deep

    @staticmethod
    def _qr_render_size_for_payload(text: str) -> int:
        """Pick QR render size based on payload length."""
        n = len(str(text or ""))
        if n >= 380:
            return max(QR_IMAGE_SIZE, 360)
        if n >= 260:
            return max(QR_IMAGE_SIZE, 320)
        if n >= 180:
            return max(QR_IMAGE_SIZE, 280)
        return int(QR_IMAGE_SIZE)

    def _set_qr_placeholder(self, text: str) -> Any:
        """Set QR placeholder."""
        try:
            if hasattr(self, "lbl_qr") and self.lbl_qr:
                self._qr_ctk_img = None
                self._qr_tk_img = None
                self.lbl_qr.configure(text=text, image=None)
        except Exception:
            pass

    def _build_qr_image(self, qr_text: str, size: int = QR_IMAGE_SIZE) -> Any:
        """Build QR image."""
        def _hex_to_rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
            """Parse #RRGGBB color to RGB tuple with fallback."""
            text = str(value or "").strip()
            if len(text) == 7 and text.startswith("#"):
                try:
                    return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))
                except Exception:
                    pass
            return fallback

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_text)
        qr.make(fit=True)
        accent_rgb = _hex_to_rgb(COLOR_ACCENT, (60, 255, 145))
        panel_rgb = _hex_to_rgb(COLOR_PANEL, (8, 18, 14))
        module_rgb = (8, 26, 18)
        qr_bg_rgb = (246, 255, 250)

        qr_img = qr.make_image(fill_color=module_rgb, back_color=qr_bg_rgb).convert("RGBA")

        out = Image.new("RGBA", (size, size), panel_rgb + (255,))
        draw = ImageDraw.Draw(out)
        frame_pad = max(1, int(size * 0.005))
        frame_radius = max(6, int(size * 0.04))
        draw.rounded_rectangle(
            [frame_pad, frame_pad, size - frame_pad - 1, size - frame_pad - 1],
            radius=frame_radius,
            fill=panel_rgb + (255,),
            outline=accent_rgb + (105,),
            width=max(1, int(size * 0.004)),
        )

        qr_pad = max(8, int(size * 0.036))
        qr_side = max(1, size - qr_pad * 2)

        shadow = Image.new("RGBA", (qr_side, qr_side), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            [0, 0, qr_side - 1, qr_side - 1],
            radius=max(6, int(qr_side * 0.04)),
            fill=(0, 0, 0, 58),
        )
        shadow_off = max(1, int(size * 0.006))
        out.alpha_composite(shadow, (qr_pad + shadow_off, qr_pad + shadow_off))

        panel = Image.new("RGBA", (qr_side, qr_side), (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.rounded_rectangle(
            [0, 0, qr_side - 1, qr_side - 1],
            radius=max(6, int(qr_side * 0.04)),
            fill=qr_bg_rgb + (255,),
            outline=(205, 225, 214, 255),
            width=1,
        )
        qr_inner_pad = max(4, int(qr_side * 0.015))
        qr_inner_side = qr_side - qr_inner_pad * 2
        qr_img = qr_img.resize((qr_inner_side, qr_inner_side), Image.NEAREST)
        panel.alpha_composite(qr_img, (qr_inner_pad, qr_inner_pad))
        out.alpha_composite(panel, (qr_pad, qr_pad))

        try:
            logo_path = self.icon_path_qr_png if os.path.exists(self.icon_path_qr_png) else self.icon_path_png
            if os.path.exists(logo_path):
                logo_size = max(42, int(size * 0.18))
                logo = Image.open(logo_path).convert("RGBA")
                bbox = logo.getbbox()
                if bbox:
                    logo = logo.crop(bbox)
                logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
                quiet_size = int(max(logo_size + 12, logo_size * 1.34))
                quiet_x = (size - quiet_size) // 2
                quiet_y = (size - quiet_size) // 2

                quiet = Image.new("RGBA", (quiet_size, quiet_size), qr_bg_rgb + (255,))
                qmask = Image.new("L", (quiet_size, quiet_size), 0)
                qdraw = ImageDraw.Draw(qmask)
                qdraw.rounded_rectangle(
                    [0, 0, quiet_size - 1, quiet_size - 1],
                    radius=max(5, int(quiet_size * 0.16)),
                    fill=255,
                )
                quiet.putalpha(qmask)
                qdraw = ImageDraw.Draw(quiet)
                qdraw.rounded_rectangle(
                    [0, 0, quiet_size - 1, quiet_size - 1],
                    radius=max(5, int(quiet_size * 0.16)),
                    outline=accent_rgb + (150,),
                    width=1,
                )
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

        current_sig = (
            str(getattr(self, "server_id", "") or ""),
            str(getattr(self, "pairing_code", "") or ""),
            str(getattr(self, "server_port", "") or ""),
            str(getattr(self, "api_scheme", "") or ""),
        )
        last_sig = getattr(self, "_qr_last_state_signature", None)
        if current_sig != last_sig:
            force = True
            self._qr_last_state_signature = current_sig

        if not self.server_online:
            self._set_qr_placeholder(self.tr("qr_unavailable"))
            return

        now = time.time()
        if (not force) and (now < float(getattr(self, "_qr_next_fetch_ts", 0.0) or 0.0)):
            return
        if bool(getattr(self, "_qr_fetch_inflight", False)):
            return
        self._qr_fetch_inflight = True

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
                    # For better scanner compatibility, emit a regular http(s) URL
                    # with open=app so the landing page can auto-open cyberdeck://.
                    try:
                        url = str(data.get("url") or "").strip()
                        fallback = self._build_app_fallback_url(payload, base_url=url)
                        if fallback:
                            qr_text = fallback
                        else:
                            deep_link = self._build_app_qr_deep_link(payload)
                            if deep_link:
                                qr_text = deep_link
                            else:
                                qr_text = self._append_open_mode_app(url) if url else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    except Exception:
                        url = str(data.get("url") or "").strip()
                        qr_text = self._append_open_mode_app(url) if url else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                else:
                    url = str(data.get("url") or "").strip()
                    qr_text = url if url else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

                img = self._build_qr_image(qr_text, size=QR_IMAGE_SIZE)

                def _ui() -> None:
                    """Apply prepared QR image on UI thread."""
                    try:
                        self._qr_tk_img = ImageTk.PhotoImage(img)
                        self._qr_ctk_img = None
                        self.lbl_qr.configure(image=self._qr_tk_img, text="")
                    except Exception as tk_err:
                        self.append_log(f"[launcher] qr render error: {tk_err}\n")
                        fallback_text = str(data.get("url") or "").strip()
                        self.lbl_qr.configure(image=None, text=(fallback_text or self.tr("qr_error")))

                self.ui_call(_ui)
                self._qr_last_fetch_ts = time.time()
                self._qr_next_fetch_ts = self._qr_last_fetch_ts + 30.0
            except Exception as e:
                self.append_log(f"[launcher] qr error: {e}\n")
                # After a failed fetch retry quickly, do not lock QR updates for 30s.
                self._qr_next_fetch_ts = time.time() + 2.0
                self.ui_call(lambda: self._set_qr_placeholder(self.tr("qr_error")))
            finally:
                self._qr_fetch_inflight = False

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
        approved = bool(d.get("approved", True)) if d else True
        if not approved:
            status = self.tr("status_pending")
        else:
            status = self.tr("status_online") if online else self.tr("status_offline")

        self.lbl_target.configure(text=f"{name}\n{self.selected_token[:8]}...")
        self.lbl_target_status.configure(
            text=f"{status} | {ip}",
            text_color=(COLOR_WARN if (not approved) else (COLOR_ACCENT if online else COLOR_TEXT_DIM)),
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
                self.tr("app_name"),
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

        def tr(k: str, **kw: Any) -> str:
            """Translate helper with current app locale context."""
            return _tr_any(self, k, **kw)

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

    def toggle_remote_input_lock(self) -> Any:
        """Toggle remote input lock state via local API."""
        locked = bool((getattr(self, "security_state", {}) or {}).get("locked", False))
        target = not locked

        def _bg() -> None:
            """Send input-lock toggle request and refresh launcher state."""
            try:
                reason = "launcher_lock" if target else "launcher_unlock"
                resp = self.api_client.set_input_lock(target, reason=reason, actor="launcher", timeout=2.0)
                if int(getattr(resp, "status_code", 0) or 0) != 200:
                    raise RuntimeError(f"http {getattr(resp, 'status_code', '?')}")
                body = resp.json() if hasattr(resp, "json") else {}
                sec = body.get("security") if isinstance(body, dict) else {}
                if isinstance(sec, dict):
                    self.security_state = {
                        "locked": bool(sec.get("locked", target)),
                        "reason": str(sec.get("reason", "") or ""),
                        "actor": str(sec.get("actor", "launcher") or "launcher"),
                        "updated_ts": float(sec.get("updated_ts", 0.0) or 0.0),
                    }
                msg = self.tr("input_locked") if target else self.tr("input_unlocked")
                self.ui_call(lambda msg=msg: self.show_toast(msg, level="warning" if target else "success"))
            except Exception as e:
                self.ui_call(lambda e=e: self.show_toast(self.tr("input_lock_error", msg=e), level="error"))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

    def panic_mode_action(self) -> Any:
        """Revoke all sessions and lock remote input in one emergency action."""
        try:
            ok = bool(
                messagebox.askyesno(
                    self.tr("app_name"),
                    self.tr("panic_confirm"),
                )
            )
        except Exception:
            ok = False
        if not ok:
            return

        def _bg() -> None:
            """Execute panic-mode request and refresh launcher state."""
            try:
                resp = self.api_client.panic_mode(keep_token="", lock_input=True, reason="launcher_panic", timeout=4.0)
                if int(getattr(resp, "status_code", 0) or 0) != 200:
                    raise RuntimeError(f"http {getattr(resp, 'status_code', '?')}")
                body = resp.json() if hasattr(resp, "json") else {}
                revoked = int((body or {}).get("revoked", 0) or 0)
                sec = (body or {}).get("security") if isinstance((body or {}).get("security"), dict) else {}
                if isinstance(sec, dict):
                    self.security_state = {
                        "locked": bool(sec.get("locked", True)),
                        "reason": str(sec.get("reason", "panic_mode") or "panic_mode"),
                        "actor": str(sec.get("actor", "panic_mode") or "panic_mode"),
                        "updated_ts": float(sec.get("updated_ts", 0.0) or 0.0),
                    }
                self.ui_call(
                    lambda revoked=revoked: self.show_toast(
                        self.tr("panic_mode_revoked", count=revoked), level="warning"
                    )
                )
            except Exception as e:
                self.ui_call(lambda e=e: self.show_toast(self.tr("panic_mode_error", msg=e), level="error"))
            finally:
                self.ui_call(lambda: self.request_sync(150))

        threading.Thread(target=_bg, daemon=True).start()

