"""
Prompt Engine — Builds the full message list for LLM chat.

Layers:
  1. Character system prompt (from character card)
  2. Affection state (mood, desire, relationship stage)
  3. Scene context (current scene state)
  4. Format enforcement (universal rules)

Immersion anchor (few-shot priming):
  - Builtin characters: hardcoded in character file
  - UGC characters: auto-generated on first chat, cached GLOBALLY per character+lang
"""
import logging
from characters import get_all_characters
from core.llm_client import chat_complete

logger = logging.getLogger("dokichat.prompt_engine")


# Immersion cache lives in Redis.
# Key pattern: "immersion:{character_key}:{lang_code}"
# Shared across ALL server instances — zero server-side memory.
from core.redis_client import cache_get, cache_set


# ── Universal format enforcement ─────────────────────────────
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


# ── Immersion anchor generation ──────────────────────────────

IMMERSION_GEN_TEMPLATE = """\
You are {char_name}. Write a short scene (2-4 sentences) in {language} \
where you observe something mundane and reveal your personality through it.

Requirements:
- 100% in {language}. ZERO English words.
- Show character voice, not just describe a scene.
- Include one sensory detail and one emotional micro-reaction.
- Keep it under 80 words.

Example style (English): "Moving day reveals truth. Every box is a secret carried in daylight. \
She watches from the kitchen window, fingers curling around a cold mug, \
and wonders if this one will stay."

Now write YOUR version as {char_name}, entirely in {language}."""


# Language code → display name mapping
_LANG_NAMES = {
    "en": "English", "es": "Spanish", "vi": "Vietnamese",
    "pt": "Portuguese", "id": "Indonesian", "de": "German",
    "fr": "French", "hi": "Hindi", "tl": "Filipino",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "th": "Thai", "ru": "Russian", "ar": "Arabic",
    "it": "Italian", "nl": "Dutch", "tr": "Turkish",
}


def detect_language(text: str) -> str:
    """Simple language detection from user message.

    Returns ISO 639-1 code. Falls back to 'en'.
    Uses character-range heuristics for speed (no external lib).
    """
    if not text or len(text.strip()) < 3:
        return "en"

    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            return "zh"
        if '\u3040' <= ch <= '\u309f' or '\u30a0' <= ch <= '\u30ff':
            return "ja"
        if '\uac00' <= ch <= '\ud7af':
            return "ko"
        if '\u0e00' <= ch <= '\u0e7f':
            return "th"
        if '\u0600' <= ch <= '\u06ff':
            return "ar"
        if '\u0900' <= ch <= '\u097f':
            return "hi"

    es_unique = set("¿¡ñ")
    text_lower = text.lower()
    if any(c in es_unique for c in text_lower):
        return "es"

    vi_unique = set("ăâđêôơưằẳẵắặầẩẫấậẻẽẹềểễếệỉĩịỏọồổỗốộờởỡớợủụừửữứựỳỷỹỵ")
    vi_shared = set("àảãáạèéẹìíịòóọùúụỳýỵ")
    vi_unique_count = sum(1 for c in text_lower if c in vi_unique)
    vi_shared_count = sum(1 for c in text_lower if c in vi_shared)

    if vi_unique_count >= 1:
        return "vi"
    if vi_unique_count == 0 and vi_shared_count >= 2:
        vi_words = {"bạn", "tôi", "của", "không", "này", "một", "chào", "xin", "giúp"}
        words_in_text = set(text_lower.split())
        if words_in_text & vi_words:
            return "vi"

    es_accents = set("áéíóú")
    es_accent_count = sum(1 for c in text_lower if c in es_accents)
    if es_accent_count >= 1:
        return "es"

    return "en"


def _generate_immersion_anchor(
    char_name: str,
    system_prompt: str,
    lang_code: str,
) -> dict:
    """Generate a language-specific immersion anchor pair via LLM.

    Returns:
        {"prompt": str, "response": str} or empty dict on failure.
    """
    lang_name = _LANG_NAMES.get(lang_code, "English")

    if lang_code == "en":
        prompt = f"{char_name}, describe what you see right now."
    else:
        prompt_translations = {
            "vi": f"{char_name}, kể cho tôi nghe bạn đang nhìn thấy gì.",
            "es": f"{char_name}, dime qué ves en este momento.",
            "pt": f"{char_name}, me conte o que você está vendo agora.",
            "id": f"{char_name}, ceritakan apa yang kamu lihat sekarang.",
            "de": f"{char_name}, erzähl mir was du gerade siehst.",
            "fr": f"{char_name}, dis-moi ce que tu vois en ce moment.",
            "ja": f"{char_name}、今何が見えるか教えて。",
            "ko": f"{char_name}, 지금 뭐가 보여?",
            "zh": f"{char_name}，告诉我你现在看到了什么。",
            "th": f"{char_name} บอกฉันว่าคุณเห็นอะไรตอนนี้",
            "ru": f"{char_name}, расскажи что ты сейчас видишь.",
        }
        prompt = prompt_translations.get(
            lang_code, f"{char_name}, describe what you see right now."
        )

    gen_prompt = IMMERSION_GEN_TEMPLATE.format(
        char_name=char_name,
        language=lang_name,
    )

    try:
        response = chat_complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": gen_prompt},
            ],
            temperature=0.7,
            max_tokens=200,
        )

        if response and len(response.strip()) > 20:
            logger.info(
                f"Generated immersion anchor for {char_name} [{lang_code}]: "
                f"{len(response)} chars"
            )
            return {"prompt": prompt, "response": response.strip()}

    except Exception as e:
        logger.warning(f"Immersion gen failed for {char_name} [{lang_code}]: {e}")

    return {}


def get_immersion_anchor(
    character_key: str,
    char_name: str,
    system_prompt: str,
    lang_code: str,
) -> dict:
    """Get immersion anchor from Redis, or generate + cache it.

    Redis key: "immersion:{character_key}:{lang_code}"
    Shared across ALL users and server instances.

    Returns:
        {"prompt": str, "response": str} or empty dict
    """
    redis_key = f"immersion:{character_key}:{lang_code}"

    # Try Redis first
    cached = cache_get(redis_key)
    if cached:
        return cached

    # Generate new anchor
    anchor = _generate_immersion_anchor(char_name, system_prompt, lang_code)
    if anchor:
        cache_set(redis_key, anchor)  # No TTL — immersion anchors are permanent
        logger.info(f"Cached immersion anchor in Redis: {redis_key}")
    return anchor


# ── Main builder ─────────────────────────────────────────────

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
    """Build the full message list for LLM.

    Args:
        character_key: Character identifier
        conversation_window: Recent chat messages (7 turns max)
        user_name: User's display name
        total_turns: Total turns so far
        memory_context: TODO — Qdrant semantic recall
        scene_context: [CURRENT SCENE] block from SceneTracker
        affection_context: [CHARACTER INTERNAL STATE] block from AffectionState
        user_message: Current user message (for language detection)
    """
    all_chars = get_all_characters()
    char = all_chars[character_key]

    # Base system prompt with user name substitution
    system = char["system_prompt"].replace("{{user}}", user_name)

    # Layer: Affection state
    if affection_context:
        system += f"\n\n{affection_context}"

    # Layer: Memory context (TODO: Qdrant)
    if memory_context:
        system += f"\n\n{memory_context}"

    # Layer: Scene state
    if scene_context:
        system += f"\n\n{scene_context}"

    # Layer: Format enforcement (always last)
    system += FORMAT_ENFORCEMENT

    messages = [{"role": "system", "content": system}]

    # ── Immersion anchor injection ────────────────────────────
    # Priority: builtin hardcoded > global cache > skip
    immersion_injected = False

    # 1. Builtin characters with hardcoded immersion
    if char.get("immersion_prompt") and char.get("immersion_response"):
        messages.append({"role": "user", "content": char["immersion_prompt"]})
        messages.append({"role": "assistant", "content": char["immersion_response"]})
        immersion_injected = True

    # 2. UGC characters: global cache lookup (shared across all users)
    if not immersion_injected and user_message:
        lang = detect_language(user_message)
        char_name = char.get("name", character_key)
        anchor = get_immersion_anchor(
            character_key=character_key,
            char_name=char_name,
            system_prompt=system,
            lang_code=lang,
        )
        if anchor:
            messages.append({"role": "user", "content": anchor["prompt"]})
            messages.append({"role": "assistant", "content": anchor["response"]})

    # Conversation history
    messages.extend(conversation_window)

    return messages
