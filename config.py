"""
DokiChat — Central Configuration

All settings loaded from environment variables (.env file).
Uses pydantic BaseSettings for validation and defaults.
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
    LLM_MODEL: str = os.environ.get("LLM_MODEL", "dokichat-8b")
    LLM_MAX_TOKENS: int = int(os.environ.get("LLM_MAX_TOKENS", "1024"))
    LLM_TEMPERATURE: float = float(os.environ.get("LLM_TEMPERATURE", "0.85"))

    # ── Conversation ──────────────────────────────────────────
    CONV_MAX_TURNS: int = int(os.environ.get("CONV_MAX_TURNS", "20"))
    CONV_MIN_TURNS: int = int(os.environ.get("CONV_MIN_TURNS", "6"))
    CONV_MAX_TOKENS: int = int(os.environ.get("CONV_MAX_TOKENS", "4000"))
    CONV_MIN_TOKENS: int = int(os.environ.get("CONV_MIN_TOKENS", "1500"))

    # ── Memory / Qdrant ───────────────────────────────────────
    QDRANT_URL: str = os.environ.get("QDRANT_URL", "localhost")
    QDRANT_PORT: int = int(os.environ.get("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION: str = os.environ.get("QDRANT_COLLECTION", "dokichat_memories")
    EMBEDDING_MODEL: str = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
    EMBEDDING_DIM: int = int(os.environ.get("EMBEDDING_DIM", "1024"))

    # ── Database (Phase 2) ────────────────────────────────────
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    REDIS_URL: str = os.environ.get("REDIS_URL", "")

    # ── Content ───────────────────────────────────────────────
    DEFAULT_CONTENT_MODE: str = os.environ.get("DEFAULT_CONTENT_MODE", "romantic")

    # ── Summarizer ────────────────────────────────────────────
    SUMMARY_TRIGGER_TURNS: int = int(os.environ.get("SUMMARY_TRIGGER_TURNS", "10"))
    SUMMARY_MAX_TOKENS: int = int(os.environ.get("SUMMARY_MAX_TOKENS", "500"))


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings singleton."""
    return Settings()
