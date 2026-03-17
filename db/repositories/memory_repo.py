"""
Memory Repository — fact storage CRUD.

In-memory wraps the existing MemoryStore (Qdrant + JSON).
PostgreSQL stores facts in DB, uses Qdrant as read-cache only.
"""
import uuid
import logging
from typing import Optional
from datetime import datetime

from db.repositories.base import BaseRepository

logger = logging.getLogger("dokichat.repo.memory")


class InMemoryMemoryRepository(BaseRepository):
    """In-memory — wraps existing MemoryStore per user-character pair."""

    def __init__(self):
        self._stores: dict[str, object] = {}  # key → MemoryStore

    def _get_store(self, user_id: str, character_id: str):
        key = f"{user_id}_{character_id}"
        if key not in self._stores:
            from memory.mem0_store import create_memory_store
            self._stores[key] = create_memory_store(user_id, character_id)
        return self._stores[key]

    def get(self, id: str) -> Optional[dict]:
        # Not efficient for in-memory, but rarely needed
        return None

    def get_all(self, *, user_id: str = "", character_id: str = "", **filters) -> list[dict]:
        store = self._get_store(user_id, character_id)
        return store.get_all()

    def create(self, data: dict) -> dict:
        user_id = data["user_id"]
        character_id = data["character_id"]
        store = self._get_store(user_id, character_id)
        facts = [{"text": data["text"], "type": data.get("type", "user_fact"),
                  "confidence": data.get("confidence", 0.8)}]
        store.add(facts)
        return data

    def create_batch(self, user_id: str, character_id: str, facts: list[dict]) -> int:
        """Add multiple facts at once. Returns count added."""
        store = self._get_store(user_id, character_id)
        store.add(facts)
        return len(facts)

    def update(self, id: str, data: dict) -> Optional[dict]:
        return None  # Not supported in-memory

    def delete(self, id: str) -> bool:
        return False  # Not supported in-memory

    def search(self, user_id: str, character_id: str, query: str, top_k: int = 5) -> list[str]:
        """Semantic search for relevant facts."""
        store = self._get_store(user_id, character_id)
        return store.search(query, top_k=top_k)

    def get_summary(self, user_id: str, character_id: str) -> str:
        store = self._get_store(user_id, character_id)
        return store.get_summary()

    def update_summary(self, user_id: str, character_id: str, summary: str):
        store = self._get_store(user_id, character_id)
        store.update_summary(summary)

    def clear(self, user_id: str, character_id: str):
        store = self._get_store(user_id, character_id)
        if hasattr(store, 'clear'):
            store.clear()


class PostgresMemoryRepository(BaseRepository):
    """PostgreSQL — facts in DB, Qdrant as semantic search cache."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get(self, id: str) -> Optional[dict]:
        from db.models import Memory
        with self._session_factory() as session:
            m = session.query(Memory).filter_by(id=id, superseded_by=None).first()
            if m:
                return {"id": m.id, "text": m.text, "type": m.type,
                        "confidence": m.confidence, "created_at": m.created_at.isoformat()}
            return None

    def get_all(self, *, user_id: str = "", character_id: str = "", **filters) -> list[dict]:
        from db.models import Memory
        with self._session_factory() as session:
            q = session.query(Memory).filter_by(
                user_id=user_id, character_id=character_id, superseded_by=None
            ).order_by(Memory.created_at)
            return [{"id": m.id, "text": m.text, "type": m.type,
                     "confidence": m.confidence} for m in q.all()]

    def create(self, data: dict) -> dict:
        from db.models import Memory
        with self._session_factory() as session:
            m = Memory(
                id=str(uuid.uuid4()),
                user_id=data["user_id"],
                character_id=data["character_id"],
                text=data["text"],
                type=data.get("type", "user_fact"),
                confidence=data.get("confidence", 0.8),
            )
            session.add(m)
            session.commit()
            return {"id": m.id, "text": m.text, "type": m.type}

    def create_batch(self, user_id: str, character_id: str, facts: list[dict]) -> int:
        from db.models import Memory
        with self._session_factory() as session:
            for f in facts:
                m = Memory(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    character_id=character_id,
                    text=f["text"],
                    type=f.get("type", "user_fact"),
                    confidence=f.get("confidence", 0.8),
                )
                session.add(m)
            session.commit()
            return len(facts)

    def update(self, id: str, data: dict) -> Optional[dict]:
        from db.models import Memory
        with self._session_factory() as session:
            m = session.query(Memory).filter_by(id=id).first()
            if not m:
                return None
            for k, v in data.items():
                if hasattr(m, k):
                    setattr(m, k, v)
            session.commit()
            return {"id": m.id, "text": m.text, "type": m.type}

    def supersede(self, old_id: str, new_fact: dict) -> dict:
        """Mark old fact as superseded and create new one."""
        from db.models import Memory
        with self._session_factory() as session:
            new_id = str(uuid.uuid4())
            # Mark old
            old = session.query(Memory).filter_by(id=old_id).first()
            if old:
                old.superseded_by = new_id
            # Create new
            m = Memory(
                id=new_id,
                user_id=new_fact["user_id"],
                character_id=new_fact["character_id"],
                text=new_fact["text"],
                type=new_fact.get("type", "user_fact"),
            )
            session.add(m)
            session.commit()
            return {"id": new_id, "text": m.text, "superseded": old_id}

    def delete(self, id: str) -> bool:
        from db.models import Memory
        with self._session_factory() as session:
            m = session.query(Memory).filter_by(id=id).first()
            if m:
                session.delete(m)
                session.commit()
                return True
            return False

    def search(self, user_id: str, character_id: str, query: str, top_k: int = 5) -> list[str]:
        """Semantic search via Qdrant cache (falls back to text search)."""
        # TODO: integrate Qdrant read-cache
        # For now, simple text match
        from db.models import Memory
        with self._session_factory() as session:
            all_mems = session.query(Memory).filter_by(
                user_id=user_id, character_id=character_id, superseded_by=None
            ).all()
            # Basic keyword matching
            query_words = set(query.lower().split())
            scored = []
            for m in all_mems:
                text_words = set(m.text.lower().split())
                overlap = len(query_words & text_words)
                if overlap > 0:
                    scored.append((overlap, m.text))
            scored.sort(reverse=True)
            return [text for _, text in scored[:top_k]]

    def get_summary(self, user_id: str, character_id: str) -> str:
        from db.models import SessionSummary
        with self._session_factory() as session:
            s = session.query(SessionSummary).filter_by(
                user_id=user_id, character_id=character_id
            ).order_by(SessionSummary.created_at.desc()).first()
            return s.summary if s else ""

    def update_summary(self, user_id: str, character_id: str, summary: str):
        from db.models import SessionSummary
        with self._session_factory() as session:
            s = SessionSummary(
                user_id=user_id, character_id=character_id,
                summary=summary,
            )
            session.add(s)
            session.commit()

    def clear(self, user_id: str, character_id: str):
        from db.models import Memory
        with self._session_factory() as session:
            session.query(Memory).filter_by(
                user_id=user_id, character_id=character_id
            ).delete()
            session.commit()


# ── Factory ───────────────────────────────────────────────────

def MemoryRepository(session_factory=None):
    if session_factory is not None:
        return PostgresMemoryRepository(session_factory)
    return InMemoryMemoryRepository()
