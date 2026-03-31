"""
AI Companion — Central Configuration

All settings loaded from environment variables (.env file).
"""
import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

# ── Project paths ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
CUSTOM_CHARACTERS_DIR = PROJECT_ROOT / "characters" / "custom"
CUSTOM_CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    """Application settings — reads from env vars with defaults."""

    # ── LLM ───────────────────────────────────────────────────
    LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1")
    LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "lm-studio")
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "google/gemma-3-4b-it")
    LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "1024"))
    LLM_TEMPERATURE: float = float(os.environ.get("LLM_TEMPERATURE", "0.85"))

    # ── Conversation (Sliding Window) ─────────────────────────
    CONV_MAX_TURNS: int = int(os.environ.get("CONV_MAX_TURNS", "7"))
    CONV_MIN_TURNS: int = int(os.environ.get("CONV_MIN_TURNS", "4"))

    # ── Database ──────────────────────────────────────────────
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    REDIS_URL: str = os.environ.get("REDIS_URL", "")  # TODO: session + chat window storage

    # ── Auth (JWT) ────────────────────────────────────────────
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "change-me-in-production-use-long-random-secret")
    JWT_ACCESS_EXPIRE_MINUTES: int = int(os.environ.get("JWT_ACCESS_EXPIRE_MINUTES", "30"))
    JWT_REFRESH_EXPIRE_DAYS: int = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "7"))

    # ── Content ───────────────────────────────────────────────
    DEFAULT_CONTENT_MODE: str = os.environ.get("DEFAULT_CONTENT_MODE", "romantic")

    # ── Memory (TODO) ─────────────────────────────────────────
    # Qdrant integration for semantic memory search
    # QDRANT_URL: str = os.environ.get("QDRANT_URL", "localhost")
    # QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", "6333"))
    # QDRANT_COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "dokichat_memories")
    # EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
    # EMBEDDING_DIM: int = int(os.environ.get("EMBEDDING_DIM", "1024"))


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings singleton."""
    return Settings()
