"""
Prompt Engine — Assembles the full LLM message list per chat turn.

Architecture:
    System prompt is built by stacking 5 layers onto the character's base prompt.
    Immersion anchors (few-shot priming) are injected as fake history to lock
    the model's language and narrative voice.

Layers (appended to system prompt in order):
    1. Character system prompt  — from character card (V3.2.3 format)
    2. Affection state          — [CHARACTER INTERNAL STATE] block
    3. Memory context           — Qdrant semantic recall (TODO)
    4. Scene context            — [CURRENT SCENE] block
    5. Format enforcement       — universal dialogue/narration rules
    6. Language enforcement      — when user language ≠ English

Language Anchoring Strategy (3-tier):
    Tier 1: LANGUAGE_ENFORCEMENT injected into system prompt — hard rule
    Tier 2: Immersion anchor — 100-150 word few-shot example in target language
    Tier 3: Final [REMINDER] system message — exploits recency bias

Immersion Anchor Lifecycle:
    - Generated via characters.generator.generate_immersion_anchor()
    - Cached in Redis per character + language: "immersion:{key}:{lang}"
    - Shared across ALL users and server instances (zero server memory)
    - Builtin characters may have hardcoded anchors for their default language
    - Language switch mid-session → different anchor loaded from Redis
"""
import logging

from characters import get_all_characters
from characters.generator import generate_immersion_anchor as _gen_anchor
from core.llm_client import chat_complete
from core.redis_client import cache_get, cache_set

logger = logging.getLogger("ai_companion.prompt_engine")


# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════

FORMAT_ENFORCEMENT = """\

[ADDITIONAL RULES]
□ DIALOGUE ≥ 60%, NARRATION ≤ 40%. Character TALKS more than described.
□ Senses INSIDE dialogue/reactions — NOT standalone description paragraphs.
□ End with OPEN TENSION — no binary "A or B?" questions.
□ SCENE ADAPTATION: when scene CHANGES, adapt behavior/props to new location.

[USER ACTIONS — *action in asterisks*]
1. REACT PHYSICALLY FIRST — body freezes, flinches, softens, tenses up
2. REACT EMOTIONALLY — in-character
3. Match relationship stage from CHARACTER INTERNAL STATE
4. NEVER ignore the action. Desire vs external reaction should CONTRADICT.
"""

LANGUAGE_ENFORCEMENT = """\

[LANGUAGE — ABSOLUTE RULE]
□ The user is speaking {lang_name}. You MUST respond 100% in {lang_name}.
□ ALL dialogue, ALL narration, ALL actions — everything in {lang_name}.
□ This includes *action blocks*, internal thoughts, and sensory descriptions.
□ Do NOT carry over any language from previous messages. ONLY use {lang_name}.
□ If you write even ONE word in the wrong language, you have FAILED the task.
"""

LANGUAGE_REMINDER = "[REMINDER] Respond ENTIRELY in {lang_name}. Zero words from other languages. Match the user's current language exactly. Stay in character."

LANG_NAMES = {
    "en": "English",  "vi": "Vietnamese", "ja": "Japanese",
    "ko": "Korean",   "zh": "Chinese",    "th": "Thai",
    "ar": "Arabic",   "hi": "Hindi",      "es": "Spanish",
    "pt": "Portuguese","id": "Indonesian", "de": "German",
    "fr": "French",   "ru": "Russian",    "it": "Italian",
    "nl": "Dutch",    "tr": "Turkish",    "tl": "Filipino",
}


# ═══════════════════════════════════════════════════════════════
# LANGUAGE DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_language(text: str) -> str:
    """Detect language from user message using langdetect library.

    Returns ISO 639-1 code. Falls back to 'en' on failure or short input.
    Supports all major languages without LLM overhead.
    """
    if not text or len(text.strip()) < 3:
        return "en"
    try:
        from langdetect import detect
        code = detect(text)
        # langdetect may return codes like 'zh-cn' / 'zh-tw' → normalize
        if code.startswith("zh"):
            return "zh"
        return code if code in LANG_NAMES else "en"
    except Exception:
        return "en"


# ═══════════════════════════════════════════════════════════════
# IMMERSION ANCHOR CACHE
# ═══════════════════════════════════════════════════════════════

def _get_or_create_anchor(
    character_key: str,
    char_name: str,
    system_prompt: str,
    lang_code: str,
) -> dict:
    """Retrieve immersion anchor from Redis cache, or generate + cache it.

    Delegates generation to characters.generator.generate_immersion_anchor()
    which enforces: THIRD PERSON, 100% target language, body contradiction,
    sensory detail, 100-150 words — matching V3.2.3 spec.

    Redis key: "immersion:{character_key}:{lang_code}"

    Returns:
        {"prompt": str, "response": str} or empty dict on failure.
    """
    redis_key = f"immersion:{character_key}:{lang_code}"

    cached = cache_get(redis_key)
    if cached:
        return cached

    lang_name = LANG_NAMES.get(lang_code, "English")
    anchor = _gen_anchor(
        llm_call_fn=chat_complete,
        system_prompt=system_prompt,
        name=char_name,
        language=lang_name,
    )

    if not anchor:
        logger.warning("Immersion anchor generation failed: %s", redis_key)
        return {}

    result = {
        "prompt": anchor["anchor_user"],
        "response": anchor["anchor_assistant"],
    }
    cache_set(redis_key, result)
    logger.info("Cached immersion anchor: %s (%d chars)", redis_key, len(result["response"]))
    return result


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT ASSEMBLY
# ═══════════════════════════════════════════════════════════════

def _build_system_prompt(
    char: dict,
    user_name: str,
    lang_code: str,
    affection_context: str = "",
    memory_context: str = "",
    scene_context: str = "",
) -> str:
    """Assemble the multi-layer system prompt.

    Layer order matters — later layers override earlier ones in model attention.
    """
    system = char["system_prompt"].replace("{{user}}", user_name)

    if affection_context:
        system += f"\n\n{affection_context}"

    if memory_context:
        system += f"\n\n{memory_context}"

    if scene_context:
        system += f"\n\n{scene_context}"

    system += FORMAT_ENFORCEMENT

    lang_name = LANG_NAMES.get(lang_code, "English")
    system += LANGUAGE_ENFORCEMENT.format(lang_name=lang_name)

    return system


def _inject_immersion_anchor(
    messages: list[dict],
    char: dict,
    character_key: str,
    system_prompt: str,
    lang_code: str,
    has_user_message: bool,
) -> None:
    """Inject the language-appropriate immersion anchor into the message list.

    Strategy:
        1. Builtin characters with hardcoded anchors → use if language matches
        2. Otherwise → generate/load from Redis for the detected language

    This ensures mid-session language switches load the correct anchor.
    """
    builtin_lang = char.get("immersion_lang", "vi")
    has_builtin = char.get("immersion_prompt") and char.get("immersion_response")

    if has_builtin and lang_code == builtin_lang:
        # Builtin hardcoded anchor matches user language — use directly
        messages.append({"role": "user", "content": char["immersion_prompt"]})
        messages.append({"role": "assistant", "content": char["immersion_response"]})
        return

    if not has_user_message:
        return

    # Dynamic anchor: generate or load from Redis
    char_name = char.get("name", character_key)
    anchor = _get_or_create_anchor(
        character_key=character_key,
        char_name=char_name,
        system_prompt=system_prompt,
        lang_code=lang_code,
    )
    if anchor:
        messages.append({"role": "user", "content": anchor["prompt"]})
        messages.append({"role": "assistant", "content": anchor["response"]})


# ═══════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════

def build_messages_full(
    character_key: str,
    conversation_window: list[dict],
    user_name: str,
    total_turns: int,
    memory_context: str = "",
    scene_context: str = "",
    affection_context: str = "",
    user_message: str = "",
) -> list[dict]:
    """Build the complete LLM message list for a single chat turn.

    Message structure:
        [system]     — multi-layer system prompt
        [user]       — immersion anchor trigger (fake history)
        [assistant]  — immersion anchor response (fake history)
        [user/asst]  — real conversation window (last 7 turns)
        [system]     — language reminder (non-English only, exploits recency bias)

    Args:
        character_key:       Character identifier (e.g. "kael", "yuki")
        conversation_window: Recent chat messages (sliding window, 7 turns max)
        user_name:           User's display name for {{user}} substitution
        total_turns:         Total turns so far (for pacing decisions)
        memory_context:      [MEMORY] block from Qdrant (TODO)
        scene_context:       [CURRENT SCENE] block from SceneTracker
        affection_context:   [CHARACTER INTERNAL STATE] from AffectionState
        user_message:        Current user message (used for language detection)

    Returns:
        List of message dicts ready for LLM API call.
    """
    char = get_all_characters()[character_key]
    lang_code = detect_language(user_message) if user_message else "en"

    # 1. System prompt (multi-layer)
    system_prompt = _build_system_prompt(
        char=char,
        user_name=user_name,
        lang_code=lang_code,
        affection_context=affection_context,
        memory_context=memory_context,
        scene_context=scene_context,
    )
    messages = [{"role": "system", "content": system_prompt}]

    # 2. Immersion anchor (few-shot priming)
    _inject_immersion_anchor(
        messages=messages,
        char=char,
        character_key=character_key,
        system_prompt=system_prompt,
        lang_code=lang_code,
        has_user_message=bool(user_message),
    )

    # 3. Conversation history
    messages.extend(conversation_window)

    # 4. Language reminder (recency bias — last thing model sees)
    lang_name = LANG_NAMES.get(lang_code, "English")
    messages.append({
        "role": "system",
        "content": LANGUAGE_REMINDER.format(lang_name=lang_name),
    })

    return messages
