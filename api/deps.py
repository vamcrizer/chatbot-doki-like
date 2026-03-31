"""
AI Companion API — Dependency Injection container.

Session state lives in Redis (TTL 30 min).
Zero server-side memory — safe for horizontal scaling.

Usage in routes:
    from api.deps import get_session, save_session
    session = get_session(user_id, character_id)
    # ... mutate session ...
    save_session(session)
"""
import logging
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings
from core.redis_client import session_load, session_save

logger = logging.getLogger("dokichat.deps")

# ── Auth dependency ───────────────────────────────────────────

_bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency: validate Bearer JWT, return user_id.

    Raises 401 if token is missing, malformed, or expired.
    Usage in routes:
        current_user: str = Depends(get_current_user)
    """
    from api.auth import decode_access_token

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id

_settings = get_settings()


# ══════════════════════════════════════════════════════════════
# SESSION — per-user-character state (stored in Redis)
# ══════════════════════════════════════════════════════════════

@dataclass
class UserSession:
    """All state for one user-character conversation.

    Loaded from Redis on each request, saved back after mutation.
    TTL 30 min — auto-expires when user stops chatting.
    """
    user_id: str
    character_id: str
    conversation: object = field(default=None)  # ConversationManager
    affection: object = field(default=None)      # AffectionState
    scene: object = field(default=None)          # SceneTracker
    user_name: str = "bạn"
    content_mode: str = "romantic"

    def __post_init__(self):
        from core.conversation import ConversationManager
        from state.affection import AffectionState
        from state.scene import SceneTracker

        if self.conversation is None:
            self.conversation = ConversationManager(
                max_turns=_settings.CONV_MAX_TURNS,
                min_turns=_settings.CONV_MIN_TURNS,
            )
        if self.affection is None:
            self.affection = AffectionState()
        if self.scene is None:
            self.scene = SceneTracker(character_key=self.character_id)

    def to_dict(self) -> dict:
        """Serialize entire session for Redis storage."""
        return {
            "user_id": self.user_id,
            "character_id": self.character_id,
            "user_name": self.user_name,
            "content_mode": self.content_mode,
            "conversation": self.conversation.to_dict(),
            "affection": self.affection.to_dict(),
            "scene": self.scene.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserSession":
        """Restore session from Redis data."""
        from core.conversation import ConversationManager
        from state.affection import AffectionState
        from state.scene import SceneTracker

        session = cls.__new__(cls)
        session.user_id = d["user_id"]
        session.character_id = d["character_id"]
        session.user_name = d.get("user_name", "bạn")
        session.content_mode = d.get("content_mode", "romantic")
        session.conversation = ConversationManager.from_dict(d.get("conversation", {}))
        session.affection = AffectionState.from_dict(d.get("affection", {}))
        session.scene = SceneTracker.from_dict(
            d.get("scene", {}),
            character_key=session.character_id,
        )
        return session


def get_session(user_id: str, character_id: str) -> UserSession:
    """Load session from Redis, or create a fresh one.

    Always returns a usable session. If Redis is down or session
    expired, creates a new default session.
    """
    # Try Redis first
    cached = session_load(user_id, character_id)
    if cached:
        try:
            return UserSession.from_dict(cached)
        except Exception as e:
            logger.warning("Failed to deserialize session: %s", e)

    # Fresh session
    logger.info("New session: %s/%s", user_id, character_id)
    return UserSession(user_id=user_id, character_id=character_id)


def save_session(session: UserSession) -> bool:
    """Save session to Redis with TTL reset (30 min).

    Call this after every mutation (add message, update affection, etc).
    Each save resets the TTL — user stays active = session stays alive.
    """
    return session_save(
        session.user_id,
        session.character_id,
        session.to_dict(),
    )


def destroy_session(user_id: str, character_id: str) -> bool:
    """Delete session from Redis."""
    from core.redis_client import get_redis
    r = get_redis()
    if r:
        return bool(r.delete(f"session:{user_id}:{character_id}"))
    return False


# ══════════════════════════════════════════════════════════════
# REPOSITORIES — data access (lazy singletons)
# ══════════════════════════════════════════════════════════════

_db_session_factory = None
_repos_initialized = False

_user_repo = None
_chat_repo = None


def _init_repos():
    """Initialize repositories. Uses PostgreSQL if DATABASE_URL is set."""
    global _db_session_factory, _repos_initialized
    global _user_repo, _chat_repo

    if _repos_initialized:
        return

    from db.database import get_session_factory
    _db_session_factory = get_session_factory()

    from db.repositories.user_repo import UserRepository
    from db.repositories.chat_repo import ChatRepository

    _user_repo = UserRepository(_db_session_factory)
    _chat_repo = ChatRepository(_db_session_factory)

    backend = "PostgreSQL" if _db_session_factory else "in-memory"
    logger.info("Repositories initialized (%s)", backend)
    _repos_initialized = True


def get_user_repo():
    _init_repos()
    return _user_repo


def get_chat_repo():
    _init_repos()
    return _chat_repo


# ══════════════════════════════════════════════════════════════
# SERVICES — business logic (lazy singletons)
# ══════════════════════════════════════════════════════════════

_chat_service = None
_character_service = None


def get_chat_service():
    """Get ChatService singleton."""
    global _chat_service
    if _chat_service is None:
        from services.chat_service import ChatService
        _chat_service = ChatService(
            chat_repo=get_chat_repo(),
        )
    return _chat_service


def get_character_service():
    """Get CharacterService singleton."""
    global _character_service
    if _character_service is None:
        from services.character_service import CharacterService
        from core.llm_client import chat_complete

        def _llm_call_fn(messages, max_tokens=1024):
            return chat_complete(messages, temperature=0.7, max_tokens=max_tokens)

        _character_service = CharacterService(llm_call_fn=_llm_call_fn)
    return _character_service
