"""Password hashing (bcrypt, not passlib) and JWT helpers."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

ACCESS_TOKEN_TTL = timedelta(days=7)
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt, returning a str hash."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if the password matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash (e.g. not a valid bcrypt string) -> never match.
        return False


def create_access_token(user_id: int, role: str) -> str:
    """Create a signed JWT (HS256) valid for 7 days.

    Payload: sub=str(user_id), role, iat, exp.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT.

    Raises jwt.InvalidTokenError (base class, incl. ExpiredSignatureError)
    when the token is invalid, tampered, or expired.
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
