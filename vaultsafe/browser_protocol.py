"""Validate browser requests at both native boundaries."""

import json
import re
from urllib.parse import urlsplit


MAX_MESSAGE = 4096
DEMO_URL = "http://localhost:8765/vaultsafe-demo/"
DEMO_NAME = "VaultSafe Demo"
HTTPS_DEMO_URL = "https://vaultsafe-demo.test:8766/vaultsafe-demo/login"
DIALOG_DEMO_URL = "https://vaultsafe-dialog.test:8766/vaultsafe-demo/inline"
SITES = {
    "localhost": (DEMO_NAME, DEMO_URL),
    "https_demo": ("VaultSafe HTTPS Demo", HTTPS_DEMO_URL),
    "https_dialog_demo": ("VaultSafe Dialog Demo", DIALOG_DEMO_URL),
}
DEMO_PASSWORDS = ("DemoOnly!123", "DemoOnly!456")


def encode_message(message):
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_message(data):
    if not data or len(data) > MAX_MESSAGE:
        raise ValueError("Invalid message length")
    return json.loads(data.decode("utf-8"))


def valid_request(request):
    if not isinstance(request, dict):
        return False
    operation = request.get("op")
    if operation == "status":
        return request.keys() == {"op"}
    if operation == "check_tab":
        return request.keys() == {"op", "url"} and _check_tab_url(request["url"])
    fields = {"op", "target", "username", "password"}
    site = request.get("site")
    if site == "manual":
        fields.update(("site", "url"))
    elif site in ("https_demo", "https_dialog_demo"):
        fields.add("site")
    if operation == "update":
        fields.add("confirmation")
        if not _matches(r"[0-9a-f]{64}", request.get("confirmation")):
            return False
    elif operation != "save":
        return False
    if request.keys() != fields or not _matches(r"[0-9a-f]{32}", request["target"]):
        return False
    if site == "manual":
        return (
            manual_hostname(request["url"]) is not None
            and _manual_text(request["username"], 128)
            and request["username"] == request["username"].strip()
            and _manual_text(request["password"], 256)
        )
    return (
        _matches(r"[a-z0-9][a-z0-9._-]{0,63}@example\.test", request["username"])
        and request["password"] in DEMO_PASSWORDS
    )


def _matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def _check_tab_url(value):
    return (isinstance(value, str) and len(value) <= 264
            and _matches(r"https?://(?:[a-z0-9.-]+|\[[0-9a-f:.]+\])/", value))


def _manual_text(value, limit):
    return (isinstance(value, str) and 0 < len(value) <= limit and bool(value.strip())
            and not re.search(r"[\x00-\x1f\x7f\ud800-\udfff]", value))


def manual_hostname(value):
    if not isinstance(value, str) or not re.fullmatch(r"[!-~]{1,1024}", value):
        return None
    if any(character in value for character in ("?", "#", "\\")):
        return None
    try:
        url = urlsplit(value)
        port = url.port
        host = url.hostname
        if (url.scheme in ("https", "http") and url.username is None
                and (port is None or port > 0) and host
                and re.fullmatch(r"[a-z0-9._:-]+", host)):
            return host
    except ValueError:
        pass
    return None
