"""
User routes — profile, memories, settings.
"""
import logging
from fastapi import APIRouter, HTTPException

from api.schemas import UserProfileResponse, UserSettingsRequest
from api.deps import get_session

logger = logging.getLogger("dokichat.user")
router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile/{user_id}/{character_id}", response_model=UserProfileResponse)
async def get_user_profile(user_id: str, character_id: str):
    """Get user profile for a specific character relationship."""
    session = get_session(user_id, character_id)
    mem = session.memory
    aff = session.affection

    return UserProfileResponse(
        user_id=user_id,
        character_id=character_id,
        memories=[
            {"text": m["text"], "type": m.get("type", "user_fact")}
            for m in mem.get_all()
        ],
        summary=mem.get_summary() or None,
        affection_score=aff.score if hasattr(aff, 'score') else 0,
        affection_stage=aff.stage if hasattr(aff, 'stage') else "stranger",
        total_turns=session.conversation.total_turns,
    )


@router.post("/settings/{user_id}")
async def update_user_settings(user_id: str, req: UserSettingsRequest):
    """Update user settings (applies to future sessions)."""
    # In Phase 2, this writes to PostgreSQL
    # For now, we just acknowledge
    updates = {}
    if req.content_mode:
        updates["content_mode"] = req.content_mode
    if req.user_name:
        updates["user_name"] = req.user_name

    if not updates:
        raise HTTPException(400, "No settings to update")

    logger.info(f"User {user_id} settings update: {updates}")
    return {"status": "ok", "updates": updates}


@router.delete("/memories/{user_id}/{character_id}")
async def clear_memories(user_id: str, character_id: str):
    """Clear all memories for a user-character pair."""
    session = get_session(user_id, character_id)
    mem = session.memory
    if hasattr(mem, 'clear'):
        mem.clear()
    return {"status": "ok", "message": "Memories cleared"}
