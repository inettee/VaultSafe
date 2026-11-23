"""Tạo bản sao mã hóa và xác nhận khôi phục vào hồ sơ mới."""

from functools import partial
from pathlib import Path
from tkinter import TclError, filedialog

import customtkinter as ctk

from .. import theme
from ..recovery_key import SUFFIX as RECOVERY_SUFFIX
from ..vault_backup import BACKUP_PASSWORD_ERROR, EXTENSION, export_backup, preview_backup, restore_backup


BACKUP_FILES = (("Bản sao VaultSafe", f"*{EXTENSION}"),)
OPEN_FILES = (*BACKUP_FILES, ("Tất cả tệp", "*"))


class BackupView(ctk.CTkFrame):
    def __init__(self, parent, app, session=None, on_restored=None):
        super().__init__(parent, fg_color="transparent")
        self._app, self._session, self._on_restored = app, session, on_restored
        self._active, self._busy = True, False
        self._backup_path = None
        self._preview = None
        self._reveal_timer = None
        self._buttons = []
        self.status = theme.wrapped_label(self, "", margin=32, color=theme.MUTED, height=20)
        self.status.pack(fill="x", padx=theme.FIELD_PADDING, pady=(0, theme.SPACING))
        if session is not None:
            export = self._card(f"Sao lưu hồ sơ · {session.profile.name}")
            self.export_password = self._field(export, "Mật khẩu bản sao (12–128 ký tự)", secret=True)
            self.export_confirmation = self._field(export, "Nhập lại mật khẩu bản sao", secret=True)
            self.export_button = self._button(export, "Tạo tệp sao lưu", self.export)

        restore = self._card("Khôi phục vào hồ sơ mới")
        file_row = ctk.CTkFrame(restore, fg_color="transparent")
        file_row.pack(fill="x", padx=theme.FIELD_PADDING, pady=(0, 7))
        self.choose_button = theme.button(file_row, "Chọn tệp", self.choose_file, width=90)
        self.choose_button.pack(side="right", padx=(theme.SPACING, 0))
        self._buttons.append(self.choose_button)
        self.file_label = theme.wrapped_label(file_row, "Chưa chọn tệp .vaultsafe", margin=100,
                                              color=theme.MUTED, size=theme.FONT_META, width=1)
        self.file_label.pack(side="left", fill="x", expand=True)
        self.backup_password = self._field(restore, "Mật khẩu của tệp bản sao", secret=True)
        self.restore_status = self._status_line(restore)
        self.preview_button = self._button(restore, "Xem trước", self.preview)
        self.preview_button.configure(state="disabled")
        self.restore_card = self._card("Hồ sơ sau khi khôi phục", visible=False)
        self.preview_summary = theme.wrapped_label(self.restore_card, "", margin=32, color=theme.MUTED)
        self.preview_summary.pack(fill="x", padx=theme.FIELD_PADDING, pady=(0, 8))
        self.new_name = self._field(self.restore_card, "Tên hồ sơ mới")
        self.new_password = self._field(self.restore_card, "Mật khẩu chính cho hồ sơ mới", secret=True)
        self.new_confirmation = self._field(self.restore_card, "Nhập lại mật khẩu chính", secret=True)
        self.confirm_status = self._status_line(self.restore_card)
        self.restore_button = self._button(self.restore_card, "Khôi phục hồ sơ", self.restore)

    def _card(self, title, *, visible=True):
        card = theme.card(self)
        if visible:
            card.pack(fill="x", pady=(0, theme.SECTION_GAP))
        theme.wrapped_label(card, title, margin=32, bold=True, size=16).pack(
            fill="x", padx=theme.FIELD_PADDING, pady=(theme.FIELD_PADDING, 7),
        )
        return card

    def _field(self, card, title, *, secret=False):
        theme.label(card, title, anchor="w").pack(fill="x", padx=theme.FIELD_PADDING, pady=(2, 0))
        entry = theme.entry(card, height=36, show=theme.MASK if secret else "")
        entry.pack(fill="x", padx=theme.FIELD_PADDING, pady=(0, 7))
        return entry

    def _button(self, card, text, command):
        button = theme.button(card, text, command, kind="primary", width=158)
        button.pack(anchor="e", padx=theme.FIELD_PADDING, pady=(2, theme.FIELD_PADDING))
        self._buttons.append(button)
        return button

    @staticmethod
    def _status_line(card):
        line = theme.wrapped_label(card, "", margin=2 * theme.FIELD_PADDING, size=theme.FONT_META)
        line.pack(fill="x", padx=theme.FIELD_PADDING)
        return line

    def _notify(self, text, color=theme.MUTED, *, label=None):
        target = self.status if label is None else label
        target.configure(text=text, text_color=color)

    def _run(self, operation, args, complete, *, label=None):
        for button in self._buttons:
            button.configure(state="disabled")
        self._busy = True
        self._notify("Đang xử lý…", label=label)

        def finish(result, error):
            if not self._active:
                return
            self._busy = False
            for button in self._buttons:
                button.configure(state="normal")
            if self._backup_path is None:
                self.preview_button.configure(state="disabled")
            if error:
                self._notify(error, theme.WARNING, label=label)
            else:
                complete(result)

        self._app.run_auth(operation, args, finish)

    def export(self):
        if not self._active or self._busy:
            return
        password = self.export_password.get()
        if not 12 <= len(password) <= 128 or not password.strip():
            self._notify(BACKUP_PASSWORD_ERROR, theme.WARNING)
            return
        if password != self.export_confirmation.get():
            self._notify("Mật khẩu bản sao nhập lại chưa khớp.", theme.WARNING)
            return
        try:
            path = filedialog.asksaveasfilename(parent=self.winfo_toplevel(), defaultextension=EXTENSION,
                                                filetypes=BACKUP_FILES, confirmoverwrite=False)
        except TclError:
            return
        if path and self._active:
            self.export_password.delete(0, "end")
            self.export_confirmation.delete(0, "end")
            self._run(export_backup, (self._app.service, self._session, path, password),
                      lambda _: self._notify("Đã tạo tệp sao lưu mã hóa.", theme.SUCCESS))

    def choose_file(self):
        if not self._active or self._busy:
            return
        try:
            path = filedialog.askopenfilename(parent=self.winfo_toplevel(), title="Chọn tệp sao lưu VaultSafe",
                                             filetypes=OPEN_FILES)
        except TclError:
            if self._active:
                self._notify("Không mở được hộp thoại chọn tệp.", theme.WARNING, label=self.restore_status)
            return
        if not path or not self._active:
            return
        self._discard_preview()
        self._backup_path = None
        self.preview_button.configure(state="disabled")
        if Path(path).suffix.lower() == RECOVERY_SUFFIX:
            self._show_filename("Chưa chọn tệp .vaultsafe")
            self._notify("Tệp .vaultkey dùng để đặt lại mật khẩu chính. Hãy chọn bản sao .vaultsafe.",
                         theme.WARNING, label=self.restore_status)
            return
        self._backup_path = path
        self._show_filename(f"Đã chọn {Path(path).name}")
        self.preview_button.configure(state="normal")
        self._notify("Nhập mật khẩu của bản sao, rồi bấm Xem trước.", label=self.restore_status)
        self.backup_password.focus_set()

    def _show_filename(self, text):
        self.file_label.configure(text=theme.short_text(text, 52))

    def preview(self):
        if not self._active or self._busy or self._backup_path is None:
            return
        password = self.backup_password.get()
        if not 12 <= len(password) <= 128 or not password.strip():
            message = "Nhập mật khẩu đã đặt khi tạo bản sao." if not password.strip() else BACKUP_PASSWORD_ERROR
            self._notify(message, theme.WARNING, label=self.restore_status)
            self.backup_password.focus_set()
            return
        self.backup_password.delete(0, "end")
        self._discard_preview()
        self._run(preview_backup, (self._backup_path, password), self._show_preview, label=self.restore_status)

    def _show_preview(self, preview):
        self._preview = preview
        self.preview_summary.configure(text=f"Bản sao hồ sơ {preview.name} · {preview.item_count} mục")
        self.new_name.insert(0, f"{preview.name[:48]} (khôi phục)")
        self.restore_card.pack(fill="x", pady=(0, theme.SECTION_GAP))
        self._notify("Đã xác thực bản sao. Đặt tên và mật khẩu chính cho hồ sơ mới.", label=self.restore_status)
        self._reveal_timer = self.after_idle(self._reveal_preview)

    def _reveal_preview(self):
        self._reveal_timer = None
        if self._preview is not None:
            pane = self.master
            while pane is not None and not isinstance(pane, theme.ScrollPane):
                pane = pane.master
            if pane is not None:
                pane.reveal(self.new_name)
            self.new_name.focus_set()

    def restore(self):
        if not self._active or self._busy or self._preview is None:
            return
        name, password, confirmation = self.new_name.get(), self.new_password.get(), self.new_confirmation.get()
        self.new_password.delete(0, "end")
        self.new_confirmation.delete(0, "end")

        def saved(info):
            self._discard_preview()
            self._notify(f"Đã khôi phục vào hồ sơ {info.name}.", theme.SUCCESS, label=self.restore_status)
            if self._on_restored is not None:
                self._on_restored(info)

        self._run(partial(restore_backup, session=self._session),
                  (self._app.service, self._preview, name, password, confirmation), saved, label=self.confirm_status)

    def _discard_preview(self):
        self._preview = None
        self.restore_card.pack_forget()
        self._notify("", label=self.confirm_status)
        for entry in (self.new_name, self.new_password, self.new_confirmation):
            entry.delete(0, "end")

    def destroy(self):
        self._active = False
        self._backup_path = None
        self._preview = None
        if self._reveal_timer is not None:
            self.after_cancel(self._reveal_timer)
        super().destroy()
