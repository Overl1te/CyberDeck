import customtkinter as ctk


def _create_accordion(parent, title: str, ui: dict, *, expanded: bool = True):
    """Create accordion."""
    CyberBtn = ui["CyberBtn"]
    COLOR_PANEL_ALT = ui["COLOR_PANEL_ALT"]
    COLOR_BORDER = ui["COLOR_BORDER"]
    COLOR_TEXT_DIM = ui["COLOR_TEXT_DIM"]
    FONT_SMALL = ui["FONT_SMALL"]

    root = ctk.CTkFrame(parent, fg_color="transparent")
    root.pack(padx=18, fill="x", pady=(8, 0))

    body = ctk.CTkFrame(
        root,
        fg_color=COLOR_PANEL_ALT,
        corner_radius=4,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    state = {"open": bool(expanded)}

    def _refresh():
        """Refresh state."""
        marker = "v" if state["open"] else ">"
        btn.configure(text=f"{marker} {title}")
        if state["open"]:
            if body.winfo_manager() != "pack":
                body.pack(fill="x", pady=(6, 0))
        elif body.winfo_manager() == "pack":
            body.pack_forget()

    def _toggle():
        """Toggle accordion expanded state and refresh its layout."""
        state["open"] = not state["open"]
        _refresh()

    btn = CyberBtn(
        root,
        text="",
        command=_toggle,
        height=32,
        font=FONT_SMALL,
        fg_color="transparent",
        border_color=COLOR_BORDER,
        text_color=COLOR_TEXT_DIM,
        hover_color=COLOR_PANEL_ALT,
    )
    btn.pack(fill="x")
    _refresh()
    return body


def setup_devices_ui(app, ui: dict):
    """Set up devices UI."""
    CyberBtn = ui["CyberBtn"]
    COLOR_BG = ui["COLOR_BG"]
    COLOR_PANEL = ui["COLOR_PANEL"]
    COLOR_PANEL_ALT = ui["COLOR_PANEL_ALT"]
    COLOR_BORDER = ui["COLOR_BORDER"]
    COLOR_ACCENT = ui["COLOR_ACCENT"]
    COLOR_ACCENT_HOVER = ui["COLOR_ACCENT_HOVER"]
    COLOR_WARN = ui["COLOR_WARN"]
    COLOR_FAIL = ui["COLOR_FAIL"]
    COLOR_TEXT = ui["COLOR_TEXT"]
    COLOR_TEXT_DIM = ui["COLOR_TEXT_DIM"]
    FONT_HEADER = ui["FONT_HEADER"]
    FONT_UI_BOLD = ui["FONT_UI_BOLD"]
    FONT_SMALL = ui["FONT_SMALL"]
    DEFAULT_SETTINGS = ui["DEFAULT_SETTINGS"]
    DEFAULT_DEVICE_PRESETS = ui["DEFAULT_DEVICE_PRESETS"]

    page = ctk.CTkFrame(app.devices_frame, fg_color="transparent")
    page.pack(fill="both", expand=True, padx=20, pady=(18, 20))

    header = ctk.CTkFrame(
        page,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
        height=72,
    )
    header.pack(fill="x", pady=(0, 12))
    header.grid_columnconfigure(0, weight=1)
    header.grid_columnconfigure(1, weight=0)

    left = ctk.CTkFrame(header, fg_color="transparent")
    left.grid(row=0, column=0, sticky="w", padx=16, pady=14)
    ctk.CTkLabel(left, text=app.tr("devices_title"), font=FONT_HEADER, text_color=COLOR_TEXT).pack(anchor="w")
    app.lbl_devices_status = ctk.CTkLabel(
        left,
        text=app.tr("updated_offline"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_devices_status.pack(anchor="w", pady=(2, 0))

    header_actions = ctk.CTkFrame(header, fg_color="transparent")
    header_actions.grid(row=0, column=1, sticky="e", padx=14, pady=14)

    app.sw_show_offline = ctk.CTkSwitch(
        header_actions,
        text=app.tr("show_offline"),
        text_color=COLOR_TEXT,
        variable=app.show_offline,
        command=app.update_gui_data,
    )
    app.sw_show_offline.pack(side="right", padx=(10, 0))

    app.btn_toggle_devices_panel = CyberBtn(
        header_actions,
        text=app.tr("hide_panel"),
        command=app.toggle_devices_panel,
        width=150,
        font=FONT_SMALL,
    )
    app.btn_toggle_devices_panel.pack(side="right")

    split = ctk.CTkFrame(page, fg_color="transparent")
    split.pack(fill="both", expand=True)
    split.grid_columnconfigure(0, weight=1)
    split.grid_columnconfigure(1, weight=0, minsize=10)
    split.grid_columnconfigure(
        2,
        weight=0,
        minsize=int(app.settings.get("devices_panel_width", DEFAULT_SETTINGS["devices_panel_width"])),
    )
    split.grid_rowconfigure(0, weight=1)
    app.devices_split = split

    list_card = ctk.CTkFrame(
        split,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    list_card.grid(row=0, column=0, sticky="nsew")

    ctk.CTkLabel(list_card, text=app.tr("devices_title"), font=FONT_UI_BOLD, text_color=COLOR_TEXT).pack(
        anchor="w", padx=14, pady=(12, 2)
    )
    ctk.CTkLabel(list_card, text=app.tr("choose_device"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
        anchor="w", padx=14, pady=(0, 10)
    )

    app.device_list = ctk.CTkScrollableFrame(
        list_card,
        fg_color=COLOR_BG,
        corner_radius=4,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    app.device_list.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    app.devices_splitter = ctk.CTkFrame(
        split,
        fg_color=COLOR_BORDER,
        corner_radius=4,
        width=8,
        cursor="sb_h_double_arrow",
    )
    app.devices_splitter.grid(row=0, column=1, sticky="ns", padx=(0, 10))
    try:
        app.devices_splitter.bind("<ButtonPress-1>", app._start_devices_panel_resize)
        app.devices_splitter.bind("<B1-Motion>", app._on_devices_panel_resize)
        app.devices_splitter.bind("<ButtonRelease-1>", app._stop_devices_panel_resize)
    except Exception:
        pass

    panel = ctk.CTkScrollableFrame(
        split,
        fg_color=COLOR_PANEL,
        corner_radius=6,
        border_width=1,
        border_color=COLOR_BORDER,
    )
    panel.grid(row=0, column=2, sticky="nsew")
    app.devices_panel = panel

    ctk.CTkLabel(panel, text=app.tr("target"), font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM).pack(pady=(16, 4))
    app.lbl_target = ctk.CTkLabel(panel, text=app.tr("none"), font=FONT_UI_BOLD, text_color=COLOR_TEXT)
    app.lbl_target.pack(pady=(0, 4))
    app.lbl_target_status = ctk.CTkLabel(
        panel,
        text=app.tr("target_not_selected"),
        font=FONT_SMALL,
        text_color=COLOR_TEXT_DIM,
    )
    app.lbl_target_status.pack(pady=(0, 12))

    action_row = ctk.CTkFrame(panel, fg_color="transparent")
    action_row.pack(padx=18, fill="x", pady=(0, 8))
    action_row.grid_columnconfigure(0, weight=1)
    action_row.grid_columnconfigure(1, weight=1)

    app.btn_disconnect_selected = CyberBtn(
        action_row,
        text=app.tr("disconnect"),
        command=app.disconnect_selected_device,
        height=32,
        font=FONT_SMALL,
    )
    app.btn_disconnect_selected.grid(row=0, column=0, sticky="ew", padx=(0, 6))

    app.btn_delete_selected = CyberBtn(
        action_row,
        text=app.tr("delete"),
        command=app.delete_selected_device,
        height=32,
        font=FONT_SMALL,
        fg_color="transparent",
        border_color=COLOR_FAIL,
        text_color=COLOR_FAIL,
        hover_color=COLOR_PANEL_ALT,
    )
    app.btn_delete_selected.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    try:
        app.btn_disconnect_selected.configure(state="disabled", text_color=COLOR_TEXT_DIM)
        app.btn_delete_selected.configure(state="disabled", text_color=COLOR_TEXT_DIM)
    except Exception:
        pass

    ctk.CTkLabel(panel, text=app.tr("alias"), font=FONT_UI_BOLD, text_color=COLOR_TEXT_DIM).pack(pady=(8, 4))
    app.ent_alias = ctk.CTkEntry(
        panel,
        textvariable=app.var_device_alias,
        height=34,
        corner_radius=4,
        fg_color=COLOR_PANEL_ALT,
        border_color=COLOR_BORDER,
        text_color=COLOR_TEXT,
    )
    app.ent_alias.pack(padx=18, fill="x")

    transfer_body = _create_accordion(panel, app.tr("transfer"), ui, expanded=True)
    ctk.CTkLabel(transfer_body, text=app.tr("transfer_profile"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).pack(
        anchor="w", padx=14, pady=(12, 4)
    )
    app.opt_preset = ctk.CTkOptionMenu(
        transfer_body,
        values=DEFAULT_DEVICE_PRESETS,
        variable=app.var_transfer_preset,
        corner_radius=4,
        fg_color=COLOR_PANEL_ALT,
        button_color=COLOR_BORDER,
        button_hover_color=COLOR_PANEL,
        text_color=COLOR_TEXT,
        dropdown_fg_color=COLOR_PANEL,
        dropdown_hover_color=COLOR_PANEL_ALT,
        dropdown_text_color=COLOR_TEXT,
    )
    app.opt_preset.pack(padx=14, fill="x")

    adv = ctk.CTkFrame(transfer_body, fg_color="transparent")
    adv.pack(padx=14, pady=(10, 12), fill="x")
    adv.grid_columnconfigure(0, weight=1)
    adv.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(adv, text=app.tr("chunk_kb"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).grid(
        row=0, column=0, sticky="w"
    )
    ctk.CTkLabel(adv, text=app.tr("sleep_ms"), font=FONT_SMALL, text_color=COLOR_TEXT_DIM).grid(
        row=0, column=1, sticky="w", padx=(10, 0)
    )

    app.ent_chunk_kb = ctk.CTkEntry(
        adv,
        textvariable=app.var_transfer_chunk_kb,
        height=32,
        corner_radius=4,
        fg_color=COLOR_PANEL_ALT,
        border_color=COLOR_BORDER,
        text_color=COLOR_TEXT,
    )
    app.ent_chunk_kb.grid(row=1, column=0, sticky="ew", pady=(4, 0))

    app.ent_sleep_ms = ctk.CTkEntry(
        adv,
        textvariable=app.var_transfer_sleep_ms,
        height=32,
        corner_radius=4,
        fg_color=COLOR_PANEL_ALT,
        border_color=COLOR_BORDER,
        text_color=COLOR_TEXT,
    )
    app.ent_sleep_ms.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(4, 0))

    note_body = _create_accordion(panel, app.tr("note"), ui, expanded=False)
    app.ent_note = ctk.CTkEntry(
        note_body,
        textvariable=app.var_device_note,
        height=34,
        corner_radius=4,
        fg_color=COLOR_PANEL_ALT,
        border_color=COLOR_BORDER,
        text_color=COLOR_TEXT,
    )
    app.ent_note.pack(padx=14, pady=12, fill="x")

    perms_body = _create_accordion(panel, app.tr("permissions"), ui, expanded=False)
    ctk.CTkSwitch(perms_body, text=app.tr("perm_mouse"), text_color=COLOR_TEXT, variable=app.var_perm_mouse).pack(
        anchor="w", padx=14, pady=(12, 6)
    )
    ctk.CTkSwitch(perms_body, text=app.tr("perm_keyboard"), text_color=COLOR_TEXT, variable=app.var_perm_keyboard).pack(
        anchor="w", padx=14, pady=6
    )
    ctk.CTkSwitch(perms_body, text=app.tr("perm_stream"), text_color=COLOR_TEXT, variable=app.var_perm_stream).pack(
        anchor="w", padx=14, pady=6
    )
    ctk.CTkSwitch(perms_body, text=app.tr("perm_upload"), text_color=COLOR_TEXT, variable=app.var_perm_upload).pack(
        anchor="w", padx=14, pady=6
    )
    ctk.CTkSwitch(
        perms_body,
        text=app.tr("perm_file_send"),
        text_color=COLOR_TEXT,
        variable=app.var_perm_file_send,
    ).pack(anchor="w", padx=14, pady=6)
    ctk.CTkSwitch(perms_body, text=app.tr("perm_power"), text_color=COLOR_TEXT, variable=app.var_perm_power).pack(
        anchor="w", padx=14, pady=(6, 12)
    )

    for v in (
        app.var_device_alias,
        app.var_device_note,
        app.var_transfer_preset,
        app.var_transfer_chunk_kb,
        app.var_transfer_sleep_ms,
        app.var_perm_mouse,
        app.var_perm_keyboard,
        app.var_perm_upload,
        app.var_perm_file_send,
        app.var_perm_stream,
        app.var_perm_power,
    ):
        try:
            v.trace_add("write", app._on_device_setting_changed)
        except Exception:
            pass

    save_row = ctk.CTkFrame(panel, fg_color="transparent")
    save_row.pack(padx=18, pady=(12, 6), fill="x")
    save_row.grid_columnconfigure(0, weight=1)
    save_row.grid_columnconfigure(1, weight=1)

    app.btn_save_device_settings = CyberBtn(
        save_row,
        text=app.tr("save"),
        command=app.save_device_settings,
        fg_color=COLOR_ACCENT,
        text_color="#04110A",
        hover_color=COLOR_ACCENT_HOVER,
        border_color=COLOR_ACCENT,
    )
    app.btn_save_device_settings.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    app.btn_save_device_settings.configure(state="disabled")

    app.btn_reset_device_settings = CyberBtn(
        save_row,
        text=app.tr("reset"),
        command=app.reset_device_settings,
    )
    app.btn_reset_device_settings.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    app.btn_reset_device_settings.configure(state="disabled")

    app.lbl_device_dirty = ctk.CTkLabel(panel, text="", text_color=COLOR_WARN, font=FONT_SMALL)
    app.lbl_device_dirty.pack(padx=18, anchor="w")

    CyberBtn(panel, text=app.tr("send_file"), command=app.send_file, height=38).pack(
        padx=18, pady=(6, 14), fill="x"
    )

    app.lbl_status = ctk.CTkLabel(panel, text=app.tr("choose_device"), text_color=COLOR_TEXT_DIM, font=FONT_SMALL)
    app.lbl_status.pack(pady=(0, 16))

    app._apply_devices_panel_layout(persist=False)
