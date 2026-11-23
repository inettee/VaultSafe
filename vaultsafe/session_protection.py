"""Khóa phiên khi rảnh và quản lý bản sao mật khẩu trên clipboard."""

from dataclasses import dataclass
import json
import os
import sys
from tempfile import NamedTemporaryFile
from time import monotonic
import tkinter as tk
from uuid import uuid4

from .errors import StorageError, ValidationError


IDLE_MINUTES = (1, 5, 10, 15, 30)
CLIPBOARD_SECONDS = (15, 30, 60, 120)
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
WINDOWS_ERRORS = (OSError,)
if sys.platform == "win32":
    try:
        from pywintypes import error as WindowsError
    except ImportError:
        pass
    else:
        WINDOWS_ERRORS += (WindowsError,)


@dataclass(frozen=True, slots=True)
class SecurityPreferences:
    idle_minutes: int = 5
    clipboard_seconds: int = 30


def load_preferences(path):
    defaults = SecurityPreferences()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        idle, clipboard = data["idle_minutes"], data["clipboard_seconds"]
    except (OSError, ValueError, KeyError, TypeError):
        return defaults
    return SecurityPreferences(
        idle if type(idle) is int and idle in IDLE_MINUTES else defaults.idle_minutes,
        clipboard if type(clipboard) is int and clipboard in CLIPBOARD_SECONDS else defaults.clipboard_seconds,
    )


def save_preferences(path, preferences):
    if (type(preferences.idle_minutes) is not int or preferences.idle_minutes not in IDLE_MINUTES
            or type(preferences.clipboard_seconds) is not int
            or preferences.clipboard_seconds not in CLIPBOARD_SECONDS):
        raise ValidationError("Thời gian bảo vệ không hợp lệ.")
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, dir=path.parent) as output:
            temporary = output.name
            json.dump({"idle_minutes": preferences.idle_minutes,
                       "clipboard_seconds": preferences.clipboard_seconds}, output)
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise StorageError("Không lưu được cài đặt bảo vệ.") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


class WindowsSessionMonitor:
    """Cửa sổ ẩn nhận thông báo khóa của phiên Windows hiện tại."""

    def __init__(self):
        import win32api
        import win32gui
        import win32ts

        self.gui, self.ts = win32gui, win32ts
        self.instance = win32api.GetModuleHandle(None)
        self.class_name = f"VaultSafeSession_{uuid4().hex}"
        self.hwnd = None
        self.registered = False
        self.lock_pending = False
        self.desktop_locked = False

        def handle(hwnd, message, parameter, session):
            if message == WM_WTSSESSION_CHANGE:
                # Tk can be dispatching native messages while its Python lock is released.
                if parameter == WTS_SESSION_LOCK:
                    self.lock_pending = self.desktop_locked = True
                elif parameter == WTS_SESSION_UNLOCK:
                    self.desktop_locked = False
                return 0
            return win32gui.DefWindowProc(hwnd, message, parameter, session)

        definition = win32gui.WNDCLASS()
        definition.hInstance = self.instance
        definition.lpszClassName = self.class_name
        definition.lpfnWndProc = handle
        win32gui.RegisterClass(definition)
        try:
            self.hwnd = win32gui.CreateWindow(self.class_name, "", 0, 0, 0, 0, 0, 0, 0, self.instance, None)
            win32ts.WTSRegisterSessionNotification(self.hwnd, win32ts.NOTIFY_FOR_THIS_SESSION)
            self.registered = True
        except WINDOWS_ERRORS:
            self.close()
            raise

    def close(self):
        try:
            if self.hwnd is not None:
                try:
                    if self.registered:
                        self.ts.WTSUnRegisterSessionNotification(self.hwnd)
                finally:
                    self.gui.DestroyWindow(self.hwnd)
                    self.hwnd = None
        finally:
            self.gui.UnregisterClass(self.class_name, self.instance)


class SessionProtection:
    def __init__(self, root, on_lock, minutes, *, clock=monotonic):
        self.root, self.on_lock, self.clock = root, on_lock, clock
        self.minutes = minutes
        self.deadline = None
        self.timer = self.pending_lock = None
        self.monitor = None
        if sys.platform == "win32":
            try:
                self.monitor = WindowsSessionMonitor()
            except WINDOWS_ERRORS + (ImportError,):
                pass

    @property
    def windows_locked(self):
        return self.monitor is not None and self.monitor.desktop_locked

    def start(self):
        self.stop()
        if self.monitor is not None:
            self.monitor.lock_pending = False
        self.deadline = self.clock() + self.minutes * 60
        self._schedule(self.minutes * 60)

    def _schedule(self, remaining):
        delay = max(1, round(remaining * 1000))
        self.timer = self.root.after(min(delay, 250) if self.monitor is not None else delay, self._check)

    def activity(self, _event=None):
        if self.deadline is not None:
            now = self.clock()
            if now >= self.deadline:
                self.request_lock()
            else:
                self.deadline = now + self.minutes * 60

    def _check(self):
        self.timer = None
        remaining = self.deadline - self.clock()
        if remaining > 0 and not (self.monitor is not None and self.monitor.lock_pending):
            self._schedule(remaining)
        else:
            self._lock()

    def request_lock(self):
        if self.deadline is not None and self.pending_lock is None:
            self.pending_lock = self.root.after(0, self._lock)

    def _lock(self):
        self.stop()
        self.on_lock()

    def set_minutes(self, minutes):
        self.minutes = minutes
        if self.deadline is not None:
            self.activity()
            if self.pending_lock is None and self.timer is not None:
                self.root.after_cancel(self.timer)
                self._schedule(minutes * 60)

    def stop(self):
        self.deadline = None
        for timer in (self.timer, self.pending_lock):
            if timer is not None:
                self.root.after_cancel(timer)
        self.timer = self.pending_lock = None

    def close(self):
        self.stop()
        if self.monitor is not None:
            try:
                self.monitor.close()
            except WINDOWS_ERRORS:
                pass
            self.monitor = None


class WindowsClipboard:
    def __init__(self, root):
        import win32clipboard

        self.api = win32clipboard
        self.root = root
        self.exclude_history = self.api.RegisterClipboardFormat("ExcludeClipboardContentFromMonitorProcessing")
        self.copy_marker = self.api.RegisterClipboardFormat("VaultSafeClipboardCopy")

    def copy(self, text):
        api = self.api
        marker = os.urandom(16)
        api.OpenClipboard(self.root.winfo_id())
        try:
            api.EmptyClipboard()
            api.SetClipboardData(self.exclude_history, b"\x01")
            api.SetClipboardData(self.copy_marker, marker)
            api.SetClipboardText(text, api.CF_UNICODETEXT)
            return marker
        finally:
            api.CloseClipboard()

    def clear_if_current(self, token):
        api = self.api
        owner = self.root.winfo_id()
        api.OpenClipboard(owner)
        try:
            if (api.GetClipboardOwner() == owner and api.IsClipboardFormatAvailable(self.copy_marker)
                    and api.GetClipboardData(self.copy_marker) == token):
                api.EmptyClipboard()
        finally:
            api.CloseClipboard()


class TkClipboard:
    def __init__(self, root):
        self.root = root

    def copy(self, text):
        marker = os.urandom(16).hex()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.clipboard_append(marker, type="VAULTSAFE_CLIPBOARD_COPY")
        return marker

    def clear_if_current(self, token):
        try:
            current = self.root.clipboard_get(type="VAULTSAFE_CLIPBOARD_COPY")
        except tk.TclError:
            return
        if current == token:
            self.root.clipboard_clear()


class ClipboardProtection:
    def __init__(self, root, seconds):
        self.root, self.seconds = root, seconds
        try:
            self.backend = WindowsClipboard(root) if sys.platform == "win32" else TkClipboard(root)
        except WINDOWS_ERRORS + (ImportError,):
            self.backend = TkClipboard(root)
        self.timer = self.token = None

    def copy(self, text, *, secret=True):
        try:
            token = self.backend.copy(text)
        except WINDOWS_ERRORS + (tk.TclError, ValueError):
            return False
        self._cancel_timer()
        self.token = token if secret else None
        if secret:
            self.timer = self.root.after(self.seconds * 1000, self.clear)
        return True

    def _cancel_timer(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None

    def clear(self, retries=10):
        self._cancel_timer()
        if self.token is None:
            return
        try:
            self.backend.clear_if_current(self.token)
        except WINDOWS_ERRORS + (tk.TclError,):
            if retries:
                self.timer = self.root.after(100, self.clear, retries - 1)
                return
        self.token = None
