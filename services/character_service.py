"""
Character Service — character management logic.
"""
import logging
from typing import Optional

from characters import get_all_characters
from characters.generator import (
    generate_character_from_bio,
    generate_emotional_states,
    save_character,
    delete_character as delete_char_file,
)

logger = logging.getLogger("dokichat.service.character")

BUILTIN_KEYS = {"kael", "seraphine", "ren", "linh_dan", "sol"}

SECTION_MARKERS = [
    "RULE 0", "CORE PHILOSOPHY", "FORBIDDEN", "CHARACTER", "WOUND",
    "VOICE", "NARRATIVE STYLE", "PROPS", "CONTRADICTION", "CHALLENGE",
    "ENGAGEMENT", "SENSES", "INTIMACY", "ROMANTIC", "18+",
    "RECOVERY", "MEMORY INTEGRITY", "SAFETY",
]


class CharacterService:
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

    def get_detail(self, character_id: str) -> Optional[dict]:
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
            "immersion_prompt": char.get("immersion_prompt", ""),
            "is_custom": character_id not in BUILTIN_KEYS,
            "system_prompt_length": len(char.get("system_prompt", "")),
        }

    def create_from_bio(self, bio: str, content_mode: str = "romantic") -> dict:
        """Generate character from bio using LLM.

        Returns:
            {key, name, system_prompt_length, sections_detected}
        """
        logger.info(f"Generating character ({len(bio)} chars, mode={content_mode})")

        char_data = generate_character_from_bio(bio, content_mode=content_mode)
        char_data["_bio"] = bio

        emo_states = generate_emotional_states(bio, char_data.get("name", ""))

        key = save_character(char_data, emo_states)

        sp = char_data.get("system_prompt", "")
        sections_found = sum(
            1 for m in SECTION_MARKERS if m.upper() in sp.upper()
        )

        logger.info(f"Created '{key}' ({sections_found}/18 sections)")

        return {
            "key": key,
            "name": char_data.get("name", key),
            "system_prompt_length": len(sp),
            "sections_detected": sections_found,
        }

    def delete(self, key: str) -> bool:
        """Delete a custom character. Returns False if builtin or not found."""
        if key in BUILTIN_KEYS:
            return False
        return delete_char_file(key)
