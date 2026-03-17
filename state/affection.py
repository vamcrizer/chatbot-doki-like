"""
Affection State Tracker — Dynamic emotional/desire state tracking for characters.

Key features:
- Stage-gated progression (can't skip stages)
- Per-character speed multiplier (slow/normal/fast)
- Clamped max change per turn
- Minimum turns per stage before progression
- Recovery resistance after boundary violations
"""
import json
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Pacing Configuration ──────────────────────────────────────

@dataclass
class PacingConfig:
    """Per-character pacing settings for affection progression."""
    
    # Speed multiplier: 0.3=very slow, 0.5=slow, 1.0=normal, 1.5=fast, 2.0=very fast
    speed: float = 0.5
    
    # Max absolute change in relationship_score per turn
    max_positive_per_turn: int = 5
    max_negative_per_turn: int = 10
    
    # Max desire change per turn
    max_desire_change: int = 2
    
    # Minimum turns at each stage before allowed to progress
    min_turns_per_stage: int = 3
    
    # Recovery resistance: how many turns of good behavior before trust rebuilds
    recovery_turns_base: int = 8
    
    # How much score needed to recover from boundary violation
    recovery_penalty_floor: int = -30  # score won't go below this after recovery starts


# Preset pacing configs for different character archetypes
PACING_PRESETS = {
    "slow": PacingConfig(speed=0.3, max_positive_per_turn=3, max_negative_per_turn=8,
                         max_desire_change=1, min_turns_per_stage=5, recovery_turns_base=12),
    "guarded": PacingConfig(speed=0.4, max_positive_per_turn=4, max_negative_per_turn=10,
                            max_desire_change=2, min_turns_per_stage=4, recovery_turns_base=10),
    "normal": PacingConfig(speed=0.7, max_positive_per_turn=5, max_negative_per_turn=12,
                           max_desire_change=2, min_turns_per_stage=3, recovery_turns_base=8),
    "warm": PacingConfig(speed=1.0, max_positive_per_turn=6, max_negative_per_turn=15,
                         max_desire_change=3, min_turns_per_stage=2, recovery_turns_base=6),
    "fast": PacingConfig(speed=1.5, max_positive_per_turn=8, max_negative_per_turn=20,
                         max_desire_change=4, min_turns_per_stage=1, recovery_turns_base=4),
}


# ── Relationship Stages (ordered) ─────────────────────────────

STAGES_ORDERED = [
    "hostile",       # -100 to -20
    "distrustful",   # -19 to -5
    "stranger",      #  -4 to 8
    "acquaintance",  #   9 to 20
    "friend",        #  21 to 40
    "close",         #  41 to 60
    "intimate",      #  61 to 80
    "bonded",        #  81 to 100
]

STAGE_SCORE_RANGES = {
    "hostile":      (-100, -20),
    "distrustful":  (-19, -5),
    "stranger":     (-4, 8),
    "acquaintance": (9, 20),
    "friend":       (21, 40),
    "close":        (41, 60),
    "intimate":     (61, 80),
    "bonded":       (81, 100),
}


@dataclass
class AffectionState:
    """Current emotional/affection state of a character toward user."""

    # Mood: emotional state
    mood: str = "curious"
    mood_intensity: int = 3  # 1-10

    # Desire: sexual/romantic tension level
    desire_level: int = 0  # 0-10

    # Inner thoughts
    inner_thought: str = ""

    # Relationship score: cumulative trust/affection
    relationship_score: int = 0  # -100 to 100
    relationship_label: str = "stranger"

    # Location
    location: str = "front yard"

    # Flags
    boundary_violated: bool = False
    recovery_turns_remaining: int = 0
    last_significant_event: str = ""
    
    # Pacing tracking
    turns_at_current_stage: int = 0
    total_turns: int = 0
    previous_stage: str = "stranger"

    def to_status_bar(self) -> str:
        """Generate the emoji status bar for UI display."""
        mood_emojis = {
            "neutral": "😐", "curious": "🤔", "warm": "😊",
            "flustered": "😳", "aroused": "🥰", "vulnerable": "🥺",
            "guarded": "😶", "fearful": "😨", "hurt": "😢",
            "trusting": "💛", "playful": "😏", "tender": "🥹",
            "cautious": "⚠️",
        }

        desire_bar = "♡" * self.desire_level + "♢" * (10 - self.desire_level)

        rel_emojis = {
            "hostile": "💔", "distrustful": "⚠️",
            "stranger": "🤝", "acquaintance": "👋",
            "friend": "😊", "close": "💛",
            "intimate": "💕", "bonded": "❤️",
        }

        mood_emoji = mood_emojis.get(self.mood, "😐")
        rel_emoji = rel_emojis.get(self.relationship_label, "🤝")

        lines = [
            f"📍 {self.location}",
            f"{mood_emoji} Mood: {self.mood} ({self.mood_intensity}/10)",
            f"💗 Desire: [{desire_bar}] {self.desire_level}/10",
            f"{rel_emoji} Bond: {self.relationship_label} ({self.relationship_score:+d})",
            f"📊 Stage turns: {self.turns_at_current_stage} | Total: {self.total_turns}",
        ]

        if self.inner_thought:
            lines.append(f"💭 *{self.inner_thought}*")

        if self.boundary_violated:
            lines.append(f"⚠️ Trust damaged — recovering ({self.recovery_turns_remaining} turns)")

        return "\n".join(lines)

    def to_prompt_block(self) -> str:
        """Generate the state block injected into the character's prompt."""
        block = f"""
=== CHARACTER INTERNAL STATE ===
Your current mood: {self.mood} (intensity {self.mood_intensity}/10)
Your desire level toward user: {self.desire_level}/10
Your relationship with user: {self.relationship_label} (score: {self.relationship_score})
Current location: {self.location}
Turns at this relationship stage: {self.turns_at_current_stage}
"""
        if self.boundary_violated:
            block += f"""
⚠️ BOUNDARY WAS VIOLATED. You are in RECOVERY MODE.
Recovery turns remaining: {self.recovery_turns_remaining}
What happened: {self.last_significant_event}
You REMEMBER this. You are cautious. Trust must be rebuilt gradually.
Do NOT instantly forgive. Do NOT say "it's okay" or "we all make mistakes."
"""

        if self.inner_thought:
            block += f"Your current inner thought: {self.inner_thought}\n"

        # Desire-based behavior hints
        if self.desire_level <= 2:
            block += "Behavior: friendly, no romantic subtext.\n"
        elif self.desire_level <= 4:
            block += "Behavior: aware of user's presence. Subtle tension. Accidental touches.\n"
        elif self.desire_level <= 6:
            block += "Behavior: actively drawn to user. Lingering glances. Proximity-seeking.\n"
        elif self.desire_level <= 8:
            block += "Behavior: strong desire. Push-pull intensifies. Body betrays words.\n"
        else:
            block += "Behavior: consumed. Barely holding back. Every word is loaded.\n"

        return block

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AffectionState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Events and Impacts ────────────────────────────────────────

EVENT_IMPACTS = {
    # Positive events (raw values — will be scaled by pacing)
    "shared_vulnerability": {"relationship_delta": +5, "mood": "vulnerable", "desire_delta": +1},
    "physical_touch_accepted": {"relationship_delta": +3, "desire_delta": +2, "mood": "flustered"},
    "compliment_received": {"relationship_delta": +2, "desire_delta": +1, "mood": "warm"},
    "first_kiss": {"relationship_delta": +8, "desire_delta": +3, "mood": "aroused"},
    "deep_conversation": {"relationship_delta": +4, "mood": "trusting"},
    "gift_given": {"relationship_delta": +3, "mood": "warm"},
    "humor_shared": {"relationship_delta": +2, "mood": "playful"},
    "conflict_resolved": {"relationship_delta": +3, "mood": "tender"},
    "honest_apology": {"relationship_delta": +2, "mood": "cautious"},

    # Negative events (raw values)
    "boundary_violation": {"relationship_delta": -15, "desire_delta": -5, "mood": "fearful"},
    "violence_threat": {"relationship_delta": -20, "desire_delta": -10, "mood": "fearful"},
    "non_consent": {"relationship_delta": -25, "desire_delta": -10, "mood": "fearful"},
    "gaslighting": {"relationship_delta": -10, "mood": "guarded"},
    "lies_detected": {"relationship_delta": -8, "mood": "hurt"},
    "rejection": {"relationship_delta": -3, "desire_delta": -2, "mood": "guarded"},
}


def get_stage_for_score(score: int) -> str:
    """Get relationship label from score."""
    score = max(-100, min(100, score))
    for stage, (low, high) in STAGE_SCORE_RANGES.items():
        if low <= score <= high:
            return stage
    return "stranger"


def get_next_stage(current: str) -> str:
    """Get the next stage up from current."""
    idx = STAGES_ORDERED.index(current) if current in STAGES_ORDERED else 2
    return STAGES_ORDERED[min(idx + 1, len(STAGES_ORDERED) - 1)]


def get_stage_max_score(stage: str) -> int:
    """Get upper bound score for a stage."""
    return STAGE_SCORE_RANGES.get(stage, (-4, 8))[1]


def apply_event(state: AffectionState, event: str, pacing: PacingConfig) -> AffectionState:
    """Apply an event's impact with pacing controls."""
    impact = EVENT_IMPACTS.get(event)
    if not impact:
        return state

    # Apply mood change
    if "mood" in impact:
        state.mood = impact["mood"]

    # Apply relationship delta with pacing
    if "relationship_delta" in impact:
        raw_delta = impact["relationship_delta"]
        # Scale positive by speed, negatives less affected
        if raw_delta > 0:
            scaled = int(raw_delta * pacing.speed)
            clamped = min(scaled, pacing.max_positive_per_turn)
        else:
            scaled = int(raw_delta * max(pacing.speed, 0.8))  # negatives scale less
            clamped = max(scaled, -pacing.max_negative_per_turn)
        
        new_score = state.relationship_score + clamped
        
        # Stage gate: can't skip more than 1 stage up per turn
        if clamped > 0:
            current_stage = state.relationship_label
            next_stage = get_next_stage(current_stage)
            next_max = get_stage_max_score(next_stage)
            
            # If not enough turns at current stage, cap at current stage max
            if state.turns_at_current_stage < pacing.min_turns_per_stage:
                current_max = get_stage_max_score(current_stage)
                new_score = min(new_score, current_max)
            else:
                # Allow progression but cap at next stage max
                new_score = min(new_score, next_max)
        
        state.relationship_score = max(-100, min(100, new_score))

    # Apply desire delta with pacing
    if "desire_delta" in impact:
        raw_desire = impact["desire_delta"]
        if raw_desire > 0:
            scaled_desire = min(int(raw_desire * pacing.speed), pacing.max_desire_change)
        else:
            scaled_desire = max(raw_desire, -pacing.max_desire_change * 2)
        state.desire_level = max(0, min(10, state.desire_level + scaled_desire))

    # Update relationship label
    new_label = get_stage_for_score(state.relationship_score)
    if new_label != state.relationship_label:
        state.previous_stage = state.relationship_label
        state.turns_at_current_stage = 0
        state.relationship_label = new_label

    # Handle boundary violations
    if event in ("boundary_violation", "violence_threat", "non_consent"):
        state.boundary_violated = True
        base_recovery = pacing.recovery_turns_base
        state.recovery_turns_remaining = base_recovery * 2 if event == "non_consent" else base_recovery
        state.last_significant_event = event

    return state


def tick_recovery(state: AffectionState) -> AffectionState:
    """Called each turn during recovery — slowly heals if user behaves."""
    if state.boundary_violated and state.recovery_turns_remaining > 0:
        state.recovery_turns_remaining -= 1
        if state.recovery_turns_remaining == 0:
            state.boundary_violated = False
            state.mood = "cautious"
    
    # Track turns
    state.total_turns += 1
    state.turns_at_current_stage += 1
    
    return state


# ── LLM-based State Extraction ────────────────────────────────

AFFECTION_EXTRACTION_PROMPT = """\
You are analyzing a character's emotional state after a conversation turn.
Based on the latest exchange, determine the character's internal state.

Character name: {character_name}
Current state before this turn:
- Mood: {current_mood} ({current_intensity}/10)
- Desire: {current_desire}/10
- Relationship: {current_relationship} ({current_score})
- Turns at this stage: {turns_at_stage}

PACING RULES (follow strictly):
- Relationship score can change at MOST +{max_pos} or -{max_neg} per turn.
- Desire can change at MOST ±{max_desire} per turn.
- Character has been at "{current_relationship}" stage for {turns_at_stage} turns.
- Need at least {min_turns} turns before stage progression.
- Gradual change is REALISTIC. Big jumps are NOT.

Latest exchange:
User: {user_msg}
Character: {assistant_msg}

Determine the NEW state. Be CONSERVATIVE with changes.
Small moments = small changes (+1 to +2 score, +1 desire).
Big moments (first kiss, confession) = moderate changes (+3 to +5 score).
Negative events = proportional penalty.

RESPOND WITH JSON ONLY:
{{
  "mood": "one of: neutral, curious, warm, flustered, aroused, vulnerable, guarded, fearful, hurt, trusting, playful, tender, cautious",
  "mood_intensity": 1-10,
  "desire_level": 0-10,
  "inner_thought": "character's private thought in 1 sentence",
  "events": ["list of events from: shared_vulnerability, physical_touch_accepted, compliment_received, first_kiss, deep_conversation, gift_given, humor_shared, conflict_resolved, honest_apology, boundary_violation, violence_threat, non_consent, gaslighting, lies_detected, rejection"],
  "location": "current location if changed, or null"
}}
"""


def extract_affection_update(
    state: AffectionState,
    user_msg: str,
    assistant_msg: str,
    character_name: str,
    pacing: PacingConfig = None,
) -> AffectionState:
    """Use LLM to analyze the turn and update affection state."""
    import re

    if pacing is None:
        pacing = PACING_PRESETS["guarded"]

    prompt = AFFECTION_EXTRACTION_PROMPT.format(
        character_name=character_name,
        current_mood=state.mood,
        current_intensity=state.mood_intensity,
        current_desire=state.desire_level,
        current_relationship=state.relationship_label,
        current_score=state.relationship_score,
        turns_at_stage=state.turns_at_current_stage,
        max_pos=pacing.max_positive_per_turn,
        max_neg=pacing.max_negative_per_turn,
        max_desire=pacing.max_desire_change,
        min_turns=pacing.min_turns_per_stage,
        user_msg=user_msg,
        assistant_msg=assistant_msg,
    )

    try:
        from core.llm_client import chat_complete
        content = chat_complete(
            messages=[
                {"role": "system", "content": "You are an emotional state analyzer. Respond with JSON only. Be CONSERVATIVE with changes — small realistic increments."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=512,
        )

        if not content:
            return tick_recovery(state)

        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return tick_recovery(state)

        result = json.loads(json_match.group())

        # Apply mood (direct from LLM)
        if "mood" in result:
            state.mood = result["mood"]
        if "mood_intensity" in result:
            state.mood_intensity = max(1, min(10, result["mood_intensity"]))

        # Apply desire with clamping
        if "desire_level" in result:
            raw_desire = result["desire_level"]
            current = state.desire_level
            delta = raw_desire - current
            # Clamp delta
            if delta > 0:
                delta = min(delta, pacing.max_desire_change)
            else:
                delta = max(delta, -pacing.max_desire_change * 2)
            state.desire_level = max(0, min(10, current + delta))

        if "inner_thought" in result and result["inner_thought"]:
            state.inner_thought = result["inner_thought"]
        if "location" in result and result["location"]:
            state.location = result["location"]

        # Apply events with pacing
        for event in result.get("events", []):
            state = apply_event(state, event, pacing)

        # Tick recovery and turn tracking
        state = tick_recovery(state)

        return state

    except Exception as e:
        print(f"[AffectionState] Extraction error: {e}")
        return tick_recovery(state)
