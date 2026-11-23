"""Lỗi nghiệp vụ có thông báo an toàn để hiển thị trong UI."""


class VaultError(Exception):
    pass


class ValidationError(VaultError):
    pass


class StorageError(VaultError):
    pass


class FormatError(VaultError):
    pass


class UnlockError(VaultError):
    pass


class ConflictError(VaultError):
    pass


class SessionClosedError(VaultError):
    pass
