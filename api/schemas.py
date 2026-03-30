"""
DokiChat API — Pydantic schemas for request/response models.

Character creation follows C.AI-style input fields:
  name, subtitle, description, definition, greetings, tags, gender, visibility

Tags drive content_mode automatically:
  tags contain "18+"|"nsfw"|"explicit" → explicit mode
  otherwise → romantic (companion, fade-to-black)
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional


# ── NSFW tag detection ────────────────────────────────────────

NSFW_TAGS = {"18+", "nsfw", "explicit", "adult", "erotic", "mature"}


def detect_content_mode(tags: list[str]) -> str:
    """Tags drive content mode. NSFW tags → explicit, else → romantic."""
    if not tags:
        return "romantic"
    tag_set = {t.lower().strip() for t in tags}
    if tag_set & NSFW_TAGS:
        return "explicit"
    return "romantic"


# ── Chat ──────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Request body for /chat/stream"""
    user_id: str = Field(..., description="Unique user identifier")
    character_id: str = Field(..., description="Character ID")
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    user_name: str = Field(default="bạn", max_length=50, description="User display name")


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


# ── Character — C.AI-style fields ────────────────────────────

class CharacterSummary(BaseModel):
    """Brief character info for listing."""
    id: str
    name: str
    subtitle: Optional[str] = None
    gender: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    visibility: str = "public"
    is_custom: bool = False
    creator_id: Optional[str] = None


class CharacterListResponse(BaseModel):
    """Response for /character/list"""
    characters: list[CharacterSummary]


class CharacterCreateRequest(BaseModel):
    """
    Request body for /character/create — mirrors C.AI form.

    Fields (matching Character.AI):
      name:         Character name (required)
      subtitle:     Short tagline (optional)
      description:  Brief description (optional)
      definition:   Detailed character definition (optional, advanced)
      greetings:    Up to 5 custom greetings (optional, AI generates if empty)
      ai_greeting:  If true, each new chat gets an AI variation of stored greetings
      tags:         Content tags — drives content_mode automatically
      gender:       male | female
      visibility:   public | private
    """
    name: str = Field(..., min_length=1, max_length=100)
    gender: str = Field(default="female", pattern="^(male|female)$")
    subtitle: str = Field(default="", max_length=200, description="Short tagline")
    description: str = Field(default="", max_length=2000, description="Brief description")
    definition: str = Field(default="", max_length=5000, description="Detailed character definition")
    system_prompt: str = Field(..., description="Generated system prompt (from /generate-prompt)")
    opening_scene: str = Field(default="", description="Primary greeting / opening scene")
    greetings_alt: list[str] = Field(
        default_factory=list,
        description="Alternative greetings (max 5, max 4096 chars each)"
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Content tags. Include '18+' or 'nsfw' for explicit mode."
    )
    pacing: str = Field(default="guarded", description="Relationship pacing: guarded | normal | eager")
    visibility: str = Field(default="public", pattern="^(public|private)$")

    @field_validator("greetings_alt")
    @classmethod
    def validate_greetings(cls, v):
        if len(v) > 5:
            raise ValueError("Maximum 5 greetings allowed")
        for g in v:
            if len(g) > 4096:
                raise ValueError("Each greeting must be ≤ 4096 characters")
        return v

    @property
    def content_mode(self) -> str:
        """Derived from tags — not a user input."""
        return detect_content_mode(self.tags)

    @property
    def bio(self) -> str:
        """Construct bio from C.AI fields for storage."""
        parts = []
        if self.subtitle:
            parts.append(self.subtitle)
        if self.description:
            parts.append(self.description)
        if self.definition:
            parts.append(self.definition)
        return "\n\n".join(parts) if parts else self.name


class CharacterCreateResponse(BaseModel):
    """Response for /character/create"""
    id: str
    name: str
    content_mode: str
    system_prompt_length: int
    greetings_count: int


class GeneratePromptRequest(BaseModel):
    """
    Request body for /character/generate-prompt

    C.AI fields → fill 8 sections → assemble system prompt V3.2.3
    """
    name: str = Field(..., min_length=1, max_length=100)
    gender: str = Field(default="female", pattern="^(male|female)$")
    subtitle: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=2000)
    definition: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list)

    @property
    def content_mode(self) -> str:
        return detect_content_mode(self.tags)

    @property
    def bio(self) -> str:
        """Construct bio from C.AI fields for generator."""
        parts = [f"Name: {self.name}"]
        if self.subtitle:
            parts.append(self.subtitle)
        if self.description:
            parts.append(self.description)
        if self.definition:
            parts.append(self.definition)
        return "\n\n".join(parts)


class GeneratePromptResponse(BaseModel):
    """Response for /character/generate-prompt"""
    system_prompt: str
    name: str
    gender: str
    content_mode: str
    char_count: int
    sections_found: int
    sections_total: int
    valid: bool


class GenerateGreetingRequest(BaseModel):
    """
    Request body for /character/generate-greeting ("Write for me" / "Viết giúp tôi")

    AI generates a greeting based on character info.
    existing_greetings avoids duplicating what user already has.
    """
    name: str = Field(..., min_length=1, max_length=100)
    gender: str = Field(default="female", pattern="^(male|female)$")
    subtitle: str = Field(default="")
    description: str = Field(default="")
    definition: str = Field(default="")
    existing_greetings: list[str] = Field(
        default_factory=list,
        description="Already saved greetings — AI will avoid duplicating these"
    )

    @property
    def bio(self) -> str:
        """Construct bio from C.AI fields."""
        parts = [f"Name: {self.name}"]
        if self.subtitle:
            parts.append(self.subtitle)
        if self.description:
            parts.append(self.description)
        if self.definition:
            parts.append(self.definition)
        return "\n\n".join(parts)

    @property
    def personality(self) -> str:
        """Extract personality hint from description."""
        return self.description or self.subtitle or ""


class GenerateGreetingResponse(BaseModel):
    """Response for /character/generate-greeting"""
    greeting: str
    word_count: int


class CharacterDeleteRequest(BaseModel):
    """Request body for /character/delete"""
    id: str


# ── User ──────────────────────────────────────────────────────

class UserProfileResponse(BaseModel):
    """Response for /user/profile"""
    user_id: str
    display_name: str
    bio: Optional[str] = None  # optional, just toss into context if provided
    character_id: str
    memories: list[dict]
    summary: Optional[str] = None
    affection_score: float = 0
    affection_stage: str = "stranger"
    total_turns: int = 0


class UserSettingsRequest(BaseModel):
    """Request body for /user/settings"""
    display_name: Optional[str] = Field(None, max_length=50)
    bio: Optional[str] = Field(None, max_length=500, description="User bio — just toss into context as-is")
    user_name: Optional[str] = Field(None, max_length=50, description="Alias for display_name")
    content_mode: Optional[str] = Field(None, pattern="^(romantic|explicit)$")


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


# ── Regenerate ────────────────────────────────────────────────

class RegenerateRequest(BaseModel):
    """Request body for /chat/regenerate"""
    user_id: str = Field(..., description="Unique user identifier")
    character_id: str = Field(..., description="Character ID")
    user_name: str = Field(default="bạn", max_length=50, description="User display name")


# ── Greeting ──────────────────────────────────────────────────

class GreetingResponse(BaseModel):
    """
    Response for /chat/greeting

    If ai_greeting is enabled: returns AI-generated variation.
    Otherwise: returns one of the stored greetings.
    """
    character_id: str
    greeting: str
    is_ai_variation: bool = False
    total_greetings: int = 0
