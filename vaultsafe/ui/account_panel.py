"""Chi tiết tài khoản và biểu mẫu thêm, sửa."""

from datetime import date
import re

import customtkinter as ctk

from .. import theme
from ..models import Account, ITEM_TYPES, REQUIRED_ACCOUNT_FIELDS, account_field_errors
from ..passwords import password_weak_reason


def detail_header(parent, account, on_edit, on_delete, *, on_favorite, on_restore, folder=""):
    summary = theme.card(parent, bg=theme.HEADER_SURFACE)
    summary.pack(fill="x", pady=(0, theme.SECTION_GAP))
    inset = theme.CARD_PADDING + 1
    identity = ctk.CTkFrame(summary, fg_color="transparent")
    identity.pack(fill="x", padx=inset, pady=(theme.CARD_PADDING, theme.FIELD_PADDING))
    if not account.trashed:
        star = theme.button(
            identity, "★" if account.favorite else "☆", on_favorite,
            kind="quiet", width=36, height=34, size=21, border_spacing=2,
        )
        star.configure(text_color=theme.WARNING if account.favorite else theme.MUTED)
        star.pack(side="right")
    theme.service_mark(identity, account.service).pack(side="left", padx=(0, theme.FIELD_PADDING))
    names = ctk.CTkFrame(identity, fg_color="transparent")
    names.pack(side="left", fill="x", expand=True)
    theme.ellipsized_label(names, account.service, size=theme.FONT_TITLE, bold=True,
                           height=28).pack(fill="x")
    metadata = [account.subtitle if account.kind == "login" else ITEM_TYPES[account.kind], folder]
    subtitle = "  ·  ".join(text for text in metadata if text)
    if subtitle:
        theme.ellipsized_label(
            names, subtitle, size=theme.FONT_META, color=theme.MUTED, height=20,
        ).pack(fill="x", pady=(4, 0))

    actions = ctk.CTkFrame(summary, fg_color="transparent")
    actions.pack(fill="x", padx=inset, pady=(0, theme.CARD_PADDING + 2))
    if account.trashed:
        theme.button(actions, "Khôi phục", on_restore, kind="primary", width=106,
                     icon_name="refresh").pack(side="left")
        return
    edit = theme.button(
        actions, "Chỉnh sửa", on_edit, kind="primary", width=104,
        height=theme.DETAIL_ACTION_HEIGHT, icon_name="edit", border_spacing=4,
    )
    edit.grid_propagate(False)
    edit.pack(side="left", padx=(0, theme.SPACING))
    delete = theme.button(
        actions, "Xóa", on_delete, kind="danger", width=58,
        height=theme.DETAIL_ACTION_HEIGHT, icon_name="delete", border_spacing=3,
    )
    delete.grid_propagate(False)
    delete.pack(side="left")


class AccountDetails(ctk.CTkFrame):
    def __init__(self, parent, account: Account, copy_text, *, copy_value=None, reused_reason=""):
        super().__init__(parent, fg_color="transparent")
        self.account = account
        self.copy_text = copy_text
        self.copy_value = copy_value or copy_text
        self.password_visible = False

        if account.kind == "login":
            self._login_details(reused_reason)
        elif account.kind in ("card", "identity"):
            self._other_details()
        if account.kind in ("login", "note") or account.notes:
            self._notes(account.notes, secure=account.kind == "note")

    def _login_details(self, reused_reason):
        account = self.account
        information = theme.card(self)
        information.pack(fill="x", pady=(0, theme.SECTION_GAP))
        self.status = theme.label(information, size=theme.FONT_META, anchor="w", height=18)
        self._value(information, "Tên đăng nhập / Email", account.username)
        theme.divider(information).pack(fill="x", padx=1)

        password_row = self.password_row = ctk.CTkFrame(information, fg_color="transparent")
        password_row.pack(
            fill="x", padx=theme.FIELD_PADDING + 1, pady=(theme.FIELD_PADDING, 10),
        )
        self.copy_button = theme.button(
            password_row, "Sao chép", self.copy_password, width=90, height=34, icon_name="copy",
        )
        self.copy_button.pack(side="right", padx=(6, 0))
        self.toggle_button = theme.button(
            password_row, "Hiện", self.toggle_password, width=65, height=34, icon_name="eye",
        )
        self.toggle_button.pack(side="right", padx=(theme.SPACING, 0))
        password_field = ctk.CTkFrame(password_row, fg_color="transparent")
        password_field.pack(side="left", fill="x", expand=True)
        strength_caption = ctk.CTkFrame(password_field, fg_color="transparent")
        strength_caption.pack(fill="x")
        theme.label(strength_caption, "Mật khẩu", size=theme.FONT_META,
                    color=theme.MUTED, height=17).pack(side="left")
        weak_reason = password_weak_reason(account.password)
        if not account.trashed:
            theme.label(
                strength_caption, "• Yếu" if weak_reason else "• Đạt tiêu chí mẫu",
                size=11, color=theme.WARNING if weak_reason else theme.SUCCESS, height=17, bold=True,
            ).pack(side="left", padx=(theme.SPACING, 0))
        self.password_label = theme.wrapped_label(
            password_field, theme.MASK * 12, family=theme.MONO, height=20,
        )
        self.password_label.pack(fill="x", pady=(2, 0))
        if not account.trashed:
            theme.strength_strip(information, theme.WARNING if weak_reason else theme.SUCCESS_BAR).pack(
                fill="x", padx=theme.FIELD_PADDING + 1, pady=(0, theme.FIELD_PADDING),
            )
            for reason in (weak_reason, reused_reason):
                if reason:
                    theme.wrapped_label(
                        information, reason, margin=2 * theme.FIELD_PADDING + 2,
                        size=theme.FONT_META, color=theme.WARNING, height=17,
                    ).pack(fill="x", padx=theme.FIELD_PADDING + 1, pady=(0, 7))
        theme.divider(information).pack(fill="x", padx=1)
        self._value(information, "Trang web", account.url, color=theme.ACCENT)

    def _other_details(self):
        account = self.account
        information = theme.card(self)
        information.pack(fill="x", pady=(0, theme.SECTION_GAP))
        self.status = theme.label(information, size=theme.FONT_META, anchor="w", height=18)
        if account.kind == "card":
            self._value(information, "Chủ thẻ mẫu", account.card_holder)
            theme.divider(information).pack(fill="x", padx=1)
            self._value(information, "Số thẻ giả", account.masked_card, copy=False)
            if account.card_expiry:
                theme.divider(information).pack(fill="x", padx=1)
                self._value(information, "Hạn mẫu", account.card_expiry)
            if account.card_security_code:
                theme.divider(information).pack(fill="x", padx=1)
                self._card_security_details(information, account.card_security_code)
        else:
            self._value(information, "Tên mẫu", account.identity_name)
            theme.divider(information).pack(fill="x", padx=1)
            self._value(information, "Liên hệ mẫu", account.identity_contact)

    def _card_security_details(self, parent, code):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        inset = theme.FIELD_PADDING
        row.pack(fill="x", padx=inset + 1, pady=inset)
        hidden = theme.MASK * len(code)
        value = theme.label(row, hidden, family=theme.MONO, anchor="w", height=20)

        def toggle():
            reveal = value.cget("text") == hidden
            value.configure(text=code if reveal else hidden)
            button.configure(text="Ẩn" if reveal else "Hiện", image=theme.icon("hide" if reveal else "eye"))

        button = theme.button(row, "Hiện", toggle, width=65, height=34, icon_name="eye")
        button.pack(side="right")
        self._caption(row, "Mã bảo mật mẫu")
        value.pack(fill="x", pady=(2, 0))

    def _notes(self, content, *, secure=False):
        notes = theme.card(self)
        notes.pack(fill="x")
        self._caption(notes, ITEM_TYPES["note"] if secure else "Ghi chú", padx=theme.FIELD_PADDING + 1,
                      pady=(theme.FIELD_PADDING, theme.SPACING))
        note_box = ctk.CTkFrame(notes, fg_color=theme.CONTROL, corner_radius=theme.CONTROL_RADIUS)
        note_box.pack(fill="x", padx=theme.FIELD_PADDING + 1, pady=(0, theme.FIELD_PADDING))
        theme.wrapped_label(
            note_box, content or "Chưa có", margin=28,
            color=theme.TEXT if content else theme.MUTED, height=30,
        ).pack(fill="x", padx=14, pady=9)

    @staticmethod
    def _caption(parent, title, **padding):
        theme.label(parent, title, anchor="w", size=theme.FONT_META, color=theme.MUTED,
                    height=17).pack(fill="x", **padding)

    def _value(self, parent, title, value, *, color=theme.TEXT, copy=True):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(
            fill="x", padx=theme.FIELD_PADDING + 1, pady=theme.FIELD_PADDING,
        )
        if value and copy:
            theme.button(
                row, "Chép", lambda: self._copy(value, row), width=65, height=32, icon_name="copy",
            ).pack(side="right", padx=(theme.SPACING, 0))
        field = ctk.CTkFrame(row, fg_color="transparent")
        field.pack(side="left", fill="x", expand=True)
        self._caption(field, title)
        theme.wrapped_label(
            field, value or "Chưa có", color=color if value else theme.MUTED, height=20,
        ).pack(fill="x", pady=(2, 0))

    def toggle_password(self):
        self.password_visible = not self.password_visible
        self.password_label.configure(
            text=self.account.password if self.password_visible else theme.MASK * 12,
        )
        self.toggle_button.configure(
            text="Ẩn" if self.password_visible else "Hiện",
            image=theme.icon("hide" if self.password_visible else "eye"),
        )

    def copy_password(self):
        self._copy(self.account.password, self.password_row, secret=True)

    def _copy(self, value, row, *, secret=False):
        copied = (self.copy_text if secret else self.copy_value)(value)
        success = "Đã sao chép mật khẩu." if secret else "Đã sao chép."
        self.status.configure(
            text=success if copied else "Không thể sao chép. Hãy thử lại.",
            text_color=theme.SUCCESS if copied else theme.ERROR,
        )
        self.status.pack(fill="x", padx=theme.FIELD_PADDING, pady=(0, 6), after=row)

    def destroy(self):
        self.account = None
        self.password_visible = False
        super().destroy()


class AccountForm(ctk.CTkFrame):
    FIELDS = {
        "login": (
            ("username", "Tên đăng nhập / Email"),
            ("password", "Mật khẩu"),
            ("url", "URL (không bắt buộc)"),
        ),
        "card": (("card_last_four", "Số thẻ mẫu"), ("card_expiry", "Ngày hết hạn"),
                 ("card_security_code", "Mã bảo mật"),
                 ("card_holder", "Tên trên thẻ mẫu")),
        "identity": (
            ("identity_name", "Tên mẫu"),
            ("identity_contact", "Liên hệ mẫu (không bắt buộc)"),
        ),
        "note": (),
    }

    @classmethod
    def values_from(cls, account):
        keys = [key for key, _ in cls.FIELDS[account.kind]]
        return {key: getattr(account, key)
                for key in ("service", "kind", "folder_id", "notes", *keys)}

    def __init__(self, parent, values, on_save, on_generate, folders):
        super().__init__(parent, fg_color="transparent")
        self.on_save = on_save
        self.on_generate = on_generate
        self.kind = values.get("kind", "login")
        self._drafts = {}
        self.kind_choices = {title: key for key, title in ITEM_TYPES.items()}
        self.folder_choices = {}

        choices = theme.card(self)
        choices.pack(fill="x", pady=(0, theme.SPACING))
        choices.grid_columnconfigure((0, 1), weight=1, uniform="item_choices")
        for column, title in enumerate(("Loại mục", "Thư mục")):
            theme.label(choices, title, size=theme.FONT_META, color=theme.MUTED, anchor="w",
                        height=18).grid(row=0, column=column, sticky="ew", padx=12, pady=(10, 3))
        self.kind_menu = self._option_menu(choices, list(self.kind_choices), self._switch_kind)
        self.kind_menu.set(ITEM_TYPES[self.kind])
        self.kind_menu.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.folder_menu = self._option_menu(choices, [""])
        self.folder_menu.grid(row=1, column=1, sticky="ew", padx=12, pady=(0, 12))
        self.set_folders(folders, folder_id=values.get("folder_id", ""))

        self.fields = theme.card(self)
        self.fields.pack(fill="x")
        self._build_fields(values)

    @staticmethod
    def _option_menu(parent, values, command=None, *, width=1):
        return ctk.CTkOptionMenu(
            parent, values=values, command=command, width=width, height=36, dynamic_resizing=False,
            fg_color=theme.CONTROL, button_color=theme.SECONDARY,
            button_hover_color=theme.SECONDARY_HOVER, text_color=theme.TEXT,
            dropdown_fg_color=theme.SURFACE, dropdown_hover_color=theme.SECONDARY,
            font=(theme.FONT, theme.FONT_BODY), dropdown_font=(theme.FONT, theme.FONT_BODY),
        )

    def set_folders(self, folders, *, folder_id=None):
        if folder_id is None:
            folder_id = self.folder_choices.get(self.folder_menu.get(), "")
        empty_label = "Không gán thư mục"
        while empty_label in folders.values():
            empty_label = "— " + empty_label
        self.folder_choices = {empty_label: "", **{name: key for key, name in folders.items()}}
        self.folder_menu.configure(values=list(self.folder_choices))
        self.folder_menu.set(folders.get(folder_id, empty_label))

    def _switch_kind(self, label):
        kind = self.kind_choices[label]
        if kind == self.kind:
            return
        current = self.read_fields()
        self._drafts[self.kind] = current
        self.kind = kind
        self._build_fields({**self._drafts.get(kind, {}),
                            "service": current["service"], "notes": current["notes"]})

    def _build_fields(self, values):
        fields = self.fields
        for child in fields.winfo_children():
            child.destroy()
        self.entries = {}
        self.errors = {}
        self.generate_button = None
        self.card_expiry = None
        padding = theme.CARD_PADDING + 1
        if self.kind == "card":
            self._build_card_fields(values, padding)
        else:
            self._build_standard_fields(values, padding)

        note_label = "Nội dung *" if self.kind == "note" else "Ghi chú (không bắt buộc)"
        self._field_label(note_label, padding)
        self.notes = ctk.CTkTextbox(
            fields, height=102,
            fg_color=theme.CONTROL, text_color=theme.TEXT,
            border_color=theme.INPUT_BORDER, border_width=1, corner_radius=theme.CONTROL_RADIUS,
            scrollbar_button_color=theme.SCROLL_THUMB, wrap="word", font=(theme.FONT, theme.FONT_BODY),
        )
        self.notes.pack(fill="x", padx=padding, pady=(0, padding))
        self.notes.insert("1.0", values.get("notes", ""))
        self.note_error = theme.label(fields, size=12, color=theme.ERROR, anchor="w", height=18)

    def _field_label(self, title, padding, *, top=15):
        theme.label(self.fields, title, anchor="w", size=theme.FONT_META, color=theme.MUTED,
                    height=16).pack(fill="x", padx=padding, pady=(top, 6))

    def _add_entry(self, key, field, values, *, validate_optional=False):
        value = values.get(key, "")
        if value:
            field.insert(0, value)
        self.entries[key] = field
        if validate_optional or key in REQUIRED_ACCOUNT_FIELDS[self.kind]:
            self.errors[key] = theme.label(self.fields, size=12, color=theme.ERROR, anchor="w", height=18)

    def _build_standard_fields(self, values, padding):
        fields = self.fields
        title = "Tên dịch vụ" if self.kind == "login" else "Tiêu đề"
        required = REQUIRED_ACCOUNT_FIELDS[self.kind]
        for index, (key, title) in enumerate((("service", title), *self.FIELDS[self.kind])):
            self._field_label(f"{title} *" if key in required else title, padding,
                              top=padding if index == 0 else 15)
            if key == "password":
                password_row = self.password_row = ctk.CTkFrame(fields, fg_color="transparent")
                password_row.pack(fill="x", padx=padding)
                field = theme.entry(password_row, show=theme.MASK, family=theme.MONO)
                field.pack(side="left", fill="x", expand=True, padx=(0, theme.SPACING))
                self.generate_button = theme.button(
                    password_row, "Tạo mật khẩu", lambda: self.on_generate(self.read_fields()),
                    kind="accent", icon_name="key", width=122, height=38,
                )
                self.generate_button.pack(side="right")
            else:
                field = theme.entry(fields)
                field.pack(fill="x", padx=padding)
            self._add_entry(key, field, values)

    def _build_card_fields(self, values, padding):
        self._field_label("Số thẻ mẫu *", padding, top=padding)
        digits = theme.entry(self.fields)
        digits.configure(validate="key", validatecommand=(digits.register(_card_digits), "%P"))
        digits.pack(fill="x", padx=padding)
        self._add_entry("card_last_four", digits, values)
        theme.label(self.fields, "Chỉ nhập 4 số cuối giả.", size=theme.FONT_META, color=theme.MUTED,
                    anchor="w", height=16).pack(fill="x", padx=padding, pady=(4, 0))

        self._field_label("Ngày hết hạn (không bắt buộc)", padding)
        self.card_expiry = CardExpiry(self.fields, values.get("card_expiry", ""), self._option_menu)
        self.card_expiry.pack(fill="x", padx=padding)

        self._field_label("Mã bảo mật (không bắt buộc)", padding)
        code = theme.entry(self.fields, width=100, show=theme.MASK, family=theme.MONO)
        code.configure(validate="key", validatecommand=(code.register(_card_digits), "%P"))
        code.pack(anchor="w", padx=padding)
        self._add_entry("card_security_code", code, values, validate_optional=True)
        theme.label(self.fields, "Chỉ nhập 3 hoặc 4 chữ số mẫu.", size=theme.FONT_META, color=theme.MUTED,
                    anchor="w", height=16).pack(fill="x", padx=padding, pady=(4, 0))

        for key, title in (("card_holder", "Tên trên thẻ mẫu *"), ("service", "Biệt hiệu của thẻ *")):
            self._field_label(title, padding)
            entry = theme.entry(self.fields)
            entry.pack(fill="x", padx=padding)
            self._add_entry(key, entry, values)

    def focus_first_field(self):
        self.entries[next(iter(self.entries))].focus_set()

    def read_fields(self):
        values = {key: field.get() for key, field in self.entries.items()}
        if self.card_expiry is not None:
            values["card_expiry"] = self.card_expiry.get()
        return values | {
            "notes": self.notes.get("1.0", "end-1c"),
            "kind": self.kind,
            "folder_id": self.folder_choices[self.folder_menu.get()],
        }

    def destroy(self):
        self._drafts.clear()
        super().destroy()

    def save(self):
        values = self.read_fields()
        first_invalid = None
        errors = account_field_errors(self.kind, values)
        for key, error in self.errors.items():
            message = errors.get(key)
            entry = self.entries[key]
            entry.configure(border_color=theme.ERROR if message else theme.INPUT_BORDER)
            if message:
                error.configure(text=message)
                error.pack(fill="x", padx=theme.CARD_PADDING + 1,
                           after=self.password_row if key == "password" else entry)
            else:
                error.pack_forget()
            if message and first_invalid is None:
                first_invalid = entry
        if "notes" in errors:
            self.note_error.configure(text=errors["notes"])
            self.note_error.pack(fill="x", padx=theme.CARD_PADDING + 1, pady=(0, 12))
            if first_invalid is None:
                first_invalid = self.notes
        else:
            self.note_error.pack_forget()
        if self.card_expiry is not None and not self.card_expiry.validate():
            if first_invalid is None:
                self.card_expiry.focus_missing()
            else:
                first_invalid.focus_set()
            return
        if first_invalid is not None:
            first_invalid.focus_set()
            return
        self.on_save(values)


def _card_digits(value):
    return not value or len(value) <= 4 and value.isascii() and value.isdigit()


class CardExpiry(ctk.CTkFrame):
    """Chọn tháng và năm, giữ chuỗi ngày cũ cho tới khi người dùng đổi giá trị."""

    MONTH = "Tháng"
    YEAR = "Năm"

    def __init__(self, parent, previous, option_menu):
        super().__init__(parent, fg_color="transparent")
        parsed = re.fullmatch(r"(0?[1-9]|1[0-2])\s*/\s*([0-9]{2}|[0-9]{4})", previous.strip())
        self._previous = previous
        self._initial = (self.MONTH, self.YEAR)
        start_year = date.today().year
        years = {str(year) for year in range(start_year, start_year + 16)}
        if parsed:
            month, year = parsed.groups()
            year = "20" + year if len(year) == 2 else year
            self._initial = (month.zfill(2), year)
            years.add(year)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x")
        self.month = option_menu(row, [self.MONTH, *(f"{n:02}" for n in range(1, 13))], width=94)
        self.year = option_menu(row, [self.YEAR, *sorted(years)], width=108)
        self.month.set(self._initial[0])
        self.year.set(self._initial[1])
        self.month.pack(side="left", padx=(0, theme.SPACING))
        self.year.pack(side="left")

        if previous and not parsed:
            self.legacy = ctk.CTkFrame(self, fg_color="transparent")
            self.legacy.pack(fill="x", pady=(6, 0))
            theme.wrapped_label(self.legacy, f"Hạn đã lưu: {theme.short_text(previous, 50)}",
                                margin=4, size=theme.FONT_META, color=theme.MUTED).pack(fill="x")
            theme.button(self.legacy, "Bỏ hạn cũ", self._clear_legacy, kind="quiet", height=26).pack(anchor="w")
        self.error = theme.label(self, "Chọn cả tháng và năm, hoặc để trống cả hai.", size=12,
                                 color=theme.ERROR, anchor="w")

    def _clear_legacy(self):
        self._previous = ""
        self.legacy.pack_forget()

    def get(self):
        month, year = selection = (self.month.get(), self.year.get())
        if selection == self._initial:
            return self._previous
        if month != self.MONTH and year != self.YEAR:
            return f"{month}/{year}"
        return ""

    def validate(self):
        incomplete = (self.month.get() == self.MONTH) != (self.year.get() == self.YEAR)
        if incomplete:
            self.error.pack(fill="x", pady=(4, 0))
        else:
            self.error.pack_forget()
        return not incomplete

    def focus_missing(self):
        (self.month if self.month.get() == self.MONTH else self.year).focus_set()
