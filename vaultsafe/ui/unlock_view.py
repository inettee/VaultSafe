"""Tạo hồ sơ và mở khóa kho mã hóa."""

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from .. import recovery_key, theme
from ..errors import VaultError
from ..vault_service import MASTER_PASSWORD_HINT, PROFILE_NAME_HINT, profile_creation_errors
from .unlock_background import BACKGROUND, UnlockViewport


COMPACT_LOGO_SIZE = 40
COMPACT_FIELD_WIDTH = 272


class UnlockView(ctk.CTkFrame):
    def __init__(self, app, preferred_profile_id=None):
        super().__init__(app, fg_color=BACKGROUND, corner_radius=0)
        self.app = app
        self.preferred_profile_id = preferred_profile_id
        self.busy = False
        self._compact = False
        self._controls = []
        self._rows = []

        self.viewport = UnlockViewport(self, self._resize_form)
        branding = self.viewport.branding
        self.logo = None
        if app.unlock_logo:
            width, height = app.unlock_logo.cget("size")
            factor = COMPACT_LOGO_SIZE / max(width, height)
            self.compact_logo = ctk.CTkImage(
                light_image=app.unlock_logo.cget("light_image"),
                size=(round(width * factor), round(height * factor)),
            )
            self.logo = ctk.CTkLabel(branding, image=app.unlock_logo, text="", width=96,
                                     height=theme.UNLOCK_LOGO_SIZE)
            self.logo.pack()
        self.title_label = theme.label(branding, "VaultSafe", size=31, bold=True)
        self.title_label.pack(pady=(2, 6))
        self.badge = theme.label(
            branding, "Kho mã hóa cục bộ", size=12, color=theme.ACCENT,
            fg_color=theme.NAV_SELECTED, corner_radius=theme.CONTROL_RADIUS, height=26, padx=12,
        )
        self.badge.pack(pady=(0, 15))
        self.form = theme.card(self.viewport.content, bg=theme.HEADER_SURFACE)
        self.form.pack()
        self.show_unlock()
        self.viewport.pack(fill="both", expand=True, padx=(theme.SCROLLBAR_WIDTH, 0))

    def _resize_form(self, compact):
        self._compact = compact
        if self.logo is not None:
            self.logo.configure(image=self.compact_logo if compact else self.app.unlock_logo,
                                width=58 if compact else 96,
                                height=COMPACT_LOGO_SIZE if compact else theme.UNLOCK_LOGO_SIZE)
        self.title_label.configure(font=(theme.FONT, 24 if compact else 31, "bold"))
        self.title_label.pack(pady=(0, 1) if compact else (2, 6))
        self.badge.configure(height=20 if compact else 26)
        self.badge.pack(pady=(0, 3 if compact else 15))
        for widget, normal, small in self._controls:
            widget.configure(**(small if compact else normal))
        for widget, row, padding in self._rows:
            if widget.winfo_manager():
                self._place_row(widget, row, padding)

    def _track_control(self, widget):
        if isinstance(widget, ctk.CTkFrame):
            for control in widget.pack_slaves():
                self._track_control(control)
            return
        height = widget.cget("height")
        normal = {"height": height}
        minimum = 16 if isinstance(widget, ctk.CTkLabel) else 26
        small = {"height": max(minimum, round(height * .73))}
        if widget.cget("width") == 336:
            normal["width"], small["width"] = 336, COMPACT_FIELD_WIDTH
        if isinstance(widget, ctk.CTkLabel) and widget.cget("wraplength") == 336:
            normal["wraplength"], small["wraplength"] = 336, COMPACT_FIELD_WIDTH
        self._controls.append((widget, normal, small))
        if self._compact:
            widget.configure(**small)

    def _place_row(self, widget, row, padding):
        if self._compact:
            padding = tuple(round(side * .38) for side in padding)
        widget.grid(row=row, column=0, sticky="ew", padx=20, pady=padding)

    def _form_grid(self, widget, row, pady=(0, 0)):
        self._track_control(widget)
        if any(pady):
            self._rows.append((widget, row, pady))
        self._place_row(widget, row, pady)

    def _prepare_form(self, title):
        self.submit_button = None
        self.busy_controls = []
        self._controls.clear()
        self._rows.clear()
        for child in self.form.winfo_children():
            child.destroy()
        self._form_grid(theme.label(self.form, title, size=20, bold=True, anchor="w"), 0, (13, 8))
        self.viewport.scroll_to_top()

    def _field(self, title, row, *, secret=False):
        label = theme.label(self.form, title, size=13, bold=True, anchor="w", height=19)
        self._form_grid(label, row, (2, 2))
        field = theme.entry(self.form, width=336, height=34, show=theme.MASK if secret else "")
        self._form_grid(field, row + 1)
        return field

    def _error(self, row):
        error = theme.label(self.form, size=12, color=theme.ERROR, anchor="w",
                            justify="left", wraplength=336, height=17)
        self._form_grid(error, row)
        error.grid_remove()
        return error

    @staticmethod
    def _show_error(label, message):
        label.configure(text=message)
        if message:
            label.grid()
        else:
            label.grid_remove()

    def show_unlock(self, notice=""):
        self.creating = False
        self.recovering = False
        self.recovery_path = None
        try:
            profiles = self.app.list_profiles()
        except VaultError as error:
            self._start_screen("Không đọc được kho", str(error), "Thử lại", self.show_unlock)
            return
        if not profiles:
            self._start_screen("Bắt đầu với VaultSafe", "Tạo hồ sơ để mở kho đầu tiên.",
                               "Tạo hồ sơ", self.show_create)
            return
        self._prepare_form("Mở khóa kho")
        self.profile_ids = {profile.name: profile.id for profile in profiles}
        initial_name = next((profile.name for profile in profiles
                             if profile.id == self.preferred_profile_id), profiles[0].name)
        self.preferred_profile_id = self.profile_ids[initial_name]

        label = theme.label(self.form, "Hồ sơ", size=13, bold=True, anchor="w", height=19)
        self._form_grid(label, 1, (5, 3))
        self.profile_menu = ctk.CTkOptionMenu(
            self.form, values=list(self.profile_ids), command=self._change_profile,
            width=336, height=38, corner_radius=theme.CONTROL_RADIUS,
            dynamic_resizing=False, fg_color=theme.CONTROL,
            button_color=theme.SECONDARY, button_hover_color=theme.SECONDARY_HOVER,
            text_color=theme.TEXT, dropdown_fg_color=theme.SURFACE,
            dropdown_hover_color=theme.SECONDARY, dropdown_text_color=theme.TEXT,
            font=(theme.FONT, 14), dropdown_font=(theme.FONT, 14),
        )
        self.profile_menu.set(initial_name)
        self._form_grid(self.profile_menu, 2)

        caption = ctk.CTkFrame(self.form, fg_color="transparent")
        theme.label(caption, "Mật khẩu chính", size=13, bold=True, anchor="w", height=19).pack(side="left")
        recovery = theme.button(caption, "Quên mật khẩu?", self.show_recovery,
                                kind="quiet", width=106, height=23, size=12)
        recovery.pack(side="right")
        self._form_grid(caption, 3, (9, 3))
        row = ctk.CTkFrame(self.form, fg_color="transparent")
        self.password = theme.entry(row, show=theme.MASK)
        self.password.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.toggle_button = theme.button(row, "Hiện", self._toggle_password, width=62)
        self.toggle_button.pack(side="right")
        self._form_grid(row, 4)
        self.password_error = self._error(5)
        if notice:
            self._form_grid(theme.label(self.form, notice, size=12, color=theme.SUCCESS, anchor="w"), 6)
        self.submit_button = theme.button(self.form, "Mở khóa", self.submit, kind="primary")
        self._form_grid(self.submit_button, 7, (12, 4))
        create = theme.button(self.form, "Tạo hồ sơ", self.show_create, kind="quiet")
        self._form_grid(create, 8, (0, 7))
        guide = theme.button(self.form, "Hướng dẫn nhanh", self.app.tour.start, kind="quiet")
        self._form_grid(guide, 9, (0, 7))
        self.busy_controls = [self.profile_menu, self.password, self.toggle_button, recovery, create, guide]
        self.password.focus_set()

    def _start_screen(self, title, message, action, command):
        self._prepare_form(title)
        label = theme.label(self.form, message, color=theme.MUTED, anchor="w", justify="left",
                            wraplength=336, width=336)
        self._form_grid(label, 1, (2, 10))
        self._form_grid(theme.button(self.form, action, command, kind="primary"), 2, (0, 17))
        if action == "Tạo hồ sơ":
            guide = theme.button(self.form, "Hướng dẫn nhanh", self.app.tour.start, kind="quiet")
            self._form_grid(guide, 3, (0, 9))
            restore = theme.button(self.form, "Khôi phục bản sao", self.app.show_backup_restore, kind="quiet")
            self._form_grid(restore, 4, (0, 9))

    def _change_profile(self, name):
        self.preferred_profile_id = self.profile_ids[name]
        self.password.delete(0, "end")
        self.password.configure(show=theme.MASK)
        self.toggle_button.configure(text="Hiện")
        self._show_error(self.password_error, "")
        self.password.focus_set()

    def _toggle_password(self):
        visible = bool(self.password.cget("show"))
        self.password.configure(show="" if visible else theme.MASK)
        self.toggle_button.configure(text="Ẩn" if visible else "Hiện")

    def show_create(self):
        self.creating = True
        self.recovering = False
        self._prepare_form("Tạo hồ sơ")
        hint = theme.label(
            self.form, PROFILE_NAME_HINT + "\n" + MASTER_PASSWORD_HINT,
            size=12, color=theme.MUTED, anchor="w", justify="left",
        )
        self._form_grid(hint, 1, (0, 7))
        self.profile_name = self._field("Tên hồ sơ", 2)
        self.name_error = self._error(4)
        self.new_password = self._field("Mật khẩu chính", 5, secret=True)
        self.new_password_error = self._error(7)
        self.confirmation = self._field("Xác nhận mật khẩu", 8, secret=True)
        self.confirmation_error = self._error(10)
        self.creation_error = self._error(11)
        actions = ctk.CTkFrame(self.form, fg_color="transparent")
        back = theme.button(actions, "Quay lại", self.show_unlock, width=145)
        back.pack(side="left")
        self.submit_button = theme.button(actions, "Tạo hồ sơ", self.submit, kind="primary", width=133)
        self.submit_button.pack(side="right")
        self._form_grid(actions, 12, (8, 10))
        self.busy_controls = [self.profile_name, self.new_password, self.confirmation, back]
        self.profile_name.focus_set()

    def show_recovery(self):
        name = self.profile_menu.get()
        self.preferred_profile_id = self.profile_ids[name]
        self.recovering = True
        self.recovery_path = None
        self._prepare_form("Đặt lại mật khẩu chính")
        info = theme.label(self.form, f"Hồ sơ · {name}\nChọn tệp .vaultkey đã lưu cho hồ sơ này.",
                           size=12, color=theme.MUTED, anchor="w", justify="left", wraplength=336)
        self._form_grid(info, 1, (0, 6))
        choose = theme.button(self.form, "Chọn tệp khóa", self._choose_recovery_file)
        self._form_grid(choose, 2, (0, 4))
        self.key_status = theme.label(self.form, "Chưa xác thực tệp khóa.", size=12, color=theme.MUTED,
                                      anchor="w", justify="left", wraplength=336)
        self._form_grid(self.key_status, 3, (0, 4))
        self.new_password = self._field("Mật khẩu chính mới", 4, secret=True)
        self.confirmation = self._field("Xác nhận mật khẩu mới", 6, secret=True)
        self.recovery_error = self._error(8)
        actions = ctk.CTkFrame(self.form, fg_color="transparent")
        back = theme.button(actions, "Quay lại", self.show_unlock, width=110)
        back.pack(side="left")
        self.submit_button = theme.button(actions, "Đặt lại mật khẩu", self.submit, kind="primary", width=146)
        self.submit_button.pack(side="right")
        self._form_grid(actions, 9, (8, 10))
        self.busy_controls = [choose, self.new_password, self.confirmation, back]
        self._set_busy(False)

    def _choose_recovery_file(self):
        path = filedialog.askopenfilename(parent=self, title="Chọn tệp khóa khôi phục của hồ sơ",
                                          filetypes=recovery_key.FILE_TYPE)
        if not path or not self.winfo_exists():
            return
        self.recovery_path = None
        self._show_error(self.recovery_error, "")
        self.key_status.configure(text="Đang xác thực tệp khóa…", text_color=theme.MUTED)
        self._set_busy(True)

        def checked(_result, error):
            self.recovery_path = None if error else path
            self._set_busy(False)
            self.key_status.configure(text=error or "Đã xác thực tệp khóa. Bạn có thể đặt mật khẩu mới.",
                                      text_color=theme.ERROR if error else theme.SUCCESS)
            if not error:
                self.new_password.focus_set()

        self.app.run_auth(self.app.service.verify_recovery_file, (self.preferred_profile_id, path), checked)

    def _reset_password(self):
        if self.recovery_path is None:
            return
        password, confirmation = self.new_password.get(), self.confirmation.get()
        errors = profile_creation_errors("Hồ sơ", password, confirmation)[1:]
        error = next((message for message in errors if message), "")
        self._show_error(self.recovery_error, error)
        if error:
            return
        self._set_busy(True)

        def reset(_result, failure):
            self._set_busy(False)
            if failure:
                self._show_error(self.recovery_error, failure)
            else:
                self.show_unlock("Đã đổi mật khẩu chính. Hãy mở kho bằng mật khẩu mới.")

        args = (self.preferred_profile_id, self.recovery_path, password, confirmation)
        self.app.run_auth(self.app.service.reset_master_password, args, reset)

    def submit(self):
        if self.busy or self.submit_button is None:
            return
        if self.creating:
            self._create_profile()
            return
        if self.recovering:
            self._reset_password()
            return
        profile_id = self.profile_ids[self.profile_menu.get()]
        password = self.password.get()
        if not password:
            self._show_error(self.password_error, "Nhập mật khẩu chính.")
            return
        self._show_error(self.password_error, "")
        self.password.delete(0, "end")
        self.password.configure(show=theme.MASK)
        self.toggle_button.configure(text="Hiện")
        self._set_busy(True)
        self.app.run_auth(self.app.service.open_profile, (profile_id, password), self._opened)

    def _opened(self, session, error):
        self._set_busy(False)
        if error:
            self._show_error(self.password_error, error)
            self.password.focus_set()
        else:
            self.app.open_session(session)

    def _create_profile(self):
        name = self.profile_name.get()
        password = self.new_password.get()
        confirmation = self.confirmation.get()
        name_error, password_error, confirmation_error = profile_creation_errors(name, password, confirmation)
        self._show_error(self.creation_error, "")
        self._show_error(self.name_error, name_error)
        self._show_error(self.new_password_error, password_error)
        self._show_error(self.confirmation_error, confirmation_error)
        if not any((name_error, password_error, confirmation_error)):
            path = filedialog.asksaveasfilename(
                parent=self, title="Lưu tệp khóa khôi phục ở nơi an toàn", initialdir=str(Path.home()),
                initialfile=recovery_key.filename(name), defaultextension=recovery_key.SUFFIX,
                filetypes=recovery_key.FILE_TYPE, confirmoverwrite=False,
            )
            if not path or not self.winfo_exists():
                return
            self._set_busy(True)
            self.app.run_auth(self.app.service.create_profile, (name, password, confirmation, path), self._created)

    def _created(self, profile, error):
        self._set_busy(False)
        if error:
            self._show_error(self.creation_error, error)
        else:
            self.preferred_profile_id = profile.id
            self.show_unlock("Đã lưu tệp khóa. Nhập mật khẩu để mở kho.")

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in self.busy_controls:
            widget.configure(state=state)
        label = "Tạo hồ sơ" if self.creating else "Đặt lại mật khẩu" if self.recovering else "Mở khóa"
        self.submit_button.configure(state=state, text="Đang xử lý…" if busy else label)
        if self.recovering and self.recovery_path is None:
            for widget in (self.new_password, self.confirmation, self.submit_button):
                widget.configure(state="disabled")
