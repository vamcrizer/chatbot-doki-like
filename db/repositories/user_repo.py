"""
User Repository — CRUD for user accounts and auth tokens.

In-memory: dict-based storage (development/testing).
PostgreSQL: uses User / AuthToken models via SQLAlchemy.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from db.repositories.base import BaseRepository

logger = logging.getLogger("ai_companion.repo.user")


class InMemoryUserRepository(BaseRepository):

    def __init__(self):
        self._users: dict[str, dict] = {}        # id → user dict
        self._email_idx: dict[str, str] = {}     # email → id
        self._tokens: dict[str, dict] = {}       # hashed_token → token dict

    # ── User CRUD ─────────────────────────────────────────────

    def get(self, id: str) -> Optional[dict]:
        return self._users.get(id)

    def get_all(self, **filters) -> list[dict]:
        return list(self._users.values())

    def create(self, data: dict) -> dict:
        import uuid
        user_id = data.get("id") or str(uuid.uuid4())
        record = {
            "id": user_id,
            "email": data.get("email", ""),
            "password_hash": data.get("password_hash", ""),
            "display_name": data.get("display_name", "User"),
            "bio": data.get("bio", ""),
            "language": data.get("language", "vi"),
            "content_mode": data.get("content_mode", "romantic"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._users[user_id] = record
        if record["email"]:
            self._email_idx[record["email"].lower()] = user_id
        return record

    def update(self, id: str, data: dict) -> Optional[dict]:
        if id not in self._users:
            return None
        self._users[id].update(data)
        return self._users[id]

    def delete(self, id: str) -> bool:
        user = self._users.pop(id, None)
        if user:
            self._email_idx.pop(user.get("email", "").lower(), None)
        return user is not None

    def get_or_create(self, user_id: str, **defaults) -> dict:
        user = self.get(user_id)
        if user is None:
            user = self.create({"id": user_id, **defaults})
        return user

    # ── Email lookup ──────────────────────────────────────────

    def find_by_email(self, email: str) -> Optional[dict]:
        """Find user by email (case-insensitive)."""
        user_id = self._email_idx.get(email.lower())
        return self._users.get(user_id) if user_id else None

    # ── Refresh tokens ────────────────────────────────────────

    def save_refresh_token(self, user_id: str, hashed_token: str, expires_at: datetime) -> None:
        """Store hashed refresh token."""
        self._tokens[hashed_token] = {
            "user_id": user_id,
            "token_hash": hashed_token,
            "expires_at": expires_at,
        }

    def find_refresh_token(self, hashed_token: str) -> Optional[dict]:
        """Find a refresh token record; returns None if expired."""
        record = self._tokens.get(hashed_token)
        if not record:
            return None
        if record["expires_at"] < datetime.now(timezone.utc):
            self._tokens.pop(hashed_token, None)
            return None
        return record

    def delete_refresh_token(self, hashed_token: str) -> None:
        """Invalidate (delete) a refresh token."""
        self._tokens.pop(hashed_token, None)

    def delete_all_refresh_tokens(self, user_id: str) -> None:
        """Invalidate all refresh tokens for a user (logout-all-devices)."""
        to_delete = [h for h, r in self._tokens.items() if r["user_id"] == user_id]
        for h in to_delete:
            del self._tokens[h]

    # ── OAuth ─────────────────────────────────────────────────

    def find_or_create_oauth_user(self, email: str, display_name: str, provider: str) -> dict:
        """Find existing user by email or create a new OAuth-only account.

        Email is the link between OAuth and password accounts:
        - If an account with this email exists → return it (auto-link)
        - Otherwise → create new account (no password set)
        """
        user = self.find_by_email(email)
        if user:
            return user
        return self.create({
            "email": email,
            "password_hash": "",  # OAuth-only; set via POST /auth/set-password later
            "display_name": display_name or email.split("@")[0],
        })


class PostgresUserRepository(BaseRepository):

    def __init__(self, session_factory):
        self._sf = session_factory

    # ── User CRUD ─────────────────────────────────────────────

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

    # ── Email lookup ──────────────────────────────────────────

    def find_by_email(self, email: str) -> Optional[dict]:
        """Find user by email (case-insensitive)."""
        from db.models import User
        from sqlalchemy import func
        with self._sf() as session:
            user = session.query(User).filter(
                func.lower(User.email) == email.lower()
            ).first()
            return self._to_dict(user) if user else None

    # ── Refresh tokens ────────────────────────────────────────

    def save_refresh_token(self, user_id: str, hashed_token: str, expires_at: datetime) -> None:
        from db.models import AuthToken
        with self._sf() as session:
            token = AuthToken(
                user_id=user_id,
                token_hash=hashed_token,
                token_type="refresh",
                expires_at=expires_at,
            )
            session.add(token)
            session.commit()

    def find_refresh_token(self, hashed_token: str) -> Optional[dict]:
        from db.models import AuthToken
        with self._sf() as session:
            record = session.query(AuthToken).filter_by(token_hash=hashed_token).first()
            if not record:
                return None
            if record.expires_at < datetime.now(timezone.utc):
                session.delete(record)
                session.commit()
                return None
            return {"user_id": str(record.user_id), "token_hash": record.token_hash}

    def delete_refresh_token(self, hashed_token: str) -> None:
        from db.models import AuthToken
        with self._sf() as session:
            record = session.query(AuthToken).filter_by(token_hash=hashed_token).first()
            if record:
                session.delete(record)
                session.commit()

    def delete_all_refresh_tokens(self, user_id: str) -> None:
        from db.models import AuthToken
        with self._sf() as session:
            session.query(AuthToken).filter_by(user_id=user_id).delete()
            session.commit()

    # ── OAuth ─────────────────────────────────────────────────

    def find_or_create_oauth_user(self, email: str, display_name: str, provider: str) -> dict:
        """Find existing user by email or create a new OAuth-only account."""
        user = self.find_by_email(email)
        if user:
            return user
        return self.create({
            "email": email,
            "password_hash": "",
            "display_name": display_name or email.split("@")[0],
        })

    @staticmethod
    def _to_dict(user) -> dict:
        return {
            "id": str(user.id),
            "email": user.email,
            "password_hash": user.password_hash,
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
