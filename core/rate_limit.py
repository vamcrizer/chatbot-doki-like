"""
Rate Limiter — Redis ZSET sliding window.

Uses sorted sets to count messages per user in a rolling 60-second window.
Returns 429 if user exceeds MAX_REQUESTS_PER_MINUTE.

Graceful: if Redis is down, rate limiting is SKIPPED (fail-open).
"""
import time
import logging
from core.redis_client import get_redis

logger = logging.getLogger("ai_companion.ratelimit")

MAX_REQUESTS_PER_MINUTE = 30


def check_rate_limit(user_id: str) -> bool:
    """Check if user is within rate limit.

    Returns True if allowed, False if rate-limited (should return 429).
    Uses Redis ZSET sliding window: O(1) amortized.
    """
    r = get_redis()
    if r is None:
        # No Redis → fail-open, allow all requests
        return True

    key = f"ratelimit:{user_id}"
    now = time.time()
    window_start = now - 60  # 60-second window

    try:
        pipe = r.pipeline()
        # Remove entries older than 60 seconds
        pipe.zremrangebyscore(key, 0, window_start)
        # Add current request
        pipe.zadd(key, {f"{now}": now})
        # Count requests in window
        pipe.zcard(key)
        # Auto-expire key after 61 seconds (cleanup)
        pipe.expire(key, 61)
        results = pipe.execute()

        request_count = results[2]  # ZCARD result

        if request_count > MAX_REQUESTS_PER_MINUTE:
            logger.warning("Rate limited user %s: %d req/min", user_id, request_count)
            return False

        return True

    except Exception as e:
        logger.warning("Rate limit check error: %s", e)
        # Fail-open on Redis errors
        return True
