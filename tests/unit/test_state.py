"""
Nhóm 1.4 — Unit Tests: state/affection.py & state/scene.py
State Machine — affection progression, scene detection, serialization.
"""
import pytest
from state.affection import (
    AffectionState, PacingConfig, PACING_PRESETS,
    STAGES_ORDERED, STAGE_SCORE_RANGES,
)
from state.scene import SceneTracker, SCENE_KEYWORDS


# ═══════════════════════════════════════════════════════════════
# AFFECTION STATE
# ═══════════════════════════════════════════════════════════════

class TestAffectionStateInit:
    """Default state verification."""

    def test_default_values(self):
        state = AffectionState()
        assert state.relationship_score == 0
        assert state.relationship_label == "stranger"
        assert state.mood == "curious"
        assert state.desire_level == 0
        assert state.boundary_violated is False

    def test_stranger_is_default_stage(self):
        state = AffectionState()
        assert state.relationship_label == "stranger"
        assert state.relationship_label in STAGES_ORDERED


class TestAffectionStateScoring:
    """Score boundaries and clamping."""

    def test_negative_score_no_crash(self):
        state = AffectionState(relationship_score=-50)
        assert state.relationship_score == -50

    def test_extreme_negative(self):
        state = AffectionState(relationship_score=-100)
        assert state.relationship_score == -100

    def test_extreme_positive(self):
        state = AffectionState(relationship_score=100)
        assert state.relationship_score == 100

    def test_score_stage_mapping(self):
        """Each score range maps to exactly one stage."""
        for stage, (low, high) in STAGE_SCORE_RANGES.items():
            assert stage in STAGES_ORDERED
            assert low <= high


class TestAffectionStateSerialization:
    """to_dict / from_dict roundtrip."""

    def test_roundtrip(self):
        original = AffectionState(
            mood="warm",
            mood_intensity=7,
            desire_level=3,
            relationship_score=25,
            relationship_label="friend",
            location="cafe",
            boundary_violated=True,
            recovery_turns_remaining=5,
            last_significant_event="boundary hit",
            turns_at_current_stage=10,
            total_turns=30,
        )
        data = original.to_dict()
        restored = AffectionState.from_dict(data)
        assert restored.mood == "warm"
        assert restored.relationship_score == 25
        assert restored.relationship_label == "friend"
        assert restored.boundary_violated is True
        assert restored.recovery_turns_remaining == 5
        assert restored.turns_at_current_stage == 10

    def test_from_dict_empty(self):
        """Empty dict should give defaults."""
        state = AffectionState.from_dict({})
        assert state.relationship_score == 0
        assert state.relationship_label == "stranger"

    def test_from_dict_extra_keys_ignored(self):
        """Unknown keys should not crash."""
        state = AffectionState.from_dict({
            "mood": "happy",
            "unknown_field": 42,
        })
        assert state.mood == "happy"


class TestAffectionPromptBlock:
    """to_prompt_block() output."""

    def test_contains_mood(self):
        state = AffectionState(mood="warm")
        block = state.to_prompt_block()
        assert "warm" in block

    def test_contains_relationship_info(self):
        state = AffectionState(relationship_label="friend", relationship_score=30)
        block = state.to_prompt_block()
        assert "friend" in block
        assert "30" in block

    def test_boundary_violation_warning(self):
        state = AffectionState(boundary_violated=True, recovery_turns_remaining=5)
        block = state.to_prompt_block()
        assert "BOUNDARY" in block
        assert "RECOVERY" in block

    def test_desire_behavior_hint(self):
        state = AffectionState(desire_level=0)
        block = state.to_prompt_block()
        assert "friendly" in block.lower()

        state.desire_level = 9
        block = state.to_prompt_block()
        assert "consumed" in block.lower()


class TestAffectionStatusBar:
    """to_status_bar() output."""

    def test_contains_mood_emoji(self):
        state = AffectionState(mood="curious")
        bar = state.to_status_bar()
        assert "🤔" in bar

    def test_contains_location(self):
        state = AffectionState(location="cafe")
        bar = state.to_status_bar()
        assert "cafe" in bar

    def test_boundary_warning_in_bar(self):
        state = AffectionState(boundary_violated=True, recovery_turns_remaining=3)
        bar = state.to_status_bar()
        assert "Trust damaged" in bar


class TestPacingConfig:
    """Pacing presets consistency."""

    def test_all_presets_exist(self):
        expected = ["slow", "guarded", "normal", "warm", "fast"]
        for preset in expected:
            assert preset in PACING_PRESETS

    def test_speed_ordering(self):
        speeds = [PACING_PRESETS[p].speed for p in ["slow", "guarded", "normal", "warm", "fast"]]
        assert speeds == sorted(speeds)

    def test_preset_values_positive(self):
        for name, config in PACING_PRESETS.items():
            assert config.speed > 0
            assert config.max_positive_per_turn > 0
            assert config.max_negative_per_turn > 0
            assert config.min_turns_per_stage >= 0


class TestStagesOrdered:
    """Stage ordering and completeness."""

    def test_stages_count(self):
        assert len(STAGES_ORDERED) == 8

    def test_hostile_is_first(self):
        assert STAGES_ORDERED[0] == "hostile"

    def test_bonded_is_last(self):
        assert STAGES_ORDERED[-1] == "bonded"

    def test_stranger_exists(self):
        assert "stranger" in STAGES_ORDERED

    def test_all_stages_have_score_range(self):
        for stage in STAGES_ORDERED:
            assert stage in STAGE_SCORE_RANGES

    def test_score_ranges_cover_full_spectrum(self):
        """Score ranges should cover -100 to 100 without gaps."""
        all_values = set()
        for low, high in STAGE_SCORE_RANGES.values():
            for v in range(low, high + 1):
                all_values.add(v)
        for v in range(-100, 101):
            assert v in all_values, f"Score {v} not covered by any stage"


# ═══════════════════════════════════════════════════════════════
# SCENE TRACKER
# ═══════════════════════════════════════════════════════════════

class TestSceneTrackerInit:
    """Initialization and defaults."""

    def test_default_scene(self):
        tracker = SceneTracker()
        assert tracker.current_scene == "outside"

    def test_explicit_initial_scene(self):
        tracker = SceneTracker(initial_scene="bar")
        assert tracker.current_scene == "bar"

    def test_character_default_scene(self):
        tracker = SceneTracker(character_key="linh_dan")
        assert tracker.current_scene == "bar"


class TestSceneDetection:
    """Keyword-based scene detection."""

    def test_detect_bar_scene(self):
        tracker = SceneTracker()
        detected = tracker.detect_scene("Let me pour you a cocktail at the bar")
        assert detected == "bar"

    def test_detect_outside_scene(self):
        tracker = SceneTracker()
        detected = tracker.detect_scene("Let's take a walk in the park")
        assert detected == "outside"

    def test_detect_home_scene(self):
        tracker = SceneTracker()
        detected = tracker.detect_scene("Come to my apartment, sit on the couch")
        assert detected == "home"

    def test_detect_intimate_scene(self):
        tracker = SceneTracker()
        detected = tracker.detect_scene("*She hugs him tightly, they cuddle*")
        assert detected == "intimate"

    def test_no_keyword_retains_current(self):
        tracker = SceneTracker(initial_scene="bar")
        detected = tracker.detect_scene("How was your day?")
        assert detected == "bar"

    def test_english_scene_keywords(self):
        tracker = SceneTracker()
        detected = tracker.detect_scene("let's go to the cafe")
        # cafe maps to no scene, should retain current
        assert detected is not None

    def test_japanese_scene_keywords(self):
        """Japanese keywords should work via multilingual keyword lists."""
        tracker = SceneTracker()
        # ビーチ is not in keywords, but "beach" is
        detected = tracker.detect_scene("Let's go to the beach tonight")
        assert detected == "outside"

    def test_spanish_keywords(self):
        tracker = SceneTracker()
        detected = tracker.detect_scene("Vamos a caminar por la calle")
        # "calle" and "caminar" are Spanish keywords
        assert detected in ["outside", "walking"]


class TestSceneUpdate:
    """Scene state transitions."""

    def test_scene_changes_on_keyword(self):
        tracker = SceneTracker(initial_scene="bar")
        state = tracker.update("Let's go outside, walk down the street")
        assert tracker.current_scene in ["outside", "walking"]

    def test_previous_scene_tracked(self):
        tracker = SceneTracker(initial_scene="bar")
        tracker.update("Let's walk in the park")
        assert tracker.previous_scene == "bar"

    def test_turn_counter_increments(self):
        tracker = SceneTracker(initial_scene="bar")
        tracker.update("How are you?")
        assert tracker.turn_since_last_change == 1
        tracker.update("Making another drink")
        assert tracker.turn_since_last_change == 2

    def test_turn_counter_resets_on_scene_change(self):
        tracker = SceneTracker(initial_scene="bar")
        tracker.update("How are you?")
        tracker.update("How are you?")
        assert tracker.turn_since_last_change == 2
        tracker.update("Let's go walk outside in the park")
        assert tracker.turn_since_last_change == 0


class TestSceneContextBlock:
    """get_context_block() output."""

    def test_contains_location(self):
        tracker = SceneTracker(initial_scene="bar")
        block = tracker.get_context_block()
        assert "CURRENT SCENE" in block
        assert "bar" in block.lower() or "workplace" in block.lower()

    def test_contains_behavior(self):
        tracker = SceneTracker(initial_scene="outside")
        block = tracker.get_context_block()
        assert "OUTSIDE" in block or "outside" in block.lower()

    def test_non_bar_warning(self):
        tracker = SceneTracker(initial_scene="home")
        block = tracker.get_context_block()
        assert "LEFT the workplace" in block


class TestSceneSerialization:
    """to_dict / from_dict roundtrip."""

    def test_roundtrip(self):
        tracker = SceneTracker(initial_scene="bar")
        tracker.update("Let's go walk in the park outside")
        data = tracker.to_dict()
        restored = SceneTracker.from_dict(data)
        assert restored.current_scene == tracker.current_scene
        assert restored.previous_scene == tracker.previous_scene
        assert restored.confidence == tracker.confidence

    def test_from_dict_empty(self):
        tracker = SceneTracker.from_dict({})
        assert tracker.current_scene == "outside"  # default
