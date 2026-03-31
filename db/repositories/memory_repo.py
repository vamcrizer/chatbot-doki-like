"""
Memory Repository — CRUD for extracted facts and session summaries.

In-memory: delegates to MemoryStore (JSON-based).
PostgreSQL: stores in memories + session_summaries tables.
"""
import uuid
import logging
from typing import Optional

from db.repositories.base import BaseRepository

logger = logging.getLogger("ai_companion.repo.memory")


class InMemoryMemoryRepository(BaseRepository):
    """Wraps MemoryStore per user-character pair."""

    def __init__(self):
        self._stores: dict[str, object] = {}

    def _get_store(self, user_id: str, character_id: str):
        key = f"{user_id}_{character_id}"
        if key not in self._stores:
            from memory.mem0_store import create_memory_store
            self._stores[key] = create_memory_store(user_id, character_id)
        return self._stores[key]

    def get(self, id: str) -> Optional[dict]:
        return None

    def get_all(self, *, user_id: str = "", character_id: str = "", **filters) -> list[dict]:
        return self._get_store(user_id, character_id).get_all()

    def create(self, data: dict) -> dict:
        store = self._get_store(data["user_id"], data["character_id"])
        store.add([{
            "text": data["text"],
            "type": data.get("type", "user_fact"),
            "confidence": data.get("confidence", 0.8),
        }])
        return data

    def create_batch(self, user_id: str, character_id: str, facts: list[dict]) -> int:
        self._get_store(user_id, character_id).add(facts)
        return len(facts)

    def update(self, id: str, data: dict) -> Optional[dict]:
        return None

    def delete(self, id: str) -> bool:
        return False

    def search(self, user_id: str, character_id: str, query: str, top_k: int = 5) -> list[str]:
        return self._get_store(user_id, character_id).search(query, top_k=top_k)

    def get_summary(self, user_id: str, character_id: str) -> str:
        return self._get_store(user_id, character_id).get_summary()

    def update_summary(self, user_id: str, character_id: str, summary: str):
        self._get_store(user_id, character_id).update_summary(summary)

    def clear(self, user_id: str, character_id: str):
        self._get_store(user_id, character_id).clear()


class PostgresMemoryRepository(BaseRepository):

    def __init__(self, session_factory):
        self._sf = session_factory

    def get(self, id: str) -> Optional[dict]:
        from db.models import Memory
        with self._sf() as session:
            m = session.query(Memory).filter_by(id=id, superseded_by=None).first()
            return self._to_dict(m) if m else None

    def get_all(self, *, user_id: str = "", character_id: str = "", **filters) -> list[dict]:
        from db.models import Memory
        with self._sf() as session:
            rows = session.query(Memory).filter_by(
                user_id=user_id, character_id=character_id, superseded_by=None
            ).order_by(Memory.created_at).all()
            return [self._to_dict(m) for m in rows]

    def create(self, data: dict) -> dict:
        from db.models import Memory
        with self._sf() as session:
            m = Memory(
                user_id=data["user_id"],
                character_id=data["character_id"],
                text=data["text"],
                type=data.get("type", "user_fact"),
                confidence=data.get("confidence", 0.8),
            )
            session.add(m)
            session.commit()
            return self._to_dict(m)

    def create_batch(self, user_id: str, character_id: str, facts: list[dict]) -> int:
        from db.models import Memory
        with self._sf() as session:
            for f in facts:
                session.add(Memory(
                    user_id=user_id,
                    character_id=character_id,
                    text=f["text"],
                    type=f.get("type", "user_fact"),
                    confidence=f.get("confidence", 0.8),
                ))
            session.commit()
            return len(facts)

    def update(self, id: str, data: dict) -> Optional[dict]:
        from db.models import Memory
        with self._sf() as session:
            m = session.query(Memory).filter_by(id=id).first()
            if not m:
                return None
            for key, value in data.items():
                if hasattr(m, key) and key != "id":
                    setattr(m, key, value)
            session.commit()
            return self._to_dict(m)

    def supersede(self, old_id: str, new_fact: dict) -> dict:
        """Mark old fact as superseded and create replacement."""
        from db.models import Memory
        with self._sf() as session:
            new_id = uuid.uuid4()
            old = session.query(Memory).filter_by(id=old_id).first()
            if old:
                old.superseded_by = new_id

            m = Memory(
                id=new_id,
                user_id=new_fact["user_id"],
                character_id=new_fact["character_id"],
                text=new_fact["text"],
                type=new_fact.get("type", "user_fact"),
            )
            session.add(m)
            session.commit()
            return {"id": str(new_id), "text": m.text, "superseded": str(old_id)}

    def delete(self, id: str) -> bool:
        from db.models import Memory
        with self._sf() as session:
            m = session.query(Memory).filter_by(id=id).first()
            if not m:
                return False
            session.delete(m)
            session.commit()
            return True

    def search(self, user_id: str, character_id: str, query: str, top_k: int = 5) -> list[str]:
        """Keyword search fallback.

        # TODO: Replace with Qdrant semantic search
        """
        from db.models import Memory
        with self._sf() as session:
            rows = session.query(Memory).filter_by(
                user_id=user_id, character_id=character_id, superseded_by=None
            ).all()
            query_words = set(query.lower().split())
            scored = []
            for m in rows:
                overlap = len(query_words & set(m.text.lower().split()))
                if overlap > 0:
                    scored.append((overlap, m.text))
            scored.sort(reverse=True)
            return [text for _, text in scored[:top_k]]

    def get_summary(self, user_id: str, character_id: str) -> str:
        from db.models import SessionSummary
        with self._sf() as session:
            s = session.query(SessionSummary).filter_by(
                user_id=user_id, character_id=character_id
            ).order_by(SessionSummary.created_at.desc()).first()
            return s.summary if s else ""

    def update_summary(self, user_id: str, character_id: str, summary: str):
        from db.models import SessionSummary
        with self._sf() as session:
            session.add(SessionSummary(
                user_id=user_id,
                character_id=character_id,
                summary=summary,
            ))
            session.commit()

    def clear(self, user_id: str, character_id: str):
        from db.models import Memory
        with self._sf() as session:
            session.query(Memory).filter_by(
                user_id=user_id, character_id=character_id
            ).delete()
            session.commit()

    @staticmethod
    def _to_dict(m) -> dict:
        return {
            "id": str(m.id),
            "text": m.text,
            "type": m.type,
            "confidence": m.confidence,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }


# ── Factory ───────────────────────────────────────────────────

def MemoryRepository(session_factory=None):
    if session_factory is not None:
        return PostgresMemoryRepository(session_factory)
    return InMemoryMemoryRepository()
