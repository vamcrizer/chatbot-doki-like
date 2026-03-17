"""
Chat Repository — persists conversation messages.

In-memory: stores in ConversationManager (existing).
PostgreSQL: stores in conversations table for cross-session recall.
"""
import logging
from typing import Optional
from datetime import datetime

from db.repositories.base import BaseRepository

logger = logging.getLogger("dokichat.repo.chat")


class InMemoryChatRepository(BaseRepository):
    """In-memory — uses existing ConversationManager per session."""

    def __init__(self):
        self._stores: dict[str, list[dict]] = {}  # key → message list

    def _key(self, user_id: str, character_id: str) -> str:
        return f"{user_id}_{character_id}"

    def get(self, id: str) -> Optional[dict]:
        return None  # Individual message lookup not needed

    def get_all(self, *, user_id: str = "", character_id: str = "",
                limit: int = 100, **filters) -> list[dict]:
        key = self._key(user_id, character_id)
        messages = self._stores.get(key, [])
        return messages[-limit:]

    def create(self, data: dict) -> dict:
        key = self._key(data["user_id"], data["character_id"])
        if key not in self._stores:
            self._stores[key] = []
        record = {
            "role": data["role"],
            "content": data["content"],
            "turn_number": data.get("turn_number", 0),
            "created_at": datetime.utcnow().isoformat(),
        }
        self._stores[key].append(record)
        return record

    def update(self, id: str, data: dict) -> Optional[dict]:
        return None

    def delete(self, id: str) -> bool:
        return False

    def clear(self, user_id: str, character_id: str):
        """Clear conversation history for a pair."""
        key = self._key(user_id, character_id)
        self._stores[key] = []

    def get_turn_count(self, user_id: str, character_id: str) -> int:
        key = self._key(user_id, character_id)
        messages = self._stores.get(key, [])
        return sum(1 for m in messages if m["role"] == "assistant")


class PostgresChatRepository(BaseRepository):
    """PostgreSQL — stores all messages for cross-session recall."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get(self, id: str) -> Optional[dict]:
        from db.models import Conversation
        with self._session_factory() as session:
            c = session.query(Conversation).filter_by(id=int(id)).first()
            if c:
                return {"role": c.role, "content": c.content, "turn_number": c.turn_number}
            return None

    def get_all(self, *, user_id: str = "", character_id: str = "",
                limit: int = 100, **filters) -> list[dict]:
        from db.models import Conversation
        with self._session_factory() as session:
            q = session.query(Conversation).filter_by(
                user_id=user_id, character_id=character_id
            ).order_by(Conversation.created_at.desc()).limit(limit)
            return [
                {"role": c.role, "content": c.content, "turn_number": c.turn_number,
                 "created_at": c.created_at.isoformat()}
                for c in reversed(q.all())
            ]

    def create(self, data: dict) -> dict:
        from db.models import Conversation
        with self._session_factory() as session:
            c = Conversation(
                user_id=data["user_id"],
                character_id=data["character_id"],
                role=data["role"],
                content=data["content"],
                turn_number=data.get("turn_number", 0),
            )
            session.add(c)
            session.commit()
            return {"role": c.role, "content": c.content, "turn_number": c.turn_number}

    def update(self, id: str, data: dict) -> Optional[dict]:
        return None

    def delete(self, id: str) -> bool:
        from db.models import Conversation
        with self._session_factory() as session:
            c = session.query(Conversation).filter_by(id=int(id)).first()
            if c:
                session.delete(c)
                session.commit()
                return True
            return False

    def clear(self, user_id: str, character_id: str):
        from db.models import Conversation
        with self._session_factory() as session:
            session.query(Conversation).filter_by(
                user_id=user_id, character_id=character_id
            ).delete()
            session.commit()

    def get_turn_count(self, user_id: str, character_id: str) -> int:
        from db.models import Conversation
        with self._session_factory() as session:
            return session.query(Conversation).filter_by(
                user_id=user_id, character_id=character_id, role="assistant"
            ).count()


# ── Factory ───────────────────────────────────────────────────

def ChatRepository(session_factory=None):
    if session_factory is not None:
        return PostgresChatRepository(session_factory)
    return InMemoryChatRepository()
