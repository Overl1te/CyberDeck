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
    root = ctk.CTkFrame(app.home_frame, fg_color="transparent")
    root.pack(fill="both", expand=True, padx=20, pady=(18, 20))
    root.grid_columnconfigure(0, weight=1, minsize=220)
    root.grid_columnconfigure(1, weight=2, minsize=340)
    root.grid_columnconfigure(2, weight=1, minsize=220)

    header = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
        height=74,
    )
    header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))
    header.grid_columnconfigure(0, weight=1)
    header.grid_columnconfigure(1, weight=0)
    ctk.CTkLabel(
        header,
        text=app.tr("home_title"),
        font=FONT_HEADER,
        text_color=COLOR_TEXT,
    ).grid(row=0, column=0, sticky="w", padx=20, pady=16)
    app.lbl_header_status = ctk.CTkLabel(
        header,
        text=app.tr("server_placeholder"),
        font=FONT_UI_BOLD,
        text_color=COLOR_TEXT_DIM,
        fg_color=COLOR_PANEL_ALT,
        corner_radius=4,
    )
    app.lbl_header_status.grid(row=0, column=1, sticky="e", padx=16, pady=16)

    code_card = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    code_card.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

    ctk.CTkLabel(code_card, text=app.tr("access_code"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
        anchor="w", padx=16, pady=(14, 4)
    )
    app.lbl_code = ctk.CTkLabel(
        code_card,
        text="....",
        font=("Consolas", 40, "bold"),
        text_color=COLOR_TEXT,
    )
    app.lbl_code.pack(anchor="w", padx=16, pady=(0, 4))

    app.lbl_pairing_ttl = ctk.CTkLabel(
        code_card,
        text=app.tr("pairing_ttl_placeholder"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_pairing_ttl.pack(anchor="w", padx=16, pady=(0, 8))

    code_btns = ctk.CTkFrame(code_card, fg_color="transparent")
    code_btns.pack(fill="x", padx=16, pady=(4, 14))
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
    qr_card.grid(row=1, column=1, sticky="nsew", padx=8)
    ctk.CTkLabel(qr_card, text=app.tr("login_qr"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
        anchor="w", padx=16, pady=(14, 8)
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
    app.lbl_qr.pack(expand=True, fill="both", padx=16, pady=(0, 8))
    CyberBtn(
        qr_card,
        text=app.tr("refresh_qr"),
        command=lambda: app.refresh_qr_code(force=True),
    ).pack(padx=16, pady=(0, 14), fill="x")

    info_card = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    info_card.grid(row=1, column=2, sticky="nsew", padx=(8, 0))

    ctk.CTkLabel(info_card, text=app.tr("server_label"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
        anchor="w", padx=16, pady=(14, 4)
    )
    app.lbl_server = ctk.CTkLabel(info_card, text="0.0.0.0:8080", font=FONT_UI_BOLD, text_color=COLOR_TEXT)
    app.lbl_server.pack(anchor="w", padx=16, pady=2)
    app.lbl_version = ctk.CTkLabel(
        info_card,
        text=app.tr("version_placeholder"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_version.pack(anchor="w", padx=16, pady=(0, 4))
    app.lbl_updates = ctk.CTkLabel(
        info_card,
        text=app.tr("updates_not_checked"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_updates.pack(anchor="w", padx=16, pady=(0, 8))

    CyberBtn(
        info_card,
        text=app.tr("restart_server"),
        command=app.restart_server,
        fg_color=COLOR_ACCENT,
        text_color="#04110A",
        hover_color=COLOR_ACCENT_HOVER,
        border_color=COLOR_ACCENT,
    ).pack(padx=16, pady=(0, 14), fill="x")

    summary = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    summary.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
    summary.grid_columnconfigure(0, weight=1)
    summary.grid_columnconfigure(1, weight=1)

    left = ctk.CTkFrame(summary, fg_color="transparent")
    left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=14)
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
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=14)
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
