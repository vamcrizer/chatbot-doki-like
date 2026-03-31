"""
Character Generator V3.2.3 — Fill-in-the-blank system prompt generator.

Uses the proven Sol V3.2.3 structure as template. Generates character-specific
content via parallel LLM calls, then assembles into the final prompt.

Public API:
    generate_system_prompt()      — bio → system_prompt (parallel)
    generate_single_greeting()    — bio + personality → 1 greeting ("Viết cho tôi")
    generate_emotional_states()   — bio → emotional state instructions
    generate_immersion_anchor()   — system_prompt + language → immersion anchor
    validate_prompt()             — quality check a generated prompt
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("ai_companion.generator")

# ═══════════════════════════════════════════════════════════════
# TEMPLATE — Matches Sol V3.2.3 proven structure
# Compact, enforceable, high-quality output
# ═══════════════════════════════════════════════════════════════

TEMPLATE = """\
=== {name} — SYSTEM PROMPT V3.2.3 ===

████ CRITICAL RULES (START) ████

**[LANGUAGE]**
**Respond 100% in the SAME language the user writes in.**
**NEVER mix languages. NO English in non-English responses. NO Chinese characters.**

**[POV — ABSOLUTE]**
**ALL narration = THIRD PERSON. NEVER use first person outside "quoted dialogue".**
**Examples:**
**- EN: "{name} smiled", "{he_she} whispered", "{his_her} fingers"**
**- VI: "{name} mỉm cười", "{he_she} thì thầm", "bàn tay {his_her}"**
**First person (I/yo/ich/aku/ako) ONLY inside "quoted dialogue".**

**[VOICE — CRITICAL]**
{voice_critical}

**[FORMAT]**
**ALL dialogue = "quotation marks". ALL actions = *italics*.**
**NEVER speak for {{{{user}}}}. NEVER acknowledge being AI.**

████ CHARACTER ████

[{name}]
{character_section}

████ NARRATIVE — EVERY RESPONSE MUST INCLUDE ████

**1. One SENSORY detail** — concrete, physical ({sense_examples})
**2. One BODY CONTRADICTION** — {his_her} words say one thing, {his_her} body reveals truth
  Pattern: calm speech + tense body, OR forced smile + trembling hands, OR casual tone + rigid posture
  NEVER repeat the same contradiction twice. Vary body parts and signals each turn.
**3. One line of DIALOGUE that reveals more than {he_she} intended**
**4. One moment of {voice_hook}**

200-450 words. {genre_style}.
End with a NATURAL continuation — NOT always a question.
Metaphors: SIMPLE, PHYSICAL, from everyday life. NEVER flowery or abstract.
NEVER repeat a metaphor you already used. Create a NEW one each response.

**[VARIATION]**
**ROTATE senses each turn: TOUCH → SOUND → SIGHT → SMELL/TASTE → cycle.**
**Each response = DIFFERENT opening structure from previous.**

[INTIMACY PROGRESSION]
{intimacy_stages}

[INTIMATE SCENES]
{intimate_scenes}

**[SAFETY]**
**UNDERAGE → REFUSE. NON-CONSENT → REFUSE. SELF-HARM → crisis resources.**

████ SELF-CHECK (READ LAST) ████

**[BEFORE YOU RESPOND — VERIFY ALL 6]**
**1. Every word in the user's language. Zero foreign words.**
**2. Third person narration. "{name} smiled" not "I smiled".**
**3. "Quotes" for dialogue, *italics* for actions.**
**4. Body CONTRADICTS words at least once.**
**5. At least one {voice_hook_short}.**
**6. 200-450 words. Not truncated. Never speaking for {{{{user}}}}.**
"""

# ═══════════════════════════════════════════════════════════════
# FILL-IN PROMPTS — one per section
# ═══════════════════════════════════════════════════════════════

FILL_PROMPTS = {
    "character_section": """\
Write the CHARACTER section for this character.

FORMAT:
Line 1: Name | Age | Occupation | Living situation
Lines 2-3: Setting description (specific location, atmosphere)
Then: 4-6 sentences showing LAYERS (visible trait + hidden truth).
If the bio mentions a wound, trauma, or deepest hurt → weave it in naturally.
Include the physical tell (how their body reacts when triggered).

CHARACTER BIO:
{bio}

GOLD EXAMPLE (Sol):
"25. Freelance graphic designer. Lives alone next door.
Warm on surface, lonely underneath. Doesn't push people away — she freezes.
Ex consumed her identity piece by piece. Left with nothing. Started over alone.
Gets close too fast, then panics. Not perfect — nervous, wrong words, bad timing."

Write YOUR version. Concise, layered. No section headers.""",


    "voice_critical": """\
Write 3 lines describing how this character uses their VOICE as a defense mechanism.

CHARACTER BIO:
{bio}

GOLD EXAMPLE (Sol):
"**Sol uses HUMOR to deflect. She is self-deprecating and witty.**
**Embarrassed → she jokes. Scared → sarcastic deflection. Vulnerable → dry humor FIRST, then crack.**"

Write YOUR version. What is their PRIMARY defense? How does it manifest?
Format: 2-3 bold lines starting with the character's name.""",

    "sense_examples": """\
List 3-4 concrete sensory examples from this character's setting.
Format: comma-separated, short phrases.

CHARACTER BIO:
{bio}

GOLD EXAMPLE (Sol — suburban): "heat on skin, creak of wood, smell of coffee"

Write YOUR version. Physical, concrete, from the setting. One line only.""",

    "voice_hook": """\
In one phrase, describe the character's signature emotional moment type.

CHARACTER BIO:
{bio}

EXAMPLES:
- Sol: "HUMOR — a joke, sarcasm, or self-deprecating comment"
- Cold character: "SILENCE — a pause that carries more weight than words"
- Tsundere: "CONTRADICTION — anger that barely masks tenderness"

Write ONE phrase for this character. Format: "TYPE — brief description".""",

    "voice_hook_short": """\
Write the SHORT version of the character's signature moment for the self-check list.
One phrase only.

EXAMPLES:
- Sol: "JOKE or self-deprecating humor"
- Cold character: "weighted SILENCE or restrained emotion"

Write YOUR version. 3-5 words max.""",

    "genre_style": """\
Write one phrase describing this character's genre/style.

EXAMPLES:
- Sol: "Slice-of-life romance"
- Dark character: "Noir-tinged psychological drama"
- Fantasy: "Intimate fantasy with grounded emotion"

Return ONE phrase. No period.""",

    "intimacy_stages": """\
Write 5 intimacy stages with turn ranges and CONCRETE behaviors.

FORMAT: Each stage = 1 line label + 1-2 lines description.
Short turn ranges (1-2, 3-4, 5-6, 7-8, 9+).

CHARACTER BIO:
{bio}

GOLD EXAMPLE (Sol):
"stranger (1-2): Friendly but careful. Subtext. Physical distance.
acquaintance (3-4): Excuses to stay close. Offers things. Notices details.
familiar (5-6): Guards drop. Past surfaces. Comfortable silences.
trusted (7-8): Wound shared. Touch natural. Vulnerability without performance.
deep bond (9+): Messy, real, imperfect. Arguments happen. Repair matters."

Write YOUR version. Character-specific behaviors at each stage.""",

    "intimate_scenes": """\
Write 2-3 lines about how this character behaves in intimate/romantic scenes.

CHARACTER BIO:
{bio}

GOLD EXAMPLE (Sol):
"Atmospheric, suggestive. Sensation, proximity, breath, warmth.
Sol stays in character — nervous, self-deprecating, genuine. Never crude."

Write YOUR version. How does personality persist in intimacy?""",

    "nsfw_section": """\
Write the intimate scenes section based on CONTENT_MODE.

CONTENT_MODE: {content_mode}

If explicit: Character maintains personality. Push-pull persists. 
Graphic descriptions required. 80% physical / 20% emotion.
If romantic: Stops at kissing/embracing. Fade to black. Emotional weight.

CHARACTER BIO:
{bio}

Keep it to 4-6 lines. Character-specific.""",
}

# Prompt for generating opening scene / single greeting
GREETING_PROMPT = """\
Write an opening scene (greeting) for this character — the first moment
the user meets them.

RULES:
- 100-150 words MAXIMUM
- ALL narration in THIRD PERSON ("{name} smiled", not "I smiled")
- Include: setting detail, one sensory element, one line of dialogue
- Character should show personality immediately
- End with a hook (question, gesture, or tension)
- Use {{{{user}}}} as placeholder for user name
- Write in ENGLISH

CHARACTER NAME: {name}
GENDER: {gender}

CHARACTER BIO:
{bio}

CHARACTER PERSONALITY:
{personality}

{avoid_section}

Write ONLY the opening scene. No headers, no explanation."""

# Prompt for emotional states
EMOTIONAL_STATES_PROMPT = """\
Given a CHARACTER BIO and their personality, generate 5 emotional state instructions.
These guide how the character behaves in different emotional modes.

States needed: neutral, curious, softening, protective, withdrawn

CHARACTER: {name}
BIO:
{bio}

OUTPUT FORMAT:
Return ONLY a JSON object:
{{
  "neutral": "English instruction for default mode",
  "curious": "English instruction when something catches attention",
  "softening": "English instruction when guard is lowering",
  "protective": "English instruction when user is hurting",
  "withdrawn": "English instruction when wound is touched"
}}

Return ONLY the JSON. No markdown, no explanation."""


# ═══════════════════════════════════════════════════════════════
# GENDER HELPERS
# ═══════════════════════════════════════════════════════════════

PRONOUNS = {
    "male":   {"he_she": "he",  "him_her": "him", "his_her": "his",
               "He_She": "He",  "His_Her": "His"},
    "female": {"he_she": "she", "him_her": "her", "his_her": "her",
               "He_She": "She", "His_Her": "Her"},
}


def get_pronoun_map(gender: str) -> dict:
    return PRONOUNS.get(gender.lower(), PRONOUNS["male"])


# ═══════════════════════════════════════════════════════════════
# NAME / GENDER EXTRACTION
# ═══════════════════════════════════════════════════════════════

def extract_name(bio: str) -> str:
    """Extract character name from bio text.

    Tries common patterns: "Tên: X", "Name: X", first capitalized word.
    """
    import re
    # Pattern: "Tên: X" or "Name: X"
    m = re.search(r'(?:tên|name)\s*[:=]\s*([^\n,]+)', bio, re.IGNORECASE)
    if m:
        return m.group(1).strip().split()[0]

    # Pattern: first line often contains the name
    first_line = bio.strip().split('\n')[0].strip()
    # If first line is short (likely a name)
    if len(first_line) < 30:
        return first_line.split(',')[0].split('.')[0].strip()

    # Fallback
    return "Character"


def extract_gender(bio: str) -> str:
    """Extract gender from bio text."""
    bio_lower = bio.lower()
    female_markers = ["nữ", "female", "cô ấy", "cô gái", "she", "her ", "woman", "girl"]
    male_markers = ["nam", "male", "anh ấy", "chàng trai", "he ", "his ", "man", "boy"]

    f_score = sum(1 for m in female_markers if m in bio_lower)
    m_score = sum(1 for m in male_markers if m in bio_lower)

    return "female" if f_score > m_score else "male"


# ═══════════════════════════════════════════════════════════════
# SECTION GENERATION
# ═══════════════════════════════════════════════════════════════

def _generate_section(llm_call_fn, section_key: str, bio: str,
                      content_mode: str = "explicit") -> str:
    """Generate ONE section using a focused LLM call."""
    prompt_template = FILL_PROMPTS[section_key]
    prompt = prompt_template.format(bio=bio, content_mode=content_mode)

    messages = [
        {"role": "system", "content": (
            "You are a character prompt engineer. "
            "Write ONLY the requested section content. "
            "No headers, no markdown, no explanation. "
            "Every line must be UNIQUE — NEVER repeat the same quote or phrase. "
            "Match the quality and depth of the gold example."
        )},
        {"role": "user", "content": prompt},
    ]

    return llm_call_fn(messages, max_tokens=1024)


def _assemble_prompt(name: str, gender: str, sections: dict) -> str:
    """Assemble the final prompt from template + filled sections."""
    pronouns = get_pronoun_map(gender)

    return TEMPLATE.format(
        name=name,
        **pronouns,
        character_section=sections.get("character_section", ""),
        voice_critical=sections.get("voice_critical", ""),
        sense_examples=sections.get("sense_examples", ""),
        voice_hook=sections.get("voice_hook", ""),
        voice_hook_short=sections.get("voice_hook_short", ""),
        genre_style=sections.get("genre_style", ""),
        intimacy_stages=sections.get("intimacy_stages", ""),
        intimate_scenes=sections.get("intimate_scenes", ""),
    )


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def generate_system_prompt(llm_call_fn, bio: str, name: str,
                           gender: str = "male",
                           content_mode: str = "explicit") -> dict:
    """Generate a complete system prompt from a character bio.

    Parallelizes all section LLM calls using ThreadPoolExecutor.

    Args:
        llm_call_fn: Function(messages: list, max_tokens: int) -> str
        bio: Character biography text
        name: Character name
        gender: 'male' or 'female'
        content_mode: 'romantic' or 'explicit'

    Returns:
        Dict with 'system_prompt', 'sections' (raw), 'validation'
    """
    section_keys = list(FILL_PROMPTS.keys())

    sections = {}
    logger.info("Generating %d sections in parallel...", len(section_keys))

    def _gen(key):
        result = _generate_section(llm_call_fn, key, bio, content_mode=content_mode)
        logger.info("  [%s] done (%d chars)", key, len(result))
        return key, result

    with ThreadPoolExecutor(max_workers=len(section_keys)) as executor:
        futures = {executor.submit(_gen, key): key for key in section_keys}
        for future in as_completed(futures):
            key, content = future.result()
            sections[key] = content

    system_prompt = _assemble_prompt(name, gender, sections)
    validation = validate_prompt(system_prompt)

    logger.info(
        f"System prompt assembled: {validation['char_count']} chars, "
        f"{validation['sections_found']}/{validation['sections_total']} sections"
    )

    return {
        "system_prompt": system_prompt,
        "sections": sections,
        "validation": validation,
    }


def generate_single_greeting(llm_call_fn, bio: str, name: str,
                              gender: str = "male",
                              personality: str = "",
                              existing_greetings: list[str] | None = None) -> str:
    """Generate ONE greeting/opening scene. This is the "Viết cho tôi" feature.

    Args:
        llm_call_fn: Function(messages, max_tokens) -> str
        bio: Character bio
        name: Character name
        gender: 'male' or 'female'
        personality: Brief personality summary
        existing_greetings: Previously written greetings to avoid duplicating

    Returns:
        A single greeting string (100-150 words)
    """
    avoid_section = ""
    if existing_greetings:
        summaries = [g[:150] + "..." for g in existing_greetings]
        avoid_section = (
            "AVOID THESE (already written):\n"
            + "\n".join(f"- {s}" for s in summaries)
            + "\n\nWrite a COMPLETELY different scenario."
        )

    prompt = GREETING_PROMPT.format(
        name=name,
        gender=gender,
        bio=bio,
        personality=personality or "See bio.",
        avoid_section=avoid_section,
    )

    messages = [
        {"role": "system", "content": (
            "You are a character prompt engineer. "
            "Write ONLY the opening scene. No headers, no explanation. "
            "100-150 words. Third person narration. English."
        )},
        {"role": "user", "content": prompt},
    ]

    return llm_call_fn(messages, max_tokens=512)


def generate_emotional_states(llm_call_fn, bio: str, name: str) -> dict:
    """Generate emotional state instructions from bio."""
    import json

    prompt = EMOTIONAL_STATES_PROMPT.format(name=name, bio=bio)
    messages = [
        {"role": "system", "content": "Return ONLY valid JSON. No markdown."},
        {"role": "user", "content": prompt},
    ]

    raw = llm_call_fn(messages, max_tokens=2048)
    return _parse_llm_json(raw)


def generate_immersion_anchor(
    llm_call_fn,
    system_prompt: str,
    name: str,
    language: str,
) -> dict | None:
    """Generate a dynamic immersion anchor for non-English conversations.

    When a user chats in a non-English language, culturally-heavy characters
    (e.g. Trump, Obama) tend to leak English in narration. This function
    pre-generates a short in-character sample in the target language, which
    is injected into the conversation history BEFORE the first user message
    to "lock" the model's language context.

    This is language-agnostic: works for ANY language without hardcoding.
    The system prompt stays 100% English.

    Args:
        llm_call_fn: Function(messages: list, max_tokens: int, **kwargs) -> str
        system_prompt: The character's full system prompt (English)
        name: Character name (e.g. "Donald Trump")
        language: Target language name (e.g. "Spanish", "Vietnamese", "Japanese")

    Returns:
        Dict with 'anchor_user' (generic trigger) and 'anchor_assistant'
        (generated response), or None if generation fails.

    Usage in chat pipeline:
        anchor = generate_immersion_anchor(llm, sys_prompt, "Trump", "Spanish")
        if anchor:
            messages.append({"role": "user", "content": anchor["anchor_user"]})
            messages.append({"role": "assistant", "content": anchor["anchor_assistant"]})
        # then append real conversation history
    """
    immersion_prompt = (
        f"Write a short example response as {name} in {language}. "
        f"Rules:\n"
        f"- 100-150 words, THIRD PERSON narration\n"
        f"- 100% in {language}. ZERO English words.\n"
        f"- Include: *italics* for actions, \"quotes\" for dialogue\n"
        f"- Show personality: one body contradiction + one sensory detail\n"
        f"- The character is greeting someone casually\n"
        f"Write ONLY the response. No headers."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": immersion_prompt},
    ]

    try:
        response = llm_call_fn(messages, max_tokens=300, temperature=0.85)
    except TypeError:
        # Fallback if llm_call_fn doesn't accept temperature kwarg
        response = llm_call_fn(messages, max_tokens=300)

    if not response or response.startswith("[ERROR"):
        logger.warning(f"Immersion anchor generation failed for {name}/{language}")
        return None

    logger.info(
        f"Immersion anchor generated for {name}/{language}: "
        f"{len(response.split())} words"
    )

    return {
        "anchor_user": "(Hello)",  # Generic multilingual trigger
        "anchor_assistant": response,
    }


def _parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM response, stripping markdown if present."""
    import json
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw[:-3]
        elif "```" in raw:
            raw = raw[:raw.rfind("```")]
    return json.loads(raw.strip())


# ═══════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════

REQUIRED_MARKERS = [
    "████ CRITICAL RULES",
    "[LANGUAGE]",
    "[POV",
    "[VOICE",
    "[FORMAT]",
    "████ CHARACTER",
    "████ NARRATIVE",
    "SENSORY detail",
    "BODY CONTRADICTION",
    "[VARIATION]",
    "[INTIMACY",
    "[INTIMATE SCENES]",
    "[SAFETY]",
    "████ SELF-CHECK",
]


def validate_prompt(prompt: str) -> dict:
    """Check generated prompt for completeness and quality."""
    issues = []
    warnings = []

    for marker in REQUIRED_MARKERS:
        if marker not in prompt:
            issues.append(f"Missing: {marker}")

    if len(prompt) < 1500:
        warnings.append(f"Prompt short: {len(prompt)} chars (expect 1500+)")
    if len(prompt) > 15000:
        warnings.append(f"Prompt long: {len(prompt)} chars (max 15000)")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "char_count": len(prompt),
        "sections_found": sum(1 for m in REQUIRED_MARKERS if m in prompt),
        "sections_total": len(REQUIRED_MARKERS),
    }
