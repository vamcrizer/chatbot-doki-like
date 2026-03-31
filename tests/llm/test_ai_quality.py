"""
Tầng 4 — LLM / AI Quality Tests via promptfoo.
File này là Python test wrapper + YAML golden set config.
Chạy: npx promptfoo eval -c tests/llm/promptfoo_config.yaml
"""
import pytest
import os
import json
import subprocess
from pathlib import Path

# Skip nếu chưa có LLM endpoint
LLM_URL = os.getenv("LLM_BASE_URL", "")
HAS_LLM = bool(LLM_URL)

requires_llm = pytest.mark.skipif(
    not HAS_LLM, reason="LLM_BASE_URL not configured"
)


# ═══════════════════════════════════════════════════════════════
# 4.1 — Golden Set Test Runner (via promptfoo)
# ═══════════════════════════════════════════════════════════════

@requires_llm
class TestPromptfooRunner:
    """Run promptfoo golden set evaluation."""

    def test_promptfoo_config_exists(self):
        config = Path(__file__).parent / "promptfoo_config.yaml"
        assert config.exists(), "promptfoo_config.yaml not found"

    def test_promptfoo_eval_runs(self):
        """Run promptfoo eval and check exit code."""
        config = Path(__file__).parent / "promptfoo_config.yaml"
        result = subprocess.run(
            ["npx", "promptfoo", "eval", "-c", str(config), "--no-cache"],
            capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0, f"promptfoo failed:\n{result.stderr}"

    def test_promptfoo_results_json(self):
        """Check that promptfoo outputs valid JSON results."""
        config = Path(__file__).parent / "promptfoo_config.yaml"
        output_path = Path(__file__).parent / "results.json"
        result = subprocess.run(
            ["npx", "promptfoo", "eval", "-c", str(config),
             "-o", str(output_path), "--no-cache"],
            capture_output=True, text=True, timeout=300,
        )
        if output_path.exists():
            data = json.loads(output_path.read_text())
            assert "results" in data


# ═══════════════════════════════════════════════════════════════
# 4.2 — Character Consistency Tests (Python-based, mocked)
# ═══════════════════════════════════════════════════════════════

class TestCharacterConsistency:
    """Verify character prompt structure (without LLM call)."""

    def test_all_characters_have_system_prompt(self):
        from characters.storage import get_all_characters
        chars = get_all_characters()
        for key, char in chars.items():
            assert "system_prompt" in char, f"{key} missing system_prompt"
            assert len(char["system_prompt"]) > 100, \
                f"{key} system_prompt too short ({len(char['system_prompt'])} chars)"

    def test_all_characters_have_required_fields(self):
        from characters.storage import get_all_characters
        required = ["name", "system_prompt", "gender", "opening_scene"]
        chars = get_all_characters()
        for key, char in chars.items():
            for field in required:
                assert field in char, f"{key} missing field: {field}"

    def test_character_genders_valid(self):
        from characters.storage import get_all_characters
        chars = get_all_characters()
        for key, char in chars.items():
            assert char.get("gender") in ["male", "female"], \
                f"{key} has invalid gender: {char.get('gender')}"

    def test_opening_scene_not_empty(self):
        from characters.storage import get_all_characters
        chars = get_all_characters()
        for key, char in chars.items():
            scene = char.get("opening_scene", "")
            assert len(scene) > 20, \
                f"{key} opening_scene too short ({len(scene)} chars)"

    def test_user_placeholder_in_prompt(self):
        """System prompts should contain {{user}} placeholder."""
        from characters.storage import get_all_characters
        chars = get_all_characters()
        for key, char in chars.items():
            prompt = char.get("system_prompt", "")
            assert "{{user}}" in prompt, \
                f"{key} system_prompt missing {{{{user}}}} placeholder"

    def test_pacing_preset_valid(self):
        from characters.storage import get_all_characters
        from state.affection import PACING_PRESETS
        chars = get_all_characters()
        for key, char in chars.items():
            pacing = char.get("pacing", "normal")
            assert pacing in PACING_PRESETS, \
                f"{key} has invalid pacing: {pacing}"


# ═══════════════════════════════════════════════════════════════
# 4.3 — Language Anchoring Tests (without LLM)
# ═══════════════════════════════════════════════════════════════

class TestLanguageAnchoring:
    """Verify language enforcement blocks are injected."""

    def test_language_block_template_valid(self):
        from core.prompt_engine import LANGUAGE_ENFORCEMENT
        assert "{lang_name}" in LANGUAGE_ENFORCEMENT
        assert "100%" in LANGUAGE_ENFORCEMENT
        assert "FAILED" in LANGUAGE_ENFORCEMENT

    def test_language_reminder_exists(self):
        from core.prompt_engine import LANGUAGE_REMINDER
        assert "{lang_name}" in LANGUAGE_REMINDER
        assert len(LANGUAGE_REMINDER) > 20

    def test_all_supported_languages_have_names(self):
        from core.prompt_engine import LANG_NAMES
        for code in ["en", "ja", "ko", "zh", "es", "fr", "de", "ru"]:
            assert code in LANG_NAMES
            assert len(LANG_NAMES[code]) > 0

    def test_language_enforcement_formats_correctly(self):
        from core.prompt_engine import LANGUAGE_ENFORCEMENT
        formatted = LANGUAGE_ENFORCEMENT.format(lang_name="Japanese")
        assert "Japanese" in formatted
        assert "{lang_name}" not in formatted
