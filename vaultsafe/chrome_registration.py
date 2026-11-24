"""Register the packaged Native Messaging host for the current Windows user."""

from base64 import b64decode
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import winreg


HOST_NAME = "com.vaultsafe.chrome"
EXTENSION_ID = "fgbffhmgdhahlcmgcabnjdnbamboamin"
EXTENSION_ORIGIN = f"chrome-extension://{EXTENSION_ID}/"
REGISTRY_KEY = rf"Software\Google\Chrome\NativeMessagingHosts\{HOST_NAME}"
HOST_EXECUTABLE = Path("native_host/VaultSafeChromeHost/VaultSafeChromeHost.exe")


def _manifest_path():
    return Path(os.environ["LOCALAPPDATA"]) / "VaultSafe" / "ChromeHost" / f"{HOST_NAME}.json"


def _registered_manifest():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            value, kind = winreg.QueryValueEx(key, "")
    except FileNotFoundError:
        return None
    if kind != winreg.REG_SZ or not value:
        raise ValueError("Chrome đang có cấu hình VaultSafe khác. Cấu hình đó vẫn được giữ.")
    return Path(value)


def register(package):
    host = package / HOST_EXECUTABLE
    if not host.is_file():
        raise ValueError("Thiếu chương trình kết nối. Hãy giải nén lại toàn bộ gói VaultSafe-Windows-x64.")
    try:
        manifest = json.loads((package / "chrome_extension" / "manifest.json").read_text(encoding="utf-8"))
        digest = sha256(b64decode(manifest["key"], validate=True)).hexdigest()[:32]
        extension_id = digest.translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop"))
    except (OSError, ValueError, KeyError, TypeError):
        extension_id = ""
    if extension_id != EXTENSION_ID:
        raise ValueError("Thiếu hoặc sai phiên bản tiện ích Chrome. Hãy giải nén lại toàn bộ gói.")
    path = _manifest_path()
    current = _registered_manifest()
    if current is not None and current != path:
        raise ValueError("Chrome đang có cấu hình VaultSafe khác. Cấu hình đó vẫn được giữ.")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "name": HOST_NAME,
        "description": "VaultSafe Chrome host",
        "path": str(host),
        "type": "stdio",
        "allowed_origins": [EXTENSION_ORIGIN],
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, indent=2)
            # Register the path before replacing the file, so a failed registry write
            # cannot replace a working manifest.
            if current is None:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(path))
            try:
                temporary.replace(path)
            except OSError:
                if current is None:
                    winreg.DeleteValue(key, "")
                raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def unregister(package):
    path = _manifest_path()
    current = _registered_manifest()
    if current is None:
        return False
    if current != path:
        raise ValueError("Chrome đang kết nối với một bản VaultSafe khác.")
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(manifest, dict) or manifest.get("path") != str(package / HOST_EXECUTABLE):
            raise ValueError("Chrome đang kết nối với một bản VaultSafe khác.")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.DeleteValue(key, "")
    # Chrome stops finding the host as soon as the registry value is gone.
    path.unlink(missing_ok=True)
    return True
