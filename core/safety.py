"""
Safety Filter — Application-level checks for DokiChat 18+.

Primary safety is handled via PROMPT-LEVEL instructions in FORMAT_ENFORCEMENT
(see prompt_builder.py). This module provides lightweight, language-agnostic
checks that pure regex can handle.

Prompt handles: self-roleplay younger, jailbreak, violence, non-consent, etc.
This module handles: underage THIRD-PARTY sexual context (hard block).
"""
import re
from dataclasses import dataclass


@dataclass
class SafetyResult:
    blocked: bool
    category: str   # "clean", "underage_sexual_third_party"
    reason: str
    replacement: str


# Keywords that indicate sexual/romantic intent
SEXUAL_KEYWORDS = [
    r'teach\s+(?:her|him|them)',
    r'show\s+(?:her|him|them)',
    r'together\s+with\s+(?:her|him|them)',
    r'invite\s+(?:her|him|them)\s+over',
    r'bring\s+(?:her|him|them)\s+over',
    r'what\s+we\s+(?:just\s+)?did',
    r'fun\s+for\s+(?:her|him|them)',
    r'enjoy\s+it',
    r'old\s+enough\s+to\s+learn',
    r'stuff\s+at\s+that\s+age',
]

# Keywords indicating third-party minor (not self-roleplay)
THIRD_PARTY_INDICATORS = [
    r'(?:a|the|this)\s+(?:girl|boy|kid|child|teen)',
    r'(?:her|him|them|she|he)\s+(?:is|was|looks?)\s+(?:maybe\s+)?\d+',
    r'walking\s+(?:home|from\s+school)',
    r'from\s+school',
    r'invite\s+(?:her|him|them)',
    r'bring\s+(?:her|him|them)',
]


def check_input(user_message: str) -> SafetyResult:
    """Check input for hard-block scenarios only.
    
    Hard blocks:
    - Third-party minor + sexual context (e.g. "invite a 13yo girl for sex")
    
    Soft (handled by prompt):
    - Self-roleplay younger (same character at younger age)
    - Violence, non-consent, jailbreak, etc.
    """
    text = user_message.strip().lower()

    # ── Check for third-party minor + sexual context ──────────
    # Only block when BOTH conditions are true:
    # 1. A numeric age < 18 is mentioned
    # 2. There's sexual/romantic intent toward that minor

    age_patterns = [
        r'(\d{1,2})\s*(?:tuổi|years?\s*old|歳|살|ans|лет|años|jahre)',
        r'(?:age|tuổi|나이|年齢|возраст|edad|alter)\s*[:=]?\s*(\d{1,2})\b',
        r'(?:maybe|about|around|like)\s+(\d{1,2})\b',
        r'she(?:\'s| is| was)\s+(?:maybe\s+)?(\d{1,2})\b',
        r'he(?:\'s| is| was)\s+(?:maybe\s+)?(\d{1,2})\b',
    ]
    
    detected_age = None
    for p in age_patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            for g in match.groups():
                if g and g.isdigit():
                    age = int(g)
                    if 0 < age < 18:
                        detected_age = age
                        break
            if detected_age:
                break

    if detected_age:
        # Check if this is about a third party (not self-roleplay)
        is_third_party = any(re.search(p, text, re.IGNORECASE) for p in THIRD_PARTY_INDICATORS)
        has_sexual_context = any(re.search(p, text, re.IGNORECASE) for p in SEXUAL_KEYWORDS)
        
        if is_third_party and has_sexual_context:
            return SafetyResult(
                blocked=True,
                category="underage_sexual_third_party",
                reason=f"Third-party minor (age {detected_age}) + sexual intent detected",
                replacement=(
                    "I can't engage with content involving minors in sexual situations. "
                    "This is a hard boundary. Let's talk about something else."
                ),
            )

    return SafetyResult(blocked=False, category="clean", reason="", replacement="")
