"""Argon2id và AES-GCM cho một bản ghi kho."""

import json
import secrets

from argon2.exceptions import HashingError
from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .errors import FormatError, UnlockError


FORMAT_VERSION = 1
KDF_VERSION = 19
MEMORY_KIB = 19_456
ITERATIONS = 2
PARALLELISM = 1
SALT_SIZE = 16
NONCE_SIZE = 12
MAX_PAYLOAD_SIZE = 16 * 1024 * 1024
UNLOCK_ERROR = "Không mở được kho. Hãy kiểm tra mật khẩu chính hoặc dữ liệu của hồ sơ."


def derive_key(password: str, salt: bytes, *, version=KDF_VERSION, memory_kib=MEMORY_KIB,
               iterations=ITERATIONS, parallelism=PARALLELISM) -> bytes:
    valid = (
        (version, KDF_VERSION, KDF_VERSION), (memory_kib, MEMORY_KIB, 65_536),
        (iterations, ITERATIONS, 4), (parallelism, PARALLELISM, 2),
    )
    if (not isinstance(salt, bytes) or len(salt) != SALT_SIZE
            or any(type(value) is not int or not low <= value <= high
                   for value, low, high in valid)):
        raise FormatError("Thông số Argon2id của hồ sơ không hợp lệ hoặc chưa được hỗ trợ.")
    try:
        return hash_secret_raw(password.encode("utf-8"), salt, iterations, memory_kib,
                               parallelism, 32, Type.ID, version=version)
    except (HashingError, UnicodeError):
        raise UnlockError(UNLOCK_ERROR) from None


def derive_cipher(password: str, salt: bytes, **parameters) -> AESGCM:
    return AESGCM(derive_key(password, salt, **parameters))


def _aad(profile_id: str, format_version: int, revision: int) -> bytes:
    return json.dumps(["VaultSafe", profile_id, format_version, revision],
                      separators=(",", ":")).encode("ascii")


def encrypt(cipher: AESGCM, profile_id: str, revision: int, payload: bytes) -> tuple[bytes, bytes]:
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise FormatError("Nội dung kho vượt quá giới hạn 16 MiB.")
    nonce = secrets.token_bytes(NONCE_SIZE)
    ciphertext = cipher.encrypt(nonce, payload, _aad(profile_id, FORMAT_VERSION, revision))
    return nonce, ciphertext


def decrypt(cipher: AESGCM, record) -> bytes:
    if (not isinstance(record.nonce, bytes) or len(record.nonce) != NONCE_SIZE
            or not isinstance(record.ciphertext, bytes)
            or not 16 <= len(record.ciphertext) <= MAX_PAYLOAD_SIZE + 16):
        raise UnlockError(UNLOCK_ERROR)
    try:
        return cipher.decrypt(record.nonce, record.ciphertext,
                              _aad(record.profile_id, record.format_version, record.revision))
    except InvalidTag:
        raise UnlockError(UNLOCK_ERROR) from None
