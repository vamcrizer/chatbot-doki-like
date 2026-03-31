"""
DB Write-Behind Buffer — collects chat messages and batch-flushes to PostgreSQL.

Architecture:
  - Thread-safe collections.deque holds pending messages in memory.
  - enqueue() is called from chat routes — O(1), non-blocking, zero latency impact.
  - flush() is called by background worker (api/main.py) every 30s or when queue > 100.
  - Graceful degradation: if DATABASE_URL is not set, messages are discarded silently.
  - On DB error: messages are lost (logged at ERROR level). Acceptable because Redis
    still holds the full session for 30 min — the write-behind is a persistence layer,
    not the source of truth.

Usage:
    from core.db_buffer import enqueue, flush, get_pending_count

    # In chat route — instant, never blocks:
    enqueue("user123", "kael", "user", "hello", turn=5)

    # In background worker — periodic:
    count = flush()  # returns number of messages persisted
"""
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("ai_companion.db_buffer")


# ── Data Types ────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PendingMessage:
    """A chat message waiting to be persisted to PostgreSQL."""

    user_id: str
    character_id: str
    role: str           # "user" | "assistant"
    content: str
    turn_number: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Configuration ─────────────────────────────────────────────

FLUSH_THRESHOLD: int = 100   # Flush early if queue exceeds this
FLUSH_INTERVAL: int = 30     # Seconds between periodic flushes


# ── Module State (thread-safe) ────────────────────────────────

_queue: deque[PendingMessage] = deque()
_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────

def enqueue(
    user_id: str,
    character_id: str,
    role: str,
    content: str,
    turn_number: int = 0,
) -> None:
    """Add a message to the write-behind queue.

    O(1) and thread-safe — safe to call from any async context.
    """
    msg = PendingMessage(
        user_id=user_id,
        character_id=character_id,
        role=role,
        content=content,
        turn_number=turn_number,
    )
    with _lock:
        _queue.append(msg)


def get_pending_count() -> int:
    """Return current queue size. Used for monitoring via /health endpoint."""
    return len(_queue)


def should_flush_early() -> bool:
    """Check if queue has exceeded threshold and needs an early flush."""
    return len(_queue) >= FLUSH_THRESHOLD


def flush() -> int:
    """Drain the queue and batch-INSERT all pending messages to PostgreSQL.

    Returns:
        Number of messages successfully persisted.

    Thread-safety:
        Atomically drains the queue under lock, then writes outside lock.
        This means new messages enqueued during DB write are safe in the queue.
    """
    # Atomically drain
    with _lock:
        if not _queue:
            return 0
        batch = list(_queue)
        _queue.clear()

    # Lazy import — avoid circular imports at module load time
    from db.database import get_session_factory

    session_factory = get_session_factory()
    if session_factory is None:
        logger.debug("No DATABASE_URL configured — %d messages discarded", len(batch))
        return 0

    try:
        from db.repositories.chat_repo import PostgresChatRepository

        repo = PostgresChatRepository(session_factory)
        persisted = repo.bulk_create_messages(batch)
        logger.info("DB flush: %d messages persisted", persisted)
        return persisted
    except Exception:
        logger.exception("DB flush FAILED — %d messages lost", len(batch))
        return 0
