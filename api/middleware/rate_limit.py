"""
Rate limiting middleware — delegates to core/rate_limit.py (Redis ZSET).

This middleware is kept for character generation rate limiting.
Chat rate limiting is handled directly in chat.py route.
"""
import time
import logging
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from core.rate_limit import check_rate_limit

logger = logging.getLogger("dokichat.ratelimit")

# Character generation: 5 per hour per user
CHARGEN_LIMIT = 5
CHARGEN_WINDOW = 3600


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Character generation rate limit
        if path == "/character/create" and request.method == "POST":
            try:
                body = await request.body()
                import json
                data = json.loads(body)
                user_id = data.get("user_id", "unknown")

                # Reuse Redis check with chargen-specific key
                from core.redis_client import get_redis
                r = get_redis()
                if r:
                    key = f"ratelimit:chargen:{user_id}"
                    now = time.time()
                    pipe = r.pipeline()
                    pipe.zremrangebyscore(key, 0, now - CHARGEN_WINDOW)
                    pipe.zadd(key, {f"{now}": now})
                    pipe.zcard(key)
                    pipe.expire(key, CHARGEN_WINDOW + 1)
                    results = pipe.execute()
                    if results[2] > CHARGEN_LIMIT:
                        raise HTTPException(
                            429,
                            detail=f"Rate limit: {CHARGEN_LIMIT} character generations per hour"
                        )

                # Reconstruct request with body
                from starlette.requests import Request as StarletteRequest
                request = StarletteRequest(request.scope, receive=self._make_receive(body))

            except HTTPException:
                raise
            except Exception:
                pass  # Fail-open

        response = await call_next(request)
        return response

    @staticmethod
    def _make_receive(body: bytes):
        async def receive():
            return {"type": "http.request", "body": body}
        return receive
