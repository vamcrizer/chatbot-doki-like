"""
Character Storage — JSON file I/O for custom characters.

Handles saving, loading, and deleting UGC characters from the
custom_characters/ directory.
"""
import os
import json
import unicodedata
from datetime import datetime

from config import CUSTOM_CHARACTERS_DIR

CUSTOM_DIR = str(CUSTOM_CHARACTERS_DIR)

# ── Performance: In-memory LRU-like Cache ───────────────────
_cache_mtime: float = 0.0
_characters_cache: dict = {}
_states_cache: dict = {}

def _get_folder_mtime() -> float:
    """Get max modification time of custom_characters folder and its files."""
    if not os.path.exists(CUSTOM_DIR):
        return 0.0
    return max(
        (os.path.getmtime(os.path.join(CUSTOM_DIR, f)) 
         for f in os.listdir(CUSTOM_DIR) if f.endswith(".json")),
        default=os.path.getmtime(CUSTOM_DIR)
    )


def _parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM response, stripping markdown code blocks if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
        elif "```" in raw:
            raw = raw[:raw.rfind("```")]
    return json.loads(raw.strip())


def _safe_filename(name: str) -> str:
    """Convert character name to filesystem-safe key."""
    safe = name.lower().replace(" ", "_")
    safe = unicodedata.normalize("NFD", safe)
    safe = "".join(c for c in safe if not unicodedata.combining(c))
    safe = "".join(c for c in safe if c.isalnum() or c == "_")
    return safe


def save_character(character_data: dict, emotional_states: dict) -> str:
    """Save a character to JSON file.

    Args:
        character_data: Dict with name, system_prompt, opening_scene, etc.
        emotional_states: Dict of emotional state instructions.

    Returns:
        The character key (safe filename).
    """
    os.makedirs(CUSTOM_DIR, exist_ok=True)

    name = character_data.get("name", "unknown")
    key = _safe_filename(name)
    filepath = os.path.join(CUSTOM_DIR, f"{key}.json")

    data = {
        "character": character_data,
        "emotional_states": emotional_states,
        "created_at": datetime.now().isoformat(),
        "bio": character_data.get("_bio", ""),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return key


def load_custom_characters() -> dict:
    """Load all custom characters from JSON files, with fast mtime caching."""
    global _cache_mtime, _characters_cache

    current_mtime = _get_folder_mtime()
    if current_mtime > 0 and current_mtime == _cache_mtime and _characters_cache:
        return _characters_cache

    characters = {}
    if not os.path.exists(CUSTOM_DIR):
        return characters

    for filename in os.listdir(CUSTOM_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(CUSTOM_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            key = filename[:-5]
            characters[key] = data["character"]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not load {filename}: {e}")

    _characters_cache = characters
    _cache_mtime = current_mtime
    return characters


def load_custom_emotional_states() -> dict:
    """Load emotional states for all custom characters.

    Returns:
        Dict[key, emotional_states_dict]
    """
    states = {}
    if not os.path.exists(CUSTOM_DIR):
        return states

    for filename in os.listdir(CUSTOM_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(CUSTOM_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            key = filename[:-5]
            states[key] = data.get("emotional_states", {})
        except (json.JSONDecodeError, KeyError):
            pass

    return states


def delete_character(key: str) -> bool:
    """Delete a custom character JSON file.

    Returns:
        True if deleted, False if not found.
    """
    filepath = os.path.join(CUSTOM_DIR, f"{key}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False
