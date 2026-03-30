"""
Chat Repository — persists conversations and messages.

In-memory: list-based storage per user-character pair.
PostgreSQL: Conversation (session) + ChatMessage (per-message).
"""
import logging
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from db.repositories.base import BaseRepository

if TYPE_CHECKING:
    from core.db_buffer import PendingMessage

logger = logging.getLogger("dokichat.repo.chat")


class InMemoryChatRepository(BaseRepository):

    def __init__(self):
        self._stores: dict[str, list[dict]] = {}

    def _key(self, user_id: str, character_id: str) -> str:
        return f"{user_id}_{character_id}"

    def get(self, id: str) -> Optional[dict]:
        return None

    def get_all(self, *, user_id: str = "", character_id: str = "",
                limit: int = 100, **filters) -> list[dict]:
        key = self._key(user_id, character_id)
        return self._stores.get(key, [])[-limit:]

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
        self._stores[self._key(user_id, character_id)] = []

    def get_turn_count(self, user_id: str, character_id: str) -> int:
        key = self._key(user_id, character_id)
        return sum(1 for m in self._stores.get(key, []) if m["role"] == "assistant")


class PostgresChatRepository(BaseRepository):

    def __init__(self, session_factory):
        self._sf = session_factory

    def get(self, id: str) -> Optional[dict]:
        from db.models import ChatMessage
        with self._sf() as session:
            msg = session.query(ChatMessage).filter_by(id=id).first()
            return self._msg_to_dict(msg) if msg else None

    def get_all(self, *, user_id: str = "", character_id: str = "",
                limit: int = 100, **filters) -> list[dict]:
        """Get recent messages for a user-character conversation."""
        from db.models import Conversation, ChatMessage
        with self._sf() as session:
            conv = session.query(Conversation).filter_by(
                user_id=user_id, character_id=character_id, status="active"
            ).first()
            if not conv:
                return []

            messages = session.query(ChatMessage).filter_by(
                conversation_id=conv.id
            ).order_by(ChatMessage.created_at.desc()).limit(limit).all()

            return [self._msg_to_dict(m) for m in reversed(messages)]

    def create(self, data: dict) -> dict:
        """Create a message. Auto-creates conversation if needed."""
        from db.models import Conversation, ChatMessage
        with self._sf() as session:
            # Get or create conversation
            conv = session.query(Conversation).filter_by(
                user_id=data["user_id"],
                character_id=data["character_id"],
                status="active",
            ).first()

            if not conv:
                conv = Conversation(
                    user_id=data["user_id"],
                    character_id=data["character_id"],
                )
                session.add(conv)
                session.flush()

            # Create message
            msg = ChatMessage(
                conversation_id=conv.id,
                role=data["role"],
                content=data["content"],
                turn_number=data.get("turn_number", 0),
            )
            session.add(msg)

            # Update conversation
            conv.turn_count += 1
            conv.last_message_at = datetime.utcnow()

            session.commit()
            return self._msg_to_dict(msg)

    def update(self, id: str, data: dict) -> Optional[dict]:
        return None

    def delete(self, id: str) -> bool:
        from db.models import ChatMessage
        with self._sf() as session:
            msg = session.query(ChatMessage).filter_by(id=id).first()
            if not msg:
                return False
            session.delete(msg)
            session.commit()
            return True

    def clear(self, user_id: str, character_id: str):
        """Archive conversation and start fresh."""
        from db.models import Conversation
        with self._sf() as session:
            conv = session.query(Conversation).filter_by(
                user_id=user_id, character_id=character_id, status="active"
            ).first()
            if conv:
                conv.status = "archived"
                session.commit()

    def get_turn_count(self, user_id: str, character_id: str) -> int:
        from db.models import Conversation, ChatMessage
        with self._sf() as session:
            conv = session.query(Conversation).filter_by(
                user_id=user_id, character_id=character_id, status="active"
            ).first()
            if not conv:
                return 0
            return session.query(ChatMessage).filter_by(
                conversation_id=conv.id, role="assistant"
            ).count()

    def bulk_create_messages(self, items: "list[PendingMessage]") -> int:
        """Batch insert messages from write-behind buffer.

        Groups messages by (user_id, character_id) to minimize
        conversation lookups. Single transaction for the batch.

        Args:
            items: list of PendingMessage dataclass instances

        Returns:
            Number of messages persisted.
        """
        from db.models import Conversation, ChatMessage
        from datetime import datetime

        if not items:
            return 0

        # Group by (user_id, character_id)
        groups: dict[tuple[str, str], list] = {}
        for msg in items:
            key = (msg.user_id, msg.character_id)
            groups.setdefault(key, []).append(msg)

        count = 0
        with self._sf() as session:
            try:
                for (user_id, char_id), messages in groups.items():
                    # Get or create conversation
                    conv = session.query(Conversation).filter_by(
                        user_id=user_id,
                        character_id=char_id,
                        status="active",
                    ).first()

                    if not conv:
                        conv = Conversation(
                            user_id=user_id,
                            character_id=char_id,
                        )
                        session.add(conv)
                        session.flush()  # get conv.id

                    # Bulk insert messages
                    for msg in messages:
                        chat_msg = ChatMessage(
                            conversation_id=conv.id,
                            role=msg.role,
                            content=msg.content,
                            turn_number=msg.turn_number,
                        )
                        session.add(chat_msg)

                    # Update conversation metadata
                    conv.turn_count += sum(1 for m in messages if m.role == "assistant")
                    conv.last_message_at = datetime.utcnow()
                    count += len(messages)

                session.commit()
            except Exception:
                session.rollback()
                raise

        return count

    @staticmethod
    def _msg_to_dict(msg) -> dict:
        return {
            "role": msg.role,
            "content": msg.content,
            "turn_number": msg.turn_number,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }


# ── Factory ───────────────────────────────────────────────────

def ChatRepository(session_factory=None):
    if session_factory is not None:
        return PostgresChatRepository(session_factory)
    return InMemoryChatRepository()
