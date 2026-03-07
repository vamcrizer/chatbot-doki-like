class ConversationManager:
    def __init__(self, max_turns: int = 10):
        self.max_turns    = max_turns
        self.history:     list[dict] = []
        self.total_turns: int = 0

    def add_user(self, content: str):
        self.history.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self.history.append({"role": "assistant", "content": content})
        self.total_turns += 1

    def get_window(self) -> list[dict]:
        return self.history[-(self.max_turns * 2):]

    def clear(self):
        self.history      = []
        self.total_turns  = 0
