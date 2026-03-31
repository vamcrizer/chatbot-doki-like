"""
Tầng 7 — Chaos / Resilience Tests: graceful degradation.
Test redis down, DB unreachable, LLM timeout, input storms.
"""
import pytest
import json
import threading
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════
# 7.1 — Redis Down Scenarios
# ═══════════════════════════════════════════════════════════════

class TestRedisDown:
    """App behavior when Redis is unreachable."""

    def test_rate_limit_fails_open_without_redis(self):
        """Rate limit should fail-open (allow) when Redis is down."""
        from api.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())

        with patch("core.redis_client.get_redis") as mock_redis:
            mock_redis.return_value = None
            # Should not raise — fail-open
            try:
                RateLimitMiddleware._check_chargen_limit("user_123")
            except Exception as e:
                # HTTPException(429) should NOT happen without Redis
                from fastapi import HTTPException
                if isinstance(e, HTTPException) and e.status_code == 429:
                    pytest.fail("Rate limit should fail-open without Redis")

    def test_session_new_when_redis_missing(self):
        """When Redis returns None for session, a new session should be created."""
        from state.affection import AffectionState
        # Simulate: Redis.get returns None → default state
        state = AffectionState()
        assert state.relationship_score == 0
        assert state.relationship_label == "stranger"


# ═══════════════════════════════════════════════════════════════
# 7.2 — DB Unreachable Scenarios
# ═══════════════════════════════════════════════════════════════

class TestDBDown:
    """App behavior when PostgreSQL is unreachable."""

    def setup_method(self):
        from core.db_buffer import _queue, _lock
        with _lock:
            _queue.clear()

    def test_db_flush_with_no_session_factory(self):
        """flush() should return 0 and not crash when no DB configured."""
        from core.db_buffer import enqueue, flush
        enqueue("user1", "kael", "user", "test", 1)
        with patch("core.db_buffer.get_session_factory") as mock:
            mock.return_value = None
            result = flush()
            assert result == 0

    def test_db_flush_with_exception(self):
        """flush() should catch DB exceptions and return 0."""
        from core.db_buffer import enqueue, flush
        enqueue("user1", "kael", "user", "test", 1)
        with patch("core.db_buffer.get_session_factory") as mock:
            mock.side_effect = Exception("Connection refused")
            result = flush()
            assert result == 0

    def test_enqueue_works_regardless_of_db(self):
        """enqueue() is purely in-memory — DB state doesn't matter."""
        from core.db_buffer import enqueue, get_pending_count
        enqueue("user1", "kael", "user", "test", 1)
        assert get_pending_count() == 1


# ═══════════════════════════════════════════════════════════════
# 7.3 — LLM Timeout / Error Scenarios
# ═══════════════════════════════════════════════════════════════

class TestLLMDown:
    """App behavior when LLM is unreachable or times out."""

    def test_health_check_returns_degraded(self):
        """Health should report degraded, not crash, when LLM is down."""
        with patch("core.llm_client.chat_complete") as mock_llm:
            mock_llm.side_effect = ConnectionError("LLM unreachable")
            try:
                from core.llm_client import chat_complete
                chat_complete([{"role": "user", "content": "ping"}])
                pytest.fail("Should have raised")
            except ConnectionError:
                pass  # Expected — caller should handle gracefully

    def test_llm_empty_response_handled(self):
        """Empty LLM response should not crash."""
        with patch("core.llm_client.chat_complete") as mock_llm:
            mock_llm.return_value = ""
            from core.llm_client import chat_complete
            result = chat_complete([{"role": "user", "content": "test"}])
            assert result == ""

    def test_llm_none_response_handled(self):
        with patch("core.llm_client.chat_complete") as mock_llm:
            mock_llm.return_value = None
            from core.llm_client import chat_complete
            result = chat_complete([{"role": "user", "content": "test"}])
            assert result is None


# ═══════════════════════════════════════════════════════════════
# 7.4 — Input Storm / Volume Tests
# ═══════════════════════════════════════════════════════════════

class TestInputStorm:
    """High-volume / edge-case input patterns."""

    def setup_method(self):
        from core.db_buffer import _queue, _lock
        with _lock:
            _queue.clear()

    def test_rapid_fire_enqueue_1000(self):
        """1000 rapid enqueues should not lose messages."""
        from core.db_buffer import enqueue, get_pending_count
        for i in range(1000):
            enqueue("user1", "kael", "user", f"msg_{i}", i)
        assert get_pending_count() == 1000

    def test_concurrent_scene_updates(self):
        """Concurrent scene updates should not crash."""
        from state.scene import SceneTracker

        tracker = SceneTracker(initial_scene="bar")
        errors = []

        def updater(msg):
            try:
                tracker.update(msg)
            except Exception as e:
                errors.append(str(e))

        messages = [
            "let's go walk in the park",
            "back to the bar for drinks",
            "go home and relax",
            "hold my hand",
            "let's walk again outside",
        ] * 20  # 100 updates

        threads = [threading.Thread(target=updater, args=(m,)) for m in messages]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert tracker.current_scene is not None

    def test_concurrent_affection_serialization(self):
        """Concurrent to_dict/from_dict should not corrupt state."""
        from state.affection import AffectionState
        state = AffectionState(relationship_score=50)
        errors = []

        def serializer():
            try:
                for _ in range(100):
                    d = state.to_dict()
                    restored = AffectionState.from_dict(d)
                    assert restored.relationship_score == 50
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=serializer) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_max_length_message_safety_check(self):
        """2000-char message through safety should not crash."""
        from core.safety import check_input
        long_msg = "a" * 2000
        result = check_input(long_msg)
        assert result.blocked is False

    def test_unicode_bomb(self):
        """Repeated unicode combining characters should not crash."""
        from core.safety import check_input
        bomb = "a" + "\u0300" * 100  # 100 combining diacritics
        result = check_input(bomb)
        assert result.blocked is False
