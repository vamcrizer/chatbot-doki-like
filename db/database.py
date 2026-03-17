"""
Database connection — async SQLAlchemy engine + session factory.

Graceful degradation: if DATABASE_URL is not set, returns None.
All repositories check for this and fall back to in-memory.
"""
import logging
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from db.models import Base

logger = logging.getLogger("dokichat.db")

_settings = get_settings()
_engine = None
_SessionFactory = None


def get_engine():
    """Get or create SQLAlchemy engine. Returns None if no DATABASE_URL."""
    global _engine
    if _engine is not None:
        return _engine

    db_url = _settings.DATABASE_URL
    if not db_url:
        logger.info("DATABASE_URL not set — using in-memory storage")
        return None

    try:
        _engine = create_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
        logger.info(f"✅ Database connected: {db_url[:30]}...")
        return _engine
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return None


def get_session_factory() -> Optional[sessionmaker]:
    """Get session factory. Returns None if no database."""
    global _SessionFactory
    if _SessionFactory is not None:
        return _SessionFactory

    engine = get_engine()
    if engine is None:
        return None

    _SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    return _SessionFactory


def get_db() -> Optional[Session]:
    """Get a database session. Returns None if no database configured."""
    factory = get_session_factory()
    if factory is None:
        return None
    return factory()


def init_db():
    """Create all tables. Call once on first setup."""
    engine = get_engine()
    if engine is None:
        logger.warning("Cannot init DB — no DATABASE_URL")
        return False

    Base.metadata.create_all(engine)
    logger.info("✅ Database tables created")
    return True
