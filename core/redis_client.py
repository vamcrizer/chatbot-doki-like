"""
Redis Client — centralized Redis connection for the application.

Used for:
  - Immersion anchor cache (character:lang -> anchor)
  - TODO: Session state (conversation window, affection, scene)
  - TODO: Rate limiting counters

Graceful fallback: returns None if REDIS_URL is not configured,
allowing callers to handle the no-Redis case.
"""
import json
import logging
from typing import Optional

logger = logging.getLogger("dokichat.redis")

_redis_client = None
_initialized = False


def _init_redis():
    """Initialize Redis connection. Called once on first use."""
    global _redis_client, _initialized

    if _initialized:
        return

    _initialized = True

    from config import get_settings
    settings = get_settings()

    if not settings.REDIS_URL:
        logger.warning("REDIS_URL not set — Redis features disabled")
        return

    try:
        import redis
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        _redis_client.ping()
        logger.info(f"Redis connected: {settings.REDIS_URL}")
    except ImportError:
        logger.warning("redis package not installed — pip install redis")
        _redis_client = None
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        _redis_client = None


def get_redis():
    """Get Redis client instance. Returns None if unavailable."""
    _init_redis()
    return _redis_client


# ══════════════════════════════════════════════════════════════
# HIGH-LEVEL HELPERS
# ══════════════════════════════════════════════════════════════

def cache_get(key: str) -> Optional[dict]:
    """Get a JSON value from Redis cache. Returns None on miss or error."""
    r = get_redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning(f"Redis GET error [{key}]: {e}")
    return None


def cache_set(key: str, value: dict, ttl_seconds: int = 0) -> bool:
    """Set a JSON value in Redis cache. Returns True on success."""
    r = get_redis()
    if r is None:
        return False
    try:
        raw = json.dumps(value, ensure_ascii=False)
        if ttl_seconds > 0:
            r.setex(key, ttl_seconds, raw)
        else:
            r.set(key, raw)
        return True
    except Exception as e:
        logger.warning(f"Redis SET error [{key}]: {e}")
    return False


# ══════════════════════════════════════════════════════════════
# SESSION HELPERS — with TTL auto-expiry
# ══════════════════════════════════════════════════════════════

SESSION_TTL = 1800  # 30 minutes — session auto-expires when user stops chatting


def session_save(user_id: str, character_id: str, data: dict) -> bool:
    """Save session state to Redis with TTL.

    Every save resets the 30-minute TTL timer.
    When user stops chatting, session auto-deletes from Redis.
    """
    key = f"session:{user_id}:{character_id}"
    return cache_set(key, data, ttl_seconds=SESSION_TTL)


def session_load(user_id: str, character_id: str) -> Optional[dict]:
    """Load session state from Redis. Returns None if expired or missing."""
    key = f"session:{user_id}:{character_id}"
    return cache_get(key)
