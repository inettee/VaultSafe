"""Double-click setup for the unpacked VaultSafe Chrome extension on Windows."""

import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import winreg

from vaultsafe.chrome_registration import register, unregister


def chrome_executable():
    key_name = r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key_name) as key:
                path = Path(os.path.expandvars(winreg.QueryValueEx(key, "")[0]))
                if path.is_file():
                    return path
        except OSError:
            continue
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        folder = os.environ.get(variable)
        if folder:
            path = Path(folder) / "Google/Chrome/Application/chrome.exe"
            if path.is_file():
                return path
    return None


def main():
    package = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    root = tk.Tk()
    root.title("Thiết lập VaultSafe cho Chrome")
    root.resizable(False, False)
    content = ttk.Frame(root, padding=24)
    content.pack(fill="both", expand=True)
    ttk.Label(content, text="Kết nối VaultSafe với Chrome",
              font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(0, 10))
    ttk.Label(content, justify="left", wraplength=470, text=(
        "1. Bấm Kết nối và mở Chrome.\n"
        "2. Trong Chrome, bật Chế độ dành cho nhà phát triển (Developer mode).\n"
        "3. Bấm Tải tiện ích đã giải nén (Load unpacked), dán đường dẫn đã được chép sẵn rồi chọn thư mục.\n"
        "4. Mở VaultSafe.exe, mở khóa kho và bấm biểu tượng VaultSafe trong Chrome."
    )).pack(anchor="w")

    status = tk.StringVar()
    ttk.Label(content, textvariable=status, wraplength=470, justify="left").pack(anchor="w", pady=12)

    def copy_folder():
        root.clipboard_clear()
        root.clipboard_append(str(package / "chrome_extension"))

    def connect():
        try:
            register(package)
        except ValueError as error:
            messagebox.showerror(root.title(), str(error), parent=root)
            return
        except OSError:
            messagebox.showerror(root.title(), "Không ghi được cấu hình kết nối Chrome.", parent=root)
            return
        copy_folder()
        chrome = chrome_executable()
        if chrome is not None:
            try:
                subprocess.Popen([str(chrome), "chrome://extensions/"], cwd=str(chrome.parent))
                status.set("Đã thiết lập kết nối và chép đường dẫn. Hãy làm tiếp bước 2 trong Chrome.")
                return
            except OSError:
                pass
        status.set("Đã thiết lập kết nối và chép đường dẫn. Hãy tự mở chrome://extensions trong Chrome.")

    def disconnect():
        try:
            removed = unregister(package)
        except ValueError as error:
            messagebox.showerror(root.title(), str(error), parent=root)
            return
        except OSError:
            messagebox.showerror(root.title(), "Không gỡ được cấu hình kết nối Chrome.", parent=root)
            return
        status.set("Đã ngắt kết nối. Bạn có thể gỡ tiện ích trong Chrome." if removed
                   else "Chrome chưa được kết nối với VaultSafe.")

    actions = ttk.Frame(content)
    actions.pack(fill="x")
    ttk.Button(actions, text="Kết nối và mở Chrome", command=connect).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="Chép thư mục tiện ích", command=copy_folder).pack(side="left", padx=(0, 8))
    ttk.Button(actions, text="Ngắt kết nối", command=disconnect).pack(side="right")
    root.mainloop()


if __name__ == "__main__":
    main()
