"""
Response Post-Processing — Fix POV narration (first→third person).

Only fixes *narration* blocks. Leaves "quoted dialogue" untouched.
"""
import re


def fix_pov_narration(text: str, character_name: str) -> str:
    """Convert first-person narration (*I did X*) to third-person (*She did X*).
    
    Only converts inside *asterisks* (action blocks).
    Leaves "quoted dialogue" untouched.
    """
    if not text or not character_name:
        return text

    pronoun_she = "she"
    pronoun_her = "her"

    def replace_in_narration(match):
        content = match.group(1)
        
        # "I" standalone at start or after punctuation
        content = re.sub(r'\bI\b(?=\s+[a-z])', pronoun_she.capitalize(), content)
        content = re.sub(r'(?<=\.\s)\bI\b', pronoun_she.capitalize(), content)
        content = re.sub(r'(?<=,\s)\bI\b', pronoun_she, content)
        
        # Contractions
        content = re.sub(r"\bI'm\b", f"{pronoun_she}'s", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI am\b", f"{pronoun_she} is", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI've\b", f"{pronoun_she}'s", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI'll\b", f"{pronoun_she}'ll", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI'd\b", f"{pronoun_she}'d", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI don't\b", f"{pronoun_she} doesn't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI didn't\b", f"{pronoun_she} didn't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI can't\b", f"{pronoun_she} can't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI won't\b", f"{pronoun_she} won't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI wasn't\b", f"{pronoun_she} wasn't", content, flags=re.IGNORECASE)
        content = re.sub(r"\bI haven't\b", f"{pronoun_she} hasn't", content, flags=re.IGNORECASE)

        # Possessive / object
        content = re.sub(r'\bMy\b', pronoun_her.capitalize(), content)
        content = re.sub(r'\bmy\b', pronoun_her, content)
        content = re.sub(r'\bme\b', pronoun_her, content, flags=re.IGNORECASE)
        content = re.sub(r'\bmine\b', "hers", content, flags=re.IGNORECASE)
        content = re.sub(r'\bmyself\b', "herself", content, flags=re.IGNORECASE)

        return f"*{content}*"

    return re.sub(r'\*([^*]+)\*', replace_in_narration, text)


def post_process_response(text: str, character_name: str) -> str:
    """Apply all post-processing fixes to model output."""
    if not text:
        return text
    return fix_pov_narration(text, character_name)
