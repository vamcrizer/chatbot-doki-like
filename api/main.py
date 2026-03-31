"""
DokiChat API — FastAPI Application

Entry point: uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import auth, chat, character, user
from api.middleware.rate_limit import RateLimitMiddleware
from config import get_settings
from core.db_buffer import flush as db_flush, get_pending_count, should_flush_early, FLUSH_INTERVAL
from core.llm_client import chat_complete

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("dokichat")

_settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("=" * 50)
    logger.info("DokiChat API starting...")
    logger.info(f"  Model:    {_settings.LLM_MODEL}")
    logger.info(f"  LLM URL:  {_settings.LLM_BASE_URL}")
    logger.info(f"  Content:  {_settings.DEFAULT_CONTENT_MODE}")
    logger.info("=" * 50)

    # Health check LLM
    try:
        test = chat_complete(
            [{"role": "user", "content": "ping"}],
            temperature=0, max_tokens=5,
        )
        if test:
            logger.info(f"✅ LLM connected: {_settings.LLM_MODEL}")
        else:
            logger.warning("⚠️ LLM responded empty — check model")
    except Exception as e:
        logger.warning(f"⚠️ LLM not reachable: {e}")

    # Start background workers
    flush_task = asyncio.create_task(_db_flush_loop())
    logger.info("Background DB flush worker started")

    yield

    # Stop background worker
    flush_task.cancel()
    try:
        await flush_task
    except asyncio.CancelledError:
        pass

    # Graceful shutdown: flush remaining messages to DB
    pending = get_pending_count()
    if pending > 0:
        logger.info("Shutdown: flushing %d pending messages to DB...", pending)
        try:
            count = db_flush()
            logger.info("Shutdown flush complete: %d messages persisted", count)
        except Exception:
            logger.exception("Shutdown flush failed")

    logger.info("DokiChat API shutting down...")


# ── App ───────────────────────────────────────────────────────

app = FastAPI(
    title="DokiChat API",
    description="AI Companion Chat — romantic & immersive character interactions",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# Routes
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(character.router)
app.include_router(user.router)


# ── Background Workers ────────────────────────────────────────

async def _db_flush_loop():
    """Periodic background worker: flush pending messages to PostgreSQL.

    Runs every 30 seconds, or earlier if queue exceeds threshold.
    Non-blocking: uses asyncio.to_thread for DB operations.
    """
    from core.db_buffer import flush as db_flush

    while True:
        try:
            for _ in range(FLUSH_INTERVAL):
                await asyncio.sleep(1)
                if should_flush_early():
                    break

            count = await asyncio.to_thread(db_flush)
            if count > 0:
                logger.info("DB flush worker: %d messages persisted", count)

        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("DB flush worker error")
            await asyncio.sleep(5)  # back off on error


# ── Health ────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    llm_status = "unknown"
    try:
        test = chat_complete(
            [{"role": "user", "content": "hi"}],
            temperature=0, max_tokens=3,
        )
        llm_status = "connected" if test else "empty_response"
    except Exception:
        llm_status = "disconnected"

    return {
        "status": "ok" if llm_status == "connected" else "degraded",
        "llm": llm_status,
        "model": _settings.LLM_MODEL,
        "db_buffer_pending": get_pending_count(),
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    return {
        "app": "DokiChat API",
        "version": "1.0.0",
        "docs": "/docs",
    }
