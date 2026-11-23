"""Sinh mật khẩu và đánh giá cục bộ dùng chung cho giao diện kho."""

from collections import Counter
from collections.abc import Iterable
import secrets

from .models import Account, AuditFindings


MIN_PASSWORD_LENGTH = 12
MIN_CHARACTER_GROUPS = 3


def password_weak_reason(password: str) -> str:
    reasons = []
    if len(password) < MIN_PASSWORD_LENGTH:
        reasons.append(f"ít hơn {MIN_PASSWORD_LENGTH} ký tự")
    character_groups = sum((
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
        any(not char.isalnum() and not char.isspace() for char in password),
    ))
    if character_groups < MIN_CHARACTER_GROUPS:
        reasons.append(f"chỉ có {character_groups}/{MIN_CHARACTER_GROUPS} nhóm ký tự yêu cầu")
    return "Mật khẩu " + " và ".join(reasons) + "." if reasons else ""


def audit_accounts(accounts: Iterable[Account]) -> AuditFindings:
    eligible = tuple(account for account in accounts
                     if account.kind == "login" and not account.trashed and account.password)
    occurrences = Counter(account.password for account in eligible)
    findings = AuditFindings()
    for account in eligible:
        reason = password_weak_reason(account.password)
        if reason:
            findings.weak[account.id] = reason
        other_accounts = occurrences[account.password] - 1
        if other_accounts:
            findings.reused[account.id] = (
                f"Trùng mật khẩu với {other_accounts} tài khoản khác trong hồ sơ."
            )
    return findings


def generate_password(length: int, groups: list[str]) -> str:
    if not groups or any(not group for group in groups):
        raise ValueError("Chọn ít nhất một nhóm ký tự hợp lệ.")
    if length < len(groups):
        raise ValueError("Độ dài quá ngắn để có ký tự từ mọi nhóm đã chọn.")
    random = secrets.SystemRandom()
    characters = [random.choice(group) for group in groups]
    pool = "".join(groups)
    characters.extend(random.choice(pool) for _ in range(length - len(characters)))
    random.shuffle(characters)
    return "".join(characters)
