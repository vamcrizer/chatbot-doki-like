"""
Character Repository — CRUD for UGC characters.

InMemory: dict-based (development/testing without a database).
PostgreSQL: uses Character model via SQLAlchemy.

Only custom (non-builtin) characters are managed here.
Builtin characters are hardcoded in the characters/ package.
"""
import logging
from typing import Optional

from db.repositories.base import BaseRepository

logger = logging.getLogger("ai_companion.repo.character")


class InMemoryCharacterRepository(BaseRepository):

    def __init__(self):
        self._store: dict[str, dict] = {}  # key → character dict

    def get(self, id: str) -> Optional[dict]:
        return self._store.get(id)

    def get_all(self, **filters) -> list[dict]:
        return list(self._store.values())

    def create(self, data: dict) -> dict:
        self._store[data["key"]] = data
        return data

    def update(self, id: str, data: dict) -> Optional[dict]:
        if id not in self._store:
            return None
        self._store[id].update(data)
        return self._store[id]

    def delete(self, id: str) -> bool:
        return self._store.pop(id, None) is not None

    def find_by_key(self, key: str) -> Optional[dict]:
        return self._store.get(key)

    def delete_by_key(self, key: str) -> bool:
        return self._store.pop(key, None) is not None


class PostgresCharacterRepository(BaseRepository):

    def __init__(self, session_factory):
        self._sf = session_factory

    def get(self, id: str) -> Optional[dict]:
        from db.models import Character
        with self._sf() as session:
            char = session.query(Character).filter_by(id=id).first()
            return self._to_dict(char) if char else None

    def get_all(self, **filters) -> list[dict]:
        from db.models import Character
        with self._sf() as session:
            chars = session.query(Character).filter_by(is_builtin=False).all()
            return [self._to_dict(c) for c in chars]

    def create(self, data: dict) -> dict:
        from db.models import Character
        with self._sf() as session:
            char = Character(
                key=data["key"],
                creator_id=data.get("creator_id"),
                name=data["name"],
                gender=data.get("gender", "female"),
                system_prompt=data["system_prompt"],
                greeting=data.get("greeting", ""),
                greetings_alt=data.get("greetings_alt", []),
                pacing=data.get("pacing", "guarded"),
                content_mode=data.get("content_mode", "romantic"),
                bio_original=data.get("bio_original", ""),
                emotional_states=data.get("emotional_states", {}),
                is_builtin=False,
                is_public=False,
            )
            session.add(char)
            session.commit()
            session.refresh(char)
            return self._to_dict(char)

    def update(self, id: str, data: dict) -> Optional[dict]:
        from db.models import Character
        with self._sf() as session:
            char = session.query(Character).filter_by(id=id).first()
            if not char:
                return None
            for k, v in data.items():
                if hasattr(char, k) and k not in ("id", "key"):
                    setattr(char, k, v)
            session.commit()
            session.refresh(char)
            return self._to_dict(char)

    def delete(self, id: str) -> bool:
        from db.models import Character
        with self._sf() as session:
            char = session.query(Character).filter_by(id=id).first()
            if not char:
                return False
            session.delete(char)
            session.commit()
            return True

    def find_by_key(self, key: str) -> Optional[dict]:
        from db.models import Character
        with self._sf() as session:
            char = session.query(Character).filter_by(key=key).first()
            return self._to_dict(char) if char else None

    def delete_by_key(self, key: str) -> bool:
        from db.models import Character
        with self._sf() as session:
            char = session.query(Character).filter_by(key=key).first()
            if not char:
                return False
            session.delete(char)
            session.commit()
            return True

    @staticmethod
    def _to_dict(char) -> dict:
        return {
            "id": str(char.id),
            "key": char.key or "",
            "name": char.name,
            "gender": char.gender,
            "system_prompt": char.system_prompt,
            "greeting": char.greeting,
            "greetings_alt": char.greetings_alt or [],
            "pacing": char.pacing,
            "content_mode": char.content_mode,
            "bio_original": char.bio_original or "",
            "emotional_states": char.emotional_states or {},
            "is_builtin": char.is_builtin,
            "is_public": char.is_public,
            "creator_id": str(char.creator_id) if char.creator_id else None,
            "created_at": char.created_at.isoformat() if char.created_at else None,
        }


def CharacterRepository(session_factory=None):
    """Create the appropriate character repository."""
    if session_factory is not None:
        return PostgresCharacterRepository(session_factory)
    return InMemoryCharacterRepository()
