"""
Character Service — business logic for character management.

Delegates generation to characters.generator, storage to characters.storage.
Routes should only call this service, never generator/storage directly.
"""
import logging

from characters import get_all_characters
from characters.generator import (
    generate_system_prompt,
    generate_single_greeting,
    generate_emotional_states,
    extract_name,
    extract_gender,
)
from characters.storage import save_character, delete_character

logger = logging.getLogger("dokichat.service.character")

BUILTIN_KEYS = {"kael", "seraphine", "ren", "linh_dan", "sol"}


class CharacterService:

    def __init__(self, llm_call_fn):
        """Initialize with an LLM call function.

        Args:
            llm_call_fn: Function(messages: list, max_tokens: int) -> str
        """
        self._llm = llm_call_fn

    # ── Read ──────────────────────────────────────────────────

    def list_all(self) -> list[dict]:
        """List all characters with summary info."""
        all_chars = get_all_characters()
        return [
            {
                "key": key,
                "name": char.get("name", key),
                "gender": char.get("gender"),
                "setting": char.get("setting"),
                "is_custom": key not in BUILTIN_KEYS,
            }
            for key, char in all_chars.items()
        ]

    def get_detail(self, character_id: str) -> dict | None:
        """Get character detail (excludes full system prompt)."""
        all_chars = get_all_characters()
        if character_id not in all_chars:
            return None

        char = all_chars[character_id]
        return {
            "key": character_id,
            "name": char.get("name", character_id),
            "gender": char.get("gender"),
            "setting": char.get("setting"),
            "opening_scene": char.get("opening_scene", ""),
            "greetings_count": 1 + len(char.get("greetings_alt", [])),
            "is_custom": character_id not in BUILTIN_KEYS,
            "system_prompt_length": len(char.get("system_prompt", "")),
        }

    # ── Generate ──────────────────────────────────────────────

    def gen_prompt(self, bio: str, name: str = "", gender: str = "",
                   content_mode: str = "romantic") -> dict:
        """Generate system_prompt from bio. Returns prompt + metadata.

        This is the "generate-prompt" endpoint — generates but does NOT save.
        """
        if not name:
            name = extract_name(bio)
        if not gender:
            gender = extract_gender(bio)

        result = generate_system_prompt(
            llm_call_fn=self._llm,
            bio=bio,
            name=name,
            gender=gender,
            content_mode=content_mode,
        )

        return {
            "system_prompt": result["system_prompt"],
            "name": name,
            "gender": gender,
            "char_count": result["validation"]["char_count"],
            "sections_found": result["validation"]["sections_found"],
            "sections_total": result["validation"]["sections_total"],
            "valid": result["validation"]["valid"],
        }

    def gen_greeting(self, bio: str, name: str = "Character",
                     gender: str = "female", personality: str = "",
                     existing_greetings: list[str] | None = None) -> str:
        """Generate ONE greeting. This is the "Viết cho tôi" feature."""
        return generate_single_greeting(
            llm_call_fn=self._llm,
            bio=bio,
            name=name,
            gender=gender,
            personality=personality,
            existing_greetings=existing_greetings,
        )

    # ── Create ────────────────────────────────────────────────

    def create(self, name: str, gender: str, bio: str,
               system_prompt: str, opening_scene: str = "",
               greetings_alt: list[str] | None = None,
               content_mode: str = "romantic",
               pacing: str = "guarded",
               user_id: str | None = None) -> dict:
        """Save a complete character. User provides all fields.

        Returns:
            {key, name, system_prompt_length}
        """
        char_data = {
            "name": name,
            "gender": gender,
            "system_prompt": system_prompt,
            "opening_scene": opening_scene,
            "greetings_alt": greetings_alt or [],
            "content_mode": content_mode,
            "pacing": pacing,
            "_bio": bio,
        }

        # Generate emotional states
        emo_states = generate_emotional_states(self._llm, bio, name)

        key = save_character(char_data, emo_states, creator_id=user_id)
        logger.info("Created character '%s' (%d chars)", key, len(system_prompt))

        return {
            "key": key,
            "name": name,
            "system_prompt_length": len(system_prompt),
        }

    # ── Delete ────────────────────────────────────────────────

    def delete(self, key: str) -> bool:
        """Delete a custom character. Returns False if builtin or not found."""
        if key in BUILTIN_KEYS:
            return False
        return delete_character(key)
