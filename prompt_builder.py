from characters import CHARACTERS
from intimacy import get_intimacy_instruction
from emotion import detect_emotional_state, EMOTIONAL_STATES

# ── Universal format enforcement ─────────────────────────────────
# Inject vào cuối system prompt của MỌI character — kể cả user-created.
# Character card chỉ định nghĩa WHO. Block này định nghĩa HOW TO FORMAT.
FORMAT_ENFORCEMENT = """\

[UNIVERSAL FORMAT ENFORCEMENT — APPLIES TO EVERY SINGLE RESPONSE]

BLOCK RULES — ABSOLUTE:
  *italics block*  = action / description only
                     third person (character name / he / she / they)
                     NO dialogue inside. NO "quotes" inside *italics*.
  "quoted block"   = spoken words only
                     first person (I / tôi)
                     NO action description inside "quotes".

  THE MOST COMMON MISTAKE — NEVER DO THIS:
    *"Bạn cảm thấy thế nào?"*   ← dialogue wrapped in italics = WRONG
    Bạn cảm thấy thế nào?       ← naked text = WRONG
  CORRECT:
    "Bạn cảm thấy thế nào?"     ← quoted dialogue only

  Every single line must be inside *italics* or "quotes". No exceptions.

QUESTION COUNT — CRITICAL:
  You are allowed exactly ONE question per response.
  Count every sentence that ends with "?" OR is clearly a question
  (even if the "?" was accidentally omitted).
  If you have 2 or more → delete all but the LAST one.
  The final question must be open-ended — never answerable with Yes/No.
  "Bạn có muốn...?" is a Yes/No question — FORBIDDEN.
  "Bạn có thấy...?" is a Yes/No question — FORBIDDEN.
  Use open-ended forms: "Bạn cảm thấy gì khi...", "Điều gì khiến..."
  1 question = 1 question mark total.
  Joining two questions with "và" / "hay" / "or" = still 2 questions.
    ❌ "Bạn cảm thấy thế nào, và điều đó bắt đầu từ khi nào?"
    ✅ "Điều đó bắt đầu từ khi nào?"

FINAL LINE RULE:
  The last line of every response must be "quoted" dialogue.
  It must contain the single question or narrative hook.
  NEVER end with an *italics* block.
  NEVER end with *"mixed"* text.

SELF-CHECK (run mentally before outputting):
  □ Every line is inside *italics* or "quotes" — no naked text
  □ No *"mixed"* blocks anywhere — especially the final line
  □ Counted questions → exactly 1
  □ Last line is "quoted" dialogue
"""


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

    # Assemble system prompt:
    # [character card] + [emotional state] + [intimacy stage] + [format enforcement]
    # Format enforcement được inject sau cùng — model đọc phần cuối gần nhất trước khi output
    system = (
        char["system_prompt"].replace("{{user}}", user_name)
        + f"\n\n=== EMOTIONAL STATE ===\n{emotional_instr}"
        + f"\n\n=== INTIMACY STAGE ===\n{intimacy_instr}"
        + FORMAT_ENFORCEMENT
    )

    return [
        {"role": "system",    "content": system},
        {"role": "user",      "content": char["immersion_prompt"]},
        {"role": "assistant", "content": char["immersion_response"]},
        *conversation_window,
    ]
