"""
Conversation Manager — manages chat history with token-aware windowing.

Supports both turn-based (fallback) and token-based (preferred) window sizing
to prevent context overflow with variable-length prompts.
"""


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1 token per 3.5 chars for Vietnamese/English mix."""
    return max(1, len(text) // 4)


class ConversationManager:
    def __init__(self, max_turns: int = 10, min_turns: int = 5,
                 max_tokens: int = 4096, min_tokens: int = 2048):
        self.max_turns    = max_turns     # full window (no memory)
        self.min_turns    = min_turns     # reduced window (has memory summary)
        self.max_tokens   = max_tokens    # token budget for conversation window
        self.min_tokens   = min_tokens    # token budget when memory present
        self.history:     list[dict] = []
        self.total_turns: int = 0

    def add_user(self, content: str):
        self.history.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self.history.append({"role": "assistant", "content": content})
        self.total_turns += 1

    def get_window(self, has_memory: bool = False) -> list[dict]:
        """Return sliding window of recent messages.

        Uses token budget when possible, falls back to turn count.
        Always returns complete user-assistant pairs.

        Args:
            has_memory: if True, use smaller budget (memory fills the gap)
        """
        token_budget = self.min_tokens if has_memory else self.max_tokens
        max_turns = self.min_turns if has_memory else self.max_turns

        # Start from most recent, walk backwards counting tokens
        result = []
        tokens_used = 0
        pairs_added = 0

        # Walk backwards in pairs (assistant, user)
        for i in range(len(self.history) - 1, -1, -1):
            msg = self.history[i]
            msg_tokens = _estimate_tokens(msg["content"])

            if tokens_used + msg_tokens > token_budget and result:
                break
            if pairs_added >= max_turns * 2 and result:
                break

            result.insert(0, msg)
            tokens_used += msg_tokens
            pairs_added += 1

        # Ensure we start with a user message (not assistant)
        if result and result[0]["role"] == "assistant":
            result = result[1:]

        return result

    def get_token_count(self) -> int:
        """Get total tokens in full history."""
        return sum(_estimate_tokens(m["content"]) for m in self.history)

    def clear(self):
        self.history      = []
        self.total_turns  = 0
