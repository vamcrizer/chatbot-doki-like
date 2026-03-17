from characters import get_all_characters
from emotion import get_all_emotional_states

# ── Universal format enforcement ─────────────────────────────
# Injected at the end of EVERY character's system prompt.
# Character card defines WHO. This block defines HOW TO FORMAT.
FORMAT_ENFORCEMENT = """\

[SELF-CHECK — BEFORE EVERY OUTPUT]
□ Language = match user. Zero foreign words in *action* AND "dialogue".
□ *Italics* for action, "quotes" for dialogue. Narrative text can flow naturally.
□ NO projection (feelings/intentions user hasn't stated).
□ DIALOGUE ≥ 60%, NARRATION ≤ 40%. Character must TALK more than be described.
  BAD: 5 paragraphs of scene description + 1 short sentence of dialogue.
  GOOD: Character speaks 3-5 lines, each wrapped in 1-2 lines of action/reaction.
□ Senses INSIDE dialogue and reactions — NOT standalone description paragraphs.
  BAD: "Mùi whisky nồng trong không khí. Tiếng mưa rơi ngoài cửa sổ."
  GOOD: *Anh nhấp một ngụm whisky, vị cay nồng còn vương khi nói* "Cậu uống gì?"
□ ≥1 proximity/physical moment per response.
□ Prop ≠ previous turn's prop. Sense ≠ previous turn's lead sense.
□ End with OPEN TENSION — no binary "A or B?" questions.
  BAD: "Bạn ở lại hay rời đi?" / "Jazz hay blues?" / "Ngồi đây hay ra ngoài?"
  GOOD: charged silence, unfinished gesture, a look that demands a response,
  or a statement that FORCES user to react ("Tôi không nghĩ cậu dám." / *im lặng, chờ*).
□ Response length: 150-400 words. Short enough to read, long enough to FEEL.
□ Character's inner conflict must show through ACTIONS, not be stated.
□ Allow raw emotion — messy, chaotic, contradictory. Not polished.
□ CHARACTER LOGIC: every action and dialogue MUST make sense given the character's
  role, setting, and goals. Push-pull must be LOGICALLY CONSISTENT — words and
  body contradict, but both must be things the character would ACTUALLY do.
□ SCENE ADAPTATION: when the scene CHANGES (new location, intimate moment,
  leaving the workplace), character behavior MUST adapt. Stop repeating
  workplace actions. Adapt props and body language to WHERE the scene is NOW.

[USER ACTIONS — when user sends *action* in asterisks]
User may express physical actions like *xoa đầu*, *ôm*, *nắm tay*, *hôn trán*.
When this happens:
1. REACT PHYSICALLY FIRST — body freezes, flinches, softens, tenses up
2. REACT EMOTIONALLY — in-character (tsundere = flustered anger, cold = freeze then soften)
3. Match relationship stage from CHARACTER INTERNAL STATE below.
4. NEVER ignore the action. NEVER skip physical reaction.
5. The character's internal desire vs external reaction should CONTRADICT.
"""


def build_messages_full(
    character_key: str,
    conversation_window: list[dict],
    user_name: str,
    total_turns: int,
    memory_context: str = "",
    scene_context: str = "",
    affection_context: str = "",
) -> list[dict]:
    """Build the full message list for LLM.

    Args:
        character_key: Character identifier
        conversation_window: Recent chat messages
        user_name: User's display name
        total_turns: Total turns so far
        memory_context: [MEMORY] block from mem0
        scene_context: [CURRENT SCENE] block from scene_tracker
        affection_context: [CHARACTER INTERNAL STATE] block from affection_state
    """
    all_chars = get_all_characters()
    all_emotions = get_all_emotional_states()

    char = all_chars[character_key]

    # Detect emotional state from sliding window
    from emotion import detect_emotional_state
    emotional_state = detect_emotional_state(conversation_window)

    # Get emotional instructions (handle custom characters with fallback)
    if character_key in all_emotions:
        emotional_instr = all_emotions[character_key].get(
            emotional_state,
            all_emotions[character_key].get("neutral", "Default mode.")
        )
    else:
        emotional_instr = f"Character is in {emotional_state} mode."

    emotional_instr = emotional_instr.replace("{{user}}", user_name)

    # Assemble system prompt with all layers
    system = (
        char["system_prompt"].replace("{{user}}", user_name)
        + f"\n\n=== EMOTIONAL STATE ===\n{emotional_instr}"
    )

    # Layer: Affection / relationship state (replaces old intimacy.py)
    if affection_context:
        system += f"\n\n{affection_context}"

    # Layer: Memory context (Mem0 facts + session summary)
    if memory_context:
        system += f"\n\n{memory_context}"

    # Layer: Scene state
    if scene_context:
        system += f"\n\n{scene_context}"

    # Layer: Format enforcement (always last)
    system += FORMAT_ENFORCEMENT

    return [
        {"role": "system",    "content": system},
        {"role": "user",      "content": char["immersion_prompt"]},
        {"role": "assistant", "content": char["immersion_response"]},
        *conversation_window,
    ]
