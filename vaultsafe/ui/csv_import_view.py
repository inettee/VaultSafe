"""Xem trước và nhập mục Đăng nhập từ CSV vào kho đang mở."""

from tkinter import filedialog, TclError

import customtkinter as ctk

from .. import theme
from ..csv_import import read_login_csv
from ..errors import ConflictError, SessionClosedError, VaultError


PREVIEW_LIMIT = 12


class CsvImportView(ctk.CTkFrame):
    def __init__(self, parent, service, session, on_imported):
        super().__init__(parent, fg_color="transparent")
        self._service = service
        self._session = session
        self._on_imported = on_imported
        self._plan = None
        self._active = True

        controls = theme.card(self)
        controls.pack(fill="x")
        inset = theme.FIELD_PADDING
        destination = f"Hồ sơ đích · {session.profile.name}"
        theme.wrapped_label(controls, destination, margin=2 * inset, bold=True).pack(
            fill="x", padx=inset, pady=(inset, 4),
        )
        theme.wrapped_label(
            controls, "Chọn tệp CSV xuất từ Chrome hoặc Bitwarden. Tệp gốc chứa mật khẩu dạng văn bản.",
            margin=2 * inset, color=theme.MUTED,
        ).pack(fill="x", padx=inset, pady=(0, 12))
        actions = ctk.CTkFrame(controls, fg_color="transparent")
        actions.pack(fill="x", padx=inset)
        self.choose_button = theme.button(actions, "Chọn tệp CSV", self.choose, width=105)
        self.choose_button.pack(side="left")
        self.import_button = theme.button(actions, "Nhập vào kho", self.confirm, kind="primary",
                                          width=115, state="disabled")
        self.import_button.pack(side="left", padx=(theme.SPACING, 0))
        self.status = theme.wrapped_label(controls, "Xem trước các mục trước khi nhập.", margin=2 * inset,
                                          color=theme.MUTED, size=theme.FONT_META)
        self.status.pack(fill="x", padx=inset, pady=(8, inset))
        self.preview = ctk.CTkFrame(self, fg_color="transparent")
        self.preview.pack(fill="x", pady=(theme.SECTION_GAP, 0))

    def choose(self):
        try:
            path = filedialog.askopenfilename(parent=self, title="Chọn tệp CSV đăng nhập",
                                             filetypes=(("Tệp CSV", "*.csv"),))
        except TclError:
            if self._active:
                self._set_status("Không mở được hộp thoại chọn tệp CSV.", theme.WARNING)
            return
        if not path or not self._active:
            return
        self._clear_preview()
        try:
            self._session.versioned_profile()
            self._plan = self._service.preview_csv_import(self._session, read_login_csv(path))
        except VaultError as error:
            self._set_status(str(error), theme.WARNING)
            return
        self._render_preview(self._plan)

    def _render_preview(self, plan):
        self._set_status(f"Nguồn {plan.format} · {len(plan.accounts)} mục sẵn sàng nhập")
        card = theme.card(self.preview)
        card.pack(fill="x")
        inset = theme.FIELD_PADDING
        summary = f"{plan.duplicates} mục trùng · {plan.invalid} dòng không hợp lệ · {plan.unsupported} loại chưa hỗ trợ"
        theme.wrapped_label(card, summary, margin=2 * inset, color=theme.MUTED).pack(
            fill="x", padx=inset, pady=(inset, 6),
        )
        if not plan.accounts:
            theme.label(card, "Không có mục mới để nhập.").pack(anchor="w", padx=inset, pady=(0, inset))
            return
        for item in plan.accounts[:PREVIEW_LIMIT]:
            label = f"{_preview_text(item.service)} · {_preview_text(item.username)}"
            theme.wrapped_label(card, label, margin=2 * inset).pack(fill="x", padx=inset, pady=(0, 4))
        if len(plan.accounts) > PREVIEW_LIMIT:
            theme.label(card, f"Và {len(plan.accounts) - PREVIEW_LIMIT} mục khác…", color=theme.MUTED).pack(
                anchor="w", padx=inset, pady=(0, 4),
            )
        ctk.CTkFrame(card, height=inset, fg_color="transparent").pack(fill="x")
        self.import_button.configure(state="normal")

    def confirm(self):
        if not self._active or self._plan is None or not self._plan.accounts:
            return
        try:
            count = self._service.import_csv_logins(self._session, self._plan)
        except (ConflictError, SessionClosedError) as error:
            self._clear_preview()
            self._set_status(str(error), theme.WARNING)
            return
        except VaultError as error:
            self._set_status(str(error), theme.WARNING)
            return
        self._clear_preview()
        self._set_status(f"Đã nhập {count} mục vào kho.", theme.SUCCESS)
        self._on_imported()

    def _clear_preview(self):
        self._plan = None
        self.import_button.configure(state="disabled")
        for child in self.preview.winfo_children():
            child.destroy()

    def _set_status(self, text, color=theme.MUTED):
        self.status.configure(text=text, text_color=color)

    def destroy(self):
        self._active = False
        self._plan = None
        super().destroy()


def _preview_text(value):
    return theme.short_text(" ".join(value.split()), 65)
