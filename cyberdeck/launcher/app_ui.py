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

        self.sidebar = ctk.CTkFrame(
            self,
            width=258,
            corner_radius=0,
            fg_color=COLOR_PANEL,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(8, weight=1)

        brand = ctk.CTkFrame(
            self.sidebar,
            fg_color=COLOR_PANEL_ALT,
            corner_radius=6,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        brand.grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 10))
        ctk.CTkLabel(
            brand,
            text="CYBERDECK",
            font=("Consolas", 23, "bold"),
            text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=14, pady=(12, 0))
        ctk.CTkLabel(
            brand,
            text=self.tr("app_subtitle"),
            font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=14, pady=(2, 12))

        self.btn_home = self.create_nav_btn(self.tr("nav_home"), "home", 1)
        self.btn_devices = self.create_nav_btn(self.tr("nav_devices"), "devices", 2)
        self.btn_settings = self.create_nav_btn(self.tr("nav_settings"), "settings", 3)

        footer = ctk.CTkFrame(
            self.sidebar,
            fg_color=COLOR_PANEL_ALT,
            corner_radius=6,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        footer.grid(row=9, column=0, sticky="ew", padx=14, pady=(0, 12))
        self.btn_support = CyberBtn(
            footer,
            text=self.tr("nav_support"),
            command=self.open_support_page,
            height=32,
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=0,
            border_color=COLOR_BORDER,
            hover_color=COLOR_PANEL,
        )
        self.btn_support.pack(fill="x", padx=8, pady=(8, 6))
        self.btn_help = CyberBtn(
            footer,
            text=self.tr("nav_help"),
            command=self.show_help,
            height=32,
            font=FONT_SMALL,
            fg_color="transparent",
            border_width=0,
            border_color=COLOR_BORDER,
            hover_color=COLOR_PANEL,
        )
        self.btn_help.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(
            self.sidebar,
            text=self.tr("launcher_version", version=LAUNCHER_VERSION),
            font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        ).grid(row=10, column=0, padx=18, pady=(0, 14), sticky="w")

        self.home_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.devices_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.settings_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=COLOR_BG)

        self.setup_home()
        self.setup_devices()
        self.setup_settings()

        self.select_frame("home")

    def _boot_stage_defaults(self) -> dict[str, tuple[float, str]]:
        """Return boot-stage labels and target progress values."""
        return {
            "bootstrap": (0.05, self.tr("boot_stage_bootstrap")),
            "permissions": (0.14, self.tr("boot_stage_permissions")),
            "modules": (0.26, self.tr("boot_stage_modules")),
            "ports": (0.40, self.tr("boot_stage_ports")),
            "configs": (0.54, self.tr("boot_stage_configs")),
            "updates_check": (0.68, self.tr("boot_stage_updates_check")),
            "updates_install": (0.78, self.tr("boot_stage_updates_install")),
            "codes": (0.86, self.tr("boot_stage_codes")),
            "server_start": (0.92, self.tr("boot_stage_server_start")),
            "server_wait": (0.96, self.tr("boot_stage_server_wait")),
            "server_ready": (1.00, self.tr("boot_stage_server_ready")),
        }

    def _boot_stage_visual_defaults(self) -> dict[str, str]:
        """Return visual token per boot stage."""
        return {
            "bootstrap": "core",
            "permissions": "shield",
            "modules": "modules",
            "ports": "ports",
            "configs": "config",
            "updates_check": "updates",
            "updates_install": "install",
            "codes": "codes",
            "server_start": "server",
            "server_wait": "server",
            "server_ready": "ready",
        }

    def _set_boot_stage(
        self,
        stage: str,
        progress: float = None,
        detail: str = "",
        visual_key: str = "",
    ) -> Any:
        """Update current boot stage caption and target progress."""
        if not self._boot_overlay:
            return

        stages = self._boot_stage_defaults()
        default_progress, default_text = stages.get(str(stage or ""), (None, str(stage or "").strip()))
        status = str(default_text or "").strip() or self.tr("boot_loading")
        extra = str(detail or "").strip()
        if extra:
            status = f"{status}: {extra}"
        self._boot_status_base_text = status

        stage_key = str(stage or "").strip()
        visual = str(visual_key or "").strip().lower()
        if not visual:
            visual = self._boot_stage_visual_defaults().get(stage_key, "core")
        if visual and visual != str(getattr(self, "_boot_visual_key", "") or ""):
            self._boot_visual_key = visual

        if progress is None:
            progress = default_progress
        try:
            if progress is not None:
                p = max(0.0, min(1.0, float(progress)))
                if stage_key == "bootstrap":
                    self._boot_progress_value = max(0.0, min(float(self._boot_progress_value or 0.0), p))
                self._boot_progress_ceiling = max(float(getattr(self, "_boot_progress_ceiling", 0.0) or 0.0), p)
                if stage_key == "server_ready":
                    self._boot_progress_ceiling = 1.0
        except Exception:
            pass

        self._refresh_boot_overlay_status()

    def _build_boot_overlay(self) -> Any:
        """Build boot overlay."""
        overlay = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0, border_width=0)
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        overlay.lift()

        content = ctk.CTkFrame(
            overlay,
            fg_color="transparent",
            corner_radius=0,
            border_width=0,
        )
        content.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.90, relheight=0.92)

        self._boot_signature_label = None

        footer = ctk.CTkFrame(content, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=18, pady=(0, 16))

        status_row = ctk.CTkFrame(footer, fg_color="transparent")
        status_row.pack(fill="x", padx=120, pady=(0, 2))
        status_row.grid_columnconfigure(0, weight=1)
        status_row.grid_columnconfigure(1, weight=0)

        self._boot_status_label = ctk.CTkLabel(
            status_row,
            text=self.tr("boot_stage_bootstrap"),
            font=FONT_UI_BOLD,
            text_color=COLOR_TEXT,
            anchor="w",
            justify="left",
        )
        self._boot_status_label.grid(row=0, column=0, sticky="w")

        self._boot_progress_pct_label = ctk.CTkLabel(
            status_row,
            text="00%",
            font=("Consolas", 13, "bold"),
            text_color="#6CBF96",
            anchor="e",
        )
        self._boot_progress_pct_label.grid(row=0, column=1, sticky="e")

        progress_shell = ctk.CTkFrame(footer, fg_color="transparent")
        progress_shell.pack(fill="x", padx=120)
        self._boot_progress = ctk.CTkProgressBar(
            progress_shell,
            mode="determinate",
            height=8,
            corner_radius=4,
            border_width=0,
            fg_color="#07140F",
            progress_color="#2F8C65",
        )
        self._boot_progress.pack(fill="x", pady=(0, 0))
        self._boot_progress.set(0.0)

        self._boot_hint_label = None

        self._boot_media_size = (560, 300)
        media_shell = ctk.CTkFrame(content, fg_color="transparent")
        media_shell.pack(fill="both", expand=True, padx=18, pady=(6, 10))

        media_stub = ctk.CTkFrame(
            media_shell,
            fg_color="#000000",
            corner_radius=0,
            border_width=0,
            width=int(self._boot_media_size[0]),
            height=int(self._boot_media_size[1]),
        )
        media_stub.pack(expand=True)
        media_stub.pack_propagate(False)

        self._boot_bg_icon_label = ctk.CTkLabel(media_stub, text="")
        self._boot_bg_icon_label.place(relx=0.5, rely=0.5, anchor="center")

        self._boot_media_label = ctk.CTkLabel(media_stub, text="")
        self._boot_media_label.place(relx=0.5, rely=0.5, anchor="center")
        self._boot_media_text_label = ctk.CTkLabel(
            media_stub,
            text="",
            font=("Consolas", 18, "bold"),
            text_color=COLOR_TEXT_DIM,
            fg_color="transparent",
        )
        self._boot_media_text_label.place(relx=0.5, rely=0.5, anchor="center")

        self._boot_overlay = overlay
        self._boot_overlay_visible = False
        self._load_boot_media()
        try:
            overlay.place_forget()
        except Exception:
            pass

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
        self._boot_server_ready_announced = False
        self._boot_started_ts = time.time()
        self._boot_phase = -1
        self._boot_spinner_last_ts = 0.0
        self._boot_progress_value = 0.0
        self._boot_progress_target = 0.03
        self._boot_progress_ceiling = 0.03
        self._boot_visual_key = "core"
        self._boot_status_base_text = str(status or "").strip() or self.tr("boot_stage_bootstrap")
        self._boot_overlay_visible = True
        self._boot_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._boot_overlay.lift()
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass
        try:
            if self._boot_hint_label:
                self._boot_hint_label.configure(text=self.tr("boot_hint_wait"), text_color=COLOR_TEXT_DIM)
        except Exception:
            pass
        try:
            if self._boot_signature_label:
                self._boot_signature_label.configure(text=self.tr("boot_loading"))
        except Exception:
            pass
        try:
            if self._boot_progress:
                self._boot_progress.set(0.0)
            if self._boot_progress_pct_label:
                self._boot_progress_pct_label.configure(text="00%")
        except Exception:
            pass
        self._load_boot_media()
        self._start_boot_media()
        self._refresh_boot_overlay_status()
        self._schedule_boot_overlay_tick()

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
        self._boot_progress_value = 0.0
        self._boot_progress_target = 0.0
        self._boot_progress_ceiling = 0.0
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

    def _boot_background_label(self, visual_key: str) -> str:
        """Return short label rendered into background badge."""
        labels = {
            "core": "CORE",
            "shield": "PERM",
            "modules": "MOD",
            "ports": "PORT",
            "config": "CFG",
            "updates": "UPD",
            "install": "INST",
            "codes": "CODE",
            "server": "SRV",
            "ready": "READY",
            "ffmpeg": "FFMPEG",
        }
        key = str(visual_key or "").strip().lower()
        return labels.get(key, "BOOT")

    def _boot_background_icon_candidates(self, visual_key: str) -> list[str]:
        """Return stage-specific icon candidates for the boot backdrop."""
        key = str(visual_key or "").strip().lower()
        roots = []
        for raw in (
            os.path.join(getattr(self, "resource_dir", self.base_dir), "static", "boot_icons"),
            os.path.join(self.base_dir, "static", "boot_icons"),
            os.path.join(getattr(self, "resource_dir", self.base_dir), "static"),
            os.path.join(self.base_dir, "static"),
            getattr(self, "resource_dir", self.base_dir),
            self.base_dir,
        ):
            path = os.path.abspath(str(raw or ""))
            if path and path not in roots and os.path.isdir(path):
                roots.append(path)

        names = []
        if key:
            names.extend([f"{key}.png", f"{key}.webp", f"{key}.jpg", f"{key}.jpeg"])
        if key == "install":
            names.extend(["dependencies.png", "installer.png", "ffmpeg.png"])
        if key == "updates":
            names.extend(["updates.png", "cloud.png"])
        if key == "ffmpeg":
            names.extend(["ffmpeg.png", "video.png"])
        if key == "server":
            names.extend(["server.png", "network.png"])

        seen = set()
        candidates = []
        for root in roots:
            for name in names:
                path = os.path.join(root, name)
                if os.path.isfile(path):
                    norm = os.path.abspath(path)
                    if norm not in seen:
                        seen.add(norm)
                        candidates.append(norm)
        return candidates

    def _load_boot_background_icon(self, width: int, height: int, visual_key: str = "") -> Any:
        """Load background icon used under timeline media."""
        if not self._boot_bg_icon_label:
            return
        self._boot_bg_icon_ctk_img = None
        try:
            self._boot_bg_icon_label.configure(image=None, text="")
        except Exception:
            pass
        return

    def _fit_media_frame(self, src: Image.Image, width: int, height: int) -> Image.Image:
        """Fit media frame."""
        out = Image.new("RGB", (int(width), int(height)), color=(0, 0, 0))
        img = src.convert("RGB")
        img.thumbnail((int(width), int(height)), Image.LANCZOS)
        x = (int(width) - int(img.width)) // 2
        y = (int(height) - int(img.height)) // 2
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

    def _timeline_media_candidates(self, media_root: str, exts: tuple[str, ...]) -> list[str]:
        """Return timeline-oriented media candidates with stable priority."""
        roots = []
        for raw in (
            os.path.join(media_root, "static"),
            media_root,
            os.path.join(self.base_dir, "static"),
            self.base_dir,
        ):
            path = os.path.abspath(str(raw or ""))
            if path and path not in roots and os.path.isdir(path):
                roots.append(path)

        out = []
        seen = set()
        for root in roots:
            try:
                names = sorted(os.listdir(root))
            except Exception:
                names = []
            for name in names:
                low = str(name or "").strip().lower()
                if ("timeline" not in low) or (not any(low.endswith(ext) for ext in exts)):
                    continue
                path = os.path.join(root, name)
                if not os.path.isfile(path):
                    continue
                norm = os.path.abspath(path)
                if norm in seen:
                    continue
                seen.add(norm)
                out.append(norm)
        return out

    def _load_boot_media(self) -> Any:
        """Load boot media."""
        self._boot_media_frames = []
        self._boot_media_frame_delays = []
        self._boot_media_frame_idx = 0
        w, h = tuple(getattr(self, "_boot_media_size", (460, 220)))
        self._boot_media_size = (int(w), int(h))

        media_root = getattr(self, "resource_dir", self.base_dir)
        self._load_boot_background_icon(int(w), int(h), str(getattr(self, "_boot_visual_key", "") or ""))
        gif_candidates = []
        gif_candidates.extend(self._timeline_media_candidates(media_root, (".gif", ".webp")))
        gif_candidates.extend(
            [
                os.path.join(media_root, "static", "launcher_timeline.gif"),
                os.path.join(media_root, "static", "timeline.gif"),
                os.path.join(media_root, BOOT_MEDIA_GIF_REL),
                os.path.join(media_root, BOOT_MEDIA_GIF_FALLBACK_REL),
                os.path.join(self.base_dir, "launcher_timeline.gif"),
                os.path.join(self.base_dir, "timeline.gif"),
            ]
        )
        # Keep first unique existing file and preserve order.
        dedup_gif = []
        seen = set()
        for path in gif_candidates:
            norm = os.path.abspath(str(path or ""))
            if (not norm) or (norm in seen):
                continue
            seen.add(norm)
            if os.path.exists(norm):
                dedup_gif.append(norm)
        gif_candidates = tuple(dedup_gif)
        gif_path = next((p for p in gif_candidates if os.path.exists(p)), "")
        img_candidates = []
        img_candidates.extend(self._timeline_media_candidates(media_root, (".png", ".jpg", ".jpeg", ".bmp")))
        img_candidates.extend(
            [
                os.path.join(media_root, "static", "launcher_timeline.png"),
                os.path.join(media_root, BOOT_MEDIA_IMG_REL),
                self.icon_path_png,
            ]
        )
        dedup_img = []
        seen = set()
        for path in img_candidates:
            norm = os.path.abspath(str(path or ""))
            if (not norm) or (norm in seen):
                continue
            seen.add(norm)
            if os.path.exists(norm):
                dedup_img.append(norm)
        img_candidates = tuple(dedup_img)
        img_path = next((p for p in img_candidates if os.path.exists(p)), "")

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
                        frame_src = gif.copy()
                        processed = self._normalize_logo_frame_to_black(frame_src, matte_rgb)
                        frame = self._fit_media_frame(processed, w, h)
                        self._boot_media_frames.append(
                            ctk.CTkImage(light_image=frame, dark_image=frame, size=(w, h))
                        )
                        delay = int(gif.info.get("duration", 80) or 80)
                        self._boot_media_frame_delays.append(max(35, min(220, delay)))
                        frame_idx += 1
                if self._boot_media_frames:
                    return
            if img_path:
                with Image.open(img_path) as raw:
                    matte_rgb = self._estimate_matte_rgb(raw.copy())
                    source = self._normalize_logo_frame_to_black(raw.copy(), matte_rgb)
                    frame = self._fit_media_frame(source, w, h)
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
            try:
                self._boot_media_label.configure(image=None, text="")
            except Exception:
                pass
            return
        try:
            self._boot_media_label.configure(text="")
            if self._boot_media_text_label:
                self._boot_media_text_label.place_forget()
        except Exception:
            pass
        self._boot_media_frame_idx = 0
        self._render_boot_media_frame()

    def _render_boot_media_frame(self) -> Any:
        """Render the next boot media frame into the preview widget."""
        if not self._boot_overlay_visible:
            return
        if not self._boot_media_label or not self._boot_media_frames:
            return
        idx = int(self._boot_media_frame_idx) % len(self._boot_media_frames)
        self._boot_media_label.configure(image=self._boot_media_frames[idx], text="")
        delay = int(self._boot_media_frame_delays[idx]) if idx < len(self._boot_media_frame_delays) else 80
        self._boot_media_frame_idx = (idx + 1) % max(1, len(self._boot_media_frames))
        self._boot_media_job = self._safe_after(max(30, min(220, delay)), self._render_boot_media_frame)

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
        if not self._boot_overlay_visible:
            return
        spinner = ("#", "##", "###", "####")
        now = time.time()
        last_ts = float(getattr(self, "_boot_spinner_last_ts", 0.0) or 0.0)
        if (not last_ts) or ((now - last_ts) >= float(BOOT_SPINNER_STEP_S)):
            self._boot_phase = (int(self._boot_phase) + 1) % len(spinner)
            self._boot_spinner_last_ts = now
        phase = int(self._boot_phase) if int(self._boot_phase) >= 0 else 0

        status = str(getattr(self, "_boot_status_base_text", "") or "").strip() or self.tr("boot_stage_bootstrap")
        if self._boot_status_label:
            try:
                self._boot_status_label.configure(text=f"[{spinner[phase]}] {status}")
            except Exception:
                pass

        current = max(0.0, min(1.0, float(getattr(self, "_boot_progress_value", 0.0) or 0.0)))
        target = max(0.0, min(1.0, float(getattr(self, "_boot_progress_target", 0.0) or 0.0)))
        if current < target:
            step = max(0.004, (target - current) * 0.28)
            current = min(target, current + step)
        else:
            current = target
        self._boot_progress_value = current

        try:
            if self._boot_progress:
                self._boot_progress.set(current)
        except Exception:
            pass
        try:
            if self._boot_progress_pct_label:
                self._boot_progress_pct_label.configure(text=f"{int(round(current * 100)):02d}%")
        except Exception:
            pass

    def _schedule_boot_overlay_tick(self) -> Any:
        """Schedule boot overlay tick."""
        if not self._boot_overlay_visible:
            return
        if self._boot_timer_job is not None:
            try:
                self.after_cancel(self._boot_timer_job)
            except Exception:
                pass
        self._boot_timer_job = self._safe_after(int(BOOT_PROGRESS_TICK_MS), self._boot_overlay_tick)

    def _boot_overlay_tick(self) -> Any:
        """Advance boot overlay timers and periodic UI updates."""
        self._boot_timer_job = None
        if not self._boot_overlay_visible:
            return
        target = max(0.0, min(1.0, float(getattr(self, "_boot_progress_target", 0.0) or 0.0)))
        ceiling = max(0.0, min(1.0, float(getattr(self, "_boot_progress_ceiling", target) or target)))
        if target < ceiling:
            # Exponential phantom fill: fast at start, smoother near completion.
            remaining = max(0.0, ceiling - target)
            step = max(float(BOOT_PROGRESS_EXP_MIN_STEP), remaining * float(BOOT_PROGRESS_EXP_RATE))
            step = min(float(BOOT_PROGRESS_EXP_MAX_STEP), step)
            step = max(float(BOOT_PROGRESS_TARGET_STEP), step)
            target = min(ceiling, target + step)
            self._boot_progress_target = target
        self._refresh_boot_overlay_status()
        elapsed = max(0.0, time.time() - float(self._boot_started_ts or 0.0))
        if elapsed >= BOOT_OVERLAY_DISMISS_AFTER_S:
            if self._boot_hint_label:
                self._boot_hint_label.configure(
                    text=self.tr("boot_still_starting"),
                    text_color=COLOR_WARN,
                )
        self._schedule_boot_overlay_tick()

