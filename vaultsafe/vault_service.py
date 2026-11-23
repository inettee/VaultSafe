"""Chính sách hồ sơ, phiên mở khóa và cập nhật kho sau khi SQLite commit."""

from dataclasses import asdict, fields, replace
import json
import secrets
from threading import RLock
import unicodedata
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import recovery_key, vault_crypto as crypto
from .csv_import import CsvImportPlan, CsvLogins, preview_import
from .errors import ConflictError, FormatError, SessionClosedError, UnlockError, ValidationError
from .models import Account, ITEM_TYPES, Profile, ProfileInfo, account_field_errors
from .storage import VaultRecord, VaultStorage


PROFILE_NAME_LIMIT = 60
MASTER_PASSWORD_MIN = 12
MASTER_PASSWORD_MAX = 128
PROFILE_NAME_HINT = f"Tên hồ sơ dài 1–{PROFILE_NAME_LIMIT} ký tự."
MASTER_PASSWORD_HINT = f"Mật khẩu chính dài {MASTER_PASSWORD_MIN}–{MASTER_PASSWORD_MAX} ký tự."
CLOSED_ERROR = "Phiên đã khóa. Hãy mở khóa hồ sơ để tiếp tục."


def profile_creation_errors(name: str, password: str, confirmation: str) -> tuple[str, str, str]:
    name = unicodedata.normalize("NFC", name.strip())
    name_error = ""
    if not name:
        name_error = "Nhập tên hồ sơ."
    elif len(name) > PROFILE_NAME_LIMIT or not name.isprintable():
        name_error = PROFILE_NAME_HINT + " Dùng ký tự hiển thị được."
    password_error = ""
    if not password.strip():
        password_error = "Nhập mật khẩu chính."
    elif not MASTER_PASSWORD_MIN <= len(password) <= MASTER_PASSWORD_MAX:
        password_error = MASTER_PASSWORD_HINT
    confirmation_error = ""
    if not confirmation:
        confirmation_error = "Nhập lại mật khẩu chính."
    elif password != confirmation:
        confirmation_error = "Mật khẩu xác nhận không khớp."
    return name_error, password_error, confirmation_error


ACCOUNT_FIELDS = {field.name for field in fields(Account)}
FLAG_FIELDS = {"favorite", "trashed"}
INVALID_PAYLOAD = "Nội dung đã giải mã của hồ sơ không hợp lệ."


def _encode(profile: Profile) -> bytes:
    return json.dumps({
        "version": crypto.FORMAT_VERSION,
        "folders": dict(profile.folders),
        "accounts": [asdict(account) for account in profile.accounts.values()],
    }, separators=(",", ":")).encode("ascii")


def _decode(profile_id: str, name: str, payload: bytes) -> Profile:
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError
        version = data.get("version")
        if type(version) is not int:
            raise ValueError
        if version != crypto.FORMAT_VERSION:
            raise FormatError("Phiên bản nội dung kho VaultSafe chưa được hỗ trợ.")
        folders = data["folders"]
        items = data["accounts"]
        if (not isinstance(folders, dict) or not isinstance(items, list)
                or any(not key or not isinstance(name, str) or not name.strip()
                       for key, name in folders.items())):
            raise ValueError
        if len({name.casefold() for name in folders.values()}) != len(folders):
            raise ValueError
        accounts = {}
        for item in items:
            if (not isinstance(item, dict) or not item.keys() <= ACCOUNT_FIELDS
                    or any(type(value) is not (bool if key in FLAG_FIELDS else str)
                           for key, value in item.items())):
                raise ValueError
            account = Account(**item)
            if (not account.id or account.id in accounts or not account.service.strip()
                    or account.kind not in ITEM_TYPES
                    or account.folder_id and account.folder_id not in folders):
                raise ValueError
            accounts[account.id] = account
        return Profile(profile_id, name, accounts, folders)
    except (UnicodeError, ValueError, KeyError, TypeError, RecursionError):
        raise FormatError(INVALID_PAYLOAD) from None


class VaultSession:
    def __init__(self, storage, profile, cipher, revision):
        self._storage = storage
        self._profile = profile
        self._cipher = cipher
        self._revision = revision
        self._lock = RLock()

    @property
    def profile(self) -> Profile:
        return self.versioned_profile()[0]

    def versioned_profile(self) -> tuple[Profile, int]:
        with self._lock:
            if self._profile is None:
                raise SessionClosedError(CLOSED_ERROR)
            return self._profile, self._revision

    def close(self):
        with self._lock:
            self._cipher = None
            self._profile = None


class VaultService:
    def __init__(self, data_dir=None):
        self.storage = VaultStorage(data_dir)

    def initialize(self):
        self.storage.initialize()

    def list_profiles(self) -> tuple[ProfileInfo, ...]:
        return self.storage.list_profiles()

    def create_profile(self, name: str, password: str, confirmation: str, recovery_path=None) -> ProfileInfo:
        for error in profile_creation_errors(name, password, confirmation):
            if error:
                raise ValidationError(error)
        profile = Profile(uuid4().hex, unicodedata.normalize("NFC", name.strip()))
        record, key = self._password_record(profile, password)
        if recovery_path is None:
            self.storage.insert(record)
        else:
            secret = secrets.token_bytes(32)
            capsule = recovery_key.wrap(record, secret, key)
            with recovery_key.publish_file(recovery_path, profile.id, secret):
                self.storage.insert(record, recovery=capsule)
        return ProfileInfo(profile.id, profile.name)

    @staticmethod
    def _new_record(profile, password):
        return VaultService._password_record(profile, password)[0]

    @staticmethod
    def _password_record(profile, password, revision=1):
        salt = secrets.token_bytes(crypto.SALT_SIZE)
        key = crypto.derive_key(password, salt)
        nonce, ciphertext = crypto.encrypt(AESGCM(key), profile.id, revision, _encode(profile))
        record = VaultRecord(
            profile.id, profile.name, salt, crypto.KDF_VERSION, crypto.MEMORY_KIB,
            crypto.ITERATIONS, crypto.PARALLELISM, crypto.FORMAT_VERSION, nonce, ciphertext, revision,
        )
        return record, key

    def _record_for_open(self, profile_id):
        record = self.storage.read(profile_id)
        if record is None:
            raise UnlockError(crypto.UNLOCK_ERROR)
        if type(record.format_version) is not int or record.format_version != crypto.FORMAT_VERSION:
            raise FormatError("Phiên bản định dạng kho VaultSafe chưa được hỗ trợ.")
        if (type(record.revision) is not int or not 1 <= record.revision < 2**63 - 1
                or not isinstance(record.name, str) or not record.name):
            raise UnlockError(crypto.UNLOCK_ERROR)
        return record

    @staticmethod
    def _derive_record_key(record, password):
        if not password or len(password) > MASTER_PASSWORD_MAX:
            raise UnlockError(crypto.UNLOCK_ERROR)
        return crypto.derive_key(
            password, record.salt, version=record.kdf_version, memory_kib=record.memory_kib,
            iterations=record.iterations, parallelism=record.parallelism,
        )

    def open_profile(self, profile_id: str, password: str) -> VaultSession:
        record = self._record_for_open(profile_id)
        cipher = AESGCM(self._derive_record_key(record, password))
        profile = _decode(record.profile_id, record.name, crypto.decrypt(cipher, record))
        return VaultSession(self.storage, profile, cipher, record.revision)

    def issue_recovery_file(self, session, password, path):
        profile, revision = session.versioned_profile()
        record = self._record_for_open(profile.id)
        if record.revision != revision:
            raise ConflictError("Kho đã thay đổi. Hãy mở lại kho trước khi tạo tệp khóa.")
        previous = self.storage.read_recovery(profile.id)
        key = self._derive_record_key(record, password)
        crypto.decrypt(AESGCM(key), record)
        secret = secrets.token_bytes(32)
        with session._lock:
            if session._storage is not self.storage or session._cipher is None:
                raise SessionClosedError(CLOSED_ERROR)
            with recovery_key.publish_file(path, profile.id, secret):
                self.storage.set_recovery(record, previous, recovery_key.wrap(record, secret, key))

    def _recover(self, profile_id, path):
        record = self._record_for_open(profile_id)
        capsule = self.storage.read_recovery(profile_id)
        if capsule is None:
            raise UnlockError(recovery_key.MISSING)
        secret = recovery_key.read_secret(path, profile_id)
        key = recovery_key.unwrap(record, secret, capsule)
        profile = _decode(profile_id, record.name, crypto.decrypt(AESGCM(key), record))
        return record, capsule, secret, profile

    def verify_recovery_file(self, profile_id, path):
        self._recover(profile_id, path)

    def reset_master_password(self, profile_id, path, password, confirmation):
        for error in profile_creation_errors("Hồ sơ", password, confirmation)[1:]:
            if error:
                raise ValidationError(error)
        record, previous, secret, profile = self._recover(profile_id, path)
        updated, key = self._password_record(profile, password, record.revision + 1)
        self.storage.reset_password(record, updated, previous, recovery_key.wrap(updated, secret, key))

    def _commit(self, session: VaultSession, original: Profile, updated: Profile):
        with session._lock:
            if session._storage is not self.storage or session._cipher is None:
                raise SessionClosedError(CLOSED_ERROR)
            if session.profile is not original:
                raise ConflictError("Dữ liệu đã thay đổi. Hãy mở lại mục trước khi lưu.")
            revision = session._revision
            nonce, ciphertext = crypto.encrypt(session._cipher, original.id, revision + 1, _encode(updated))
            self.storage.update(original.id, revision, nonce, ciphertext)
            session._profile = updated
            session._revision = revision + 1

    def save_account(self, session: VaultSession, account_id: str | None, values: dict,
                     *, expected_revision: int | None = None) -> Account:
        profile, revision = session.versioned_profile()
        if expected_revision is not None and revision != expected_revision:
            raise ConflictError("Dữ liệu đã thay đổi. Hãy mở lại mục trước khi lưu.")
        accounts = dict(profile.accounts)
        previous = self._account(profile, account_id) if account_id else None
        if not values.keys() <= ACCOUNT_FIELDS - FLAG_FIELDS - {"id"} or any(
            not isinstance(value, str) for value in values.values()
        ):
            raise ValidationError("Các trường của mục không hợp lệ.")
        values = {key: value if key in ("password", "notes") else value.strip()
                  for key, value in values.items()}
        kind = values.get("kind", "login")
        if kind not in ITEM_TYPES:
            raise ValidationError("Chọn loại mục hợp lệ.")
        errors = account_field_errors(kind, values)
        if errors:
            raise ValidationError(next(iter(errors.values())))
        account = Account(
            account_id or uuid4().hex, **values, favorite=previous.favorite if previous else False,
            trashed=previous.trashed if previous else False,
        )
        if account.folder_id and account.folder_id not in profile.folders:
            raise ValidationError("Không tìm thấy thư mục đã chọn.")
        accounts[account.id] = account
        self._commit(session, profile, replace(profile, accounts=accounts))
        return account

    def preview_csv_import(self, session: VaultSession, batch: CsvLogins) -> CsvImportPlan:
        if session._storage is not self.storage:
            raise SessionClosedError(CLOSED_ERROR)
        return preview_import(session.profile, batch)

    def import_csv_logins(self, session: VaultSession, plan: CsvImportPlan) -> int:
        if session._storage is not self.storage:
            raise SessionClosedError(CLOSED_ERROR)
        profile = session.profile
        if profile is not plan.original:
            raise ConflictError("Hồ sơ hoặc dữ liệu kho đã thay đổi. Hãy xem trước tệp CSV lại.")
        if plan.accounts:
            accounts = {**profile.accounts, **{item.id: item for item in plan.accounts}}
            folders = {**profile.folders, **dict(plan.folders)}
            self._commit(session, profile, replace(profile, accounts=accounts, folders=folders))
        return len(plan.accounts)

    @staticmethod
    def _account(profile, account_id):
        account = profile.accounts.get(account_id)
        if account is None:
            raise ValidationError("Không tìm thấy mục trong hồ sơ đang mở.")
        return account

    def toggle_favorite(self, session: VaultSession, account_id: str):
        profile = session.profile
        account = self._account(profile, account_id)
        accounts = dict(profile.accounts)
        accounts[account_id] = replace(account, favorite=not account.favorite)
        self._commit(session, profile, replace(profile, accounts=accounts))

    def set_trashed(self, session: VaultSession, account_id: str, trashed: bool):
        if type(trashed) is not bool:
            raise ValidationError("Trạng thái Thùng rác không hợp lệ.")
        profile = session.profile
        account = self._account(profile, account_id)
        accounts = dict(profile.accounts)
        accounts[account_id] = replace(account, trashed=trashed)
        self._commit(session, profile, replace(profile, accounts=accounts))

    def create_folder(self, session: VaultSession, name: str) -> str:
        profile = session.profile
        name = unicodedata.normalize("NFC", name.strip())
        if not name:
            raise ValidationError("Nhập tên thư mục.")
        if any(current.casefold() == name.casefold() for current in profile.folders.values()):
            raise ValidationError("Thư mục đã tồn tại trong hồ sơ này.")
        folder_id = uuid4().hex
        folders = dict(profile.folders)
        folders[folder_id] = name
        self._commit(session, profile, replace(profile, folders=folders))
        return folder_id
