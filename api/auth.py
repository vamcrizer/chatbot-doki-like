"""
AI Companion — JWT & Password Utilities

Design:
  - Access token:  short-lived (30 min), HS256 JWT, sent as Bearer header
  - Refresh token: long-lived (7 days), random 48-byte token, stored SHA-256
                   hashed in auth_tokens table; rotated on every refresh
  - Passwords:     bcrypt via passlib
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import get_settings

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password ──────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return bcrypt hash of plain-text password."""
    return _pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Check plain-text password against bcrypt hash."""
    return _pwd_ctx.verify(plain, hashed)


# ── Access Token (JWT) ────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    """Create signed JWT access token.

    Payload:
      sub  — user_id (string)
      exp  — expiry (UTC)
    """
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.JWT_ACCESS_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": exp}
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    """Decode and verify JWT. Returns user_id string or None if invalid/expired."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except JWTError:
        return None


# ── Refresh Token ─────────────────────────────────────────────

def generate_refresh_token() -> tuple[str, str]:
    """Generate a secure refresh token pair.

    Returns:
        (raw_token, hashed_token)
        raw_token   — sent to client, never stored in DB
        hashed_token — stored in auth_tokens table
    """
    raw = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_refresh_token(raw: str) -> str:
    """Hash a raw refresh token for DB lookup."""
    return hashlib.sha256(raw.encode()).hexdigest()
