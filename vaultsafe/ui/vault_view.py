"""Điều hướng, danh sách và nội dung kho."""

from functools import partial
from time import monotonic
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

from .. import recovery_key, theme
from ..errors import VaultError
from ..link_checker import SavedSite
from ..models import ITEM_TYPES
from ..passwords import audit_accounts
from ..session_protection import CLIPBOARD_SECONDS, IDLE_MINUTES, SecurityPreferences
from .account_panel import AccountDetails, AccountForm, detail_header
from .audit_view import AuditView
from .backup_view import BackupView
from .csv_import_view import CsvImportView
from .generator_view import GeneratorView
from .link_checker_view import LinkCheckerView


FILTERS = {
    "all": ("Tất cả mục", "vault"),
    "favorites": ("Mục yêu thích", "favorite"),
    "trash": ("Thùng rác", "delete"),
}
ALL_ITEMS = ("filter", "all")


class VaultView(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app, fg_color=theme.BACKGROUND, corner_radius=0)
        self.app = app
        self.session = app.session
        self.page = "vault"
        self.active_filter = ALL_ITEMS
        self.account_form = None
        self.account_details = None
        self.audit_view = None
        self.fixed_sidebar = None
        self.menu_open = False
        self._scrim = None
        self._menu_timer = None
        self._menu_progress = 0.0
        self._previous_focus = None
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)

        self._build_sidebar()
        self._build_list_column()
        for column in (self.sidebar, self.list_column):
            theme.divider(column, vertical=True).place(
                relx=1, rely=0, relheight=1, anchor="ne",
            )
        self.panel = ctk.CTkFrame(self, fg_color=theme.BACKGROUND, corner_radius=0)
        self.panel.grid(row=0, column=2, sticky="nsew")
        self.panel_header = ctk.CTkFrame(self.panel, fg_color="transparent")
        self.panel_header.pack(fill="x")
        self.panel_scroll = theme.ScrollPane(self.panel, theme.BACKGROUND)
        self.panel_scroll.pack(fill="both", expand=True)
        self.write_status = theme.wrapped_label(self.panel, "", margin=36, size=theme.FONT_META)
        self.panel_body = None
        self.showing_account = False
        tk.Widget.bind(self.panel, "<Configure>", self._resize_panel, add="+")
        tk.Widget.bind(self, "<Configure>", self._resize_layout, add="+")
        self.show_detail()

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self, fg_color=theme.SIDEBAR, corner_radius=0, width=theme.SIDEBAR_WIDTH,
        )
        self.sidebar.pack_propagate(False)
        tk.Widget.bind(self.sidebar, "<Button>", self._check_drawer_click)
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(16, theme.MENU_GROUP_GAP))
        self.close_button = theme.button(
            brand, "×", self.close_menu, kind="quiet",
            width=theme.MENU_BUTTON_SIZE, height=theme.MENU_BUTTON_SIZE, size=20,
        )
        self.close_button.grid_propagate(False)
        if self.app.sidebar_logo:
            ctk.CTkLabel(
                brand, text="", image=self.app.sidebar_logo,
                width=36, height=theme.SIDEBAR_LOGO_SIZE,
            ).pack(side="left", padx=(0, 10))
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left")
        theme.label(brand_text, "VaultSafe", size=16, bold=True, height=20, anchor="w").pack(fill="x")
        theme.label(
            brand_text, "●  Kho đã mở khóa", color=theme.SUCCESS, size=11, height=14,
        ).pack(anchor="w")

        footer = ctk.CTkFrame(self.sidebar, fg_color=theme.SIDEBAR_FOOT, corner_radius=0)
        footer.pack(side="bottom", fill="x")
        theme.divider(footer).pack(fill="x")
        self.profile_panel = profile_panel = ctk.CTkFrame(footer, fg_color="transparent")
        profile_panel.pack(fill="x", padx=theme.MENU_INSET, pady=(8, 12))
        theme.label(
            profile_panel, "HỒ SƠ", size=11, color=theme.MUTED, anchor="w", height=16,
        ).pack(fill="x", padx=8)
        theme.label(
            profile_panel, theme.short_text(self.session.profile.name, 42), size=14, bold=True,
            anchor="w", justify="left", wraplength=195,
        ).pack(fill="x", padx=8)
        profile_actions = ctk.CTkFrame(profile_panel, fg_color="transparent")
        profile_actions.pack(fill="x", padx=4, pady=(6, 0))
        theme.button(
            profile_actions, "Đổi hồ sơ", self.app.show_unlock, width=91, height=31,
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.lock_button = theme.button(
            profile_actions, "Khóa kho", self.app.show_unlock, kind="quiet", width=83, height=31,
        )
        self.lock_button.pack(side="right", fill="x", expand=True)

        self.sidebar_scroll = theme.ScrollPane(self.sidebar, theme.SIDEBAR)
        self.sidebar_scroll.pack(fill="both", expand=True, padx=(0, 1))
        self.nav_buttons = {}
        self.filter_buttons = {}
        self.organize_panel = ctk.CTkFrame(self.sidebar_scroll.content, fg_color="transparent")
        self.organize_panel.pack(fill="x", padx=(6, 2))
        filters = self._menu_group("BỘ LỌC", parent=self.organize_panel)
        for key, (title, icon_name) in FILTERS.items():
            self._filter_button(filters, ("filter", key), title, icon_name)
        kinds = self._menu_group("LOẠI MỤC", parent=self.organize_panel)
        for key, title in ITEM_TYPES.items():
            self._filter_button(kinds, ("kind", key), title, key)
        folders = self._menu_group("THƯ MỤC", self._create_folder, parent=self.organize_panel)
        self.folder_buttons = ctk.CTkFrame(folders, fg_color="transparent", height=1)
        self.folder_buttons.pack(fill="x")
        self._refresh_folder_buttons()
        tools = self._menu_group("CÔNG CỤ BẢO MẬT")
        self._nav_button(tools, "generator", "Trình tạo mật khẩu", self.show_generator, "key")
        self._nav_button(tools, "audit", "Kiểm tra an toàn", self.show_audit, "audit")
        self._nav_button(tools, "link_checker", "Kiểm tra link đăng nhập", self.show_link_checker, "search")
        theme.button(tools, "Hướng dẫn nhanh", self.app.tour.start, kind="quiet", anchor="w",
                     border_spacing=7, height=theme.MENU_ROW_HEIGHT).pack(fill="x", pady=1)
        data = self._menu_group("QUẢN LÝ KHO")
        self._nav_button(data, "security_preferences", "Bảo vệ phiên", self.show_security_preferences, "audit")
        self._nav_button(data, "backup", "Sao lưu và khôi phục", self.show_backup, "vault")
        self._nav_button(data, "csv_import", "Nhập tài khoản CSV", self.show_csv_import, "folder")

    def _menu_group(self, title, on_add=None, *, parent=None):
        group = ctk.CTkFrame(parent or self.sidebar_scroll.content, fg_color="transparent")
        inset = (theme.MENU_INSET, 4) if parent is None else (theme.MENU_INSET - 6, 2)
        group.pack(fill="x", padx=inset, pady=(0, theme.MENU_GROUP_GAP))
        header = ctk.CTkFrame(group, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(0, 4))
        theme.label(header, title, size=11, color=theme.MUTED, height=20).pack(side="left")
        if on_add:
            theme.button(header, "+", on_add, kind="quiet", width=27, height=22, size=16,
                         border_spacing=2).pack(side="right")
        return group

    def _filter_button(self, parent, key, title, icon_name):
        choose = partial(self._choose_filter, key)
        button = theme.button(
            parent, theme.short_text(title, 22), choose, kind="quiet", anchor="w",
            width=1, height=theme.MENU_ROW_HEIGHT, border_spacing=7,
            icon_name=icon_name, icon_color=theme.ACCENT,
        )
        button.pack(fill="x", pady=1)
        count = theme.label(
            button, size=11, color=theme.MUTED, width=theme.MENU_COUNT_WIDTH,
            height=18, corner_radius=5,
        )
        count.place(relx=1, x=-10, rely=.5, anchor="e")
        count.bind("<Button-1>", lambda event: choose())
        self.filter_buttons[key] = button, count

    def _refresh_folder_buttons(self):
        for key in tuple(self.filter_buttons):
            if key[0] == "folder":
                del self.filter_buttons[key]
        for child in self.folder_buttons.winfo_children():
            child.destroy()
        for key, name in self.session.profile.folders.items():
            self._filter_button(self.folder_buttons, ("folder", key), name, "folder")

    def _create_folder(self):
        self.close_menu(animate=False)
        name = simpledialog.askstring("Tạo thư mục", "Tên thư mục mới", parent=self.app)
        if name is None:
            return
        try:
            self.app.service.create_folder(self.session, name)
        except VaultError as error:
            self._write_message(str(error), theme.ERROR)
            return
        self._refresh_folder_buttons()
        self._refresh_menu()
        if self.account_form is not None:
            self.account_form.set_folders(self.session.profile.folders)
        self._write_message("Đã tạo thư mục.", theme.SUCCESS)

    def _nav_button(self, parent, page, title, command, icon_name):
        def navigate():
            self.close_menu(animate=False)
            if self.page != page:
                command()

        item = theme.button(
            parent, title, navigate, kind="quiet", anchor="w", border_spacing=7,
            icon_name=icon_name, icon_color=theme.SUCCESS if page == "audit" else theme.ACCENT,
            radius=theme.SPACING, height=theme.MENU_ROW_HEIGHT,
        )
        item.pack(fill="x", pady=1)
        self.nav_buttons[page] = item

    def scroll_drawer(self, event):
        pane = self.sidebar_scroll
        x, y = pane.winfo_rootx(), pane.winfo_rooty()
        if x <= event.x_root < x + pane.winfo_width() and y <= event.y_root < y + pane.winfo_height():
            pane.scroll_by(-int(event.delta / 120) * 3)
        return "break"

    def _resize_layout(self, event):
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        fixed = event.width / scale >= theme.FIXED_SIDEBAR_MIN_WIDTH
        if fixed == self.fixed_sidebar:
            self.position_scrim()
            return
        self._finish_menu()
        self.fixed_sidebar = fixed
        if fixed:
            self.sidebar.grid(row=0, column=0, sticky="ns")
            self.menu_button.pack_forget()
            self.close_button.pack_forget()
        else:
            self.sidebar.grid_remove()
            self.menu_button.pack(
                side="left", padx=(0, theme.SPACING), before=self.search_box,
            )
            self.close_button.pack(side="right")
        self.list_column.configure(width=theme.LIST_WIDTH if fixed else theme.COMPACT_LIST_WIDTH)

    @property
    def menu_modal(self):
        return self._scrim is not None

    def open_menu(self):
        if self.fixed_sidebar or self.menu_open:
            return
        self.menu_open = True
        if not self.menu_modal:
            self._previous_focus = self.focus_get()
            self._scrim = tk.Toplevel(self.app, bg=theme.SCRIM, takefocus=False)
            self._scrim.withdraw()
            self._scrim.overrideredirect(True)
            self._scrim.transient(self.app)
            self._scrim.attributes("-alpha", theme.SCRIM_OPACITY)
            self._scrim.bind("<Button>", self._dismiss_menu)
            self._scrim.bind("<Escape>", self._dismiss_menu)
            self._scrim.bind("<MouseWheel>", lambda event: "break")
            self._place_drawer()
            self._scrim.deiconify()
            self._scrim.lift()
            self.sidebar.grab_set()
            self.sidebar.focus_force()
        self._animate_menu(1.0)

    def _dismiss_menu(self, event):
        self.close_menu()
        return "break"

    def _check_drawer_click(self, event):
        right_edge = self.sidebar.winfo_rootx() + self.sidebar.winfo_width()
        if self.menu_modal and event.x_root >= right_edge:
            return self._dismiss_menu(event)

    def close_menu(self, *, animate=True):
        if not self.menu_modal:
            return
        if not animate:
            self._finish_menu()
        elif self.menu_open:
            self.menu_open = False
            self._animate_menu(0.0)

    def _animate_menu(self, target):
        self._cancel_menu_timer()
        start = self._menu_progress
        started_at = monotonic()
        duration = theme.MENU_SLIDE_MS * abs(target - start) / 1000

        def advance():
            self._menu_timer = None
            progress = min(1.0, (monotonic() - started_at) / duration) if duration else 1.0
            self._menu_progress = start + (target - start) * (1 - (1 - progress) ** 3)
            if progress == 1.0 and target == 0.0:
                self._finish_menu()
                return
            self._place_drawer()
            if progress < 1.0:
                self._menu_timer = self.after(theme.MENU_FRAME_MS, advance)
            elif self.menu_modal:
                self._scrim.lift()
                self.sidebar.focus_force()

        advance()

    def _place_drawer(self):
        offset = round((self._menu_progress - 1) * theme.SIDEBAR_WIDTH)
        self.sidebar.place(x=offset, y=0, relheight=1)
        self.sidebar.lift()
        self.position_scrim()

    def position_scrim(self):
        if not self.menu_modal:
            return
        # Tk dùng kích thước thực tế của client cho cửa sổ phủ bán trong suốt.
        scale = ctk.ScalingTracker.get_widget_scaling(self.sidebar)
        offset = round((self._menu_progress - 1) * theme.SIDEBAR_WIDTH)
        exposed = round(theme.SIDEBAR_WIDTH * scale) + round(offset * scale)
        width = max(1, self.winfo_width() - exposed)
        x = self.winfo_rootx() + exposed
        geometry = f"{width}x{self.winfo_height()}+{x}+{self.winfo_rooty()}"
        if self._scrim.geometry() != geometry:
            self._scrim.geometry(geometry)

    def set_tour_dim(self, active):
        if self._scrim is not None:
            # Keep the drawer's input shield while the tour handles the darkening.
            self._scrim.attributes("-alpha", 0.01 if active else theme.SCRIM_OPACITY)

    def _cancel_menu_timer(self):
        if self._menu_timer is not None:
            self.after_cancel(self._menu_timer)
            self._menu_timer = None

    def _finish_menu(self, *, restore_focus=True):
        self._cancel_menu_timer()
        if not self.menu_modal:
            return
        if self.grab_current() == self.sidebar:
            self.sidebar.grab_release()
        self.sidebar.place_forget()
        self._scrim.destroy()
        self._scrim = None
        self.menu_open = False
        self._menu_progress = 0.0
        focus, self._previous_focus = self._previous_focus, None
        if restore_focus and focus is not None and focus.winfo_exists():
            focus.focus_set()

    def _build_list_column(self):
        self.list_column = ctk.CTkFrame(
            self, fg_color=theme.LIST_BACKGROUND, corner_radius=0, width=theme.LIST_WIDTH,
        )
        self.list_column.grid(row=0, column=1, sticky="ns")
        self.list_column.pack_propagate(False)

        toolbar = ctk.CTkFrame(self.list_column, fg_color=theme.TOOLBAR, corner_radius=0)
        toolbar.pack(fill="x")
        actions = ctk.CTkFrame(toolbar, fg_color="transparent")
        padding = theme.TOOLBAR_PADDING
        actions.pack(fill="x", padx=(padding, padding + 1), pady=padding)
        self.add_button = add_button = theme.button(
            actions, "+", self.show_form, kind="primary", width=theme.SEARCH_BUTTON_SIZE,
            height=theme.SEARCH_BUTTON_SIZE, size=18,
        )
        add_button.grid_propagate(False)
        add_button.pack(side="right", padx=(theme.SPACING, 0))
        self.menu_button = theme.button(
            actions, "" if theme.icon("menu", theme.MUTED) else "≡", self.open_menu,
            width=theme.MENU_BUTTON_SIZE, height=theme.SEARCH_BUTTON_SIZE, icon_name="menu",
        )
        self.menu_button.grid_propagate(False)
        self.search_box = search_box = ctk.CTkFrame(
            actions, height=theme.SEARCH_FIELD_HEIGHT, fg_color=theme.BACKGROUND, border_width=1,
            border_color=theme.INPUT_BORDER, corner_radius=theme.CONTROL_RADIUS,
        )
        search_box.pack(side="left", fill="x", expand=True)
        search_box.pack_propagate(False)
        search_icon = theme.icon("search", theme.MUTED, 13)
        search_symbol = theme.label(
            search_box, "" if search_icon else "⌕", image=search_icon,
            width=25, height=25, color=theme.MUTED,
        )
        search_symbol.pack(side="left", padx=(5, 0))
        self.search = tk.StringVar(self)
        self.search_entry = theme.entry(
            search_box, textvariable=self.search, bg=theme.BACKGROUND, border_width=0, radius=0,
        )
        self.search_entry.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=3)
        self.search_hint = theme.label(
            self.search_entry, "Tìm trong két bảo mật...", color=theme.SUBTLE, height=22,
            fg_color=theme.BACKGROUND,
        )
        self.search_hint.bind("<Button-1>", lambda event: self.search_entry.focus_set())
        search_symbol.bind("<Button-1>", lambda event: self.search_entry.focus_set())
        self.search_entry.bind("<FocusIn>", self._focus_search)
        self.search_entry.bind("<FocusOut>", self._blur_search)
        self._search_focused = False
        self._show_search_hint()
        theme.divider(toolbar).pack(fill="x")

        heading = ctk.CTkFrame(self.list_column, fg_color="transparent")
        heading.pack(fill="x", padx=(theme.FIELD_PADDING, theme.FIELD_PADDING + 1), pady=10)
        self.list_title = theme.label(
            heading, "TẤT CẢ MỤC", size=theme.FONT_META, bold=True,
            color=theme.MUTED, height=16,
        )
        self.list_title.pack(side="left")
        self.result_count = theme.label(heading, size=theme.FONT_META, color=theme.SUBTLE, height=16)
        self.result_count.pack(side="right")
        theme.divider(self.list_column).pack(fill="x")

        self.list_scroll = theme.ScrollPane(self.list_column, theme.LIST_BACKGROUND)
        self.list_scroll.pack(fill="both", expand=True, padx=(theme.SPACING, 1), pady=(theme.SPACING, 0))
        self._search_trace = self.search.trace_add("write", self._search_changed)

    def _focus_search(self, event):
        self._search_focused = True
        self._show_search_hint()

    def _blur_search(self, event):
        self._search_focused = False
        self._show_search_hint()

    def _show_search_hint(self):
        if self.search.get() or self._search_focused:
            self.search_hint.place_forget()
        else:
            self.search_hint.place(x=1, rely=0.5, anchor="w")

    def destroy(self):
        self._finish_menu(restore_focus=False)
        self.search.trace_remove("write", self._search_trace)
        self.account_form = None
        super().destroy()

    @property
    def accounts(self):
        return self.session.profile.accounts

    def _matches_search(self, account):
        query = self.search.get().strip().casefold()
        return any(query in value.casefold() for value in (account.service, account.subtitle))

    @staticmethod
    def _matches_filter(account, selection):
        group, key = selection
        if selection == ("filter", "trash"):
            return account.trashed
        if account.trashed:
            return False
        if group == "kind":
            return account.kind == key
        if group == "folder":
            return account.folder_id == key
        return key != "favorites" or account.favorite

    def _is_visible(self, account):
        return self._matches_filter(account, self.active_filter) and self._matches_search(account)

    def _choose_filter(self, selection):
        self.close_menu(animate=False)
        if self.active_filter == selection and self.page == "vault":
            return
        self.active_filter = selection
        self.list_scroll.scroll_to_top()
        self.show_detail()

    def _filter_title(self):
        group, key = self.active_filter
        if group == "kind":
            return ITEM_TYPES[key]
        if group == "folder":
            return self.session.profile.folders[key]
        return FILTERS[key][0]

    def _refresh_menu(self):
        for selection, (button, count) in self.filter_buttons.items():
            active = selection == self.active_filter and self.page in ("vault", "form")
            background = theme.NAV_SELECTED if active else "transparent"
            foreground = theme.ACCENT if active else theme.MUTED
            button.configure(fg_color=background, text_color=foreground)
            count.configure(
                text=str(sum(self._matches_filter(account, selection)
                             for account in self.accounts.values())),
                text_color=foreground, fg_color=theme.SECONDARY if active else "transparent",
                bg_color=theme.NAV_SELECTED if active else theme.SIDEBAR,
            )

    def _search_changed(self, *args):
        self._show_search_hint()
        self.list_scroll.scroll_to_top()
        account = self.accounts.get(self.app.selected_id)
        if self.page == "vault" and account and not self._is_visible(account):
            self.app.selected_id = None
            self.show_detail()
        else:
            self.render_list()

    def render_list(self):
        content = self.list_scroll.content
        for child in content.winfo_children():
            child.destroy()
        self._refresh_menu()
        matches = [account for account in self.accounts.values() if self._is_visible(account)]
        self.list_title.configure(text=theme.short_text(self._filter_title().upper(), 25))
        self.result_count.configure(text=f"{len(matches)} mục")
        if not matches:
            text = "Không tìm thấy tài khoản."
            if not self.search.get().strip():
                text = "Chưa có mục trong bộ lọc này."
            theme.label(content, text, color=theme.MUTED, size=13, anchor="w").pack(
                fill="x", padx=12, pady=10,
            )
            return
        findings = audit_accounts(self.accounts.values())
        for account in matches:
            self._add_list_row(content, account, findings)

    def _add_list_row(self, parent, account, findings):
        selected = self.page in ("vault", "form") and account.id == self.app.selected_id
        tile = ctk.CTkFrame(
            parent, height=theme.LIST_ROW_HEIGHT, corner_radius=theme.CONTROL_RADIUS,
            fg_color=theme.SELECTED if selected else "transparent",
            border_width=1, border_color=theme.SELECTED_BORDER if selected else theme.LIST_BACKGROUND,
        )
        tile.pack(fill="x", pady=(0, theme.LIST_ROW_GAP))
        tile.pack_propagate(False)
        mark = theme.service_mark(tile, account.service)
        mark.pack(side="left", padx=(11, 12))
        lines = ctk.CTkFrame(tile, fg_color="transparent")
        lines.pack(side="left", fill="x", expand=True, padx=(0, 10))
        primary_line = ctk.CTkFrame(lines, fg_color="transparent")
        primary_line.pack(fill="x")
        title = theme.ellipsized_label(primary_line, account.service, bold=True)
        username = theme.ellipsized_label(
            lines, account.subtitle, size=theme.FONT_META, color=theme.MUTED, height=16,
        )
        username.pack(fill="x", pady=(2, 0))
        warnings = []
        if account.id in findings.weak:
            warnings.append("Mật khẩu yếu")
        if account.id in findings.reused:
            warnings.append("Dùng lại mật khẩu")
        if warnings:
            alert = theme.label(
                primary_line, "Yếu · Dùng lại" if len(warnings) == 2 else warnings[0],
                size=10, color=theme.WARNING, fg_color=theme.WARNING_SURFACE,
                corner_radius=4, padx=5, height=16,
            )
            alert.pack(side="right", padx=(4, 0))
            alert.bind("<Button-1>", lambda event: self.select_account(account.id), add="+")
        if account.favorite and not account.trashed:
            star = theme.label(primary_line, "★", size=12, color=theme.WARNING, height=16)
            star.pack(side="right", padx=(4, 0))
            star.bind("<Button-1>", lambda event: self.select_account(account.id), add="+")
        title.pack(side="left", fill="x", expand=True)
        for widget in (tile, mark, lines, primary_line, title, username):
            widget.bind("<Button-1>", lambda event: self.select_account(account.id), add="+")

    def select_account(self, account_id):
        self.app.selected_id = account_id
        self.show_detail()

    def _prepare_panel(self, title, page, *, icon_name=None, hint=None):
        self.write_status.pack_forget()
        self.page = page
        self.account_form = None
        self.account_details = None
        self.audit_view = None
        self.showing_account = title is None
        active = "vault" if page in ("vault", "form") else page
        for name, item in self.nav_buttons.items():
            item.configure(
                fg_color=theme.NAV_SELECTED if name == active else "transparent",
                text_color=theme.ACCENT if name == active else theme.MUTED,
            )
        self.panel_body = None
        for parent in (self.panel_header, self.panel_scroll.content):
            for child in parent.winfo_children():
                child.destroy()
        if title:
            self.panel_actions = ctk.CTkFrame(self.panel_header, fg_color="transparent")
            self.panel_actions.pack(fill="x")
            if icon_name:
                icon_color = theme.SUCCESS if page == "audit" else theme.ACCENT
                theme.label(
                    self.panel_actions, image=theme.icon(icon_name, icon_color, 19),
                    width=20, height=28,
                ).pack(side="left", padx=(0, theme.SPACING))
            theme.label(
                self.panel_actions, title, size=theme.FONT_TITLE, bold=True, height=30,
            ).pack(side="left")
            if hint:
                theme.label(
                    self.panel_header, hint, size=theme.FONT_META,
                    color=theme.MUTED, anchor="w", height=16,
                ).pack(fill="x")
            theme.divider(self.panel_header).pack(fill="x", pady=(theme.FIELD_PADDING, 0))
        self.panel_scroll.scroll_to_top()
        self.panel_body = ctk.CTkFrame(self.panel_scroll.content, fg_color="transparent")
        self.panel_body.pack(fill="x")
        self._resize_panel()
        self.render_list()
        return self.panel_body

    def _resize_panel(self, event=None):
        if self.panel_body is None:
            return
        scale = ctk.ScalingTracker.get_widget_scaling(self.panel)
        width = round(self.panel.winfo_width() / scale)
        compact = width < theme.PANEL_INSET_MIN_WIDTH
        padding = theme.PANEL_COMPACT_PADDING if compact else theme.PANEL_PADDING
        max_width = theme.GENERATOR_MAX_WIDTH if self.page == "generator" else theme.PANEL_MAX_WIDTH
        margin = max(padding, (width - max_width) // 2)
        body_top = 0
        if self.showing_account:
            self.panel_header.pack_forget()
            body_top = padding if compact else theme.DETAIL_TOP_PADDING
        else:
            self.panel_header.pack(
                fill="x", padx=margin, pady=(padding, theme.SECTION_GAP), before=self.panel_scroll,
            )
        self.panel_body.pack_configure(
            padx=(margin, margin - theme.SCROLLBAR_WIDTH), pady=(body_top, theme.PANEL_PADDING),
        )

    def _header_button(self, title, command, *, kind="secondary", width=68):
        theme.button(
            self.panel_actions, title, command, kind=kind, width=width, height=32,
        ).pack(side="right", padx=(6, 0))

    def show_detail(self):
        account = self.accounts.get(self.app.selected_id)
        if account and not self._is_visible(account):
            self.app.selected_id = None
            account = None
        body = self._prepare_panel(None if account else "Chi tiết tài khoản", "vault")
        if account:
            detail_header(
                body, account, partial(self.show_form, account.id),
                partial(self._confirm_delete, account),
                on_favorite=partial(self._toggle_favorite, account.id),
                on_restore=partial(self._restore_account, account.id),
                folder=self.session.profile.folders.get(account.folder_id, ""),
            )
            reused = audit_accounts(self.accounts.values()).reused.get(account.id, "")
            self.account_details = AccountDetails(body, account, self.app.copy_text,
                                                  copy_value=self.app.copy_value, reused_reason=reused)
            self.account_details.pack(fill="x")
            return

        empty = theme.card(body)
        empty.pack(fill="x")
        empty_vault = not self.accounts
        heading = "Kho chưa có tài khoản" if empty_vault else "Chọn một mục"
        hint = ("Thêm một mục để bắt đầu."
                if empty_vault else "Chọn một dòng trong danh sách để xem chi tiết.")
        theme.wrapped_label(empty, heading, size=18, bold=True, margin=36).pack(
            fill="x", padx=18, pady=(17, 2),
        )
        theme.wrapped_label(empty, hint, margin=36, color=theme.MUTED).pack(
            fill="x", padx=18, pady=(0, 16),
        )
        if empty_vault:
            theme.button(
                empty, "Thêm tài khoản đầu tiên", self.show_form, kind="primary", width=174,
            ).pack(anchor="w", padx=18, pady=(0, 18))

    def show_form(self, account_id=None, values=None):
        account = self.accounts.get(account_id)
        if values is None:
            group, key = self.active_filter
            values = {"kind": key if group == "kind" else "login",
                      "folder_id": key if group == "folder" else ""}
            if account:
                values = AccountForm.values_from(account)
        body = self._prepare_panel(
            "Chỉnh sửa tài khoản" if account else "Thêm tài khoản", "form",
            hint="Các trường có dấu * là bắt buộc.",
        )
        form = AccountForm(
            body, values, partial(self._save_account, account_id),
            partial(self._generator_for_form, account_id), self.session.profile.folders,
        )
        form.pack(fill="x")
        self.account_form = form

        def save():
            self.panel_scroll.scroll_to_top()
            form.save()

        self._header_button("Lưu", save, kind="primary")
        self._header_button("Hủy", self.show_detail)
        form.focus_first_field()

    def show_generator(self):
        self._show_generator("Đóng", self.show_detail)

    def _generator_for_form(self, account_id, values):
        def use_password(password):
            self.show_form(account_id, {**values, "password": password})

        self._show_generator(
            "Về biểu mẫu", partial(self.show_form, account_id, values), use_password,
        )

    def _show_generator(self, close_text, on_close, on_use=None):
        body = self._prepare_panel(
            "Trình tạo mật khẩu", "generator", icon_name="key",
            hint="Mỗi nhóm được chọn có ít nhất một ký tự trong kết quả.",
        )
        self._header_button(close_text, on_close, width=108 if on_use else 60)
        GeneratorView(body, self.app.copy_text, on_use).pack(fill="x")

    def show_audit(self):
        body = self._prepare_panel(
            "Kiểm tra an toàn", "audit", icon_name="audit",
            hint="Kiểm tra mật khẩu của các mục đăng nhập đang hoạt động.",
        )
        self._header_button("Đóng", self.show_detail, width=60)
        findings = audit_accounts(self.accounts.values())
        self.audit_view = AuditView(body, self.accounts, findings, self._open_audit_item)
        self.audit_view.pack(fill="x")

    def show_link_checker(self):
        account = self.accounts.get(self.app.selected_id)
        saved = SavedSite(account.service, account.url) if account and account.kind == "login" and account.url else None
        body = self._prepare_panel("Kiểm tra link đăng nhập", "link_checker", icon_name="search")
        self._header_button("Đóng", self.show_detail, width=60)
        LinkCheckerView(body, saved).pack(fill="x")

    def show_security_preferences(self):
        body = self._prepare_panel("Bảo vệ phiên", "security_preferences", icon_name="audit")
        self._header_button("Đóng", self.show_detail, width=60)
        card = theme.card(body)
        card.pack(fill="x")
        preferences = self.app.security_preferences

        def option(label, values, current):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=theme.FIELD_PADDING, pady=(12, 0))
            theme.label(row, label, anchor="w").pack(side="left", fill="x", expand=True)
            menu = ctk.CTkOptionMenu(row, values=list(values), width=94, font=(theme.FONT, 13),
                                     fg_color=theme.CONTROL, button_color=theme.SECONDARY,
                                     button_hover_color=theme.SECONDARY_HOVER, text_color=theme.TEXT)
            menu.set(current)
            menu.pack(side="right")
            return menu

        timeout = option("Tự khóa sau khi không dùng app", [f"{i} phút" for i in IDLE_MINUTES],
                         f"{preferences.idle_minutes} phút")
        clipboard = option("Xóa mật khẩu đã sao chép", [f"{i} giây" for i in CLIPBOARD_SECONDS],
                           f"{preferences.clipboard_seconds} giây")
        windows_note = ("Kho cũng khóa khi Windows khóa màn hình." if self.app.protection.monitor
                        else "Khóa theo màn hình hệ thống hiện không khả dụng.")
        theme.wrapped_label(card, windows_note, margin=2 * theme.FIELD_PADDING, color=theme.MUTED,
                            size=theme.FONT_META).pack(fill="x", padx=theme.FIELD_PADDING, pady=(8, 0))

        def apply():
            selected = SecurityPreferences(int(timeout.get().split()[0]), int(clipboard.get().split()[0]))
            try:
                self.app.update_security_preferences(selected)
            except VaultError as error:
                self._write_message(str(error), theme.ERROR)
            else:
                self._write_message("Đã lưu cài đặt bảo vệ.", theme.SUCCESS)

        theme.button(card, "Áp dụng", apply, kind="primary").pack(
            anchor="e", padx=theme.FIELD_PADDING, pady=theme.FIELD_PADDING,
        )
        self._recovery_key_settings(body)

    def _recovery_key_settings(self, body):
        card = theme.card(body)
        card.pack(fill="x", pady=(theme.SECTION_GAP, 0))
        inset = theme.FIELD_PADDING
        theme.label(card, "Tệp khóa khôi phục", bold=True, anchor="w").pack(
            fill="x", padx=inset, pady=(inset, 5),
        )
        hint = "Dùng cho hồ sơ chưa có khóa hoặc khi cần thay khóa cũ. Tệp cũ hết hiệu lực sau khi tạo tệp mới."
        theme.wrapped_label(card, hint, margin=2 * inset, color=theme.MUTED).pack(fill="x", padx=inset)
        theme.label(card, "Mật khẩu chính hiện tại", anchor="w").pack(fill="x", padx=inset, pady=(8, 3))
        password = theme.entry(card, show=theme.MASK)
        password.pack(fill="x", padx=inset)
        status = theme.wrapped_label(card, "", margin=2 * inset, size=theme.FONT_META)
        status.pack(fill="x", padx=inset, pady=(5, 0))

        def choose():
            value = password.get()
            if not value:
                status.configure(text="Nhập mật khẩu chính hiện tại.", text_color=theme.WARNING)
                password.focus_set()
                return
            path = filedialog.asksaveasfilename(
                parent=self.app, title="Lưu tệp khóa khôi phục ở nơi an toàn",
                initialfile=recovery_key.filename(self.session.profile.name),
                defaultextension=recovery_key.SUFFIX, filetypes=recovery_key.FILE_TYPE, confirmoverwrite=False,
            )
            if not path or not card.winfo_exists():
                return
            password.delete(0, "end")
            action.configure(state="disabled")
            status.configure(text="Đang tạo tệp khóa…", text_color=theme.MUTED)

            def finished(_result, error):
                if card.winfo_exists():
                    action.configure(state="normal")
                    status.configure(text=error or "Đã tạo tệp khóa. Hãy cất tệp riêng khỏi kho.",
                                     text_color=theme.ERROR if error else theme.SUCCESS)

            self.app.run_auth(self.app.service.issue_recovery_file, (self.session, value, path), finished)

        action = theme.button(card, "Tạo tệp khóa mới", choose, kind="primary", width=128)
        action.pack(anchor="e", padx=inset, pady=(5, inset))

    def show_csv_import(self):
        body = self._prepare_panel("Nhập tài khoản CSV", "csv_import", icon_name="folder")
        self._header_button("Đóng", self.show_detail, width=60)
        self._header_button("Đổi hồ sơ đích", self.app.choose_csv_destination, width=112)
        CsvImportView(body, self.app.service, self.session, on_imported=self._refresh_import).pack(fill="x")

    def show_backup(self):
        body = self._prepare_panel("Sao lưu và khôi phục", "backup", icon_name="vault")
        self._header_button("Đóng", self.show_detail, width=60)
        BackupView(body, self.app, self.session).pack(fill="x")

    def _refresh_import(self):
        self._refresh_folder_buttons()
        self.render_list()

    def _open_audit_item(self, account_id):
        if not self._matches_filter(self.accounts[account_id], self.active_filter):
            self.active_filter = ALL_ITEMS
        if not self._matches_search(self.accounts[account_id]):
            self.search.set("")
        self.select_account(account_id)

    def _save_account(self, account_id, values):
        try:
            account = self.app.service.save_account(self.session, account_id, values)
        except VaultError as error:
            self._write_message(str(error), theme.ERROR)
            return
        self.app.selected_id = account.id
        if not self._matches_filter(account, self.active_filter):
            self.active_filter = ALL_ITEMS
        if not self._matches_search(account):
            self.search.set("")
        self.show_detail()
        self._write_message("Đã lưu mục.", theme.SUCCESS)

    def _write_message(self, text, color):
        if not self.winfo_exists():
            return
        self.write_status.configure(text=text, text_color=color)
        self.write_status.pack(fill="x", padx=18, pady=(0, 8), before=self.panel_scroll)

    def _confirm_delete(self, account):
        service = theme.short_text(account.service, 65)
        if messagebox.askyesno(
            "Chuyển vào Thùng rác", f'Chuyển “{service}” vào Thùng rác?',
            parent=self.app, icon="warning", default="no",
        ):
            self._change_trash(account.id, True)

    def _toggle_favorite(self, account_id):
        try:
            self.app.service.toggle_favorite(self.session, account_id)
        except VaultError as error:
            self._write_message(str(error), theme.ERROR)
            return
        self.show_detail()

    def _restore_account(self, account_id):
        self._change_trash(account_id, False)

    def _change_trash(self, account_id, trashed):
        try:
            self.app.service.set_trashed(self.session, account_id, trashed)
        except VaultError as error:
            self._write_message(str(error), theme.ERROR)
            return
        self.app.selected_id = None
        self.show_detail()
        self._write_message("Đã chuyển mục vào Thùng rác." if trashed else "Đã khôi phục mục.",
                            theme.SUCCESS)
