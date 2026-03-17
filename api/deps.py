"""
DokiChat API — Dependency injection and session management.

Manages per-user-character sessions with all state objects.
"""
import logging
from dataclasses import dataclass, field

from core.conversation import ConversationManager
from state.affection import AffectionState
from state.scene import SceneTracker
from memory.mem0_store import create_memory_store
from config import get_settings

logger = logging.getLogger("dokichat.deps")

_settings = get_settings()


@dataclass
class UserSession:
    """All state for one user-character conversation."""
    user_id: str
    character_id: str
    conversation: ConversationManager = field(default=None)
    affection: AffectionState = field(default=None)
    scene: SceneTracker = field(default=None)
    memory: object = field(default=None)  # MemoryStore
    user_name: str = "bạn"
    content_mode: str = "romantic"

    def __post_init__(self):
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


# ── Session registry (in-memory, Phase 3 → Redis) ────────────
_sessions: dict[tuple[str, str], UserSession] = {}


def get_session(user_id: str, character_id: str) -> UserSession:
    """Get or create a session for a user-character pair."""
    key = (user_id, character_id)
    if key not in _sessions:
        logger.info(f"Creating new session: user={user_id} char={character_id}")
        _sessions[key] = UserSession(user_id=user_id, character_id=character_id)
    return _sessions[key]


def destroy_session(user_id: str, character_id: str) -> bool:
    """Remove a session (e.g., on character switch)."""
    key = (user_id, character_id)
    if key in _sessions:
        del _sessions[key]
        return True
    return False


def list_sessions() -> list[tuple[str, str]]:
    """List all active session keys."""
    return list(_sessions.keys())
