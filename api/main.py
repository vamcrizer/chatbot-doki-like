"""
DokiChat API — FastAPI Application

Entry point: uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import chat, character, user
from api.middleware.rate_limit import RateLimitMiddleware
from config import get_settings
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

    yield

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
app.include_router(chat.router)
app.include_router(character.router)
app.include_router(user.router)


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
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    return {
        "app": "DokiChat API",
        "version": "1.0.0",
        "docs": "/docs",
    }
