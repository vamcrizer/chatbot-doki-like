"""
Chat Service — orchestrates the full chat pipeline.

Pipeline:
  1. Safety check
  2. Prompt assembly (system + conversation window)
  3. LLM streaming
  4. Post-processing (POV fix)
  5. Background: update affection

# TODO: Memory recall via Qdrant
# TODO: Fact extraction from conversation
"""
import logging
from typing import Generator

from characters import get_all_characters
from core.llm_client import chat_stream
from core.prompt_engine import build_messages_full
from core.response_processor import post_process_response
from core.safety import check_input
from state.affection import extract_affection_update

logger = logging.getLogger("ai_companion.service.chat")


class SafetyError(Exception):
    """Raised when user input fails safety check."""
    def __init__(self, reason: str, user_message: str):
        self.reason = reason
        self.user_message = user_message
        super().__init__(reason)


class CharacterNotFoundError(Exception):
    pass


class ChatService:
    """Stateless chat service — all state lives in session/repos."""

    def __init__(self, chat_repo=None):
        self._chat_repo = chat_repo

    def validate_character(self, character_id: str) -> dict:
        """Validate character exists and return char data."""
        all_chars = get_all_characters()
        if character_id not in all_chars:
            raise CharacterNotFoundError(f"Character '{character_id}' not found")
        return all_chars[character_id]

    def check_safety(self, message: str):
        """Run safety check. Raises SafetyError if blocked."""
        safety = check_input(message)
        if safety.blocked:
            raise SafetyError(safety.reason, safety.user_message)

    def stream_response(
        self,
        session,
        character_id: str,
        message: str,
        user_name: str = "bạn",
    ) -> Generator[str, None, str]:
        """Stream LLM response token by token.

        Yields individual tokens. Returns full processed response.
        """
        conv = session.conversation
        aff = session.affection
        scene = session.scene

        # Build contexts
        scene_ctx = scene.get_context_block() if hasattr(scene, 'get_context_block') else ""
        affection_ctx = aff.to_prompt_block() if hasattr(aff, 'to_prompt_block') else ""

        # Add user message
        conv.add_user(message)

        # Build LLM messages
        messages = build_messages_full(
            character_key=character_id,
            conversation_window=conv.get_window(),
            user_name=user_name,
            total_turns=conv.total_turns,
            # TODO: memory_context from Qdrant
            memory_context="",
            scene_context=scene_ctx,
            affection_context=affection_ctx,
            user_message=message,
        )

        # Stream
        full_response = ""
        for chunk in chat_stream(messages):
            full_response += chunk
            yield chunk

        # Post-process
        char_data = self.validate_character(character_id)
        processed = post_process_response(
            full_response,
            char_data.get("name", character_id),
            char_data.get("gender"),
        )

        # Finalize
        conv.add_assistant(processed)

        if hasattr(scene, 'update'):
            scene.update(message)

        return processed

    def finalize_turn(self, session, character_id: str,
                      user_msg: str, assistant_msg: str):
        """Background work after response is sent — update affection."""
        aff = session.affection

        all_chars = get_all_characters()
        char_name = all_chars.get(character_id, {}).get("name", character_id)

        try:
            from state.affection import AffectionState
            if isinstance(aff, AffectionState):
                session.affection = extract_affection_update(
                    state=aff,
                    user_msg=user_msg,
                    assistant_msg=assistant_msg,
                    character_name=char_name,
                )
        except Exception as e:
            logger.warning("Affection update error: %s", e)
