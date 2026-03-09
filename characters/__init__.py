"""Characters package — hardcoded + dynamically loaded custom characters."""
from characters.kael import KAEL
from characters.seraphine import SERAPHINE
from characters.ren import REN
from characters.linh_dan import LINH_DAN
from character_generator import load_custom_characters

# Hardcoded characters
CHARACTERS = {
    "kael": KAEL,
    "seraphine": SERAPHINE,
    "ren": REN,
    "linh_dan": LINH_DAN,
}


def get_all_characters() -> dict:
    """Get all characters: hardcoded + custom from JSON files."""
    all_chars = dict(CHARACTERS)
    custom = load_custom_characters()
    all_chars.update(custom)
    return all_chars
