"""
Nhóm 1.1 — Unit Tests: core/conversation.py
Quản Lý Cửa Sổ Chat — sliding window, token budget, format invariants.
"""
import pytest
from core.conversation import ConversationManager, _estimate_tokens


class TestEstimateTokens:
    """1 token ≈ 4 chars."""

    def test_empty_string(self):
        assert _estimate_tokens("") == 1  # max(1, 0)

    def test_short_string(self):
        assert _estimate_tokens("Hi") == 1  # max(1, 0)

    def test_normal_string(self):
        result = _estimate_tokens("Hello, how are you doing today?")
        assert 5 <= result <= 12  # roughly 30 chars / 4 = 7

    def test_long_string(self):
        text = "x" * 4000
        result = _estimate_tokens(text)
        assert result == 1000  # 4000 / 4


class TestConversationManager:

    def _build_conversation(self, turns: int) -> ConversationManager:
        """Helper: build a conversation with N complete turns."""
        mgr = ConversationManager(max_turns=10, min_turns=5)
        for i in range(turns):
            mgr.add_user(f"User message {i}")
            mgr.add_assistant(f"Assistant reply {i}")
        return mgr

    # ── Invariant: window starts with user, never assistant ──
    def test_window_starts_with_user_role(self):
        mgr = self._build_conversation(5)
        window = mgr.get_window()
        assert window[0]["role"] == "user"

    def test_window_starts_with_user_after_many_turns(self):
        mgr = self._build_conversation(20)
        window = mgr.get_window()
        assert window[0]["role"] == "user"

    # ── No consecutive same-role messages in window ──
    def test_no_consecutive_same_role(self):
        mgr = self._build_conversation(10)
        window = mgr.get_window()
        for i in range(1, len(window)):
            assert window[i]["role"] != window[i-1]["role"], \
                f"Consecutive {window[i]['role']} at index {i}"

    # ── Empty conversation still works ──
    def test_empty_conversation_window(self):
        mgr = ConversationManager()
        window = mgr.get_window()
        assert window == []

    def test_empty_conversation_token_count(self):
        mgr = ConversationManager()
        assert mgr.get_token_count() == 0

    # ── Single user message (no assistant) ──
    def test_single_user_no_crash(self):
        mgr = ConversationManager()
        mgr.add_user("Hello")
        window = mgr.get_window()
        assert len(window) == 1
        assert window[0]["role"] == "user"

    # ── Total turns counter ──
    def test_total_turns_increment(self):
        mgr = ConversationManager()
        mgr.add_user("Hi")
        mgr.add_assistant("Hello")
        assert mgr.total_turns == 1
        mgr.add_user("How are you")
        mgr.add_assistant("Good")
        assert mgr.total_turns == 2

    # ── Rollback: pop_last_assistant ──
    def test_pop_last_assistant(self):
        mgr = self._build_conversation(3)
        old_turns = mgr.total_turns
        popped = mgr.pop_last_assistant()
        assert popped == "Assistant reply 2"
        assert mgr.total_turns == old_turns - 1

    def test_pop_last_assistant_empty(self):
        mgr = ConversationManager()
        assert mgr.pop_last_assistant() is None

    def test_pop_last_assistant_only_user(self):
        mgr = ConversationManager()
        mgr.add_user("Hello")
        assert mgr.pop_last_assistant() is None

    # ── get_last_user_message ──
    def test_get_last_user_message(self):
        mgr = self._build_conversation(3)
        assert mgr.get_last_user_message() == "User message 2"

    def test_get_last_user_message_empty(self):
        mgr = ConversationManager()
        assert mgr.get_last_user_message() is None

    # ── Sliding window cuts from beginning ──
    def test_sliding_window_cuts_old_messages(self):
        mgr = ConversationManager(max_turns=3)
        for i in range(10):
            mgr.add_user(f"User {i}")
            mgr.add_assistant(f"Asst {i}")
        window = mgr.get_window()
        # Should contain mostly recent messages
        assert len(window) <= 10  # max_turns * 2
        if window:
            assert window[-1]["content"] == "Asst 9"

    # ── has_memory reduces window ──
    def test_has_memory_uses_smaller_budget(self):
        mgr = ConversationManager(max_turns=10, min_turns=3)
        for i in range(10):
            mgr.add_user(f"Message {i}")
            mgr.add_assistant(f"Reply {i}")
        normal_window = mgr.get_window(has_memory=False)
        memory_window = mgr.get_window(has_memory=True)
        assert len(memory_window) <= len(normal_window)

    # ── Serialization ──
    def test_serialize_deserialize(self):
        mgr = self._build_conversation(5)
        data = mgr.to_dict()
        restored = ConversationManager.from_dict(data)
        assert restored.total_turns == mgr.total_turns
        assert restored.history == mgr.history
        assert restored.max_turns == mgr.max_turns

    def test_deserialize_empty_dict(self):
        mgr = ConversationManager.from_dict({})
        assert mgr.total_turns == 0
        assert mgr.history == []

    # ── Clear ──
    def test_clear(self):
        mgr = self._build_conversation(5)
        mgr.clear()
        assert mgr.total_turns == 0
        assert mgr.history == []
