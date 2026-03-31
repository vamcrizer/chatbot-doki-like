"""
Rate limiting middleware — character generation rate limit.

Chat rate limiting is handled directly in chat.py via check_rate_limit().
This middleware limits character generation to CHARGEN_LIMIT per hour per user,
using the JWT token to identify the user (avoids body reads that break routing).
"""
import os
import time
import logging
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("ai_companion.ratelimit")

CHARGEN_LIMIT = 5
CHARGEN_WINDOW = 3600
IS_PRODUCTION = os.getenv("AI_COMPANION_ENV", "dev").lower() == "production"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not IS_PRODUCTION:
            return await call_next(request)

        if request.url.path == "/character/create" and request.method == "POST":
            user_id = self._extract_user_id(request)
            if user_id:
                self._check_chargen_limit(user_id)

        return await call_next(request)

    @staticmethod
    def _extract_user_id(request: Request) -> str | None:
        """Extract user_id from JWT Authorization header without reading the body."""
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.removeprefix("Bearer ").strip()
        if not token:
            return None
        try:
            from api.auth import decode_access_token
            return decode_access_token(token)
        except Exception:
            return None

    @staticmethod
    def _check_chargen_limit(user_id: str) -> None:
        """Raise 429 if user exceeds CHARGEN_LIMIT generations per hour."""
        try:
            from core.redis_client import get_redis
            r = get_redis()
            if not r:
                return  # fail-open when Redis unavailable
            key = f"ratelimit:chargen:{user_id}"
            now = time.time()
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - CHARGEN_WINDOW)
            pipe.zadd(key, {f"{now}": now})
            pipe.zcard(key)
            pipe.expire(key, CHARGEN_WINDOW + 1)
            results = pipe.execute()
            if results[2] > CHARGEN_LIMIT:
                logger.warning("Chargen rate limit exceeded for user %s", user_id)
                raise HTTPException(
                    429,
                    detail=f"Rate limit: {CHARGEN_LIMIT} character generations per hour",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Chargen rate limit check error: %s", exc)
            # fail-open
