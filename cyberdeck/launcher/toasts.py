import customtkinter as ctk


class ToastManager:
    def __init__(
        self,
        app,
        *,
        color_panel: str,
        color_border: str,
        color_accent: str,
        color_fail: str,
        color_text: str,
        font_small,
    ):
        """Initialize ToastManager state and collaborator references."""
        self.app = app
        self.color_panel = color_panel
        self.color_border = color_border
        self.color_accent = color_accent
        self.color_fail = color_fail
        self.color_text = color_text
        self.font_small = font_small
        self.items = []

    def show(self, message: str, level: str = "info", duration_ms: int = 2600):
        """Show a toast notification in the launcher window."""
        if not message:
            return

        palette = {
            "info": {"fg": self.color_panel, "border": self.color_border},
            "success": {"fg": "#123328", "border": self.color_accent},
            "error": {"fg": "#3A1C1C", "border": self.color_fail},
        }
        style = palette.get(level, palette["info"])

        toast = ctk.CTkFrame(
            self.app,
            fg_color=style["fg"],
            corner_radius=10,
            border_width=1,
            border_color=style["border"],
        )
        ctk.CTkLabel(
            toast,
            text=str(message),
            text_color=self.color_text,
            font=self.font_small,
            justify="left",
            wraplength=360,
        ).pack(padx=10, pady=8)

        self.items.append(toast)
        while len(self.items) > 4:
            old = self.items.pop(0)
            try:
                old.destroy()
            except Exception:
                pass

        self.reposition()
        self.app._safe_after(duration_ms, lambda t=toast: self.dismiss(t))

    def reposition(self):
        """Reposition visible toast widgets after stack changes."""
        y = 14
        for toast in self.items:
            try:
                toast.update_idletasks()
                h = max(1, int(toast.winfo_reqheight()))
                toast.place(relx=1.0, x=-20, y=y, anchor="ne")
                y += h + 8
            except Exception:
                pass

    def dismiss(self, toast):
        """Dismiss the visible element."""
        try:
            if toast in self.items:
                self.items.remove(toast)
            try:
                toast.place_forget()
            except Exception:
                pass
            toast.destroy()
            self.reposition()
        except Exception:
            pass
