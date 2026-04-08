import customtkinter as ctk
import tkinter as tk


def setup_home_ui(app, ui: dict):
    """Set up home UI."""
    CyberBtn = ui["CyberBtn"]
    COLOR_PANEL = ui["COLOR_PANEL"]
    COLOR_PANEL_ALT = ui["COLOR_PANEL_ALT"]
    COLOR_BORDER = ui["COLOR_BORDER"]
    COLOR_TEXT = ui["COLOR_TEXT"]
    COLOR_TEXT_DIM = ui["COLOR_TEXT_DIM"]
    COLOR_ACCENT = ui["COLOR_ACCENT"]
    COLOR_ACCENT_HOVER = ui["COLOR_ACCENT_HOVER"]
    COLOR_WARN = ui["COLOR_WARN"]
    COLOR_FAIL = ui["COLOR_FAIL"]
    FONT_HEADER = ui["FONT_HEADER"]
    FONT_UI_BOLD = ui["FONT_UI_BOLD"]
    FONT_SMALL = ui["FONT_SMALL"]
    ACCESS_FONT = ("Consolas", 15, "bold")

    def _make_access_textbox(parent, *, height: int = 74):
        """Create a larger read-only textbox for copyable access origins."""
        box = ctk.CTkTextbox(
            parent,
            height=height,
            fg_color=COLOR_PANEL_ALT,
            border_width=1,
            border_color=COLOR_BORDER,
            corner_radius=8,
            text_color=COLOR_TEXT,
            font=ACCESS_FONT,
            wrap="word",
        )
        box.insert("1.0", "")
        box.configure(state="disabled")
        try:
            box.bind(
                "<Control-a>",
                lambda event, widget=box: (
                    widget.focus_set(),
                    widget.tag_add("sel", "1.0", "end-1c"),
                    "break",
                )[-1],
                add="+",
            )
        except Exception:
            pass
        return box

    root = ctk.CTkFrame(app.home_frame, fg_color="transparent")
    root.pack(fill="both", expand=True, padx=16, pady=(14, 16))
    root.grid_columnconfigure(0, weight=1, minsize=210)
    root.grid_columnconfigure(1, weight=2, minsize=320)
    root.grid_columnconfigure(2, weight=2, minsize=300)

    header = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
        height=108,
    )
    header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
    header.grid_columnconfigure(0, weight=1)
    header.grid_columnconfigure(1, weight=0)
    header.grid_rowconfigure(2, weight=0)
    ctk.CTkLabel(
        header,
        text=app.tr("home_title"),
        font=FONT_HEADER,
        text_color=COLOR_TEXT,
    ).grid(row=0, column=0, sticky="sw", padx=18, pady=(12, 0))
    ctk.CTkLabel(
        header,
        text=app.tr("home_subtitle"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    ).grid(row=1, column=0, sticky="nw", padx=18, pady=(2, 12))
    app.lbl_header_meta = ctk.CTkLabel(
        header,
        text="TLS | LAN | --:--:--",
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_header_meta.grid(row=2, column=0, sticky="sw", padx=18, pady=(0, 12))
    app.lbl_header_status = ctk.CTkLabel(
        header,
        text=app.tr("server_placeholder"),
        font=FONT_UI_BOLD,
        text_color=COLOR_TEXT_DIM,
        fg_color=COLOR_PANEL_ALT,
        corner_radius=8,
    )
    app.lbl_header_status.grid(row=0, column=1, rowspan=2, sticky="e", padx=14, pady=14)

    metrics_row = ctk.CTkFrame(header, fg_color="transparent")
    metrics_row.grid(row=2, column=1, sticky="e", padx=14, pady=(0, 12))

    def _metric_pill(label_key: str, value_attr: str):
        shell = ctk.CTkFrame(
            metrics_row,
            fg_color=COLOR_PANEL_ALT,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        shell.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(
            shell,
            text=app.tr(label_key),
            font=FONT_SMALL,
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=8, pady=(5, 0))
        label = ctk.CTkLabel(
            shell,
            text="--",
            font=FONT_UI_BOLD,
            text_color=COLOR_TEXT,
        )
        label.pack(anchor="w", padx=8, pady=(0, 5))
        setattr(app, value_attr, label)

    _metric_pill("server_mode_label", "lbl_server_mode")
    _metric_pill("uptime_label", "lbl_server_uptime")
    _metric_pill("cpu_label", "lbl_server_cpu")
    _metric_pill("ram_label", "lbl_server_ram")
    _metric_pill("port_short_label", "lbl_server_port")

    code_card = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    code_card.grid(row=1, column=0, sticky="nsew", padx=(0, 6))

    ctk.CTkLabel(code_card, text=app.tr("access_code"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
        anchor="w", padx=14, pady=(12, 4)
    )
    app.lbl_code = ctk.CTkLabel(
        code_card,
        text="....",
        font=("Consolas", 34, "bold"),
        text_color=COLOR_TEXT,
    )
    app.lbl_code.pack(anchor="w", padx=14, pady=(0, 4))

    app.lbl_pairing_ttl = ctk.CTkLabel(
        code_card,
        text=app.tr("pairing_ttl_placeholder"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_pairing_ttl.pack(anchor="w", padx=14, pady=(0, 8))

    code_btns = ctk.CTkFrame(code_card, fg_color="transparent")
    code_btns.pack(fill="x", padx=14, pady=(4, 12))
    code_btns.grid_columnconfigure(0, weight=1)
    code_btns.grid_columnconfigure(1, weight=1)
    CyberBtn(
        code_btns,
        text=app.tr("copy"),
        command=app.copy_pairing_code,
        fg_color=COLOR_ACCENT,
        text_color="#04110A",
        hover_color=COLOR_ACCENT_HOVER,
        border_color=COLOR_ACCENT,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    CyberBtn(
        code_btns,
        text=app.tr("refresh"),
        command=app.regenerate_code_action,
    ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    qr_card = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    qr_card.grid(row=1, column=1, sticky="nsew", padx=6)
    ctk.CTkLabel(qr_card, text=app.tr("login_qr"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
        anchor="w", padx=14, pady=(12, 8)
    )
    app.lbl_qr = tk.Label(
        qr_card,
        text=app.tr("qr_unavailable"),
        font=FONT_SMALL,
        fg=COLOR_TEXT_DIM,
        bg=COLOR_PANEL,
        bd=0,
        highlightthickness=0,
        anchor="center",
        justify="center",
    )
    app.lbl_qr.pack(expand=True, fill="both", padx=14, pady=(0, 8))
    CyberBtn(
        qr_card,
        text=app.tr("refresh_qr"),
        command=lambda: app.refresh_qr_code(force=True),
        height=35,
    ).pack(padx=14, pady=(0, 12), fill="x")

    info_card = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    info_card.grid(row=1, column=2, sticky="nsew", padx=(6, 0))

    def _build_access_panel(title_key: str, copy_command, *, height: int = 70):
        """Create a titled access block with a large read-only value field and copy action."""
        panel = ctk.CTkFrame(
            info_card,
            fg_color=COLOR_PANEL,
            corner_radius=8,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        panel.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(panel, text=app.tr(title_key), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
            anchor="w", padx=10, pady=(9, 6)
        )
        value_box = _make_access_textbox(panel, height=height)
        value_box.pack(fill="x", padx=10, pady=(0, 8))
        copy_btn = CyberBtn(
            panel,
            text=app.tr("copy"),
            command=copy_command,
            fg_color=COLOR_ACCENT,
            text_color="#04110A",
            hover_color=COLOR_ACCENT_HOVER,
            border_color=COLOR_ACCENT,
            height=31,
        )
        copy_btn.pack(fill="x", padx=10, pady=(0, 10))
        return value_box, copy_btn

    app.txt_local_access, app.btn_copy_local_access = _build_access_panel(
        "local_access_label",
        app.copy_local_access,
        height=58,
    )
    app.txt_public_access, app.btn_copy_public_access = _build_access_panel(
        "public_access_label",
        app.copy_public_access,
        height=72,
    )

    CyberBtn(
        info_card,
        text=app.tr("restart_server"),
        command=app.restart_server,
        fg_color=COLOR_ACCENT,
        text_color="#04110A",
        hover_color=COLOR_ACCENT_HOVER,
        border_color=COLOR_ACCENT,
        height=37,
    ).pack(padx=14, pady=(12, 12), fill="x")

    summary = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    summary.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    summary.grid_columnconfigure(0, weight=1)
    summary.grid_columnconfigure(1, weight=1)

    left = ctk.CTkFrame(summary, fg_color="transparent")
    left.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=12)
    ctk.CTkLabel(left, text=app.tr("summary"), font=FONT_UI_BOLD, text_color=COLOR_TEXT).pack(anchor="w")
    app.lbl_summary_devices = ctk.CTkLabel(
        left,
        text=app.tr("devices_ratio", online=0, total=0),
        font=FONT_SMALL,
        text_color=COLOR_TEXT,
    )
    app.lbl_summary_devices.pack(anchor="w", pady=(8, 0))
    app.lbl_summary_logs = ctk.CTkLabel(left, text=app.tr("logs_off"), font=FONT_SMALL, text_color=COLOR_TEXT)
    app.lbl_summary_logs.pack(anchor="w", pady=(4, 0))
    app.lbl_summary_tray = ctk.CTkLabel(left, text=app.tr("tray_mode_main"), font=FONT_SMALL, text_color=COLOR_TEXT)
    app.lbl_summary_tray.pack(anchor="w", pady=(4, 0))
    app.lbl_logs_hint = ctk.CTkLabel(left, text="", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
    app.lbl_logs_hint.pack(anchor="w", pady=(6, 0))

    right = ctk.CTkFrame(summary, fg_color="transparent")
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 14), pady=12)
    app.lbl_security_state = ctk.CTkLabel(
        right,
        text=app.tr("security_unlocked"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_security_state.pack(anchor="w", pady=(0, 10))

    security_row = ctk.CTkFrame(right, fg_color="transparent")
    security_row.pack(fill="x")
    security_row.grid_columnconfigure(0, weight=1)
    security_row.grid_columnconfigure(1, weight=1)

    app.btn_toggle_input_lock = CyberBtn(
        security_row,
        text=app.tr("security_lock_btn"),
        command=app.toggle_remote_input_lock,
        fg_color="transparent",
        border_color=COLOR_WARN,
        text_color=COLOR_WARN,
        hover_color=COLOR_PANEL_ALT,
    )
    app.btn_toggle_input_lock.grid(row=0, column=0, sticky="ew", padx=(0, 6))

    app.btn_panic_disconnect = CyberBtn(
        security_row,
        text=app.tr("security_panic_btn"),
        command=app.panic_mode_action,
        fg_color="transparent",
        border_color=COLOR_FAIL,
        text_color=COLOR_FAIL,
        hover_color=COLOR_PANEL_ALT,
    )
    app.btn_panic_disconnect.grid(row=0, column=1, sticky="ew", padx=(6, 0))
