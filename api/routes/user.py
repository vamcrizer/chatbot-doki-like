"""
User routes — profile and settings.

All endpoints require valid JWT (Authorization: Bearer <token>).
user_id is derived from the JWT — never trusted from the request path.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException

from api.schemas import UserProfileResponse, UserSettingsRequest
from api.deps import get_current_user, get_session, get_user_repo

logger = logging.getLogger("dokichat.user")
router = APIRouter(prefix="/user", tags=["user"])


@router.get("/profile/{character_id}", response_model=UserProfileResponse)
async def get_user_profile(
    character_id: str,
    current_user: str = Depends(get_current_user),
):
    """Get user profile for a specific character relationship.

    Requires: Authorization: Bearer <access_token>
    """
    session = get_session(current_user, character_id)
    aff = session.affection

    return UserProfileResponse(
        user_id=current_user,
        display_name=session.user_name,
        character_id=character_id,
        memories=[],     # TODO: Qdrant memory recall
        summary=None,    # TODO: session summary
        affection_score=aff.relationship_score if hasattr(aff, "relationship_score") else 0,
        affection_stage=aff.relationship_label if hasattr(aff, "relationship_label") else "stranger",
        total_turns=session.conversation.total_turns,
    )


@router.post("/settings")
async def update_user_settings(
    req: UserSettingsRequest,
    current_user: str = Depends(get_current_user),
):
    """Update user settings.

    Requires: Authorization: Bearer <access_token>
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

    repo = get_user_repo()
    repo.update(current_user, updates)

    logger.info(f"User {current_user} settings update: {updates}")
    return {"status": "ok", "updates": updates}
