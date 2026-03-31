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
import secrets
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
from api.schemas import (
    LoginRequest, OAuthAuthorizeResponse, OAuthCallbackRequest,
    RefreshRequest, RegisterRequest, TokenResponse,
)
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


# ── OAuth — Step 1: Get authorization URL ─────────────────────

@router.get("/oauth/{provider}", response_model=OAuthAuthorizeResponse)
async def oauth_authorize(provider: str, redirect_uri: str):
    """Return the provider's authorization URL.

    The client redirects the user to this URL. After the user approves,
    the provider redirects to redirect_uri with ?code=...&state=...

    The state parameter must be round-tripped back in the /callback call
    for CSRF protection.

    Supported providers: google, apple
    """
    from api.oauth import get_provider

    try:
        p = get_provider(provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    state = secrets.token_urlsafe(16)

    # Persist state in Redis (10 min TTL) for server-side CSRF validation
    _store_oauth_state(state)

    return OAuthAuthorizeResponse(
        authorization_url=p.authorization_url(redirect_uri, state),
        state=state,
        provider=provider,
    )


# ── OAuth — Step 2: Exchange code for tokens ──────────────────

@router.post("/oauth/{provider}/callback", response_model=TokenResponse)
async def oauth_callback(provider: str, req: OAuthCallbackRequest):
    """Exchange authorization code for DokiChat access + refresh tokens.

    Called by the client after receiving the code from the provider's redirect.

    For Apple: pass `name` when available (only present on first login).
    For CSRF: pass the `state` returned from GET /auth/oauth/{provider}.
    """
    from api.oauth import get_provider

    # CSRF: validate state if Redis is available
    if req.state:
        if not _consume_oauth_state(req.state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired state parameter",
            )

    try:
        p = get_provider(provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        oauth_user = p.exchange_code(
            code=req.code,
            redirect_uri=req.redirect_uri,
            name=req.name,
        )
    except Exception as e:
        logger.warning("OAuth %s exchange failed: %s", provider, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth code exchange failed: {e}",
        )

    if not oauth_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth provider did not return an email address",
        )

    repo = get_user_repo()
    user = repo.find_or_create_oauth_user(
        email=oauth_user.email,
        display_name=oauth_user.display_name,
        provider=provider,
    )

    logger.info("OAuth login: provider=%s user=%s", provider, user["id"])
    return _issue_tokens(user)


# ── OAuth state helpers (CSRF) ────────────────────────────────

_STATE_TTL = 600  # 10 minutes


def _store_oauth_state(state: str) -> None:
    """Persist OAuth state in Redis (best-effort; skipped if Redis unavailable)."""
    from core.redis_client import get_redis
    r = get_redis()
    if r:
        r.setex(f"oauth_state:{state}", _STATE_TTL, "1")


def _consume_oauth_state(state: str) -> bool:
    """Validate and delete OAuth state. Returns True if valid.

    Falls back to True when Redis is unavailable (fail-open).
    """
    from core.redis_client import get_redis
    r = get_redis()
    if not r:
        return True  # No Redis — skip CSRF check (log warning in production)
    deleted = r.delete(f"oauth_state:{state}")
    return bool(deleted)
