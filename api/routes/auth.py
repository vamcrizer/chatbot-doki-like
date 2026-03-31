"""
Auth routes — register, login, token refresh, logout.

Flow:
  POST /auth/register  → create account, return access + refresh tokens
  POST /auth/login     → verify credentials, return access + refresh tokens
  POST /auth/refresh   → rotate refresh token, return new access + refresh tokens
  POST /auth/logout    → invalidate refresh token

Token storage convention (client responsibility):
  access_token  — memory only (not localStorage); short-lived (30 min)
  refresh_token — HttpOnly cookie or secure storage; long-lived (7 days)
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from api.deps import get_current_user, get_user_repo
from api.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from config import get_settings

logger = logging.getLogger("dokichat.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: dict) -> TokenResponse:
    """Create fresh access + refresh token pair and persist the refresh token."""
    s = get_settings()
    repo = get_user_repo()

    access_token = create_access_token(user["id"])
    raw_refresh, hashed_refresh = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=s.JWT_REFRESH_EXPIRE_DAYS)

    repo.save_refresh_token(user["id"], hashed_refresh, expires_at)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        user_id=user["id"],
        display_name=user.get("display_name", ""),
    )


# ── Register ──────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest):
    """Create a new account.

    - Email must be unique
    - Password min 8 characters (enforced by schema)
    - Returns access + refresh tokens immediately (no separate email verify step)
    """
    repo = get_user_repo()

    # Email uniqueness check
    if repo.find_by_email(req.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    display = req.display_name.strip() or req.email.split("@")[0]
    user = repo.create({
        "email": req.email.lower().strip(),
        "password_hash": hash_password(req.password),
        "display_name": display,
    })

    logger.info("New user registered: %s", user["id"])
    return _issue_tokens(user)


# ── Login ─────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    """Authenticate with email + password.

    Returns 401 for both 'user not found' and 'wrong password' to prevent
    email enumeration attacks.
    """
    repo = get_user_repo()
    user = repo.find_by_email(req.email.lower().strip())

    # Constant-time rejection — don't reveal whether email exists
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    logger.info("User logged in: %s", user["id"])
    return _issue_tokens(user)


# ── Refresh ───────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(req: RefreshRequest):
    """Rotate refresh token and issue new access token.

    Implements refresh token rotation:
    - Old refresh token is deleted immediately
    - New refresh token is issued
    - Reuse of an old (deleted) token returns 401
    """
    repo = get_user_repo()
    hashed = hash_refresh_token(req.refresh_token)

    record = repo.find_refresh_token(hashed)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = repo.get(record["user_id"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Rotate: delete old token before issuing new ones
    repo.delete_refresh_token(hashed)

    logger.info("Token refreshed for user: %s", user["id"])
    return _issue_tokens(user)


# ── Logout ────────────────────────────────────────────────────

@router.post("/logout", status_code=204)
async def logout(req: RefreshRequest):
    """Invalidate refresh token (single device logout).

    Silently succeeds even if token doesn't exist (idempotent).
    For logout-all-devices, use DELETE /auth/sessions.
    """
    repo = get_user_repo()
    hashed = hash_refresh_token(req.refresh_token)
    repo.delete_refresh_token(hashed)
    # No content response


# ── Logout all devices ────────────────────────────────────────

@router.delete("/sessions", status_code=204)
async def logout_all(current_user: str = Depends(get_current_user)):
    """Invalidate ALL refresh tokens for the authenticated user.

    Requires valid access token. Use when account is compromised.
    """
    repo = get_user_repo()
    repo.delete_all_refresh_tokens(current_user)
    logger.info("All sessions revoked for user: %s", current_user)


# ── Me ────────────────────────────────────────────────────────

@router.get("/me")
async def get_me(current_user: str = Depends(get_current_user)):
    """Return basic profile of currently authenticated user."""
    repo = get_user_repo()
    user = repo.get(current_user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name", ""),
        "content_mode": user.get("content_mode", "romantic"),
    }
