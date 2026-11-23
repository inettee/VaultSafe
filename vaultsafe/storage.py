"""Vị trí kho và các thao tác SQLite chỉ nhận dữ liệu đã mã hóa."""

from contextlib import contextmanager
from dataclasses import astuple, dataclass
import os
from pathlib import Path
import sqlite3

from .errors import ConflictError, FormatError, StorageError, ValidationError
from .models import ProfileInfo


SCHEMA_VERSION = 2
DATABASE_NAME = "vaultsafe.db"
DB_ERROR = "Không truy cập được dữ liệu VaultSafe. Hãy kiểm tra thư mục lưu và thử lại."


def default_data_dir() -> Path:
    override = os.environ.get("VAULTSAFE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    return (Path(local_app_data) if local_app_data else Path.home() / ".local" / "share") / "VaultSafe"


@dataclass(frozen=True, slots=True)
class VaultRecord:
    profile_id: str
    name: str
    salt: bytes
    kdf_version: int
    memory_kib: int
    iterations: int
    parallelism: int
    format_version: int
    nonce: bytes
    ciphertext: bytes
    revision: int


class VaultStorage:
    def __init__(self, data_dir: str | Path | None = None):
        self.path = (Path(data_dir) if data_dir is not None else default_data_dir()) / DATABASE_NAME

    @contextmanager
    def _connection(self, *, create=False):
        connection = None
        try:
            if create:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            # Once initialized, a missing file is a storage error instead of a fresh blank database.
            mode = "rwc" if create else "rw"
            connection = sqlite3.connect(
                f"{self.path.resolve().as_uri()}?mode={mode}", uri=True, timeout=0.25,
            )
            with connection:
                yield connection
        except (OSError, sqlite3.Error):
            raise StorageError(DB_ERROR) from None
        finally:
            if connection is not None:
                connection.close()

    def initialize(self):
        with self._connection(create=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            existing_schema = connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%' LIMIT 1",
            ).fetchone()
            if version == 1:
                # Read the previous table before altering a version-one database.
                connection.execute("SELECT profile_id, salt, ciphertext, revision FROM vaults LIMIT 0")
            elif version != 0 or existing_schema:
                raise FormatError("Phiên bản cơ sở dữ liệu VaultSafe chưa được hỗ trợ.")
            else:
                connection.execute("""
                CREATE TABLE vaults (
                    profile_id TEXT PRIMARY KEY NOT NULL,
                    name TEXT NOT NULL,
                    salt BLOB NOT NULL,
                    kdf_version INTEGER NOT NULL,
                    memory_kib INTEGER NOT NULL,
                    iterations INTEGER NOT NULL,
                    parallelism INTEGER NOT NULL,
                    format_version INTEGER NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1)
                )
                """)
            connection.execute("""
                CREATE TABLE vault_recovery (
                    profile_id TEXT PRIMARY KEY NOT NULL,
                    capsule BLOB NOT NULL
                )
            """)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def list_profiles(self) -> tuple[ProfileInfo, ...]:
        with self._connection() as connection:
            rows = connection.execute("SELECT profile_id, name FROM vaults").fetchall()
            if any(not isinstance(value, str) or not value for row in rows for value in row):
                raise FormatError("Danh sách hồ sơ trong cơ sở dữ liệu không hợp lệ.")
            return tuple(sorted((ProfileInfo(*row) for row in rows),
                                key=lambda row: row.name.casefold()))

    def read(self, profile_id: str) -> VaultRecord | None:
        with self._connection() as connection:
            row = connection.execute("""
                SELECT profile_id, name, salt, kdf_version, memory_kib, iterations, parallelism,
                       format_version, nonce, ciphertext, revision
                FROM vaults WHERE profile_id = ?
            """, (profile_id,)).fetchone()
            return VaultRecord(*row) if row else None

    def insert(self, record: VaultRecord, *, recovery=None):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            names = connection.execute("SELECT name FROM vaults").fetchall()
            if any(not isinstance(name, str) or not name for name, in names):
                raise FormatError("Danh sách hồ sơ trong cơ sở dữ liệu không hợp lệ.")
            if any(name.casefold() == record.name.casefold() for name, in names):
                raise ValidationError("Tên hồ sơ đã tồn tại.")
            connection.execute("""
                INSERT INTO vaults (profile_id, name, salt, kdf_version, memory_kib, iterations,
                                    parallelism, format_version, nonce, ciphertext, revision)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, astuple(record))
            if recovery is not None:
                connection.execute("INSERT INTO vault_recovery VALUES (?, ?)", (record.profile_id, recovery))

    def read_recovery(self, profile_id):
        with self._connection() as connection:
            row = connection.execute("SELECT capsule FROM vault_recovery WHERE profile_id = ?", (profile_id,)).fetchone()
            return row[0] if row else None

    def set_recovery(self, record, previous, capsule):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT revision FROM vaults WHERE profile_id = ?", (record.profile_id,)).fetchone()
            self._require_recovery_version(connection, record, previous, current)
            connection.execute("INSERT OR REPLACE INTO vault_recovery VALUES (?, ?)", (record.profile_id, capsule))

    def reset_password(self, record, updated, previous, capsule):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT revision FROM vaults WHERE profile_id = ?", (record.profile_id,)).fetchone()
            self._require_recovery_version(connection, record, previous, current)
            connection.execute("""
                UPDATE vaults SET salt = ?, kdf_version = ?, memory_kib = ?, iterations = ?, parallelism = ?,
                    format_version = ?, nonce = ?, ciphertext = ?, revision = ? WHERE profile_id = ?
            """, (updated.salt, updated.kdf_version, updated.memory_kib, updated.iterations,
                  updated.parallelism, updated.format_version, updated.nonce, updated.ciphertext,
                  updated.revision, updated.profile_id))
            connection.execute("UPDATE vault_recovery SET capsule = ? WHERE profile_id = ?", (capsule, record.profile_id))

    @staticmethod
    def _require_recovery_version(connection, record, previous, current):
        bound = connection.execute("SELECT capsule FROM vault_recovery WHERE profile_id = ?", (record.profile_id,)).fetchone()
        if current != (record.revision,) or (bound[0] if bound else None) != previous:
            raise ConflictError("Kho hoặc khóa khôi phục đã thay đổi. Hãy thử lại với dữ liệu mới nhất.")

    def update(self, profile_id: str, revision: int, nonce: bytes, ciphertext: bytes):
        with self._connection() as connection:
            cursor = connection.execute("""
                UPDATE vaults SET nonce = ?, ciphertext = ?, revision = revision + 1
                WHERE profile_id = ? AND revision = ?
            """, (nonce, ciphertext, profile_id, revision))
            if cursor.rowcount != 1:
                raise ConflictError(
                    "Kho đã thay đổi ở cửa sổ khác. Hãy khóa và mở lại kho trước khi lưu.",
                )
