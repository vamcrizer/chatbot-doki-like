"""
User routes — profile and settings.
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
    aff = session.affection

    return UserProfileResponse(
        user_id=user_id,
        display_name=session.user_name,
        character_id=character_id,
        memories=[],     # TODO: Qdrant memory recall
        summary=None,    # TODO: session summary
        affection_score=aff.score if hasattr(aff, "score") else 0,
        affection_stage=aff.stage if hasattr(aff, "stage") else "stranger",
        total_turns=session.conversation.total_turns,
    )


@router.post("/settings/{user_id}")
async def update_user_settings(user_id: str, req: UserSettingsRequest):
    """Update user settings (applies to future sessions).

    # TODO: Persist to PostgreSQL
    """
    updates = {}
    if req.display_name:
        updates["display_name"] = req.display_name
    if req.user_name:
        updates["display_name"] = req.user_name
    if req.content_mode:
        updates["content_mode"] = req.content_mode

    if not updates:
        raise HTTPException(400, "No settings to update")

    logger.info(f"User {user_id} settings update: {updates}")
    return {"status": "ok", "updates": updates}
