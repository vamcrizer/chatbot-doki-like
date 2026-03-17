"""
User Repository — user profile CRUD.

In-memory implementation stores users in a dict.
PostgreSQL implementation uses the User model.
"""
import logging
from typing import Optional
from datetime import datetime

from db.repositories.base import BaseRepository

logger = logging.getLogger("dokichat.repo.user")


class InMemoryUserRepository(BaseRepository):
    """In-memory user storage."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    def get(self, id: str) -> Optional[dict]:
        return self._store.get(id)

    def get_all(self, **filters) -> list[dict]:
        return list(self._store.values())

    def create(self, data: dict) -> dict:
        user_id = data["id"]
        record = {
            "id": user_id,
            "display_name": data.get("display_name", "bạn"),
            "content_mode": data.get("content_mode", "romantic"),
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
        }
        self._store[user_id] = record
        return record

    def update(self, id: str, data: dict) -> Optional[dict]:
        if id not in self._store:
            return None
        self._store[id].update(data)
        self._store[id]["last_active"] = datetime.utcnow().isoformat()
        return self._store[id]

    def delete(self, id: str) -> bool:
        if id in self._store:
            del self._store[id]
            return True
        return False

    def get_or_create(self, user_id: str, **defaults) -> dict:
        """Get user or create with defaults."""
        user = self.get(user_id)
        if user is None:
            user = self.create({"id": user_id, **defaults})
        return user


class PostgresUserRepository(BaseRepository):
    """PostgreSQL user storage — Phase 2."""

    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get(self, id: str) -> Optional[dict]:
        from db.models import User
        with self._session_factory() as session:
            user = session.query(User).filter_by(id=id).first()
            if user:
                return {
                    "id": user.id,
                    "display_name": user.display_name,
                    "content_mode": user.content_mode,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "last_active": user.last_active.isoformat() if user.last_active else None,
                }
            return None

    def get_all(self, **filters) -> list[dict]:
        from db.models import User
        with self._session_factory() as session:
            users = session.query(User).all()
            return [
                {
                    "id": u.id,
                    "display_name": u.display_name,
                    "content_mode": u.content_mode,
                }
                for u in users
            ]

    def create(self, data: dict) -> dict:
        from db.models import User
        with self._session_factory() as session:
            user = User(
                id=data["id"],
                display_name=data.get("display_name", "bạn"),
                content_mode=data.get("content_mode", "romantic"),
            )
            session.add(user)
            session.commit()
            return {"id": user.id, "display_name": user.display_name, "content_mode": user.content_mode}

    def update(self, id: str, data: dict) -> Optional[dict]:
        from db.models import User
        with self._session_factory() as session:
            user = session.query(User).filter_by(id=id).first()
            if not user:
                return None
            for k, v in data.items():
                if hasattr(user, k):
                    setattr(user, k, v)
            session.commit()
            return {"id": user.id, "display_name": user.display_name, "content_mode": user.content_mode}

    def delete(self, id: str) -> bool:
        from db.models import User
        with self._session_factory() as session:
            user = session.query(User).filter_by(id=id).first()
            if user:
                session.delete(user)
                session.commit()
                return True
            return False

    def get_or_create(self, user_id: str, **defaults) -> dict:
        user = self.get(user_id)
        if user is None:
            user = self.create({"id": user_id, **defaults})
        return user


# ── Factory ───────────────────────────────────────────────────

def UserRepository(session_factory=None) -> InMemoryUserRepository | PostgresUserRepository:
    """Create the appropriate user repository."""
    if session_factory is not None:
        return PostgresUserRepository(session_factory)
    return InMemoryUserRepository()
