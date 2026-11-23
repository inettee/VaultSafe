"""Các kiểu dữ liệu dùng chung trong phiên demo."""

from dataclasses import dataclass, field
from collections.abc import Mapping
from types import MappingProxyType


ITEM_TYPES = {
    "login": "Đăng nhập",
    "card": "Thẻ thanh toán",
    "identity": "Danh tính",
    "note": "Ghi chú bảo mật",
}
REQUIRED_ACCOUNT_FIELDS = {
    "login": {"service": "Nhập tên dịch vụ.", "username": "Nhập tên đăng nhập.",
              "password": "Nhập mật khẩu."},
    "card": {"service": "Nhập biệt hiệu của thẻ.", "card_holder": "Nhập tên mẫu của chủ thẻ.",
             "card_last_four": "Nhập đúng 4 chữ số giả."},
    "identity": {"service": "Nhập tiêu đề.", "identity_name": "Nhập tên mẫu."},
    "note": {"service": "Nhập tiêu đề.", "notes": "Nhập nội dung ghi chú."},
}


def account_field_errors(kind: str, values: Mapping[str, str]) -> dict[str, str]:
    errors = {}
    for key, message in REQUIRED_ACCOUNT_FIELDS[kind].items():
        value = values.get(key, "").strip()
        if not value or key == "card_last_four" and (
            len(value) != 4 or not value.isascii() or not value.isdigit()
        ):
            errors[key] = message
    code = values.get("card_security_code", "").strip()
    if code:
        if kind != "card":
            errors["card_security_code"] = "Mã bảo mật chỉ dành cho mục thẻ mẫu."
        elif len(code) not in (3, 4) or not code.isascii() or not code.isdigit():
            errors["card_security_code"] = "Mã bảo mật mẫu phải có 3 hoặc 4 chữ số."
    return errors


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    service: str = field(repr=False)
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    url: str = field(default="", repr=False)
    notes: str = field(default="", repr=False)
    kind: str = "login"
    folder_id: str = ""
    favorite: bool = False
    trashed: bool = False
    card_holder: str = field(default="", repr=False)
    card_last_four: str = field(default="", repr=False)
    card_expiry: str = field(default="", repr=False)
    identity_name: str = field(default="", repr=False)
    identity_contact: str = field(default="", repr=False)
    card_security_code: str = field(default="", repr=False)

    @property
    def masked_card(self) -> str:
        return f"•••• •••• •••• {self.card_last_four}" if self.card_last_four else ""

    @property
    def subtitle(self) -> str:
        return {
            "login": self.username,
            "card": f"•••• {self.card_last_four}" if self.card_last_four else "",
            "identity": self.identity_name,
            "note": ITEM_TYPES["note"],
        }[self.kind]


@dataclass(frozen=True, slots=True)
class ProfileInfo:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class Profile(ProfileInfo):
    accounts: Mapping[str, Account] = field(default_factory=dict, repr=False)
    folders: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "accounts", MappingProxyType(dict(self.accounts)))
        object.__setattr__(self, "folders", MappingProxyType(dict(self.folders)))


@dataclass(slots=True)
class AuditFindings:
    weak: dict[str, str] = field(default_factory=dict)
    reused: dict[str, str] = field(default_factory=dict)
