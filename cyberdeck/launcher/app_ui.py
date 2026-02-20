from __future__ import annotations

from typing import Any

from .shared import *
from .shared import _tr_any


class AppUiMixin:
    """Window UI layout, boot overlay, and hotkey behavior methods."""

    def apply_settings(self) -> Any:
        """Apply settings."""
        # Write-path helpers should keep side effects minimal and well-scoped.
        self._apply_topmost()
        set_autostart(bool(self.settings.get("autostart")), self.launch_cmd_for_autostart)
        save_json(self.settings_path, self.settings)
        save_json(self.app_config_path, self.app_config)

        tray_reason = tray_unavailable_reason()
        need_tray = bool(self.settings.get("start_in_tray") or self.settings.get("close_to_tray"))
        if need_tray and not getattr(self, "tray", None) and not tray_reason:
            threading.Thread(target=self.setup_tray, daemon=True).start()
        if (not need_tray) and getattr(self, "tray", None):
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None

        if bool(self.settings.get("hotkey_enabled")) and (not self._hotkey_thread_started):
            threading.Thread(target=self.hotkey_loop, daemon=True).start()
            self._hotkey_thread_started = True

    def show_toast(self, message: str, level: str = "info", duration_ms: int = 2600) -> Any:
        """Show toast."""
        try:
            self.toast_manager.show(message, level=level, duration_ms=duration_ms)
        except Exception:
            pass

    def _save_layout_settings(self) -> Any:
        """Save layout settings."""
        try:
            save_json(self.settings_path, self.settings)
        except Exception:
            pass

    def _apply_devices_panel_layout(self, persist: bool = False) -> Any:
        """Apply devices panel layout."""
        if not all(
            hasattr(self, name)
            for name in ("devices_split", "devices_splitter", "devices_panel", "btn_toggle_devices_panel")
        ):
            return

        def tr(k: str, **kw: Any) -> str:
            """Translate helper with current app locale context."""
            return _tr_any(self, k, **kw)

        visible = bool(self.settings.get("devices_panel_visible", True))
        try:
            width = max(320, int(self.settings.get("devices_panel_width", DEFAULT_SETTINGS["devices_panel_width"])))
        except Exception:
            width = int(DEFAULT_SETTINGS["devices_panel_width"])
        self.settings["devices_panel_width"] = int(width)

        if visible:
            self.devices_splitter.grid(row=0, column=1, sticky="ns", padx=(0, 10))
            self.devices_panel.grid(row=0, column=2, sticky="nsew")
            self.devices_split.grid_columnconfigure(1, weight=0, minsize=8)
            self.devices_split.grid_columnconfigure(2, weight=0, minsize=int(width))
            self.btn_toggle_devices_panel.configure(text=tr("hide_panel"))
        else:
            self.devices_splitter.grid_remove()
            self.devices_panel.grid_remove()
            self.devices_split.grid_columnconfigure(1, weight=0, minsize=0)
            self.devices_split.grid_columnconfigure(2, weight=0, minsize=0)
            self.btn_toggle_devices_panel.configure(text=tr("show_panel"))

        if persist:
            self._save_layout_settings()

    def toggle_devices_panel(self) -> Any:
        """Toggle devices panel."""
        self.settings["devices_panel_visible"] = not bool(self.settings.get("devices_panel_visible", True))
        self._apply_devices_panel_layout(persist=True)

    def _start_devices_panel_resize(self, event: Any) -> Any:
        """Start devices panel resize."""
        if not bool(self.settings.get("devices_panel_visible", True)):
            return
        self._devices_panel_resizing = True
        self._devices_panel_resize_start_x = int(getattr(event, "x_root", 0))
        try:
            current = int(self.devices_panel.winfo_width())
        except Exception:
            current = int(self.settings.get("devices_panel_width", DEFAULT_SETTINGS["devices_panel_width"]))
        self._devices_panel_resize_start_width = max(320, current)

    def _on_devices_panel_resize(self, event: Any) -> Any:
        """Track and clamp devices panel width during drag resize."""
        if not self._devices_panel_resizing:
            return
        try:
            delta = int(self._devices_panel_resize_start_x - int(getattr(event, "x_root", 0)))
        except Exception:
            delta = 0
        width = int(self._devices_panel_resize_start_width + delta)
        try:
            total = int(self.devices_split.winfo_width())
        except Exception:
            total = 0
        max_width = max(380, total - 280) if total > 0 else 800
        width = max(320, min(width, max_width))
        self.settings["devices_panel_width"] = int(width)
        self._apply_devices_panel_layout(persist=False)

    def _stop_devices_panel_resize(self, _event: Any = None) -> Any:
        """Stop devices panel resize."""
        if not self._devices_panel_resizing:
            return
        self._devices_panel_resizing = False
        self._save_layout_settings()

    def hotkey_loop(self) -> Any:
        """Ctrl+Alt+D toggles launcher window visibility."""
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
                self.append_log("[launcher] failed to register hotkey\n")
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

    def toggle_window(self) -> Any:
        """Toggle window."""
        if self.state() in ("withdrawn", "iconic"):
            self.deiconify()
            self._apply_topmost(raise_window=True)
        else:
            self.withdraw()

    def setup_ui(self) -> Any:
        """Construct the main launcher UI and bind callbacks."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=COLOR_PANEL)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            self.sidebar, text="CyberDeck", font=("Tahoma", 26, "bold"), text_color=COLOR_TEXT
        ).grid(row=0, column=0, padx=20, pady=(28, 0), sticky="w")
        ctk.CTkLabel(
            self.sidebar, text=self.tr("app_subtitle"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM
        ).grid(row=1, column=0, padx=20, pady=(2, 20), sticky="w")

        self.btn_home = self.create_nav_btn(self.tr("nav_home"), "home", 2)
        self.btn_devices = self.create_nav_btn(self.tr("nav_devices"), "devices", 3)
        self.btn_settings = self.create_nav_btn(self.tr("nav_settings"), "settings", 4)
        self.btn_support = CyberBtn(
            self.sidebar,
            text=self.tr("nav_support"),
            command=self.open_support_page,
            height=30,
            font=FONT_SMALL,
            fg_color="transparent",
        )
        self.btn_support.grid(row=11, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.btn_help = CyberBtn(
            self.sidebar,
            text=self.tr("nav_help"),
            command=self.show_help,
            height=30,
            font=FONT_SMALL,
            fg_color="transparent",
        )
        self.btn_help.grid(row=12, column=0, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkLabel(
            self.sidebar,
            text=self.tr("launcher_version", version=LAUNCHER_VERSION),
            font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        ).grid(row=13, column=0, padx=20, pady=(0, 16), sticky="w")

        self.home_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.devices_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.settings_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=COLOR_BG)

        self.setup_home()
        self.setup_devices()
        self.setup_settings()

        self.select_frame("home")

    def _build_boot_overlay(self) -> Any:
        """Build boot overlay."""
        overlay = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()

        media_stub = ctk.CTkFrame(
            overlay,
            fg_color="#000000",
            corner_radius=0,
            border_width=0,
            width=220,
            height=220,
        )
        media_stub.place(relx=0.5, rely=0.5, anchor="center")
        media_stub.pack_propagate(False)

        self._boot_media_label = ctk.CTkLabel(media_stub, text="")
        self._boot_media_label.pack(expand=True, fill="both")
        self._boot_media_text_label = None
        self._boot_signature_label = ctk.CTkLabel(
            overlay,
            text="Loading...",
            font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
            fg_color="transparent",
        )
        self._boot_signature_label.place(relx=0.5, rely=0.84, anchor="center")

        self._boot_overlay = overlay
        self._boot_overlay_visible = True
        self._load_boot_media()

    def _show_boot_overlay(self, status: str) -> Any:
        """Show boot overlay."""
        if not self._boot_overlay:
            return
        if self._boot_exit_job is not None:
            try:
                self.after_cancel(self._boot_exit_job)
            except Exception:
                pass
            self._boot_exit_job = None
        self._boot_exiting = False
        self._boot_exit_progress = 0
        self._boot_started_ts = time.time()
        self._boot_phase = 0
        self._boot_overlay_visible = True
        self._boot_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._boot_overlay.lift()
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass
        self._start_boot_media()

    def _hide_boot_overlay(self, immediate: bool = False) -> Any:
        """Hide boot overlay."""
        if not self._boot_overlay:
            return
        if not immediate:
            if (not self._boot_overlay_visible) or self._boot_exiting:
                return
            self._boot_exiting = True
            self._boot_exit_progress = 0
            self._stop_boot_media()
            self._animate_boot_overlay_exit()
            return

        self._boot_overlay_visible = False
        self._boot_exiting = False
        if self._boot_exit_job is not None:
            try:
                self.after_cancel(self._boot_exit_job)
            except Exception:
                pass
            self._boot_exit_job = None
        try:
            self._boot_overlay.place_forget()
        except Exception:
            pass
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass
        self._stop_boot_media()
        if self._boot_timer_job is not None:
            try:
                self.after_cancel(self._boot_timer_job)
            except Exception:
                pass
            self._boot_timer_job = None

    def _animate_boot_overlay_exit(self) -> Any:
        """Animate boot overlay fade-out before removing it."""
        if not self._boot_overlay:
            return
        if not self._boot_overlay_visible:
            self._hide_boot_overlay(immediate=True)
            return

        steps = max(1, int(BOOT_OVERLAY_EXIT_STEPS))
        p = min(1.0, float(self._boot_exit_progress) / float(steps))
        ease = 1.0 - ((1.0 - p) * (1.0 - p))

        shrink = max(0.0, min(0.5, float(BOOT_OVERLAY_EXIT_SHRINK))) * ease
        rw = max(0.02, 1.0 - shrink)
        rh = max(0.02, 1.0 - shrink)
        rx = (1.0 - rw) / 2.0
        ry = (1.0 - rh) / 2.0
        try:
            self._boot_overlay.place(relx=rx, rely=ry, relwidth=rw, relheight=rh)
        except Exception:
            pass

        alpha_drop = max(0.0, min(0.5, float(BOOT_OVERLAY_EXIT_ALPHA_DROP))) * ease
        try:
            self.attributes("-alpha", max(0.0, 1.0 - alpha_drop))
        except Exception:
            pass

        if self._boot_exit_progress >= steps:
            self._hide_boot_overlay(immediate=True)
            return
        self._boot_exit_progress += 1
        self._boot_exit_job = self._safe_after(max(8, int(BOOT_OVERLAY_EXIT_STEP_MS)), self._animate_boot_overlay_exit)

    def _dismiss_boot_overlay_manual(self) -> Any:
        """Dismiss the boot overlay after manual user action."""
        self._hide_boot_overlay()

    def _fit_media_frame(self, src: Image.Image, width: int, height: int) -> Image.Image:
        """Fit media frame."""
        out = Image.new("RGB", (width, height), color=(0, 0, 0))
        img = src.convert("RGB")
        img.thumbnail((width, height), Image.LANCZOS)
        x = (width - img.width) // 2
        y = (height - img.height) // 2
        out.paste(img, (x, y))
        return out

    def _estimate_matte_rgb(self, frame: Image.Image) -> tuple[int, int, int]:
        """Estimate matte RGB."""
        rgb = frame.convert("RGB")
        w, h = rgb.size
        pts = (
            (0, 0),
            (w - 1, 0),
            (0, h - 1),
            (w - 1, h - 1),
            (w // 2, 0),
            (w // 2, h - 1),
            (0, h // 2),
            (w - 1, h // 2),
        )
        pixels = [rgb.getpixel((int(x), int(y))) for x, y in pts]
        r = int(sum(p[0] for p in pixels) / len(pixels))
        g = int(sum(p[1] for p in pixels) / len(pixels))
        b = int(sum(p[2] for p in pixels) / len(pixels))
        return (r, g, b)

    def _normalize_logo_frame_to_black(self, frame: Image.Image, matte_rgb: tuple[int, int, int]) -> Image.Image:
        """Normalize logo frame to black."""
        rgb = frame.convert("RGB")
        bg = Image.new("RGB", rgb.size, matte_rgb)

        # Remove baked-in matte tint and keep glow softness with a feathered mask.
        fg = ImageChops.subtract(rgb, bg)
        diff = ImageChops.difference(rgb, bg).convert("L")
        low = 8
        high = 48

        def _alpha_map(v: int) -> int:
            """Convert luminance difference to alpha value."""
            if v <= low:
                return 0
            if v >= high:
                return 255
            return int((v - low) * 255 / max(1, (high - low)))

        mask = diff.point(_alpha_map).filter(ImageFilter.GaussianBlur(radius=1.2))
        return Image.composite(fg, Image.new("RGB", rgb.size, (0, 0, 0)), mask)

    def _load_boot_media(self) -> Any:
        """Load boot media."""
        self._boot_media_frames = []
        self._boot_media_frame_delays = []
        self._boot_media_frame_idx = 0

        media_root = getattr(self, "resource_dir", self.base_dir)
        gif_candidates = (
            os.path.join(media_root, BOOT_MEDIA_GIF_REL),
            os.path.join(media_root, BOOT_MEDIA_GIF_FALLBACK_REL),
        )
        gif_path = next((p for p in gif_candidates if os.path.exists(p)), "")
        img_candidates = (
            os.path.join(media_root, BOOT_MEDIA_IMG_REL),
            self.icon_path_png,
        )
        img_path = next((p for p in img_candidates if os.path.exists(p)), "")
        w, h = (220, 220)

        try:
            if gif_path:
                with Image.open(gif_path) as gif:
                    matte_rgb = self._estimate_matte_rgb(gif.copy())
                    frame_idx = 0
                    while True:
                        try:
                            gif.seek(frame_idx)
                        except EOFError:
                            break
                        processed = self._normalize_logo_frame_to_black(gif.copy(), matte_rgb)
                        frame = self._fit_media_frame(processed, w, h)
                        self._boot_media_frames.append(
                            ctk.CTkImage(light_image=frame, dark_image=frame, size=(w, h))
                        )
                        delay = int(gif.info.get("duration", 80) or 80)
                        self._boot_media_frame_delays.append(max(40, delay))
                        frame_idx += 1
                if self._boot_media_frames:
                    return
            if img_path:
                with Image.open(img_path) as raw:
                    matte_rgb = self._estimate_matte_rgb(raw.copy())
                    frame = self._fit_media_frame(self._normalize_logo_frame_to_black(raw.copy(), matte_rgb), w, h)
                self._boot_media_frames = [ctk.CTkImage(light_image=frame, dark_image=frame, size=(w, h))]
                self._boot_media_frame_delays = [1000]
                if self._boot_media_text_label:
                    self._boot_media_text_label.place_forget()
                return
        except Exception as e:
            self.append_log(f"[launcher] boot media load error: {e}\n")

        if self._boot_media_label:
            self._boot_media_label.configure(image=None)
        if self._boot_media_text_label:
            self._boot_media_text_label.place(relx=0.5, rely=0.5, anchor="center")

    def _start_boot_media(self) -> Any:
        """Start boot media."""
        if not self._boot_overlay_visible:
            return
        self._stop_boot_media()
        if not self._boot_media_label:
            return
        if not self._boot_media_frames:
            self._safe_after(50, self._hide_boot_overlay)
            return
        self._boot_media_frame_idx = 0
        self._render_boot_media_frame()

    def _render_boot_media_frame(self) -> Any:
        """Render the next boot media frame into the preview widget."""
        if not self._boot_overlay_visible:
            return
        if not self._boot_media_label or not self._boot_media_frames:
            return
        idx = int(self._boot_media_frame_idx)
        if idx >= len(self._boot_media_frames):
            self._hide_boot_overlay()
            return
        self._boot_media_label.configure(image=self._boot_media_frames[idx], text="")
        delay = int(self._boot_media_frame_delays[idx]) if idx < len(self._boot_media_frame_delays) else 80
        self._boot_media_frame_idx = idx + 1
        if self._boot_media_frame_idx >= len(self._boot_media_frames):
            self._boot_media_job = self._safe_after(max(40, delay), self._hide_boot_overlay)
            return
        self._boot_media_job = self._safe_after(max(40, delay), self._render_boot_media_frame)

    def _stop_boot_media(self) -> Any:
        """Stop boot media."""
        if self._boot_media_job is not None:
            try:
                self.after_cancel(self._boot_media_job)
            except Exception:
                pass
            self._boot_media_job = None

    def _refresh_boot_overlay_status(self) -> Any:
        """Refresh boot overlay status."""
        if not self._boot_overlay_visible or not self._boot_status_label:
            return
        self._boot_phase = (self._boot_phase + 1) % 4
        dots = "." * self._boot_phase
        self._boot_status_label.configure(text=f"Starting server{dots}")

    def _schedule_boot_overlay_tick(self) -> Any:
        """Schedule boot overlay tick."""
        if not self._boot_overlay_visible:
            return
        if self._boot_timer_job is not None:
            try:
                self.after_cancel(self._boot_timer_job)
            except Exception:
                pass
        self._boot_timer_job = self._safe_after(300, self._boot_overlay_tick)

    def _boot_overlay_tick(self) -> Any:
        """Advance boot overlay timers and periodic UI updates."""
        self._boot_timer_job = None
        if not self._boot_overlay_visible:
            return
        self._refresh_boot_overlay_status()
        elapsed = max(0.0, time.time() - float(self._boot_started_ts or 0.0))
        if elapsed >= BOOT_OVERLAY_DISMISS_AFTER_S:
            if self._boot_skip_btn:
                self._boot_skip_btn.configure(state="normal", text_color=COLOR_TEXT)
            if self._boot_hint_label:
                self._boot_hint_label.configure(
                    text="Server is still starting. You can open launcher and continue in background.",
                    text_color=COLOR_WARN,
                )
        self._schedule_boot_overlay_tick()

