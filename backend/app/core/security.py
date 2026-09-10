import base64
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


# ---- Password hashing (bcrypt, real salted hashes — never plaintext) ----


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---- JWT access / refresh tokens ----


def _create_token(subject: str, secret: str, expires_delta: timedelta, token_type: TokenType, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    return _create_token(
        subject=str(user_id),
        secret=settings.jwt_secret,
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
        token_type=TokenType.ACCESS,
        extra={"tenant_id": str(tenant_id), "role": role},
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _create_token(
        subject=str(user_id),
        secret=settings.jwt_refresh_secret,
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
        token_type=TokenType.REFRESH,
    )


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != TokenType.ACCESS.value:
        raise JWTError("Not an access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_refresh_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != TokenType.REFRESH.value:
        raise JWTError("Not a refresh token")
    return payload


def hash_token(token: str) -> str:
    """One-way hash of a refresh token for storage (sessions table never stores raw tokens)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---- Camera credential encryption at rest (section 14/46) ----


def _fernet() -> Fernet:
    key_material = hashlib.sha256(settings.credential_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_secret(plain_text: str) -> str:
    if not plain_text:
        return ""
    return _fernet().encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    return _fernet().decrypt(cipher_text.encode("utf-8")).decode("utf-8")
