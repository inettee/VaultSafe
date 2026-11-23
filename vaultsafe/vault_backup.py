"""Bản sao theo hồ sơ, dùng mật khẩu sao lưu và định dạng xác thực riêng."""

from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from pathlib import Path
import os
import secrets
import sys
from tempfile import NamedTemporaryFile
import unicodedata
from uuid import uuid4

from cryptography.exceptions import InvalidTag

from . import vault_crypto as crypto
from .errors import FormatError, SessionClosedError, StorageError, UnlockError, ValidationError
from .models import Profile, ProfileInfo
from .vault_service import CLOSED_ERROR, PROFILE_NAME_LIMIT, _decode, _encode, profile_creation_errors


EXTENSION = ".vaultsafe"
SIGNATURE = b"VaultSafeBackup\x01"
HEADER_SIZE = len(SIGNATURE) + 16
NONCE_SIZE = 12
MAX_BACKUP_BYTES = HEADER_SIZE + NONCE_SIZE + 16 + PROFILE_NAME_LIMIT * 4 + 1 + crypto.MAX_PAYLOAD_SIZE
INVALID_BACKUP = "Tệp không phải bản sao VaultSafe hợp lệ hoặc dùng phiên bản khác."
BACKUP_PASSWORD_ERROR = "Mật khẩu bản sao phải có 12–128 ký tự."


@dataclass(frozen=True, slots=True)
class BackupPreview:
    name: str
    item_count: int
    _profile: Profile = field(repr=False)


def _backup_cipher(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 128 or not password.strip():
        raise ValidationError(BACKUP_PASSWORD_ERROR)
    # The KDF parameters are part of the v1 backup format.
    return crypto.derive_cipher(password, salt, version=19, memory_kib=19_456, iterations=2, parallelism=1)


def _require_session(service, session):
    if session._storage is not service.storage or session._cipher is None:
        raise SessionClosedError(CLOSED_ERROR)


def export_backup(service, session, path, password):
    """Write an atomic snapshot to a new file, leaving existing files in place."""
    with session._lock:
        _require_session(service, session)
        profile = session.profile
    payload = _encode(profile)
    if len(payload) > crypto.MAX_PAYLOAD_SIZE:
        raise FormatError("Nội dung kho vượt quá giới hạn 16 MiB.")
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(NONCE_SIZE)
    header = SIGNATURE + salt
    cipher = _backup_cipher(password, salt)
    sealed = cipher.encrypt(nonce, profile.name.encode("utf-8") + b"\n" + payload, header)
    destination = Path(path)
    temporary = None
    try:
        with NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(header + nonce + sealed)
            output.flush()
            os.fsync(output.fileno())
        with session._lock:
            _require_session(service, session)
            if sys.platform == "win32":
                # On Windows rename fails if the destination already exists.
                temporary.rename(destination)
            else:
                os.link(temporary, destination)
    except FileExistsError:
        raise ValidationError("Tệp đích đã tồn tại. Hãy chọn tên tệp khác.") from None
    except OSError:
        raise StorageError("Không ghi được tệp sao lưu VaultSafe.") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def preview_backup(path, password):
    try:
        with Path(path).open("rb") as source:
            data = source.read(MAX_BACKUP_BYTES + 1)
    except OSError:
        raise StorageError("Không đọc được tệp sao lưu đã chọn.") from None
    start = HEADER_SIZE + NONCE_SIZE
    if not start + 16 <= len(data) <= MAX_BACKUP_BYTES or not data.startswith(SIGNATURE):
        raise FormatError(INVALID_BACKUP)
    cipher = _backup_cipher(password, data[len(SIGNATURE):HEADER_SIZE])
    try:
        plaintext = cipher.decrypt(data[HEADER_SIZE:start], data[start:], data[:HEADER_SIZE])
    except InvalidTag:
        raise UnlockError("Mật khẩu bản sao không đúng hoặc tệp đã bị thay đổi.") from None
    name, separator, payload = plaintext.partition(b"\n")
    try:
        name = name.decode("utf-8")
    except UnicodeError:
        raise FormatError(INVALID_BACKUP) from None
    if (not separator or not 1 <= len(name) <= PROFILE_NAME_LIMIT or not name.isprintable()
            or len(payload) > crypto.MAX_PAYLOAD_SIZE):
        raise FormatError(INVALID_BACKUP)
    profile = _decode("", name, payload)
    return BackupPreview(name, len(profile.accounts), profile)


def restore_backup(service, preview, name, password, confirmation, *, session=None):
    for error in profile_creation_errors(name, password, confirmation):
        if error:
            raise ValidationError(error)
    profile = replace(preview._profile, id=uuid4().hex, name=unicodedata.normalize("NFC", name.strip()))
    record = service._new_record(profile, password)
    with session._lock if session is not None else nullcontext():
        if session is not None:
            _require_session(service, session)
        service.storage.insert(record)
    return ProfileInfo(profile.id, profile.name)
