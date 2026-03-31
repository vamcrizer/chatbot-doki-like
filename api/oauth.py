"""
AI Companion — OAuth2 Provider Integrations (Google, Apple)

Design:
  - Provider classes encapsulate all provider-specific logic
  - Both providers return a unified OAuthUser dataclass
  - No OAuth library dependency — uses httpx (already in stack) +
    python-jose (already in stack)

SPA / Mobile flow (recommended):
  1. Client:  GET  /auth/oauth/{provider}?redirect_uri=...
              → receives {authorization_url, state}
  2. Client:  redirects user to authorization_url
  3. Provider: redirects back to client's redirect_uri with ?code=...&state=...
  4. Client:  POST /auth/oauth/{provider}/callback {code, redirect_uri, state}
              → receives TokenResponse (access + refresh tokens)

Apple-specific notes:
  - client_secret is a short-lived JWT signed with your .p8 private key (ES256)
  - User's name is only sent on the FIRST authorization — pass it in the
    callback body's `name` field when available
  - response_mode=form_post is used for web flows; SPA intercepts and POSTs
    the code to /callback manually

Required env vars (set later):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  APPLE_CLIENT_ID (Service ID, e.g. com.yourapp.signin)
  APPLE_TEAM_ID, APPLE_KEY_ID
  APPLE_PRIVATE_KEY  (contents of .p8 file; escape newlines with \\n)
"""
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from jose import jwt as jose_jwt

from config import get_settings

logger = logging.getLogger("ai_companion.oauth")


# ── Unified user info ─────────────────────────────────────────

@dataclass
class OAuthUser:
    provider: str       # "google" | "apple"
    sub: str            # provider-unique user ID
    email: str
    display_name: str
    email_verified: bool


# ── Base ──────────────────────────────────────────────────────

class OAuthProvider:
    name: str

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        raise NotImplementedError

    def exchange_code(self, code: str, redirect_uri: str, **kwargs) -> OAuthUser:
        raise NotImplementedError

    def is_configured(self) -> bool:
        raise NotImplementedError


# ── Google ────────────────────────────────────────────────────

class GoogleProvider(OAuthProvider):
    name = "google"

    _AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
    _SCOPES = "openid email profile"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET)

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        s = get_settings()
        params = {
            "client_id": s.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._SCOPES,
            "access_type": "offline",
            "state": state,
            "prompt": "select_account",
        }
        return f"{self._AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str, **kwargs) -> OAuthUser:
        s = get_settings()

        # Exchange code for tokens
        with httpx.Client(timeout=10) as client:
            r = client.post(self._TOKEN_URL, data={
                "code": code,
                "client_id": s.GOOGLE_CLIENT_ID,
                "client_secret": s.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            r.raise_for_status()
            access_token = r.json()["access_token"]

            # Fetch user info
            r = client.get(
                self._USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            r.raise_for_status()
            info = r.json()

        return OAuthUser(
            provider="google",
            sub=info["sub"],
            email=info.get("email", "").lower(),
            display_name=info.get("name", ""),
            email_verified=info.get("email_verified", False),
        )


# ── Apple ─────────────────────────────────────────────────────

class AppleProvider(OAuthProvider):
    name = "apple"

    _AUTH_URL = "https://appleid.apple.com/auth/authorize"
    _TOKEN_URL = "https://appleid.apple.com/auth/token"
    _SCOPES = "name email"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(
            s.APPLE_CLIENT_ID
            and s.APPLE_TEAM_ID
            and s.APPLE_KEY_ID
            and s.APPLE_PRIVATE_KEY
        )

    def authorization_url(self, redirect_uri: str, state: str) -> str:
        s = get_settings()
        params = {
            "client_id": s.APPLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._SCOPES,
            "response_mode": "form_post",
            "state": state,
        }
        return f"{self._AUTH_URL}?{urlencode(params)}"

    def _client_secret(self) -> str:
        """Generate short-lived client_secret JWT (valid 3 min).

        Apple requires this instead of a static client_secret.
        Signed with ES256 using your .p8 private key.
        """
        s = get_settings()
        now = int(time.time())
        # .p8 files use \\n literals in env vars — normalize to real newlines
        private_key = s.APPLE_PRIVATE_KEY.replace("\\n", "\n")
        payload = {
            "iss": s.APPLE_TEAM_ID,
            "iat": now,
            "exp": now + 180,
            "aud": "https://appleid.apple.com",
            "sub": s.APPLE_CLIENT_ID,
        }
        return jose_jwt.encode(
            payload,
            private_key,
            algorithm="ES256",
            headers={"kid": s.APPLE_KEY_ID},
        )

    def exchange_code(self, code: str, redirect_uri: str, **kwargs) -> OAuthUser:
        """Exchange Apple authorization code.

        kwargs:
            name (str): user's display name — only present on first login.
                        Apple sends it in the form_post; client should pass it
                        through to this endpoint on first use.
        """
        s = get_settings()

        with httpx.Client(timeout=10) as client:
            r = client.post(self._TOKEN_URL, data={
                "code": code,
                "client_id": s.APPLE_CLIENT_ID,
                "client_secret": self._client_secret(),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
            r.raise_for_status()
            id_token = r.json().get("id_token", "")

        # Decode id_token claims (signature verification omitted here;
        # add full JWKS verification against APPLE_KEYS_URL for extra hardening)
        claims = jose_jwt.get_unverified_claims(id_token)

        email = claims.get("email", "").lower()
        # Apple may return a relay address — still treat as valid email
        sub = claims.get("sub", "")

        return OAuthUser(
            provider="apple",
            sub=sub,
            email=email,
            display_name=kwargs.get("name", "") or "",
            email_verified=claims.get("email_verified", False),
        )


# ── Registry ──────────────────────────────────────────────────

PROVIDERS: dict[str, OAuthProvider] = {
    "google": GoogleProvider(),
    "apple": AppleProvider(),
}


def get_provider(name: str) -> OAuthProvider:
    """Return configured provider or raise ValueError."""
    provider = PROVIDERS.get(name)
    if not provider:
        raise ValueError(f"Unknown OAuth provider: '{name}'. Supported: {list(PROVIDERS)}")
    if not provider.is_configured():
        raise ValueError(
            f"OAuth provider '{name}' is not configured. "
            f"Set the required env vars and restart."
        )
    return provider
