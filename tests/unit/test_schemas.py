"""
Nhóm 1.6 — Unit Tests: api/schemas.py
Pydantic Validation — input sanitization at API boundary.
"""
import pytest
from pydantic import ValidationError
from api.schemas import (
    ChatRequest, CharacterCreateRequest, RegisterRequest,
    LoginRequest, UserSettingsRequest, RegenerateRequest,
    detect_content_mode, GeneratePromptRequest,
)


class TestChatRequest:
    """ChatRequest validation."""

    def test_valid_request(self):
        req = ChatRequest(character_id="kael", message="Hello!")
        assert req.message == "Hello!"
        assert req.character_id == "kael"

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(character_id="kael", message="")

    def test_message_too_long(self):
        with pytest.raises(ValidationError):
            ChatRequest(character_id="kael", message="x" * 2001)

    def test_message_max_length_accepted(self):
        req = ChatRequest(character_id="kael", message="x" * 2000)
        assert len(req.message) == 2000

    def test_missing_character_id(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="Hello!")

    def test_missing_message(self):
        with pytest.raises(ValidationError):
            ChatRequest(character_id="kael")

    def test_default_user_name(self):
        req = ChatRequest(character_id="kael", message="Hi")
        assert req.user_name is not None

    def test_extra_fields_stripped(self):
        """Extra fields should not appear in the model."""
        req = ChatRequest(character_id="kael", message="Hi", evil_field="hack")
        assert not hasattr(req, "evil_field")


class TestRegisterRequest:
    """RegisterRequest validation."""

    def test_valid(self):
        req = RegisterRequest(email="test@example.com", password="12345678")
        assert req.email == "test@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="12345678")

    def test_short_password(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="test@example.com", password="short")

    def test_long_password(self):
        with pytest.raises(ValidationError):
            RegisterRequest(email="test@example.com", password="x" * 129)


class TestCharacterCreateRequest:
    """Character creation validation."""

    def test_valid_minimal(self):
        req = CharacterCreateRequest(
            name="Yuki",
            system_prompt="You are Yuki."
        )
        assert req.name == "Yuki"
        assert req.gender == "female"  # default

    def test_name_required(self):
        with pytest.raises(ValidationError):
            CharacterCreateRequest(system_prompt="prompt")

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            CharacterCreateRequest(name="x" * 101, system_prompt="prompt")

    def test_invalid_gender(self):
        with pytest.raises(ValidationError):
            CharacterCreateRequest(
                name="Test", system_prompt="prompt", gender="alien"
            )

    def test_valid_genders(self):
        for g in ["male", "female"]:
            req = CharacterCreateRequest(
                name="Test", system_prompt="prompt", gender=g
            )
            assert req.gender == g

    def test_greetings_max_5(self):
        with pytest.raises(ValidationError):
            CharacterCreateRequest(
                name="Test",
                system_prompt="prompt",
                greetings_alt=["hi"] * 6,
            )

    def test_greetings_5_accepted(self):
        req = CharacterCreateRequest(
            name="Test",
            system_prompt="prompt",
            greetings_alt=["hi"] * 5,
        )
        assert len(req.greetings_alt) == 5

    def test_greeting_too_long(self):
        with pytest.raises(ValidationError):
            CharacterCreateRequest(
                name="Test",
                system_prompt="prompt",
                greetings_alt=["x" * 4097],
            )

    def test_content_mode_from_tags(self):
        req = CharacterCreateRequest(
            name="Test",
            system_prompt="prompt",
            tags=["18+", "romance"],
        )
        assert req.content_mode == "explicit"

    def test_content_mode_romantic_default(self):
        req = CharacterCreateRequest(
            name="Test",
            system_prompt="prompt",
            tags=["romance", "fantasy"],
        )
        assert req.content_mode == "romantic"

    def test_bio_construction(self):
        req = CharacterCreateRequest(
            name="Test",
            system_prompt="prompt",
            subtitle="A test character",
            description="She is kind",
        )
        bio = req.bio
        assert "A test character" in bio
        assert "She is kind" in bio

    def test_invalid_visibility(self):
        with pytest.raises(ValidationError):
            CharacterCreateRequest(
                name="Test", system_prompt="prompt", visibility="secret"
            )


class TestDetectContentMode:
    """Content mode detection from tags."""

    def test_nsfw_tag(self):
        assert detect_content_mode(["nsfw"]) == "explicit"

    def test_18plus_tag(self):
        assert detect_content_mode(["18+"]) == "explicit"

    def test_explicit_tag(self):
        assert detect_content_mode(["explicit"]) == "explicit"

    def test_no_nsfw_tags(self):
        assert detect_content_mode(["romance", "fantasy"]) == "romantic"

    def test_empty_tags(self):
        assert detect_content_mode([]) == "romantic"

    def test_mixed_case_tags(self):
        assert detect_content_mode(["NSFW"]) == "explicit"

    def test_whitespace_in_tags(self):
        assert detect_content_mode(["  nsfw  "]) == "explicit"


class TestRegenerateRequest:
    """Regenerate request validation."""

    def test_valid(self):
        req = RegenerateRequest(character_id="kael")
        assert req.character_id == "kael"

    def test_missing_character_id(self):
        with pytest.raises(ValidationError):
            RegenerateRequest()


class TestUserSettingsRequest:
    """User settings validation."""

    def test_valid(self):
        req = UserSettingsRequest(display_name="Alice")
        assert req.display_name == "Alice"

    def test_display_name_too_long(self):
        with pytest.raises(ValidationError):
            UserSettingsRequest(display_name="x" * 51)

    def test_bio_too_long(self):
        with pytest.raises(ValidationError):
            UserSettingsRequest(bio="x" * 501)

    def test_invalid_content_mode(self):
        with pytest.raises(ValidationError):
            UserSettingsRequest(content_mode="hardcore")

    def test_valid_content_modes(self):
        for mode in ["romantic", "explicit"]:
            req = UserSettingsRequest(content_mode=mode)
            assert req.content_mode == mode
