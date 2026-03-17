"""
Response Post-Processing — Fix POV narration (first→third person).

Only fixes *narration* blocks. Leaves "quoted dialogue" untouched.
"""
import re


# Pronoun sets per gender
PRONOUNS = {
    "female": {"subject": "she", "object": "her", "possessive": "her",
               "reflexive": "herself", "independent": "hers"},
    "male":   {"subject": "he",  "object": "him", "possessive": "his",
               "reflexive": "himself", "independent": "his"},
    "neutral": {"subject": "they", "object": "them", "possessive": "their",
                "reflexive": "themself", "independent": "theirs"},
}

# Known character genders (fallback if not in character config)
CHARACTER_GENDERS = {
    "sol": "female", "seraphine": "female", "linh_dan": "female",
    "kael": "male", "ren": "male",
}


def fix_pov_narration(text: str, character_name: str, gender: str = None) -> str:
    """Convert first-person narration (*I did X*) to third-person (*She/He did X*).

    Only converts inside *asterisks* (action blocks).
    Leaves "quoted dialogue" untouched.

    Args:
        text: Full response text
        character_name: Character name
        gender: "male", "female", or "neutral". Auto-detected if None.
    """
    if not text or not character_name:
        return text

    # Detect gender
    if gender is None:
        name_lower = character_name.lower().replace(" ", "_")
        gender = CHARACTER_GENDERS.get(name_lower, "female")

    p = PRONOUNS.get(gender, PRONOUNS["female"])

    def replace_in_narration(match):
        content = match.group(1)

        # "I" standalone at start or after punctuation
        content = re.sub(r'\bI\b(?=\s+[a-z])', p["subject"].capitalize(), content)
        content = re.sub(r'(?<=\.\s)\bI\b', p["subject"].capitalize(), content)
        content = re.sub(r'(?<=,\s)\bI\b', p["subject"], content)

        # Contractions
        if gender == "male":
            content = re.sub(r"\bI'm\b", f"{p['subject']}'s", content, flags=re.IGNORECASE)
            content = re.sub(r"\bI am\b", f"{p['subject']} is", content, flags=re.IGNORECASE)
        else:
            content = re.sub(r"\bI'm\b", f"{p['subject']}'s", content, flags=re.IGNORECASE)
            content = re.sub(r"\bI am\b", f"{p['subject']} is", content, flags=re.IGNORECASE)

        content = re.sub(r"\bI've\b", f"{p['subject']}'s", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI'll\b", f"{p['subject']}'ll", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI'd\b", f"{p['subject']}'d", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI don't\b", f"{p['subject']} doesn't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI didn't\b", f"{p['subject']} didn't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI can't\b", f"{p['subject']} can't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI won't\b", f"{p['subject']} won't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI wasn't\b", f"{p['subject']} wasn't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI haven't\b", f"{p['subject']} hasn't", content, flags=re.IGNORECASE)

        # Possessive / object
        content = re.sub(r'\bMy\b', p["possessive"].capitalize(), content)
        content = re.sub(r'\bmy\b', p["possessive"], content)
        content = re.sub(r'\bme\b', p["object"], content, flags=re.IGNORECASE)
        content = re.sub(r'\bmine\b', p["independent"], content, flags=re.IGNORECASE)
        content = re.sub(r'\bmyself\b', p["reflexive"], content, flags=re.IGNORECASE)

        return f"*{content}*"

    return re.sub(r'\*([^*]+)\*', replace_in_narration, text)


def post_process_response(text: str, character_name: str, gender: str = None) -> str:
    """Apply all post-processing fixes to model output."""
    if not text:
        return text
    return fix_pov_narration(text, character_name, gender=gender)
