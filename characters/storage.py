"""
Character Storage — PostgreSQL-backed custom character I/O.

Provides the public interface used by CharacterService:
  save_character(), load_custom_characters(), load_custom_emotional_states(),
  delete_character()

Backed by PostgreSQL when DATABASE_URL is set; falls back to in-memory dict.
"""
import logging
import unicodedata

logger = logging.getLogger("ai_companion.storage.character")

_repo = None


def _get_repo():
    global _repo
    if _repo is not None:
        return _repo
    from db.database import get_session_factory
    from db.repositories.character_repo import CharacterRepository
    _repo = CharacterRepository(get_session_factory())
    return _repo


def _safe_filename(name: str) -> str:
    """Convert character name to a filesystem/URL-safe slug."""
    safe = name.lower().replace(" ", "_")
    safe = unicodedata.normalize("NFD", safe)
    safe = "".join(c for c in safe if not unicodedata.combining(c))
    safe = "".join(c for c in safe if c.isalnum() or c == "_")
    return safe


def save_character(
    character_data: dict,
    emotional_states: dict,
    creator_id: str | None = None,
) -> str:
    """Save a custom character to the database.

    If a character with the same key already exists, it is overwritten.

    Args:
        character_data: Dict with name, system_prompt, opening_scene, etc.
        emotional_states: Dict of emotional state instructions.
        creator_id: User ID of the creator (for attribution).

    Returns:
        The character key (slug derived from name).
    """
    name = character_data.get("name", "unknown")
    key = _safe_filename(name)

    repo = _get_repo()
    existing = repo.find_by_key(key)

    data = {
        "key": key,
        "creator_id": creator_id,
        "name": name,
        "gender": character_data.get("gender", "female"),
        "system_prompt": character_data.get("system_prompt", ""),
        "greeting": character_data.get("opening_scene", ""),
        "greetings_alt": character_data.get("greetings_alt", []),
        "pacing": character_data.get("pacing", "guarded"),
        "content_mode": character_data.get("content_mode", "romantic"),
        "bio_original": character_data.get("_bio", ""),
        "emotional_states": emotional_states,
    }

    if existing:
        repo.update(existing["id"], data)
        logger.info("Updated character '%s' in database", key)
    else:
        repo.create(data)
        logger.info("Saved character '%s' to database", key)

    return key


def load_custom_characters() -> dict:
    """Load all custom characters from the database.

    Returns:
        Dict[key, character_dict] compatible with the characters package format.
    """
    repo = _get_repo()
    result = {}
    for char in repo.get_all():
        key = char.get("key", "")
        if not key:
            continue
        result[key] = {
            "name": char["name"],
            "gender": char["gender"],
            "system_prompt": char["system_prompt"],
            "opening_scene": char["greeting"],
            "greetings_alt": char["greetings_alt"],
            "pacing": char["pacing"],
            "content_mode": char["content_mode"],
            "_bio": char["bio_original"],
        }
    return result


def load_custom_emotional_states() -> dict:
    """Load emotional states for all custom characters.

    Returns:
        Dict[key, emotional_states_dict]
    """
    repo = _get_repo()
    return {
        char["key"]: char["emotional_states"]
        for char in repo.get_all()
        if char.get("key")
    }


def delete_character(key: str) -> bool:
    """Delete a custom character from the database.

    Returns:
        True if deleted, False if not found.
    """
    repo = _get_repo()
    deleted = repo.delete_by_key(key)
    if deleted:
        logger.info("Deleted character '%s' from database", key)
    return deleted
