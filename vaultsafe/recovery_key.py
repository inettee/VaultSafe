"""Tệp khóa khôi phục và lớp bọc khóa mã hóa của hồ sơ."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import StorageError, UnlockError, ValidationError


SUFFIX = ".vaultkey"
FILE_TYPE = (("Khóa khôi phục VaultSafe", f"*{SUFFIX}"),)
SIGNATURE = b"VaultSafeRecovery\x01"
FILE_SIZE = len(SIGNATURE) + 32 + 32
INVALID = "Tệp khóa không đúng với hồ sơ này, đã bị thay thế hoặc bị hỏng."
MISSING = "Hồ sơ này chưa có tệp khóa khôi phục. Nếu còn bản sao .vaultsafe, hãy dùng chức năng Khôi phục bản sao."


def filename(name):
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:60]
    return f"VaultSafe-{safe or 'Kho'}{SUFFIX}"


def _aad(record):
    return b"VaultSafe Recovery v1\0" + record.profile_id.encode("ascii") + record.salt


def wrap(record, secret, key):
    nonce = os.urandom(12)
    return nonce + AESGCM(secret).encrypt(nonce, key, _aad(record))


def unwrap(record, secret, capsule):
    if not isinstance(capsule, bytes) or len(capsule) != 60:
        raise UnlockError(INVALID)
    try:
        return AESGCM(secret).decrypt(capsule[:12], capsule[12:], _aad(record))
    except InvalidTag:
        raise UnlockError(INVALID) from None


def read_secret(path, profile_id):
    try:
        with Path(path).open("rb") as source:
            contents = source.read(FILE_SIZE + 1)
    except OSError:
        raise StorageError("Không đọc được tệp khóa khôi phục đã chọn.") from None
    if len(contents) != FILE_SIZE or not contents.startswith(SIGNATURE + profile_id.encode("ascii")):
        raise UnlockError(INVALID)
    return contents[-32:]


@contextmanager
def publish_file(path, profile_id, secret):
    """Publish a complete new key before committing the corresponding database row."""
    destination = Path(path)
    contents = SIGNATURE + profile_id.encode("ascii") + secret
    temporary = None
    try:
        with NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        if os.name == "nt":
            temporary.rename(destination)
            temporary = None
        else:
            os.link(temporary, destination)
    except FileExistsError:
        raise ValidationError("Tệp đích đã tồn tại. Hãy chọn tên tệp mới.") from None
    except OSError:
        raise StorageError("Không lưu được tệp khóa khôi phục.") from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    try:
        yield
    except Exception:
        try:
            with destination.open("rb") as source:
                original = source.read(FILE_SIZE + 1) == contents
            if original:
                destination.unlink()
        except OSError:
            pass
        raise
