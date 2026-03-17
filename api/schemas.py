"""
DokiChat API — Pydantic schemas for request/response models.
"""
from pydantic import BaseModel, Field
from typing import Optional


# ── Chat ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request body for /chat/stream"""
    user_id: str = Field(..., description="Unique user identifier")
    character_id: str = Field(..., description="Character key (sol, kael, etc.)")
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    user_name: str = Field(default="bạn", description="Display name for user")
    content_mode: str = Field(default="romantic", pattern="^(romantic|explicit)$")


class ChatMessage(BaseModel):
    """Single chat message."""
    role: str  # user | assistant
    content: str
    turn_number: Optional[int] = None


class ChatHistoryResponse(BaseModel):
    """Response for /chat/history"""
    character_id: str
    messages: list[ChatMessage]
    total_turns: int


# ── Character ─────────────────────────────────────────────────

class CharacterSummary(BaseModel):
    """Brief character info for listing."""
    key: str
    name: str
    gender: Optional[str] = None
    setting: Optional[str] = None
    is_custom: bool = False


class CharacterListResponse(BaseModel):
    """Response for /character/list"""
    characters: list[CharacterSummary]


class CharacterCreateRequest(BaseModel):
    """Request body for /character/create"""
    bio: str = Field(..., min_length=50, max_length=5000)
    content_mode: str = Field(default="romantic", pattern="^(romantic|explicit)$")


class CharacterCreateResponse(BaseModel):
    """Response for /character/create"""
    key: str
    name: str
    system_prompt_length: int
    sections_detected: int


class CharacterDeleteRequest(BaseModel):
    """Request body for /character/delete"""
    key: str


# ── User ──────────────────────────────────────────────────────

class UserProfileResponse(BaseModel):
    """Response for /user/profile"""
    user_id: str
    character_id: str
    memories: list[dict]
    summary: Optional[str] = None
    affection_score: float = 0
    affection_stage: str = "stranger"
    total_turns: int = 0


class UserSettingsRequest(BaseModel):
    """Request body for /user/settings"""
    content_mode: Optional[str] = Field(None, pattern="^(romantic|explicit)$")
    user_name: Optional[str] = None


# ── Session ───────────────────────────────────────────────────

class SessionState(BaseModel):
    """Current session state for a user-character pair."""
    user_id: str
    character_id: str
    total_turns: int
    emotion: str
    affection_score: float
    affection_stage: str
    scene: str


# ── Health ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response for /health"""
    status: str  # ok | degraded | error
    llm: str  # connected | disconnected
    version: str
