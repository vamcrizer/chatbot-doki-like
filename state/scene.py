"""
Scene State Tracker — tracks current scene location and character mode.
Uses hybrid approach: rule-based keyword scan (instant) + optional LLM correction.
"""
import re

# ── Scene types and their keyword triggers (EN, ES, PT, TL, AR) ──
SCENE_KEYWORDS: dict[str, list[str]] = {
    "bar": [
        "bar", "bartender", "shaker", "cocktail", "pour", "drink", "glass",
        "vaso", "bebida", "trago", "copo", "pub", "club",
        "kopa", "alak", "مقهى", "مشروب"
    ],
    "outside": [
        "outside", "street", "park", "walk", "sidewalk", "beach", "night",
        "calle", "parque", "afuera", "caminhada", "rua",
        "labas", "kalye", "gabi", "شارع", "خارج"
    ],
    "walking": [
        "walk", "walking", "stroll", "step", "together", "leave",
        "caminar", "andar", "paseo", "lakad", "magkasama",
        "يمشي", "معا"
    ],
    "home": [
        "home", "house", "apartment", "bedroom", "living room", "couch", "bed", "door",
        "casa", "hogar", "cuarto", "cama",
        "bahay", "kwarto", "kama", "منزل", "غرفة"
    ],
    "intimate": [
        "hug", "kiss", "hold hands", "whisper", "touch", "lean", "cuddle",
        "beso", "abrazo", "besar", "abraço",
        "yakap", "halik", "hawak", "lapit", "عناق", "قبلة", "لمس"
    ],
    "private_room": [
        "private", "vip", "lock", "closed door", "room",
        "privacidad", "sala privada", "quarto",
        "sarado", "pribado", "غرفة خاصة", "مغلق"
    ],
}

# ── Available props per scene ─────────────────────────────────
SCENE_PROPS: dict[str, list[str]] = {
    "bar": [
        "shaker", "cocktail glass", "wooden counter", "ice cubes",
        "liquor", "neon light", "towel", "coaster",
    ],
    "outside": [
        "night breeze", "streetlights", "night sky", "traffic sound",
        "sidewalk", "tree shadows",
    ],
    "walking": [
        "footsteps", "wind", "streetlights", "two shadows", "shoulder distance",
    ],
    "home": [
        "sofa", "desk lamp", "paintbrushes", "silence",
        "familiar scent", "soft light",
    ],
    "intimate": [
        "breath", "heartbeat", "proximity", "warmth",
        "scent of hair", "skin against skin",
    ],
    "private_room": [
        "dim light", "sofa", "silence", "enclosed space",
        "distant bass sound",
    ],
}

# ── Character behavior instruction per scene ──────────────────
SCENE_BEHAVIOR: dict[str, str] = {
    "bar": (
        "Character is AT THEIR WORKPLACE. "
        "Workplace-specific actions are natural and expected."
    ),
    "outside": (
        "Character is OUTSIDE, away from workplace. "
        "NO workplace-specific actions (no mixing drinks, no serving, no shaker). "
        "Character becomes a PERSON: hands fidget, play with hair, hold own arms. "
        "Armor shifts from professional performance to personal nervous habits."
    ),
    "walking": (
        "Characters are WALKING TOGETHER. "
        "NO workplace actions. Focus on: pace matching, distance between shoulders, "
        "accidental hand brushes, where eyes look. Movement creates intimacy."
    ),
    "home": (
        "Character is in a PRIVATE SPACE. Guard is lowest. "
        "May reference personal items (paintbrushes, photos, hidden things). "
        "Most vulnerable state — actions are small, quiet, genuine."
    ),
    "intimate": (
        "Characters are in PHYSICAL CONTACT or very close. "
        "Props = touch, breath, proximity, heartbeat. "
        "NO workplace actions. Focus entirely on physical sensation and emotion. "
        "Words become shorter. Pauses become louder."
    ),
    "private_room": (
        "Characters are in a PRIVATE enclosed space. "
        "Tension is high. NO workplace actions. "
        "Focus on: enclosed atmosphere, proximity, what hands do, eye contact."
    ),
}


class SceneTracker:
    """Tracks the current scene state based on conversation content."""

    # Default starting scenes per character archetype
    DEFAULT_SCENES = {
        "linh_dan": "bar",
        "kael": "bar",          # café, but uses bar props
        "sol": "outside",       # suburban neighborhood
        "ren": "home",          # music studio
        "seraphine": "home",    # library/study
    }

    def __init__(self, initial_scene: str = None, character_key: str = None):
        if initial_scene:
            self.current_scene = initial_scene
        elif character_key:
            self.current_scene = self.DEFAULT_SCENES.get(character_key, "outside")
        else:
            self.current_scene = "outside"
        self.previous_scene: str = self.current_scene
        self.confidence: float = 1.0
        self.turn_since_last_change: int = 0

    def detect_scene(self, user_message: str) -> str:
        """Scan user message for scene keywords. Returns detected scene or current."""
        msg_lower = user_message.lower()

        # Check each scene type — last match wins (intimate overrides location)
        best_scene = None
        best_score = 0

        for scene, keywords in SCENE_KEYWORDS.items():
            score = 0
            for kw in keywords:
                # Check if keyword appears in message (handle * for actions)
                clean_msg = msg_lower.replace("*", "")
                if kw in clean_msg:
                    score += 1
            if score > best_score:
                best_score = score
                best_scene = scene

        if best_scene and best_score > 0:
            return best_scene
        return self.current_scene

    def update(self, user_message: str) -> dict:
        """Update scene state based on user message. Returns scene info dict."""
        detected = self.detect_scene(user_message)

        if detected != self.current_scene:
            self.previous_scene = self.current_scene
            self.current_scene = detected
            self.confidence = 0.8  # rule-based = 80% confident
            self.turn_since_last_change = 0
        else:
            self.turn_since_last_change += 1

        return self.get_state()

    def get_state(self) -> dict:
        """Return current scene state as dict."""
        return {
            "scene": self.current_scene,
            "previous_scene": self.previous_scene,
            "behavior": SCENE_BEHAVIOR.get(self.current_scene, ""),
            "props": SCENE_PROPS.get(self.current_scene, []),
            "turns_since_change": self.turn_since_last_change,
        }

    def get_context_block(self) -> str:
        """Generate the [CURRENT SCENE] block to inject into prompt."""
        state = self.get_state()

        scene_names = {
            "bar": "Behind the bar / workplace",
            "outside": "Outside — street / sidewalk",
            "walking": "Walking together",
            "home": "At home / private apartment",
            "intimate": "Intimate / physical closeness",
            "private_room": "Private room",
        }

        props_str = ", ".join(state["props"][:5])

        block = (
            f"\n\n=== CURRENT SCENE ===\n"
            f"Location: {scene_names.get(state['scene'], state['scene'])}\n"
            f"Behavior: {state['behavior']}\n"
            f"Available props: {props_str}\n"
        )

        if state["scene"] != "bar":
            block += (
                "IMPORTANT: Character has LEFT the workplace. "
                "Do NOT use workplace-specific actions or props.\n"
            )

        return block

    def to_dict(self) -> dict:
        """Serialize for Redis storage."""
        return {
            "current_scene": self.current_scene,
            "previous_scene": self.previous_scene,
            "confidence": self.confidence,
            "turn_since_last_change": self.turn_since_last_change,
        }

    @classmethod
    def from_dict(cls, d: dict, character_key: str = None) -> "SceneTracker":
        """Restore from Redis data."""
        tracker = cls(character_key=character_key)
        tracker.current_scene = d.get("current_scene", tracker.current_scene)
        tracker.previous_scene = d.get("previous_scene", tracker.previous_scene)
        tracker.confidence = d.get("confidence", 1.0)
        tracker.turn_since_last_change = d.get("turn_since_last_change", 0)
        return tracker
