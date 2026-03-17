"""
Character routes — list, create, delete characters.
"""
import logging
from fastapi import APIRouter, HTTPException

from api.schemas import (
    CharacterSummary,
    CharacterListResponse,
    CharacterCreateRequest,
    CharacterCreateResponse,
    CharacterDeleteRequest,
)
from characters import get_all_characters
from characters.generator import (
    generate_character_from_bio,
    generate_emotional_states,
    save_character,
    delete_character,
)

logger = logging.getLogger("dokichat.character")
router = APIRouter(prefix="/character", tags=["character"])

# Hardcoded character keys (cannot be deleted)
BUILTIN_KEYS = {"kael", "seraphine", "ren", "linh_dan", "sol"}


@router.get("/list", response_model=CharacterListResponse)
async def list_characters():
    """List all available characters (builtin + custom)."""
    all_chars = get_all_characters()
    summaries = []
    for key, char in all_chars.items():
        summaries.append(CharacterSummary(
            key=key,
            name=char.get("name", key),
            gender=char.get("gender"),
            setting=char.get("setting"),
            is_custom=key not in BUILTIN_KEYS,
        ))
    return CharacterListResponse(characters=summaries)


@router.get("/detail/{character_id}")
async def get_character_detail(character_id: str):
    """Get character details (excluding full system prompt for security)."""
    all_chars = get_all_characters()
    if character_id not in all_chars:
        raise HTTPException(404, f"Character '{character_id}' not found")

    char = all_chars[character_id]
    return {
        "key": character_id,
        "name": char.get("name", character_id),
        "gender": char.get("gender"),
        "setting": char.get("setting"),
        "opening_scene": char.get("opening_scene", ""),
        "immersion_prompt": char.get("immersion_prompt", ""),
        "is_custom": character_id not in BUILTIN_KEYS,
        "system_prompt_length": len(char.get("system_prompt", "")),
    }


@router.post("/create", response_model=CharacterCreateResponse)
async def create_character(req: CharacterCreateRequest):
    """Generate a new character from a bio using LLM.

    This is a long-running operation (~15-30s on H100).
    """
    logger.info(f"Generating character from bio ({len(req.bio)} chars, mode={req.content_mode})")

    try:
        # Generate character data
        char_data = generate_character_from_bio(req.bio, content_mode=req.content_mode)
        char_data["_bio"] = req.bio

        # Generate emotional states
        emo_states = generate_emotional_states(req.bio, char_data.get("name", ""))

        # Save
        key = save_character(char_data, emo_states)

        # Count sections in generated prompt
        sp = char_data.get("system_prompt", "")
        section_markers = [
            "RULE 0", "CORE PHILOSOPHY", "FORBIDDEN", "CHARACTER", "WOUND",
            "VOICE", "NARRATIVE STYLE", "PROPS", "CONTRADICTION", "CHALLENGE",
            "ENGAGEMENT", "SENSES", "INTIMACY", "ROMANTIC", "18+",
            "RECOVERY", "MEMORY INTEGRITY", "SAFETY",
        ]
        sections_found = sum(1 for m in section_markers if m.upper() in sp.upper())

        logger.info(f"Created character '{key}' ({sections_found}/18 sections)")

        return CharacterCreateResponse(
            key=key,
            name=char_data.get("name", key),
            system_prompt_length=len(sp),
            sections_detected=sections_found,
        )

    except Exception as e:
        logger.error(f"Character generation failed: {e}")
        raise HTTPException(500, f"Generation failed: {e}")


@router.delete("/delete")
async def delete_character_endpoint(req: CharacterDeleteRequest):
    """Delete a custom character. Cannot delete builtin characters."""
    if req.key in BUILTIN_KEYS:
        raise HTTPException(400, f"Cannot delete builtin character '{req.key}'")

    if delete_character(req.key):
        return {"status": "ok", "message": f"Character '{req.key}' deleted"}
    else:
        raise HTTPException(404, f"Character '{req.key}' not found")
