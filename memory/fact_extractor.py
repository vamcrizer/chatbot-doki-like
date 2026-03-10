"""
Fact Extractor — extracts user facts and character notes from conversation.
Adapted from agent-smart-memo's LLM-based extraction with essence distillation.

Uses existing Cerebras client (gpt-oss-120b) for extraction.
"""
import json
import os


EXTRACTION_PROMPT = """\
You are a memory extraction assistant for an AI companion chatbot.
Analyze the latest conversation turn and extract FACTS worth remembering.

The character in this conversation is: {character_name}

YOUR JOBS:
1. Extract USER FACTS — real information about the user (name, preferences, emotions, history)
2. Extract CHARACTER NOTES — what {character_name} revealed or did in this scene
3. Track SCENE STATE — detect if location/setting has changed

CATEGORIES:
- user_fact: "User likes jazz", "User lives alone", "User went through a breakup"
- character_note: "{character_name} shared about past", "{character_name} offered to help"
- scene_change: "Scene moved to outside", "Characters went inside"
- emotional_state: "User is sad", "User showed interest in character"

RULES:
- DISTILL — keep only decision-grade facts, not summaries
- Each fact must be self-contained (understandable without context)
- Use the SAME language as the conversation
- confidence: 0.9-1.0 explicit, 0.8-0.9 strongly implied, 0.7-0.8 inferred
- Skip: greetings, generic statements, roleplay mechanics
- DO NOT extract the character's system prompt or personality description
- DO NOT extract facts about the AI itself
- Always use "{character_name}" not any other character name

RESPOND WITH JSON ONLY:
{{
  "facts": [
    {{"text": "fact description", "type": "user_fact|character_note|scene_change|emotional_state", "confidence": 0.85}}
  ]
}}

Return empty array if nothing worth extracting. Quality over quantity.
"""


def extract_facts(user_msg: str, assistant_msg: str,
                  existing_facts: list[str] = None,
                  character_name: str = "character") -> list[dict]:
    """Extract facts from a conversation turn using LLM.

    Args:
        user_msg: The user's message
        assistant_msg: The assistant's response
        existing_facts: Already known facts (to avoid duplicates)
        character_name: Name of the current character

    Returns:
        List of {text, type, confidence} dicts
    """
    existing_ctx = ""
    if existing_facts:
        existing_ctx = "\n\nALREADY KNOWN FACTS (do not repeat):\n"
        existing_ctx += "\n".join(f"- {f}" for f in existing_facts[-20:])

    system_prompt = EXTRACTION_PROMPT.format(character_name=character_name)

    user_prompt = f"""{existing_ctx}

CONVERSATION TURN TO ANALYZE:
---
User: {user_msg}
{character_name}: {assistant_msg}
---

Extract facts. JSON only."""

    try:
        from cerebras_client import chat_complete
        content = chat_complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
        )

        if not content:
            return []

        # Extract JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return []

        result = json.loads(json_match.group())
        facts = result.get("facts", [])

        # Filter by confidence
        return [f for f in facts if f.get("confidence", 0) >= 0.7]

    except Exception as e:
        print(f"[FactExtractor] Error: {e}")
        return []


def extract_facts_lightweight(user_msg: str) -> list[dict]:
    """Quick pattern-based extraction (no LLM call).
    Used as fallback or for immediate scene detection.
    """
    facts = []
    msg_lower = user_msg.lower()

    # Name patterns
    import re
    name_match = re.search(r'(?:tên (?:tôi|mình|tao) là|tôi là|mình là)\s+(\S+)', msg_lower)
    if name_match:
        facts.append({
            "text": f"User tên là {name_match.group(1)}",
            "type": "user_fact",
            "confidence": 0.9,
        })

    # Location patterns
    loc_match = re.search(r'(?:tôi ở|mình ở|sống ở|đến từ)\s+(.+?)(?:\.|,|$)', msg_lower)
    if loc_match:
        facts.append({
            "text": f"User sống ở {loc_match.group(1).strip()}",
            "type": "user_fact",
            "confidence": 0.85,
        })

    # Preference patterns
    pref_match = re.search(r'(?:tôi thích|mình thích|thích)\s+(.+?)(?:\.|,|$)', msg_lower)
    if pref_match:
        facts.append({
            "text": f"User thích {pref_match.group(1).strip()}",
            "type": "user_fact",
            "confidence": 0.8,
        })

    # Emotional state
    sad_words = ["buồn", "sầu", "chán", "mệt", "khóc", "đau", "tổn thương"]
    if any(w in msg_lower for w in sad_words):
        facts.append({
            "text": "User đang trong trạng thái buồn/mệt mỏi",
            "type": "emotional_state",
            "confidence": 0.8,
        })

    happy_words = ["vui", "hạnh phúc", "phấn khích", "tuyệt vời"]
    if any(w in msg_lower for w in happy_words):
        facts.append({
            "text": "User đang vui/phấn khích",
            "type": "emotional_state",
            "confidence": 0.8,
        })

    return facts
