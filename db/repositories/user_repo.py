"""
User Repository — CRUD for user accounts.

In-memory: dict-based storage (development/testing).
PostgreSQL: uses User model via SQLAlchemy.
"""
import logging
from typing import Optional
from datetime import datetime

from db.repositories.base import BaseRepository

logger = logging.getLogger("dokichat.repo.user")


class InMemoryUserRepository(BaseRepository):

    def __init__(self):
        self._store: dict[str, dict] = {}

    def get(self, id: str) -> Optional[dict]:
        return self._store.get(id)

    def get_all(self, **filters) -> list[dict]:
        return list(self._store.values())

    def create(self, data: dict) -> dict:
        record = {
            "id": data["id"],
            "email": data.get("email", ""),
            "display_name": data.get("display_name", "User"),
            "bio": data.get("bio", ""),
            "language": data.get("language", "vi"),
            "content_mode": data.get("content_mode", "romantic"),
            "created_at": datetime.utcnow().isoformat(),
        }
        self._store[record["id"]] = record
        return record

    def update(self, id: str, data: dict) -> Optional[dict]:
        if id not in self._store:
            return None
        self._store[id].update(data)
        return self._store[id]

    def delete(self, id: str) -> bool:
        return self._store.pop(id, None) is not None

    def get_or_create(self, user_id: str, **defaults) -> dict:
        user = self.get(user_id)
        if user is None:
            user = self.create({"id": user_id, **defaults})
        return user


class PostgresUserRepository(BaseRepository):

    def __init__(self, session_factory):
        self._sf = session_factory

    def get(self, id: str) -> Optional[dict]:
        from db.models import User
        with self._sf() as session:
            user = session.query(User).filter_by(id=id).first()
            return self._to_dict(user) if user else None

    def get_all(self, **filters) -> list[dict]:
        from db.models import User
        with self._sf() as session:
            return [self._to_dict(u) for u in session.query(User).all()]

    def create(self, data: dict) -> dict:
        from db.models import User
        with self._sf() as session:
            user = User(
                email=data["email"],
                password_hash=data.get("password_hash", ""),
                display_name=data.get("display_name", "User"),
                bio=data.get("bio", ""),
                language=data.get("language", "vi"),
                content_mode=data.get("content_mode", "romantic"),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return self._to_dict(user)

    def update(self, id: str, data: dict) -> Optional[dict]:
        from db.models import User
        with self._sf() as session:
            user = session.query(User).filter_by(id=id).first()
            if not user:
                return None
            for key, value in data.items():
                if hasattr(user, key) and key != "id":
                    setattr(user, key, value)
            session.commit()
            session.refresh(user)
            return self._to_dict(user)

    def delete(self, id: str) -> bool:
        from db.models import User
        with self._sf() as session:
            user = session.query(User).filter_by(id=id).first()
            if not user:
                return False
            session.delete(user)
            session.commit()
            return True

    def get_or_create(self, user_id: str, **defaults) -> dict:
        user = self.get(user_id)
        if user is None:
            user = self.create({"id": user_id, **defaults})
        return user

    @staticmethod
    def _to_dict(user) -> dict:
        return {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "bio": user.bio or "",
            "language": user.language,
            "content_mode": user.content_mode,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }


# ── Factory ───────────────────────────────────────────────────

def UserRepository(session_factory=None):
    """Create the appropriate user repository."""
    if session_factory is not None:
        return PostgresUserRepository(session_factory)
    return InMemoryUserRepository()
