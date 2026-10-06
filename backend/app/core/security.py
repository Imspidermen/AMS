import hashlib
import hmac
import secrets
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        return password_hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_secret() -> str:
    return secrets.token_urlsafe(40)


def secret_hash(value: str) -> str:
    key = settings.session_secret.encode("utf-8")
    if len(key) < 32:
        raise RuntimeError("SESSION_SECRET must contain at least 32 characters")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def opaque_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_password_policy(password: str) -> None:
    if len(password) < 12 or len(password) > 256:
        raise ValueError("Password must contain 12–256 characters")
    if not any(character.isalpha() for character in password) or not any(character.isdigit() for character in password):
        raise ValueError("Password must include at least one letter and one number")
