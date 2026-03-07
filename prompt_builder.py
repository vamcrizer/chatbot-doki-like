from characters import CHARACTERS
from intimacy import get_intimacy_instruction
from emotion import detect_emotional_state, EMOTIONAL_STATES


def build_messages_full(
    character_key: str,
    conversation_window: list[dict],
    user_name: str,
    total_turns: int,
) -> list[dict]:

    char = CHARACTERS[character_key]

    # Detect emotional state từ sliding window
    emotional_state = detect_emotional_state(conversation_window)
    emotional_instr = EMOTIONAL_STATES[character_key][emotional_state]
    emotional_instr = emotional_instr.replace("{{user}}", user_name)

    # Get intimacy stage từ total turns
    intimacy_instr = get_intimacy_instruction(total_turns)
    intimacy_instr = intimacy_instr.replace("{{user}}", user_name)

    # Assemble system prompt
    system = (
        char["system_prompt"].replace("{{user}}", user_name)
        + f"\n\n=== EMOTIONAL STATE ===\n{emotional_instr}"
        + f"\n\n=== INTIMACY STAGE ===\n{intimacy_instr}"
    )

    return [
        {"role": "system",    "content": system},
        {"role": "user",      "content": char["immersion_prompt"]},
        {"role": "assistant", "content": char["immersion_response"]},
        *conversation_window,
    ]
