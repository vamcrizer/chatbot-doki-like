"""
Nhóm 1.5 — Unit Tests: core/prompt_engine.py
Prompt Assembly — language detection, message structure, variable substitution.
"""
import pytest
from unittest.mock import patch, MagicMock
from core.prompt_engine import detect_language, LANG_NAMES


class TestDetectLanguage:
    """Language detection via langdetect library."""

    def test_english(self):
        result = detect_language("Hello, how are you doing today?")
        assert result == "en"

    def test_japanese(self):
        result = detect_language("こんにちは、元気ですか？")
        assert result == "ja"

    def test_korean(self):
        result = detect_language("안녕하세요, 오늘 어때요?")
        assert result == "ko"

    def test_spanish(self):
        result = detect_language("Hola, ¿cómo estás hoy?")
        assert result == "es"

    def test_french(self):
        result = detect_language("Bonjour, comment allez-vous aujourd'hui?")
        assert result == "fr"

    def test_empty_string_falls_back_to_en(self):
        assert detect_language("") == "en"

    def test_short_string_falls_back_to_en(self):
        assert detect_language("Hi") == "en"

    def test_emoji_only(self):
        # Emoji-only crashes langdetect, fallback to en
        result = detect_language("😭😭😭")
        assert result == "en"

    def test_japanese_with_emoji_not_pulled_to_en(self):
        """Emoji mixed with real text must NOT override language detection."""
        result = detect_language("こんにちは😭😭😭")
        assert result == "ja"

    def test_korean_with_emoji_not_pulled_to_en(self):
        result = detect_language("오늘 기분이 좋아요 😊😊")
        assert result == "ko"

    def test_french_with_emoji_not_pulled_to_en(self):
        result = detect_language("Bonjour mon ami 🥰🥰🥰")
        assert result == "fr"

    def test_none_input(self):
        result = detect_language(None)
        assert result == "en"

    def test_whitespace_only(self):
        result = detect_language("   ")
        assert result == "en"

    def test_unsupported_language_falls_back_en(self):
        """If langdetect returns a code not in LANG_NAMES, should fallback."""
        with patch("langdetect.detect") as mock_detect:
            mock_detect.return_value = "xx"  # unknown code
            result = detect_language("Some text here that is long enough")
            assert result == "en"


class TestLangNames:
    """LANG_NAMES dictionary completeness."""

    def test_english_in_names(self):
        assert "en" in LANG_NAMES
        assert LANG_NAMES["en"] == "English"

    def test_japanese_in_names(self):
        assert "ja" in LANG_NAMES
        assert LANG_NAMES["ja"] == "Japanese"

    def test_all_major_languages(self):
        expected = ["en", "ja", "ko", "zh", "es", "fr", "de", "ru", "ar"]
        for code in expected:
            assert code in LANG_NAMES, f"Missing language code: {code}"

    def test_no_empty_values(self):
        for code, name in LANG_NAMES.items():
            assert len(name) > 0, f"Empty name for code: {code}"


class TestBuildMessagesFull:
    """Test build_messages_full structure (mocked character data)."""

    @pytest.fixture
    def mock_character(self):
        """Return a minimal character config."""
        return {
            "name": "Yuki",
            "system_prompt": "You are Yuki, a calm and collected artist. {{user}} is your neighbor.",
            "gender": "female",
            "opening_scene": "Hello {{user}}, nice to meet you.",
            "pacing": "normal",
        }

    def test_import_succeeds(self):
        """Just verify the function can be imported."""
        from core.prompt_engine import build_messages_full
        assert callable(build_messages_full)

    def test_messages_structure_is_list(self):
        """build_messages_full returns a list of dicts."""
        from core.prompt_engine import build_messages_full
        with patch("core.prompt_engine.get_all_characters") as mock_chars:
            mock_chars.return_value = {
                "test_char": {
                    "name": "Test",
                    "system_prompt": "You are Test. Talk to {{user}}.",
                    "gender": "female",
                    "opening_scene": "Hi {{user}}",
                    "pacing": "normal",
                }
            }
            messages = build_messages_full(
                character_key="test_char",
                conversation_window=[],
                user_name="Player",
                total_turns=0,
                user_message="Hello",
            )
            assert isinstance(messages, list)
            assert len(messages) > 0

    def test_first_message_is_system(self):
        """First message should always be system role."""
        from core.prompt_engine import build_messages_full
        with patch("core.prompt_engine.get_all_characters") as mock_chars:
            mock_chars.return_value = {
                "test_char": {
                    "name": "Test",
                    "system_prompt": "You are Test. Talk to {{user}}.",
                    "gender": "female",
                    "opening_scene": "Hi {{user}}",
                    "pacing": "normal",
                }
            }
            messages = build_messages_full(
                character_key="test_char",
                conversation_window=[],
                user_name="Player",
                total_turns=0,
                user_message="Hello",
            )
            assert messages[0]["role"] == "system"

    def test_user_placeholder_replaced(self):
        """{{user}} should be replaced with actual user name."""
        from core.prompt_engine import build_messages_full
        with patch("core.prompt_engine.get_all_characters") as mock_chars:
            mock_chars.return_value = {
                "test_char": {
                    "name": "Test",
                    "system_prompt": "Talk to {{user}} nicely.",
                    "gender": "female",
                    "opening_scene": "Hi {{user}}",
                    "pacing": "normal",
                }
            }
            messages = build_messages_full(
                character_key="test_char",
                conversation_window=[],
                user_name="Alice",
                total_turns=0,
                user_message="Hello",
            )
            system_content = messages[0]["content"]
            assert "{{user}}" not in system_content
            assert "Alice" in system_content
