class ConversationManager:
    def __init__(self, max_turns: int = 10, min_turns: int = 5):
        self.max_turns    = max_turns   # full window (no memory)
        self.min_turns    = min_turns   # reduced window (has memory summary)
        self.history:     list[dict] = []
        self.total_turns: int = 0

    def add_user(self, content: str):
        self.history.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self.history.append({"role": "assistant", "content": content})
        self.total_turns += 1

    def get_window(self, has_memory: bool = False) -> list[dict]:
        """Return sliding window of recent messages.

        Args:
            has_memory: if True, use smaller window (memory fills the gap)
        """
        effective_turns = self.min_turns if has_memory else self.max_turns
        return self.history[-(effective_turns * 2):]

    def clear(self):
        self.history      = []
        self.total_turns  = 0
