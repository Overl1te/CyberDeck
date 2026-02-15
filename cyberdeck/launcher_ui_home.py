import customtkinter as ctk


def setup_home_ui(app, ui: dict):
    """Set up home UI."""
    CyberBtn = ui["CyberBtn"]
    COLOR_PANEL = ui["COLOR_PANEL"]
    COLOR_BORDER = ui["COLOR_BORDER"]
    COLOR_TEXT = ui["COLOR_TEXT"]
    COLOR_TEXT_DIM = ui["COLOR_TEXT_DIM"]
    COLOR_ACCENT = ui["COLOR_ACCENT"]
    COLOR_ACCENT_HOVER = ui["COLOR_ACCENT_HOVER"]
    FONT_HEADER = ui["FONT_HEADER"]
    FONT_UI_BOLD = ui["FONT_UI_BOLD"]
    FONT_SMALL = ui["FONT_SMALL"]
    FONT_CODE = ui["FONT_CODE"]

    header = ctk.CTkFrame(app.home_frame, fg_color=COLOR_PANEL, corner_radius=12, height=70)
    header.pack(fill="x", padx=20, pady=(20, 10))
    ctk.CTkLabel(header, text=app.tr("home_title"), font=FONT_HEADER, text_color=COLOR_TEXT).pack(
        side="left", padx=20, pady=18
    )
    app.lbl_header_status = ctk.CTkLabel(
        header, text=app.tr("server_placeholder"), font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM
    )
    app.lbl_header_status.pack(side="right", padx=20)

    grid = ctk.CTkFrame(app.home_frame, fg_color="transparent")
    grid.pack(fill="x", padx=20)

    card = ctk.CTkFrame(grid, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
    card.pack(side="left", fill="both", expand=True, padx=(0, 10))

    ctk.CTkLabel(card, text=app.tr("access_code"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(pady=(12, 4))
    app.lbl_code = ctk.CTkLabel(card, text="....", font=FONT_CODE, text_color=COLOR_TEXT)
    app.lbl_code.pack(pady=2)

    btn_row = ctk.CTkFrame(card, fg_color="transparent")
    btn_row.pack(fill="x", padx=18, pady=(6, 14))
    CyberBtn(
        btn_row,
        text=app.tr("copy"),
        command=app.copy_pairing_code,
        height=34,
        fg_color=COLOR_ACCENT,
        text_color="#0B0F12",
        hover_color=COLOR_ACCENT_HOVER,
        border_color=COLOR_ACCENT,
    ).pack(side="left", expand=True, fill="x", padx=(0, 8))
    CyberBtn(btn_row, text=app.tr("refresh"), command=app.regenerate_code_action, height=34).pack(
        side="left", expand=True, fill="x"
    )

    qr_card = ctk.CTkFrame(grid, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
    qr_card.pack(side="left", fill="both", expand=False, padx=(10, 10))
    ctk.CTkLabel(qr_card, text=app.tr("login_qr"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(pady=(12, 6))
    app.lbl_qr = ctk.CTkLabel(qr_card, text=app.tr("qr_unavailable"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
    app.lbl_qr.pack(padx=14, pady=(0, 8))
    CyberBtn(qr_card, text=app.tr("refresh_qr"), command=lambda: app.refresh_qr_code(force=True), height=34).pack(
        padx=14, pady=(0, 14), fill="x"
    )

    info = ctk.CTkFrame(grid, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
    info.pack(side="left", fill="both", expand=True, padx=(10, 0))

    ctk.CTkLabel(info, text=app.tr("server_label"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(pady=(12, 6))
    app.lbl_server = ctk.CTkLabel(info, text="0.0.0.0:8080", font=FONT_UI_BOLD, text_color=COLOR_TEXT)
    app.lbl_server.pack(pady=2)
    app.lbl_version = ctk.CTkLabel(info, text=app.tr("version_placeholder"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
    app.lbl_version.pack(pady=(0, 10))

    CyberBtn(
        info,
        text=app.tr("restart_server"),
        command=app.restart_server,
        height=34,
        fg_color=COLOR_ACCENT,
        text_color="#0B0F12",
        hover_color=COLOR_ACCENT_HOVER,
        border_color=COLOR_ACCENT,
    ).pack(padx=18, pady=(0, 14), fill="x")

    summary = ctk.CTkFrame(app.home_frame, fg_color=COLOR_PANEL, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
    summary.pack(fill="x", padx=20, pady=(12, 20))

    ctk.CTkLabel(summary, text=app.tr("summary"), font=FONT_UI_BOLD, text_color=COLOR_TEXT).pack(anchor="w", padx=18, pady=(12, 6))
    app.lbl_summary_devices = ctk.CTkLabel(summary, text=app.tr("devices_ratio", online=0, total=0), font=FONT_SMALL, text_color=COLOR_TEXT)
    app.lbl_summary_devices.pack(anchor="w", padx=18)
    app.lbl_summary_logs = ctk.CTkLabel(summary, text=app.tr("logs_off"), font=FONT_SMALL, text_color=COLOR_TEXT)
    app.lbl_summary_logs.pack(anchor="w", padx=18, pady=(4, 0))
    app.lbl_summary_tray = ctk.CTkLabel(summary, text=app.tr("tray_mode_main"), font=FONT_SMALL, text_color=COLOR_TEXT)
    app.lbl_summary_tray.pack(anchor="w", padx=18, pady=(4, 0))
    app.lbl_logs_hint = ctk.CTkLabel(summary, text="", font=FONT_SMALL, text_color=COLOR_TEXT_DIM)
    app.lbl_logs_hint.pack(anchor="w", padx=18, pady=(6, 12))
