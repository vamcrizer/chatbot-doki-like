"""
Redis client — connection management with graceful fallback.

If REDIS_URL is not set, all operations use in-memory dict.
This means: sessions survive restarts with Redis, but not without.
"""
import json
import logging
from typing import Optional

from config import get_settings

logger = logging.getLogger("dokichat.cache")

_settings = get_settings()
_redis = None
_fallback: dict[str, str] = {}  # in-memory fallback


def get_redis():
    """Get Redis client. Returns None if not configured."""
    global _redis
    if _redis is not None:
        return _redis

    redis_url = _settings.REDIS_URL
    if not redis_url:
        logger.info("REDIS_URL not set — using in-memory cache")
        return None

    try:
        import redis
        _redis = redis.from_url(redis_url, decode_responses=True)
        _redis.ping()
        logger.info("Redis connected: %s...", redis_url[:30])
        return _redis
    except Exception as e:
        logger.warning("Redis connection failed: %s — using in-memory", e)
        return None


def cache_get(key: str) -> Optional[str]:
    """Get value from cache."""
    r = get_redis()
    if r:
        return r.get(key)
    return _fallback.get(key)


def cache_set(key: str, value: str, ttl: int = 3600):
    """Set value in cache with TTL (seconds)."""
    r = get_redis()
    if r:
        r.setex(key, ttl, value)
    else:
        _fallback[key] = value


def cache_delete(key: str):
    """Delete value from cache."""
    r = get_redis()
    if r:
        r.delete(key)
    else:
        _fallback.pop(key, None)


def cache_get_json(key: str) -> Optional[dict]:
    """Get JSON value from cache."""
    raw = cache_get(key)
    if raw:
        return json.loads(raw)
    return None


def cache_set_json(key: str, value: dict, ttl: int = 3600):
    """Set JSON value in cache."""
    cache_set(key, json.dumps(value, ensure_ascii=False), ttl)


def cache_incr(key: str, ttl: int = 60) -> int:
    """Increment counter for rate limiting."""
    r = get_redis()
    if r:
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        result = pipe.execute()
        return result[0]
    else:
        count = int(_fallback.get(key, "0")) + 1
        _fallback[key] = str(count)
        return count
