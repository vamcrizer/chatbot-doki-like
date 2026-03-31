"""
Tầng 3 — Integration Tests: Redis session, DB write-behind, state persistence.
Cần Redis & PostgreSQL thật (hoặc testcontainers).
Nếu infra không available → skip toàn bộ.
"""
import pytest
import json
import threading
import time
from unittest.mock import patch, MagicMock

# ── Skip marker: skip nếu không có Redis/PG ──────────────────

try:
    import redis
    _r = redis.Redis(host="localhost", port=6379, socket_timeout=1)
    _r.ping()
    HAS_REDIS = True
except Exception:
    HAS_REDIS = False

requires_redis = pytest.mark.skipif(
    not HAS_REDIS, reason="Redis not available on localhost:6379"
)


# ═══════════════════════════════════════════════════════════════
# 3.1 — DB Write-Behind Buffer (no external deps needed)
# ═══════════════════════════════════════════════════════════════

class TestDBBuffer:
    """core/db_buffer.py — thread-safe queue, flush logic."""

    def setup_method(self):
        """Reset buffer state before each test."""
        from core.db_buffer import _queue, _lock
        with _lock:
            _queue.clear()

    def test_enqueue_increments_count(self):
        from core.db_buffer import enqueue, get_pending_count
        assert get_pending_count() == 0
        enqueue("user1", "kael", "user", "hello", 1)
        assert get_pending_count() == 1

    def test_enqueue_multiple(self):
        from core.db_buffer import enqueue, get_pending_count
        for i in range(50):
            enqueue("user1", "kael", "user", f"msg {i}", i)
        assert get_pending_count() == 50

    def test_should_flush_early_below_threshold(self):
        from core.db_buffer import enqueue, should_flush_early
        for i in range(10):
            enqueue("user1", "kael", "user", f"msg {i}", i)
        assert should_flush_early() is False

    def test_should_flush_early_above_threshold(self):
        from core.db_buffer import enqueue, should_flush_early, FLUSH_THRESHOLD
        for i in range(FLUSH_THRESHOLD + 1):
            enqueue("user1", "kael", "user", f"msg {i}", i)
        assert should_flush_early() is True

    def test_flush_without_db_returns_zero(self):
        """Flush without DATABASE_URL discards messages gracefully."""
        from core.db_buffer import enqueue, flush, get_pending_count
        enqueue("user1", "kael", "user", "test", 1)
        with patch("core.db_buffer.get_session_factory") as mock:
            mock.return_value = None
            result = flush()
            assert result == 0
        assert get_pending_count() == 0  # queue was drained

    def test_flush_empty_queue_returns_zero(self):
        from core.db_buffer import flush
        with patch("core.db_buffer.get_session_factory") as mock:
            mock.return_value = None
            assert flush() == 0

    def test_enqueue_thread_safety(self):
        """Concurrent enqueue from multiple threads should not lose messages."""
        from core.db_buffer import enqueue, get_pending_count

        def worker(n):
            for i in range(100):
                enqueue(f"user_{n}", "kael", "user", f"msg {i}", i)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert get_pending_count() == 500  # 5 threads × 100 messages


# ═══════════════════════════════════════════════════════════════
# 3.2 — Session Serialization Roundtrip (no external deps)
# ═══════════════════════════════════════════════════════════════

class TestSessionSerialization:
    """UserSession → Redis JSON → UserSession roundtrip."""

    def test_affection_survives_json_roundtrip(self):
        from state.affection import AffectionState
        original = AffectionState(
            mood="warm", mood_intensity=7,
            desire_level=5, relationship_score=42,
            relationship_label="close",
            boundary_violated=True,
            recovery_turns_remaining=3,
        )
        data = original.to_dict()
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = AffectionState.from_dict(restored_data)
        assert restored.mood == "warm"
        assert restored.relationship_score == 42
        assert restored.boundary_violated is True
        assert restored.recovery_turns_remaining == 3

    def test_scene_survives_json_roundtrip(self):
        from state.scene import SceneTracker
        tracker = SceneTracker(initial_scene="bar")
        tracker.update("let's walk outside in the park tonight")
        data = tracker.to_dict()
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = SceneTracker.from_dict(restored_data)
        assert restored.current_scene == tracker.current_scene
        assert restored.previous_scene == tracker.previous_scene

    def test_conversation_survives_json_roundtrip(self):
        from core.conversation import ConversationManager
        mgr = ConversationManager()
        mgr.add_user("Hello")
        mgr.add_assistant("Hi there!")
        data = mgr.to_dict()
        json_str = json.dumps(data)
        restored_data = json.loads(json_str)
        restored = ConversationManager.from_dict(restored_data)
        assert restored.history == mgr.history
        assert restored.total_turns == mgr.total_turns

    def test_all_state_combined_json_roundtrip(self):
        """Simulate full UserSession serialization."""
        from state.affection import AffectionState
        from state.scene import SceneTracker
        from core.conversation import ConversationManager

        session_data = {
            "affection": AffectionState(relationship_score=50, relationship_label="close").to_dict(),
            "scene": SceneTracker(initial_scene="home").to_dict(),
            "conversation": ConversationManager().to_dict(),
        }
        json_str = json.dumps(session_data)
        restored = json.loads(json_str)

        aff = AffectionState.from_dict(restored["affection"])
        scene = SceneTracker.from_dict(restored["scene"])
        conv = ConversationManager.from_dict(restored["conversation"])

        assert aff.relationship_score == 50
        assert scene.current_scene == "home"
        assert conv.total_turns == 0


# ═══════════════════════════════════════════════════════════════
# 3.3 — Redis Session Tests (requires Redis)
# ═══════════════════════════════════════════════════════════════

@requires_redis
class TestRedisSession:
    """Live Redis session get/set. Requires Redis on localhost:6379."""

    def _get_redis(self):
        return redis.Redis(host="localhost", port=6379, decode_responses=True)

    def test_session_set_get_roundtrip(self):
        r = self._get_redis()
        key = "test:session:roundtrip"
        data = {
            "mood": "warm",
            "relationship_score": 25,
            "relationship_label": "friend",
        }
        r.set(key, json.dumps(data), ex=60)
        restored = json.loads(r.get(key))
        assert restored["mood"] == "warm"
        assert restored["relationship_score"] == 25
        r.delete(key)

    def test_session_ttl_applied(self):
        r = self._get_redis()
        key = "test:session:ttl"
        r.set(key, "value", ex=10)
        ttl = r.ttl(key)
        assert 0 < ttl <= 10
        r.delete(key)

    def test_session_overwrite(self):
        r = self._get_redis()
        key = "test:session:overwrite"
        r.set(key, json.dumps({"score": 10}), ex=60)
        r.set(key, json.dumps({"score": 50}), ex=60)
        data = json.loads(r.get(key))
        assert data["score"] == 50
        r.delete(key)

    def test_nonexistent_session_returns_none(self):
        r = self._get_redis()
        result = r.get("test:session:nonexistent:12345")
        assert result is None

    def test_concurrent_session_writes(self):
        """Concurrent writes to different keys should not interfere."""
        r = self._get_redis()
        errors = []

        def writer(user_id, score):
            try:
                key = f"test:session:concurrent:{user_id}"
                r.set(key, json.dumps({"score": score}), ex=60)
                time.sleep(0.05)
                data = json.loads(r.get(key))
                assert data["score"] == score
                r.delete(key)
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=writer, args=(f"user_{i}", i * 10))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent errors: {errors}"


# ═══════════════════════════════════════════════════════════════
# 3.4 — Rate Limit Integration (requires Redis)
# ═══════════════════════════════════════════════════════════════

@requires_redis
class TestRateLimitRedis:
    """Rate limit via Redis sorted set."""

    def _get_redis(self):
        return redis.Redis(host="localhost", port=6379, decode_responses=True)

    def test_sliding_window_count(self):
        r = self._get_redis()
        key = "test:ratelimit:sliding"
        r.delete(key)

        now = time.time()
        for i in range(5):
            r.zadd(key, {f"{now + i}": now + i})

        count = r.zcard(key)
        assert count == 5
        r.delete(key)

    def test_expired_entries_removed(self):
        r = self._get_redis()
        key = "test:ratelimit:expired"
        r.delete(key)

        now = time.time()
        # Add old entries (1 hour ago)
        for i in range(3):
            r.zadd(key, {f"old_{i}": now - 7200 + i})
        # Add recent entries
        for i in range(2):
            r.zadd(key, {f"new_{i}": now + i})

        # Remove entries older than 1 hour
        r.zremrangebyscore(key, 0, now - 3600)
        count = r.zcard(key)
        assert count == 2
        r.delete(key)
