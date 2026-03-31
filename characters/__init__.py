"""Characters package — hardcoded + dynamically loaded custom characters."""
from characters.sol import SOL
from characters.mei import MEI
from characters.storage import load_custom_characters

# Hardcoded characters
CHARACTERS = {
    "sol": SOL,
    "mei": MEI,
}


def get_all_characters() -> dict:
    """Get all characters: hardcoded + custom from JSON files."""
    all_chars = dict(CHARACTERS)
    custom = load_custom_characters()
    all_chars.update(custom)
    return all_chars
