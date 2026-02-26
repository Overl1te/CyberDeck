import customtkinter as ctk
from tkinter import filedialog


def setup_settings_ui(app, ui: dict):
    """Set up settings UI."""
    CyberBtn = ui["CyberBtn"]
    COLOR_BG = ui["COLOR_BG"]
    DEFAULT_PORT = ui["DEFAULT_PORT"]
    DEFAULT_SETTINGS = ui["DEFAULT_SETTINGS"]
    COLOR_PANEL = ui["COLOR_PANEL"]
    COLOR_PANEL_ALT = ui["COLOR_PANEL_ALT"]
    COLOR_BORDER = ui["COLOR_BORDER"]
    COLOR_TEXT = ui["COLOR_TEXT"]
    COLOR_TEXT_DIM = ui["COLOR_TEXT_DIM"]
    FONT_HEADER = ui["FONT_HEADER"]
    FONT_UI_BOLD = ui["FONT_UI_BOLD"]
    FONT_SMALL = ui["FONT_SMALL"]
    APP_CONFIG_FILE_NAME = ui["APP_CONFIG_FILE_NAME"]

    scroll = ctk.CTkScrollableFrame(
        app.settings_frame,
        fg_color=COLOR_BG,
        corner_radius=0,
        scrollbar_fg_color=COLOR_BG,
        scrollbar_button_color=COLOR_BORDER,
        scrollbar_button_hover_color=COLOR_PANEL,
    )
    scroll.pack(fill="both", expand=True, padx=0, pady=0)
    try:
        scroll._parent_canvas.configure(bg=COLOR_BG, highlightthickness=0)
    except Exception:
        pass

    def _section(title: str):
        """Create a titled settings card."""
        box = ctk.CTkFrame(
            scroll,
            fg_color=COLOR_PANEL,
            corner_radius=6,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        box.pack(fill="x", padx=20, pady=(0, 12))
        ctk.CTkLabel(box, text=title, text_color=COLOR_TEXT, font=FONT_UI_BOLD).pack(
            anchor="w", padx=16, pady=(12, 8)
        )
        return box

    def _styled_entry(parent, width: int = None):
        """Create a styled entry for settings forms."""
        kwargs = {
            "height": 32,
            "corner_radius": 4,
            "fg_color": COLOR_PANEL_ALT,
            "border_color": COLOR_BORDER,
            "text_color": COLOR_TEXT,
        }
        if width is not None:
            kwargs["width"] = int(width)
        return ctk.CTkEntry(parent, **kwargs)

    header = ctk.CTkFrame(
        scroll,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
        height=74,
    )
    header.pack(fill="x", padx=20, pady=(20, 12))
    ctk.CTkLabel(header, text=app.tr("settings_title"), font=FONT_HEADER, text_color=COLOR_TEXT).pack(
        side="left", padx=20, pady=16
    )

    launcher_box = _section(app.tr("section_launcher"))

    app.sw_start_in_tray = ctk.CTkSwitch(launcher_box, text=app.tr("start_in_tray"), text_color=COLOR_TEXT)
    app.sw_start_in_tray.pack(anchor="w", padx=18, pady=(2, 6))
    app.sw_start_in_tray.select() if app.settings.get("start_in_tray") else app.sw_start_in_tray.deselect()

    app.sw_show_on_start = ctk.CTkSwitch(launcher_box, text=app.tr("show_on_start"), text_color=COLOR_TEXT)
    app.sw_show_on_start.pack(anchor="w", padx=18, pady=6)
    app.sw_show_on_start.select() if app.settings.get("show_on_start", True) else app.sw_show_on_start.deselect()

    app.sw_close_to_tray = ctk.CTkSwitch(launcher_box, text=app.tr("close_to_tray"), text_color=COLOR_TEXT)
    app.sw_close_to_tray.pack(anchor="w", padx=18, pady=6)
    app.sw_close_to_tray.select() if app.settings.get("close_to_tray") else app.sw_close_to_tray.deselect()

    app.sw_topmost = ctk.CTkSwitch(
        launcher_box,
        text=app.tr("always_on_top"),
        text_color=COLOR_TEXT,
        command=app.preview_topmost_toggle,
    )
    app.sw_topmost.pack(anchor="w", padx=18, pady=6)
    app.sw_topmost.select() if app.settings.get("always_on_top") else app.sw_topmost.deselect()

    app.sw_autostart = ctk.CTkSwitch(launcher_box, text=app.tr("autostart"), text_color=COLOR_TEXT)
    app.sw_autostart.pack(anchor="w", padx=18, pady=6)
    app.sw_autostart.select() if app.settings.get("autostart") else app.sw_autostart.deselect()

    app.sw_hotkey = ctk.CTkSwitch(launcher_box, text=app.tr("hotkey"), text_color=COLOR_TEXT)
    app.sw_hotkey.pack(anchor="w", padx=18, pady=6)
    app.sw_hotkey.select() if app.settings.get("hotkey_enabled") else app.sw_hotkey.deselect()

    app.sw_debug = ctk.CTkSwitch(launcher_box, text=app.tr("debug_logs"), text_color=COLOR_TEXT)
    app.sw_debug.pack(anchor="w", padx=18, pady=6)
    app.sw_debug.select() if app.settings.get("debug") else app.sw_debug.deselect()

    app.sw_system_notifications = ctk.CTkSwitch(launcher_box, text=app.tr("system_notifications"), text_color=COLOR_TEXT)
    app.sw_system_notifications.pack(anchor="w", padx=18, pady=(6, 10))
    app.sw_system_notifications.select() if app.settings.get("system_notifications", True) else app.sw_system_notifications.deselect()

    ctk.CTkLabel(launcher_box, text=app.tr("language"), text_color=COLOR_TEXT_DIM, font=FONT_SMALL).pack(
        anchor="w", padx=18, pady=(2, 4)
    )
    app.opt_language = ctk.CTkOptionMenu(
        launcher_box,
        values=app.language_options(),
        corner_radius=8,
        fg_color=COLOR_PANEL_ALT,
        button_color=COLOR_BORDER,
        button_hover_color=COLOR_PANEL,
        text_color=COLOR_TEXT,
        dropdown_fg_color=COLOR_PANEL,
        dropdown_hover_color=COLOR_BORDER,
        dropdown_text_color=COLOR_TEXT,
    )
    app.opt_language.pack(fill="x", padx=18, pady=(0, 14))
    app.opt_language.set(app.language_label(app.settings.get("language", "ru")))

    server_box = _section(app.tr("section_server"))

    ctk.CTkLabel(
        server_box,
        text=app.tr("server_params_auto_restart"),
        text_color=COLOR_TEXT_DIM,
        font=FONT_SMALL,
    ).pack(anchor="w", padx=18, pady=(0, 8))

    adv = ctk.CTkFrame(server_box, fg_color="transparent")
    adv.pack(fill="x", padx=18, pady=(0, 14))

    def _row(label: str, initial: str):
        """Create a labeled settings row widget."""
        r = ctk.CTkFrame(adv, fg_color="transparent")
        r.pack(fill="x", pady=4)
        ctk.CTkLabel(r, text=label, text_color=COLOR_TEXT).pack(side="left")
        e = _styled_entry(r, width=180)
        try:
            e.insert(0, str(initial))
        except Exception:
            pass
        e.pack(side="right")
        return e

    app.ent_preferred_port = _row(app.tr("preferred_port"), app.settings.get("preferred_port", DEFAULT_PORT))
    app.ent_pairing_ttl = _row(app.tr("pairing_ttl_min"), app.settings.get("pairing_ttl_min", 0))
    app.ent_session_ttl_days = _row(app.tr("session_ttl_days"), app.settings.get("session_ttl_days", 0))
    app.ent_session_idle_min = _row(app.tr("session_idle_ttl_min"), app.settings.get("session_idle_ttl_min", 0))
    app.ent_max_sessions = _row(app.tr("max_sessions"), app.settings.get("max_sessions", 0))
    app.ent_pin_window_s = _row(app.tr("pin_window_s"), app.settings.get("pin_window_s", 60))
    app.ent_pin_max_fails = _row(app.tr("pin_max_fails"), app.settings.get("pin_max_fails", 8))
    app.ent_pin_block_s = _row(app.tr("pin_block_s"), app.settings.get("pin_block_s", 300))

    ctk.CTkLabel(server_box, text=app.tr("tls_https"), text_color=COLOR_TEXT_DIM, font=FONT_SMALL).pack(
        anchor="w", padx=18, pady=(8, 4)
    )
    app.sw_tls = ctk.CTkSwitch(server_box, text=app.tr("enable_tls"), text_color=COLOR_TEXT)
    app.sw_tls.pack(anchor="w", padx=18, pady=(0, 8))
    app.sw_tls.select() if app.settings.get("tls_enabled") else app.sw_tls.deselect()

    tls_box = ctk.CTkFrame(server_box, fg_color="transparent")
    tls_box.pack(fill="x", padx=18, pady=(0, 10))

    def _row_with_browse(label: str, initial: str):
        """Create a settings row with an entry and browse button."""
        r = ctk.CTkFrame(tls_box, fg_color="transparent")
        r.pack(fill="x", pady=4)
        ctk.CTkLabel(r, text=label, text_color=COLOR_TEXT).pack(side="left")
        e = _styled_entry(r)
        try:
            e.insert(0, str(initial))
        except Exception:
            pass
        e.pack(side="left", padx=(8, 6), expand=True, fill="x")

        def _pick():
            """Pick the target operation."""
            try:
                p = filedialog.askopenfilename(title=label)
                if p:
                    e.delete(0, "end")
                    e.insert(0, p)
            except Exception:
                pass

        CyberBtn(r, text="...", width=36, height=30, command=_pick).pack(side="right")
        return e

    app.ent_tls_cert = _row_with_browse(app.tr("cert_file"), app.settings.get("tls_cert_path", ""))
    app.ent_tls_key = _row_with_browse(app.tr("key_file"), app.settings.get("tls_key_path", ""))
    app.ent_tls_ca = _row_with_browse(app.tr("ca_file"), app.settings.get("tls_ca_path", ""))

    ctk.CTkLabel(server_box, text=app.tr("qr_mode"), text_color=COLOR_TEXT_DIM, font=FONT_SMALL).pack(
        anchor="w", padx=18, pady=(8, 4)
    )
    app.qr_mode_var = ctk.StringVar(
        value=str(app.settings.get("qr_mode", DEFAULT_SETTINGS["qr_mode"]) or DEFAULT_SETTINGS["qr_mode"])
    )
    qr_row = ctk.CTkFrame(server_box, fg_color="transparent")
    qr_row.pack(fill="x", padx=18, pady=(0, 10))
    ctk.CTkRadioButton(qr_row, text=app.tr("open_site"), variable=app.qr_mode_var, value="site").pack(side="left")
    ctk.CTkRadioButton(qr_row, text=app.tr("open_app"), variable=app.qr_mode_var, value="app").pack(
        side="left", padx=(16, 0)
    )

    app_cfg_box = _section(app.tr("app_config_title", name=APP_CONFIG_FILE_NAME))
    cfg = dict(getattr(app, "app_config", {}) or {})

    app.sw_allow_query_token = ctk.CTkSwitch(app_cfg_box, text=app.tr("allow_query_token"), text_color=COLOR_TEXT)
    app.sw_allow_query_token.pack(anchor="w", padx=18, pady=(2, 6))
    app.sw_allow_query_token.select() if cfg.get("allow_query_token") else app.sw_allow_query_token.deselect()

    app.sw_pairing_single_use = ctk.CTkSwitch(
        app_cfg_box,
        text=app.tr("pairing_single_use"),
        text_color=COLOR_TEXT,
    )
    app.sw_pairing_single_use.pack(anchor="w", padx=18, pady=(0, 6))
    app.sw_pairing_single_use.select() if cfg.get("pairing_single_use", False) else app.sw_pairing_single_use.deselect()

    app.sw_ignore_vpn = ctk.CTkSwitch(
        app_cfg_box,
        text=app.tr("ignore_vpn"),
        text_color=COLOR_TEXT,
    )
    app.sw_ignore_vpn.pack(anchor="w", padx=18, pady=(0, 6))
    app.sw_ignore_vpn.select() if cfg.get("ignore_vpn", False) else app.sw_ignore_vpn.deselect()

    app.sw_mdns_enabled = ctk.CTkSwitch(app_cfg_box, text=app.tr("mdns_enable"), text_color=COLOR_TEXT)
    app.sw_mdns_enabled.pack(anchor="w", padx=18, pady=(0, 6))
    app.sw_mdns_enabled.select() if cfg.get("mdns_enabled", True) else app.sw_mdns_enabled.deselect()

    app.sw_device_approval_required = ctk.CTkSwitch(
        app_cfg_box,
        text=app.tr("device_approval_required"),
        text_color=COLOR_TEXT,
    )
    app.sw_device_approval_required.pack(anchor="w", padx=18, pady=(0, 8))
    app.sw_device_approval_required.select() if cfg.get("device_approval_required", True) else app.sw_device_approval_required.deselect()

    ctk.CTkLabel(app_cfg_box, text=app.tr("upload_max_bytes"), text_color=COLOR_TEXT_DIM, font=FONT_SMALL).pack(
        anchor="w", padx=18, pady=(4, 2)
    )
    app.ent_upload_max_bytes = _styled_entry(app_cfg_box)
    app.ent_upload_max_bytes.pack(fill="x", padx=18)
    app.ent_upload_max_bytes.insert(0, str(cfg.get("upload_max_bytes", 0)))

    ctk.CTkLabel(app_cfg_box, text=app.tr("upload_allowed_ext"), text_color=COLOR_TEXT_DIM, font=FONT_SMALL).pack(
        anchor="w", padx=18, pady=(8, 2)
    )
    app.ent_upload_allowed_ext = _styled_entry(app_cfg_box)
    app.ent_upload_allowed_ext.pack(fill="x", padx=18)
    app.ent_upload_allowed_ext.insert(0, str(cfg.get("upload_allowed_ext", "")))

    app.sw_verbose_http_log = ctk.CTkSwitch(app_cfg_box, text=app.tr("verbose_http"), text_color=COLOR_TEXT)
    app.sw_verbose_http_log.pack(anchor="w", padx=18, pady=(10, 4))
    app.sw_verbose_http_log.select() if cfg.get("verbose_http_log", True) else app.sw_verbose_http_log.deselect()

    app.sw_verbose_ws_log = ctk.CTkSwitch(app_cfg_box, text=app.tr("verbose_ws"), text_color=COLOR_TEXT)
    app.sw_verbose_ws_log.pack(anchor="w", padx=18, pady=4)
    app.sw_verbose_ws_log.select() if cfg.get("verbose_ws_log", True) else app.sw_verbose_ws_log.deselect()

    app.sw_verbose_stream_log = ctk.CTkSwitch(app_cfg_box, text=app.tr("verbose_stream"), text_color=COLOR_TEXT)
    app.sw_verbose_stream_log.pack(anchor="w", padx=18, pady=(4, 12))
    app.sw_verbose_stream_log.select() if cfg.get("verbose_stream_log", True) else app.sw_verbose_stream_log.deselect()

    action_box = _section(app.tr("section_actions"))
    btn_row = ctk.CTkFrame(action_box, fg_color="transparent")
    btn_row.pack(fill="x", padx=18, pady=(0, 8))
    btn_row.grid_columnconfigure(0, weight=1)
    btn_row.grid_columnconfigure(1, weight=1)
    CyberBtn(btn_row, text=app.tr("open_app_config"), command=app.open_app_config_file, height=32).grid(
        row=0, column=0, sticky="ew", padx=(0, 6)
    )
    CyberBtn(btn_row, text=app.tr("nav_help"), command=app.show_help, height=32).grid(
        row=0, column=1, sticky="ew", padx=(6, 0)
    )

    CyberBtn(action_box, text=app.tr("apply"), command=app.save_settings_action, height=36).pack(
        padx=18, pady=(4, 10), fill="x"
    )

    app.lbl_settings_status = ctk.CTkLabel(action_box, text="", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
    app.lbl_settings_status.pack(anchor="w", padx=18, pady=(0, 14))
