"""
DokiChat API — Dependency Injection container.

Central place that wires repositories, services, and sessions.
Everything is lazy-loaded and singleton — no circular imports.

Usage in routes:
    from api.deps import get_chat_service, get_session
    service = get_chat_service()
    session = get_session(user_id, character_id)
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from config import get_settings

logger = logging.getLogger("dokichat.deps")

_settings = get_settings()


# ══════════════════════════════════════════════════════════════
# SESSION — per-user-character state
# ══════════════════════════════════════════════════════════════

@dataclass
class UserSession:
    """All state for one user-character conversation."""
    user_id: str
    character_id: str
    conversation: object = field(default=None)  # ConversationManager
    affection: object = field(default=None)      # AffectionState
    scene: object = field(default=None)          # SceneTracker
    memory: object = field(default=None)         # MemoryStore
    user_name: str = "bạn"
    content_mode: str = "romantic"

    def __post_init__(self):
        from core.conversation import ConversationManager
        from state.affection import AffectionState
        from state.scene import SceneTracker
        from memory.mem0_store import create_memory_store

        if self.conversation is None:
            self.conversation = ConversationManager(
                max_turns=_settings.CONV_MAX_TURNS,
                min_turns=_settings.CONV_MIN_TURNS,
            )
        if self.affection is None:
            self.affection = AffectionState()
        if self.scene is None:
            self.scene = SceneTracker(character_key=self.character_id)
        if self.memory is None:
            self.memory = create_memory_store(
                user_id=self.user_id,
                character_id=self.character_id,
            )


# Session registry (Phase 3 → Redis-backed)
_sessions: dict[tuple[str, str], UserSession] = {}


def get_session(user_id: str, character_id: str) -> UserSession:
    """Get or create a session for a user-character pair."""
    key = (user_id, character_id)
    if key not in _sessions:
        logger.info(f"New session: {user_id}/{character_id}")
        _sessions[key] = UserSession(user_id=user_id, character_id=character_id)
    return _sessions[key]


def destroy_session(user_id: str, character_id: str) -> bool:
    """Remove a session."""
    key = (user_id, character_id)
    if key in _sessions:
        del _sessions[key]
        return True
    return False


def list_sessions() -> list[tuple[str, str]]:
    return list(_sessions.keys())


# ══════════════════════════════════════════════════════════════
# REPOSITORIES — data access (lazy singletons)
# ══════════════════════════════════════════════════════════════

_db_session_factory = None
_repos_initialized = False

_user_repo = None
_memory_repo = None
_chat_repo = None


def _init_repos():
    """Initialize repositories. Uses PostgreSQL if DATABASE_URL is set."""
    global _db_session_factory, _repos_initialized
    global _user_repo, _memory_repo, _chat_repo

    if _repos_initialized:
        return

    from db.database import get_session_factory
    _db_session_factory = get_session_factory()  # None if no DB

    from db.repositories.user_repo import UserRepository
    from db.repositories.memory_repo import MemoryRepository
    from db.repositories.chat_repo import ChatRepository

    _user_repo = UserRepository(_db_session_factory)
    _memory_repo = MemoryRepository(_db_session_factory)
    _chat_repo = ChatRepository(_db_session_factory)

    backend = "PostgreSQL" if _db_session_factory else "in-memory"
    logger.info(f"Repositories initialized ({backend})")
    _repos_initialized = True


def get_user_repo():
    _init_repos()
    return _user_repo


def get_memory_repo():
    _init_repos()
    return _memory_repo


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
            memory_repo=get_memory_repo(),
            chat_repo=get_chat_repo(),
        )
    return _chat_service


def get_character_service():
    """Get CharacterService singleton."""
    global _character_service
    if _character_service is None:
        from services.character_service import CharacterService
        _character_service = CharacterService()
    return _character_service
