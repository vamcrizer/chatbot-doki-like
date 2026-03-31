"""
Character routes — list, create, delete, generate prompts and greetings.

Public endpoints (no auth):
  GET  /character/list
  GET  /character/detail/{id}
  POST /character/generate-prompt
  POST /character/generate-greeting

Protected endpoints (JWT required):
  POST   /character/create
  DELETE /character/delete
"""
import logging
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from api.schemas import (
    CharacterSummary,
    CharacterListResponse,
    CharacterCreateRequest,
    CharacterCreateResponse,
    CharacterDeleteRequest,
    GeneratePromptRequest,
    GeneratePromptResponse,
    GenerateGreetingRequest,
    GenerateGreetingResponse,
)
from core.llm_client import chat_complete
from services.character_service import CharacterService

logger = logging.getLogger("dokichat.routes.character")
router = APIRouter(prefix="/character", tags=["character"])


def _llm_call_fn(messages: list, max_tokens: int = 1024) -> str:
    """Bridge: adapt chat_complete to generator's expected interface."""
    return chat_complete(messages, temperature=0.7, max_tokens=max_tokens)


# Shared service instance
_service = CharacterService(llm_call_fn=_llm_call_fn)


# ── List / Detail (public) ────────────────────────────────────

@router.get("/list", response_model=CharacterListResponse)
async def list_characters():
    """List all available characters (builtin + custom). Public."""
    results = _service.list_all()
    summaries = []
    for c in results:
        summaries.append(CharacterSummary(
            id=c.get("key", ""),
            name=c.get("name", ""),
            gender=c.get("gender"),
            is_custom=c.get("is_custom", False),
        ))
    return CharacterListResponse(characters=summaries)


@router.get("/detail/{character_id}")
async def get_character_detail(character_id: str):
    """Get character details (excluding full system prompt). Public."""
    detail = _service.get_detail(character_id)
    if not detail:
        raise HTTPException(404, f"Character '{character_id}' not found")
    return detail


# ── Generate (public, no save) ────────────────────────────────

@router.post("/generate-prompt", response_model=GeneratePromptResponse)
async def generate_prompt(req: GeneratePromptRequest):
    """Generate a system prompt from C.AI fields. Does NOT save. Public.

    User reviews the result, optionally edits, then calls /create.
    """
    try:
        result = _service.gen_prompt(
            bio=req.bio,
            name=req.name,
            gender=req.gender,
            content_mode=req.content_mode,
        )
        return GeneratePromptResponse(
            content_mode=req.content_mode,
            **result,
        )
    except Exception as e:
        logger.error("Prompt generation failed: %s", e)
        raise HTTPException(500, f"Generation failed: {e}")


@router.post("/generate-greeting", response_model=GenerateGreetingResponse)
async def generate_greeting(req: GenerateGreetingRequest):
    """Generate ONE greeting ("Viết cho tôi" button). Public."""
    try:
        greeting = _service.gen_greeting(
            bio=req.bio,
            name=req.name,
            gender=req.gender,
            personality=req.personality,
            existing_greetings=req.existing_greetings,
        )
        return GenerateGreetingResponse(
            greeting=greeting,
            word_count=len(greeting.split()),
        )
    except Exception as e:
        logger.error("Greeting generation failed: %s", e)
        raise HTTPException(500, f"Generation failed: {e}")


# ── Create / Delete (protected) ───────────────────────────────

@router.post("/create", response_model=CharacterCreateResponse)
async def create_character(
    req: CharacterCreateRequest,
    current_user: str = Depends(get_current_user),
):
    """Save a new character. Requires auth.

    Typical flow:
    1. POST /generate-prompt → get system_prompt
    2. User reviews/edits prompt
    3. POST /generate-greeting (optional) → get greeting(s)
    4. POST /create → save everything
    """
    try:
        result = _service.create(
            name=req.name,
            gender=req.gender,
            bio=req.bio,
            system_prompt=req.system_prompt,
            opening_scene=req.opening_scene,
            greetings_alt=req.greetings_alt,
            content_mode=req.content_mode,
            pacing=req.pacing,
            user_id=current_user,
        )
        logger.info("Character created by user %s: %s", current_user, result["key"])
        return CharacterCreateResponse(
            id=result["key"],
            name=result["name"],
            content_mode=req.content_mode,
            system_prompt_length=result["system_prompt_length"],
            greetings_count=1 + len(req.greetings_alt),
        )
    except Exception as e:
        logger.error("Character creation failed: %s", e)
        raise HTTPException(500, f"Creation failed: {e}")


@router.delete("/delete")
async def delete_character_endpoint(
    req: CharacterDeleteRequest,
    current_user: str = Depends(get_current_user),
):
    """Delete a custom character. Requires auth. Cannot delete builtin characters."""
    if not _service.delete(req.id):
        raise HTTPException(400, f"Cannot delete '{req.id}' (builtin or not found)")
    logger.info("Character %s deleted by user %s", req.id, current_user)
    return {"status": "ok", "message": f"Character '{req.id}' deleted"}
