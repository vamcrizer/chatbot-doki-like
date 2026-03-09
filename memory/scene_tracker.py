"""
Scene State Tracker — tracks current scene location and character mode.
Uses hybrid approach: rule-based keyword scan (instant) + optional LLM correction.
"""
import re

# ── Scene types and their keyword triggers ────────────────────
SCENE_KEYWORDS: dict[str, list[str]] = {
    "bar": [
        "quầy bar", "quán bar", "pha chế", "shaker", "bartender",
        "quầy", "cocktail", "rót rượu", "ly", "bar",
    ],
    "outside": [
        "ra ngoài", "vỉa hè", "đường phố", "bên ngoài", "ngoài trời",
        "công viên", "hồ", "bờ sông", "bãi biển", "dạo phố",
        "tản bộ", "lề đường", "ghế đá",
    ],
    "walking": [
        "đi bộ", "đi dạo", "đi cùng", "kéo đi", "dẫn đi",
        "bước đi", "rời đi", "cùng nhau đi", "đưa về",
    ],
    "home": [
        "về nhà", "căn hộ", "phòng ngủ", "nhà", "phòng khách",
        "sofa", "giường", "bếp", "cửa nhà",
    ],
    "intimate": [
        "ôm", "hôn", "nắm tay", "áp sát", "thì thầm",
        "vuốt tóc", "xoa đầu", "dựa vào", "ngả đầu",
        "chạm môi", "hôn trán", "hôn má",
    ],
    "private_room": [
        "phòng riêng", "phòng VIP", "phòng kín", "khóa cửa",
        "đóng cửa", "riêng tư",
    ],
}

# ── Available props per scene ─────────────────────────────────
SCENE_PROPS: dict[str, list[str]] = {
    "bar": [
        "shaker", "ly cocktail", "quầy gỗ", "đá viên",
        "rượu", "ánh neon", "khăn lau", "coaster",
    ],
    "outside": [
        "gió đêm", "ánh đèn phố", "bầu trời đêm", "tiếng xe",
        "vỉa hè", "bóng cây", "mùi đường phố",
    ],
    "walking": [
        "bước chân", "tiếng giày", "gió", "ánh đèn đường",
        "bóng hai người", "khoảng cách giữa vai",
    ],
    "home": [
        "ghế sofa", "đèn bàn", "hộp cọ vẽ", "im lặng",
        "mùi nhà", "ánh sáng dịu",
    ],
    "intimate": [
        "hơi thở", "nhịp tim", "khoảng cách", "hơi ấm",
        "mùi tóc", "da chạm da",
    ],
    "private_room": [
        "đèn mờ", "ghế sofa", "im lặng", "không gian kín",
        "tiếng bass xa xa",
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

    def __init__(self):
        self.current_scene: str = "bar"  # default starting scene
        self.previous_scene: str = "bar"
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
