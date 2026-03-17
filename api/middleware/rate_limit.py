"""
Rate limiting middleware — in-memory, Phase 3 → Redis.

Limits:
  - 30 messages/minute per user
  - 5 character generations/hour per user
"""
import time
import logging
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("dokichat.ratelimit")


class RateLimitEntry:
    """Track request timestamps for a key."""
    def __init__(self):
        self.timestamps: list[float] = []

    def add(self):
        self.timestamps.append(time.time())

    def count_within(self, seconds: float) -> int:
        cutoff = time.time() - seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]
        return len(self.timestamps)


# Global rate limit store (Phase 3 → Redis)
_limits: dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)

# Config
CHAT_LIMIT = 30          # messages per minute
CHAT_WINDOW = 60         # seconds
CHARGEN_LIMIT = 5        # generations per hour
CHARGEN_WINDOW = 3600    # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only rate-limit specific endpoints
        path = request.url.path

        if path == "/chat/stream" and request.method == "POST":
            # Extract user_id from body — we peek at JSON
            try:
                body = await request.body()
                import json
                data = json.loads(body)
                user_id = data.get("user_id", "unknown")

                key = f"chat:{user_id}"
                entry = _limits[key]
                if entry.count_within(CHAT_WINDOW) >= CHAT_LIMIT:
                    logger.warning(f"Rate limit hit: {user_id} ({CHAT_LIMIT}/min)")
                    raise HTTPException(
                        429,
                        detail=f"Rate limit: {CHAT_LIMIT} messages per minute"
                    )
                entry.add()

                # Reconstruct request with body (since we consumed it)
                from starlette.requests import Request as StarletteRequest
                request = StarletteRequest(request.scope, receive=self._make_receive(body))

            except HTTPException:
                raise
            except Exception:
                pass  # Don't block on rate limit errors

        elif path == "/character/create" and request.method == "POST":
            try:
                body = await request.body()
                import json
                data = json.loads(body)
                user_id = data.get("user_id", request.client.host if request.client else "unknown")

                key = f"chargen:{user_id}"
                entry = _limits[key]
                if entry.count_within(CHARGEN_WINDOW) >= CHARGEN_LIMIT:
                    raise HTTPException(
                        429,
                        detail=f"Rate limit: {CHARGEN_LIMIT} character generations per hour"
                    )
                entry.add()

                request = Request(request.scope, receive=self._make_receive(body))

            except HTTPException:
                raise
            except Exception:
                pass

        response = await call_next(request)
        return response

    @staticmethod
    def _make_receive(body: bytes):
        """Create a receive callable that returns the body."""
        async def receive():
            return {"type": "http.request", "body": body}
        return receive
