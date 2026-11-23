"""Tạo mật khẩu và tùy chọn điền kết quả vào biểu mẫu."""

import string
import tkinter as tk

import customtkinter as ctk

from .. import theme
from ..passwords import generate_password, password_weak_reason


MIN_LENGTH = 8
MAX_LENGTH = 64
DEFAULT_LENGTH = 16
CHARACTER_GROUPS = (
    ("Chữ hoa", string.ascii_uppercase),
    ("Chữ thường", string.ascii_lowercase),
    ("Chữ số", string.digits),
    ("Ký tự đặc biệt", "!@#$%^&*()-_=+[]{}?"),
)


class GeneratorView(ctk.CTkFrame):
    def __init__(self, parent, copy_text, on_use=None):
        super().__init__(parent, fg_color="transparent")
        self.copy_text = copy_text
        self.on_use = on_use
        self.password = ""
        self.length = DEFAULT_LENGTH
        self.groups = {}

        result = theme.card(self, bg=theme.HEADER_SURFACE)
        result.pack(fill="x", pady=(0, theme.SECTION_GAP))
        padding = theme.CARD_PADDING + 1
        display = ctk.CTkFrame(result, fg_color=theme.CONTROL, corner_radius=theme.CONTROL_RADIUS)
        display.pack(fill="x", padx=padding, pady=(padding, 12))
        actions = ctk.CTkFrame(display, fg_color="transparent")
        actions.pack(side="right", padx=(theme.SPACING, 12), pady=12)
        theme.button(
            actions, "Tạo lại", self.generate, width=73, icon_name="refresh",
        ).pack(side="left", padx=(0, 6))
        self.copy_button = theme.button(
            actions, "Sao chép", self.copy_password, kind="primary", width=91, icon_name="copy",
        )
        self.copy_button.pack(side="right")
        value = ctk.CTkFrame(display, fg_color="transparent")
        value.pack(side="left", fill="x", expand=True, padx=(theme.FIELD_PADDING, 0), pady=12)
        self.output = theme.wrapped_label(
            value, "", family=theme.MONO, size=20, bold=True, height=52,
        )
        self.output.pack(fill="x")

        assessment = ctk.CTkFrame(result, fg_color="transparent")
        assessment.pack(fill="x", padx=padding, pady=(0, 5))
        theme.label(
            assessment, "Đánh giá độ mạnh", color=theme.MUTED, size=theme.FONT_META, height=17,
        ).pack(side="left")
        self.strength = theme.label(assessment, size=theme.FONT_META, bold=True, height=17)
        self.strength.pack(side="right")
        self.bar = theme.strength_strip(result)
        self.bar.pack(fill="x", padx=padding, pady=(0, padding))
        self.status = theme.label(result, size=theme.FONT_META, anchor="w", height=18)
        if on_use is not None:
            self.use_button = theme.button(
                result, "Dùng mật khẩu này", self.use_password, kind="primary", width=148,
            )
            self.use_button.pack(anchor="w", padx=padding, pady=(0, padding))
        else:
            self.use_button = None

        options = theme.card(self)
        options.pack(fill="x")
        length_row = ctk.CTkFrame(options, fg_color="transparent")
        length_row.pack(fill="x", padx=padding, pady=(padding, 0))
        theme.label(length_row, "Độ dài mật khẩu", bold=True, height=24).pack(side="left")
        self.length_label = theme.label(
            length_row, color=theme.ACCENT, family=theme.MONO, bold=True, height=24, padx=9,
            fg_color=theme.SELECTED, corner_radius=theme.SPACING,
        )
        self.length_label.pack(side="right")
        self.slider = ctk.CTkSlider(
            options, from_=MIN_LENGTH, to=MAX_LENGTH, number_of_steps=MAX_LENGTH - MIN_LENGTH,
            progress_color=theme.SCROLL_THUMB, button_color=theme.PRIMARY_HOVER,
            button_hover_color=theme.ACCENT, fg_color=theme.SCROLL_THUMB, command=self._change_length,
        )
        self.slider.set(DEFAULT_LENGTH)
        self.slider.pack(fill="x", padx=padding, pady=(14, 0))

        scale_labels = ctk.CTkFrame(options, fg_color="transparent", height=16)
        scale_labels.pack(fill="x", padx=padding, pady=(2, theme.SECTION_GAP))
        for tick in (MIN_LENGTH, 24, 44, MAX_LENGTH):
            position = (tick - MIN_LENGTH) / (MAX_LENGTH - MIN_LENGTH)
            anchor = "w" if tick == MIN_LENGTH else "e" if tick == MAX_LENGTH else "center"
            theme.label(
                scale_labels, str(tick), family=theme.MONO, size=11, color=theme.SUBTLE, height=16,
            ).place(relx=position, rely=0.5, anchor=anchor)

        checks = ctk.CTkFrame(options, fg_color="transparent")
        checks.pack(fill="x", padx=padding, pady=(0, padding))
        checks.grid_columnconfigure((0, 1), weight=1, uniform="character_groups")
        for index, (name, characters) in enumerate(CHARACTER_GROUPS):
            enabled = tk.BooleanVar(self, value=True)
            self.groups[characters] = enabled
            cell = ctk.CTkFrame(
                checks, fg_color=theme.CONTROL, border_width=1, border_color=theme.BORDER,
                height=44, corner_radius=theme.CONTROL_RADIUS,
            )
            cell.grid(row=index // 2, column=index % 2, sticky="ew",
                      padx=(0, 6) if index % 2 == 0 else (6, 0), pady=(0, 8))
            cell.pack_propagate(False)
            check = ctk.CTkCheckBox(
                cell, text="", variable=enabled, command=self.generate,
                fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, border_color=theme.MUTED,
                checkbox_width=16, checkbox_height=16, width=16, height=18, border_width=1,
            )
            check.pack(side="right", padx=(4, 10))
            caption = theme.label(cell, name, size=13, height=20, anchor="w")
            caption.pack(side="left", padx=(10, 0))
            caption.bind("<Button-1>", lambda event, checkbox=check: checkbox.toggle())
        self.generate()

    def _change_length(self, value):
        self.length = round(value)
        self.generate()

    def generate(self):
        self.length_label.configure(text=f"{self.length} ký tự")
        groups = [characters for characters, enabled in self.groups.items() if enabled.get()]
        self.status.pack_forget()
        try:
            self.password = generate_password(self.length, groups)
        except ValueError as error:
            self.password = ""
            self._set_status(str(error), theme.ERROR)
        self.output.configure(text=self.password or "—")
        if self.password:
            weak = bool(password_weak_reason(self.password))
            self.strength.configure(
                text="Mật khẩu yếu" if weak else "Đạt tiêu chí mẫu",
                text_color=theme.WARNING if weak else theme.SUCCESS,
            )
            self.bar.configure(fg_color=theme.WARNING if weak else theme.SUCCESS_BAR)
        else:
            self.strength.configure(text="—", text_color=theme.MUTED)
            self.bar.configure(fg_color=theme.SECONDARY)
        state = "normal" if self.password else "disabled"
        self.copy_button.configure(state=state)
        if self.use_button is not None:
            self.use_button.configure(state=state)

    def _set_status(self, text, color):
        self.status.configure(text=text, text_color=color)
        self.status.pack(fill="x", padx=theme.CARD_PADDING + 1, pady=(0, 10),
                         after=self.bar)

    def copy_password(self):
        if self.copy_text(self.password):
            self._set_status("Đã sao chép mật khẩu.", theme.SUCCESS)
        else:
            self._set_status("Không thể sao chép. Hãy thử lại.", theme.ERROR)

    def use_password(self):
        if self.password and self.on_use is not None:
            self.on_use(self.password)

    def destroy(self):
        self.password = ""
        self.on_use = None
        super().destroy()
