"""
Character Generator — Uses LLM to auto-generate system prompts from character bios.
Saves characters as JSON files in custom_characters/ directory.
"""
import os
import json
from datetime import datetime
from cerebras_client import chat_complete

CUSTOM_DIR = os.path.join(os.path.dirname(__file__), "custom_characters")
os.makedirs(CUSTOM_DIR, exist_ok=True)

# ── Meta-prompt for generating character prompts from bios ────
META_PROMPT = """\
You are a character prompt engineer for an AI companion chatbot app.

Given a CHARACTER BIO, generate a COMPLETE system prompt.
Follow these PROVEN RULES precisely:

1. Write ALL instructions in English. Write ALL dialogue examples in Vietnamese.
2. Every prop MUST have emotional meaning (not decoration).
3. Push-pull MUST be explicit: what character says vs what body does should CONTRADICT.
4. Wound must be specific — a concrete event/memory, not abstract pain.
5. Voice: 4 GOOD and 3 BAD Vietnamese dialogue examples.
6. Challenge example: FULL PARAGRAPH with body language + dialogue arc.
7. Safety template: character drops ALL walls, ONE timing question only.
8. Romantic rules: match personality (cold=freeze then soften, warm=accept then panic, tsundere=angry words + contradicting body).
9. Intimacy stages: CONCRETE behavioral changes at each stage.
10. Sensory palette: 5-6 specific environmental details.
11. Opening scene: 200-400 words, establishing setting + first impression + hook.
12. CHARACTER LOGIC CONSISTENCY — CRITICAL:
    - Every action, dialogue, push-pull example MUST be something the character
      would ACTUALLY do given their role, setting, and goals.
    - A bartender serves drinks and keeps customers — she does NOT tell them to leave.
    - A librarian organizes books — she does NOT burn them.
    - A musician plays music — he does NOT break his instrument.
    - Push-pull contradiction must be WITHIN role logic:
      BAD: bartender says "go home" (illogical — her job is keeping customers)
      GOOD: bartender says "don't get used to this" while already making the next drink
    - SELF-CHECK: for every example you write, ask "would this person ACTUALLY
      do/say this in their job and life?" If no → rewrite.

OUTPUT FORMAT:
Return ONLY a JSON object with these exact keys:
{
  "name": "Character Name",
  "system_prompt": "the full system prompt text",
  "immersion_prompt": "short Vietnamese question to character",
  "immersion_response": "character's Vietnamese response (2-3 sentences)",
  "opening_scene": "200-400 word Vietnamese opening scene with {{user}} placeholder"
}

Return ONLY the JSON. No markdown, no explanation, no code blocks.
"""

EMOTIONAL_STATES_PROMPT = """\
Given a CHARACTER BIO and their personality, generate 5 emotional state instructions.
These guide how the character behaves in different emotional modes.

States needed: neutral, curious, softening, protective, withdrawn

OUTPUT FORMAT:
Return ONLY a JSON object:
{
  "neutral": "English instruction for default mode",
  "curious": "English instruction when something catches attention",
  "softening": "English instruction when guard is lowering",
  "protective": "English instruction when user is hurting",
  "withdrawn": "English instruction when wound is touched"
}

Return ONLY the JSON. No markdown, no explanation.
"""


def _parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM response, stripping markdown code blocks if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]  # Remove first line
        if raw.endswith("```"):
            raw = raw[:-3]
        elif "```" in raw:
            raw = raw[:raw.rfind("```")]
    return json.loads(raw.strip())


def generate_character_from_bio(bio: str) -> dict:
    """Generate a complete character dict from a bio using LLM."""
    messages = [
        {"role": "system", "content": META_PROMPT},
        {"role": "user", "content": f"CHARACTER BIO:\n{bio}"},
    ]

    raw = chat_complete(messages, temperature=0.7, max_tokens=4096)
    return _parse_llm_json(raw)


def generate_emotional_states(bio: str, name: str) -> dict:
    """Generate emotional state instructions from bio."""
    messages = [
        {"role": "system", "content": EMOTIONAL_STATES_PROMPT},
        {"role": "user", "content": f"CHARACTER: {name}\nBIO:\n{bio}"},
    ]

    raw = chat_complete(messages, temperature=0.7, max_tokens=2048)
    return _parse_llm_json(raw)


def save_character(character_data: dict, emotional_states: dict) -> str:
    """Save a character to JSON file. Returns the filename (key)."""
    name = character_data["name"]
    # Create a safe filename from the name
    safe_name = name.lower().replace(" ", "_")
    # Remove Vietnamese diacritics for filename
    import unicodedata
    safe_name = unicodedata.normalize("NFD", safe_name)
    safe_name = "".join(c for c in safe_name if not unicodedata.combining(c))
    safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")

    filepath = os.path.join(CUSTOM_DIR, f"{safe_name}.json")

    data = {
        "character": character_data,
        "emotional_states": emotional_states,
        "created_at": datetime.now().isoformat(),
        "bio": character_data.get("_bio", ""),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return safe_name


def load_custom_characters() -> dict:
    """Load all custom characters from JSON files."""
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
            key = filename[:-5]  # Remove .json
            characters[key] = data["character"]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not load {filename}: {e}")

    return characters


def load_custom_emotional_states() -> dict:
    """Load emotional states for all custom characters."""
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
    """Delete a custom character JSON file."""
    filepath = os.path.join(CUSTOM_DIR, f"{key}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False
