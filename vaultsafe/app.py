"""Cửa sổ và phiên làm việc của VaultSafe."""

from concurrent.futures import ThreadPoolExecutor
import sys
import tkinter as tk

import customtkinter as ctk

from . import theme
from .browser_bridge import BrowserBridge
from .errors import VaultError
from .session_protection import ClipboardProtection, SessionProtection, load_preferences, save_preferences
from .ui.backup_view import BackupView
from .ui.product_tour import ProductTour
from .ui.unlock_view import UnlockView
from .ui.vault_view import VaultView
from .vault_service import VaultService, VaultSession


class VaultSafeApp(ctk.CTk):
    def __init__(self, data_dir=None, *, browser_integration=False):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=theme.BACKGROUND)
        self.title("VaultSafe")
        self.minsize(*theme.MIN_WINDOW_SIZE)
        self._size_window()

        self.unlock_logo = theme.load_logo(theme.UNLOCK_LOGO_SIZE)
        self.sidebar_logo = theme.load_logo(theme.SIDEBAR_LOGO_SIZE)
        self.service = VaultService(data_dir)
        self._preferences_path = self.service.storage.path.with_name("security_preferences.json")
        self.security_preferences = load_preferences(self._preferences_path)
        self.protection = SessionProtection(self, self.show_unlock, self.security_preferences.idle_minutes)
        self.clipboard_protection = ClipboardProtection(self, self.security_preferences.clipboard_seconds)
        self.session: VaultSession | None = None
        self._storage_ready = False
        self._auth_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vault-auth")
        self._auth_future = None
        self._auth_timer = None
        self.selected_id: str | None = None
        self._choose_csv_destination = False
        self.view = None
        self.browser_bridge = None
        self.tour = ProductTour(self)
        self.bind("<MouseWheel>", self._scroll_under_pointer, add="+")
        self.bind("<Return>", self._submit_unlock)
        self.bind("<Escape>", self._dismiss_drawer)
        self.bind("<Tab>", self._block_drawer_tab)
        self.bind("<Shift-Tab>", self._block_drawer_tab)
        self.bind("<Configure>", self._move_drawer, add="+")
        self.bind("<Unmap>", self._hide_drawer, add="+")
        for sequence in ("<Motion>", "<ButtonPress>", "<KeyPress>"):
            self.bind_all(sequence, self.protection.activity, add="+")
        self.show_unlock()
        if browser_integration and sys.platform == "win32":
            try:
                self.browser_bridge = BrowserBridge(self, self._refresh_browser_item)
            except (ImportError, OSError, RuntimeError):
                print("VaultSafe: không mở được kênh kết nối Chrome. "
                      "Kiểm tra pywin32 và chỉ mở một cửa sổ VaultSafe.", file=sys.stderr)

    @property
    def profile(self):
        return self.session.profile

    def list_profiles(self):
        if not self._storage_ready:
            self.service.initialize()
            self._storage_ready = True
        return self.service.list_profiles()

    def show_unlock(self, *, preferred_profile_id=None):
        self._choose_csv_destination = False
        if self.session is not None:
            self.tour.stop(close_drawer=False)
        preferred = preferred_profile_id or (self.profile.id if self.session is not None else None)
        self.cancel_auth()
        self._close_session()
        self.selected_id = None
        self._replace_view(UnlockView, preferred)

    def show_backup_restore(self):
        self.tour.stop()
        self.cancel_auth()
        self._close_session()
        self.selected_id = None
        self._replace_view(theme.ScrollPane, theme.BACKGROUND)
        page = ctk.CTkFrame(self.view.content, fg_color="transparent")
        page.pack(fill="x", padx=24, pady=20)
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", pady=(0, theme.FIELD_PADDING))
        theme.label(header, "Khôi phục bản sao VaultSafe", size=theme.FONT_TITLE, bold=True).pack(side="left")
        theme.button(header, "Quay lại", self.show_unlock, kind="quiet").pack(side="right")
        BackupView(page, self, on_restored=lambda profile: self.show_unlock(
            preferred_profile_id=profile.id,
        )).pack(fill="x")

    def choose_csv_destination(self):
        self.show_unlock()
        self._choose_csv_destination = True

    def open_session(self, session):
        if self.protection.windows_locked:
            session.close()
            self.show_unlock()
            return
        self._close_session()
        self.session = session
        if self.browser_bridge is not None:
            self.browser_bridge.set_session(session)
        self.selected_id = None
        self._replace_view(VaultView)
        self.protection.start()
        self.tour.unlocked()
        if self._choose_csv_destination:
            self._choose_csv_destination = False
            if not self.tour.active:
                self.view.show_csv_import()

    def _close_session(self):
        self.protection.stop()
        self.clipboard_protection.clear()
        if self.browser_bridge is not None:
            self.browser_bridge.set_session(None)
        if self.session is not None:
            self.session.close()
            self.session = None

    def run_auth(self, operation, args, on_finish):
        self.cancel_auth()
        future = self._auth_worker.submit(operation, *args)
        self._auth_future = future

        def poll():
            if not future.done():
                self._auth_timer = self.after(25, poll)
                return
            self._auth_future = self._auth_timer = None
            try:
                result = future.result()
            except VaultError as error:
                on_finish(None, str(error))
            except Exception:
                on_finish(None, "Không hoàn thành được thao tác. Hãy thử lại.")
            else:
                on_finish(result, "")

        self._auth_timer = self.after(25, poll)

    def cancel_auth(self):
        if self._auth_timer is not None:
            self.after_cancel(self._auth_timer)
            self._auth_timer = None
        future, self._auth_future = self._auth_future, None
        if future is not None and not future.cancel():
            future.add_done_callback(self._discard_auth_result)

    @staticmethod
    def _discard_auth_result(future):
        if not future.cancelled() and future.exception() is None:
            result = future.result()
            if isinstance(result, VaultSession):
                result.close()

    def destroy(self):
        if self.browser_bridge is not None:
            self.browser_bridge.close()
            self.browser_bridge = None
        self.tour.stop(close_drawer=False)
        self.cancel_auth()
        self._close_session()
        self.protection.close()
        self.clipboard_protection.clear(retries=0)
        self.selected_id = None
        self._auth_worker.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    def _replace_view(self, view_type, *args):
        if self.view is not None:
            self.view.destroy()
        self.view = view_type(self, *args)
        self.view.pack(fill="both", expand=True)

    def _refresh_browser_item(self, account_id):
        if isinstance(self.view, VaultView) and account_id in self.view.accounts:
            if self.selected_id == account_id and self.view.page == "vault":
                self.view.show_detail()
            else:
                self.view.render_list()

    def _submit_unlock(self, event):
        if isinstance(self.view, UnlockView):
            self.view.submit()
            return "break"

    def copy_text(self, text):
        return self.clipboard_protection.copy(text)

    def copy_value(self, text):
        return self.clipboard_protection.copy(text, secret=False)

    def update_security_preferences(self, preferences):
        save_preferences(self._preferences_path, preferences)
        self.security_preferences = preferences
        self.protection.set_minutes(preferences.idle_minutes)
        self.clipboard_protection.seconds = preferences.clipboard_seconds

    def _size_window(self):
        scale = ctk.ScalingTracker.get_window_scaling(self)
        preferred_width, preferred_height = theme.WINDOW_SIZE
        min_width, min_height = theme.MIN_WINDOW_SIZE
        width = min(preferred_width, max(min_width, int((self.winfo_screenwidth() - 72) / scale)))
        height = min(preferred_height, max(min_height, int((self.winfo_screenheight() - 112) / scale)))
        x = max(0, round((self.winfo_screenwidth() - width * scale) / 2))
        y = max(0, round((self.winfo_screenheight() - height * scale - 56) / 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _scroll_under_pointer(self, event):
        self.protection.activity()
        if isinstance(self.view, VaultView) and self.view.menu_modal:
            return self.view.scroll_drawer(event)
        widget = event.widget
        if isinstance(widget, tk.Text) and widget.yview() != (0.0, 1.0):
            return
        while widget is not None:
            if isinstance(widget, theme.ScrollPane):
                widget.scroll_by(-int(event.delta / 120) * 3)
                return "break"
            widget = widget.master

    def _dismiss_drawer(self, event):
        if self.tour.active:
            return self.tour.stop()
        if isinstance(self.view, VaultView) and self.view.menu_modal:
            self.view.close_menu()
            return "break"

    def _block_drawer_tab(self, event):
        if isinstance(self.view, VaultView) and self.view.menu_modal:
            return "break"

    def _move_drawer(self, event):
        if event.widget is self and isinstance(self.view, VaultView):
            self.view.position_scrim()

    def _hide_drawer(self, event):
        if event.widget is self:
            self.tour._hide()
            if isinstance(self.view, VaultView):
                self.view.close_menu(animate=False)
