"""Đọc CSV đăng nhập và lập kế hoạch nhập cục bộ cho một hồ sơ."""

import csv
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
import re
import unicodedata
from uuid import uuid4

from .errors import ValidationError
from .link_checker import InvalidLink, parse_link
from .models import Account, Profile, account_field_errors


MAX_BYTES = 4 * 1024 * 1024
MAX_ROWS = 10_000
CHROME_COLUMNS = {"url", "username", "password"}
BITWARDEN_COLUMNS = {"type", "name", "login_uri", "login_username", "login_password"}
BARE_HOST = re.compile(r"^(?:localhost(?=[:/]|$)|[^\s:/]+\.[^\s:/]+)", re.IGNORECASE)


@dataclass(frozen=True, slots=True, repr=False)
class CsvLogin:
    service: str
    username: str
    password: str
    url: str
    notes: str
    folder: str
    favorite: bool


@dataclass(frozen=True, slots=True)
class CsvLogins:
    format: str
    logins: tuple[CsvLogin, ...] = field(repr=False)
    invalid: int
    unsupported: int


@dataclass(frozen=True, slots=True)
class CsvImportPlan:
    original: Profile = field(repr=False)
    format: str
    accounts: tuple[Account, ...] = field(repr=False)
    folders: tuple[tuple[str, str], ...] = field(repr=False)
    duplicates: int
    invalid: int
    unsupported: int


def _web_link(url):
    if not url:
        return None
    candidate = f"https://{url}" if "://" not in url and BARE_HOST.match(url) else url
    try:
        link = parse_link(candidate)
    except InvalidLink:
        return None
    return link if not link.has_userinfo else None


def _login_row(values, format_name):
    bitwarden = format_name == "Bitwarden"
    if bitwarden:
        uris = values["login_uri"]
        # A Bitwarden URI field can itself be a CSV row of multiple URLs.
        first_uri = next(csv.reader([uris], strict=True), [])
        url = next((uri.strip() for uri in first_uri if uri.strip()), "")
        username = values["login_username"].strip()
        password = values["login_password"]
    else:
        url = values["url"].strip()
        username = values["username"].strip()
        password = values["password"]
    link = _web_link(url)
    if link and "://" not in url:
        url = f"https://{url}"
    name = values.get("name", "").strip() or (link.hostname if link else "")
    if account_field_errors("login", {"service": name, "username": username, "password": password}):
        return None
    notes = values.get("notes" if bitwarden else "note", "")
    folder = unicodedata.normalize("NFC", values.get("folder", "").strip()) if bitwarden else ""
    favorite = bitwarden and values.get("favorite", "").strip() == "1"
    return CsvLogin(name, username, password, url, notes, folder, favorite)


def read_login_csv(path):
    """Read a bounded UTF-8 file and keep recognized login values in memory only."""
    try:
        with Path(path).open("rb") as file:
            raw = file.read(MAX_BYTES + 1)
    except OSError:
        raise ValidationError("Không đọc được tệp CSV đã chọn.") from None
    if len(raw) > MAX_BYTES:
        raise ValidationError("Tệp CSV vượt giới hạn 4 MiB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("Tệp CSV phải dùng mã hóa UTF-8.") from None
    if "\0" in text:
        raise ValidationError("Tệp CSV chứa ký tự không hợp lệ.")
    reader = csv.reader(StringIO(text, newline=""), strict=True)
    try:
        header = [column.strip().lower() for column in next(reader, [])]
        columns = set(header)
        chrome = CHROME_COLUMNS <= columns
        bitwarden = BITWARDEN_COLUMNS <= columns
        if chrome == bitwarden or len(columns) != len(header) or "" in columns:
            raise ValidationError("Không nhận ra cột của CSV Chrome hoặc Bitwarden.")
        format_name = "Bitwarden" if bitwarden else "Chrome"
        rows = []
        invalid = unsupported = 0
        for index, row in enumerate(reader, start=1):
            if index > MAX_ROWS:
                raise ValidationError("Tệp CSV vượt giới hạn 10.000 dòng dữ liệu.")
            if not any(row):
                continue
            if len(row) != len(header):
                invalid += 1
                continue
            values = dict(zip(header, row))
            if bitwarden and values["type"].strip().lower() != "login":
                unsupported += 1
                continue
            try:
                login = _login_row(values, format_name)
            except csv.Error:
                login = None
            if login is None:
                invalid += 1
            else:
                rows.append(login)
    except csv.Error:
        raise ValidationError("Tệp CSV có hàng hoặc dấu ngoặc kép không hợp lệ.") from None
    return CsvLogins(format_name, tuple(rows), invalid, unsupported)


def _identity(item):
    link = _web_link(item.url)
    if link:
        site = (link.scheme, link.hostname, link.port)
    elif item.url.strip():
        site = ("uri", item.url.strip())
    else:
        site = ("name", unicodedata.normalize("NFC", item.service.strip()).casefold())
    return site, item.username.strip()


def preview_import(profile, batch):
    """Compute duplicates and additions against the exact profile snapshot shown in the UI."""
    seen = {_identity(item) for item in profile.accounts.values() if item.kind == "login"}
    folders = {name.casefold(): folder_id for folder_id, name in profile.folders.items()}
    new_folders = []
    accounts = []
    duplicates = 0
    for login in batch.logins:
        key = _identity(login)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        folder_key = login.folder.casefold()
        if folder_key and folder_key not in folders:
            folder_id = folders[folder_key] = uuid4().hex
            new_folders.append((folder_id, login.folder))
        accounts.append(Account(
            id=uuid4().hex, service=login.service, username=login.username, password=login.password,
            url=login.url, notes=login.notes, favorite=login.favorite, folder_id=folders.get(folder_key, ""),
        ))
    return CsvImportPlan(profile, batch.format, tuple(accounts), tuple(new_folders),
                         duplicates, batch.invalid, batch.unsupported)
