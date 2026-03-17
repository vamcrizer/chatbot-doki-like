"""
Chat Service — orchestrates the full chat pipeline.

Pipeline:
  1. Safety check
  2. Memory recall (semantic + recent)
  3. Prompt assembly (5-layer)
  4. LLM streaming
  5. Post-processing (POV fix)
  6. Persist message
  7. Background: extract facts → update affection → summarize

This service owns the "how" of chatting. Routes own the "how" of HTTP.
"""
import json
import logging
import threading
from typing import Generator, Optional

from characters import get_all_characters
from core.llm_client import chat_stream
from core.prompt_engine import build_messages_full
from core.response_processor import post_process_response
from core.safety import check_input
from memory.fact_extractor import extract_facts, extract_facts_lightweight
from memory.summarizer import summarize_conversation
from state.affection import extract_affection_update

logger = logging.getLogger("dokichat.service.chat")


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

    def __init__(self, memory_repo=None, chat_repo=None):
        """
        Args:
            memory_repo: MemoryRepository instance (in-memory or Postgres)
            chat_repo: ChatRepository instance (in-memory or Postgres)
        """
        self._memory_repo = memory_repo
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

    def build_memory_context(self, session, user_name: str, current_msg: str) -> str:
        """Build [MEMORY] context block from semantic recall + recent facts."""
        mem = session.memory
        all_facts = mem.get_all()
        summary = mem.get_summary()

        if not all_facts and not summary:
            return ""

        parts = []

        # Semantic recall
        relevant_texts = set()
        if current_msg:
            relevant_texts = set(mem.search(current_msg, top_k=5))

        # Recent facts (always include last 5)
        recent_texts = {f["text"] for f in all_facts[-5:]}

        # Merge, dedup, order
        user_facts = [f for f in all_facts
                      if f.get("type") in ("user_fact", "emotional_state")]
        seen = set()
        ordered = []

        for f in user_facts:
            if f["text"] in relevant_texts and f["text"] not in seen:
                ordered.append(f["text"])
                seen.add(f["text"])

        for f in user_facts:
            if f["text"] in recent_texts and f["text"] not in seen:
                ordered.append(f["text"])
                seen.add(f["text"])

        ordered = ordered[:10]  # cap at 10 (~200 tokens)

        if ordered:
            parts.append(f"[MEMORY — what you know about {user_name}]")
            for text in ordered:
                parts.append(f"- {text}")
            parts.append('Use naturally. NEVER say "I remember that..." — just ACT on it.')

        char_notes = [f for f in all_facts if f.get("type") == "character_note"]
        if char_notes:
            parts.append("\n[CHARACTER DEVELOPMENT — what has been revealed]")
            for f in char_notes[-5:]:
                parts.append(f"- {f['text']}")
            parts.append("Do NOT repeat these revelations. Build on them.")

        if summary:
            parts.append(f"\n[PREVIOUS CONTEXT]\n{summary}")

        return "\n".join(parts) if parts else ""

    def stream_response(
        self,
        session,
        character_id: str,
        message: str,
        user_name: str = "bạn",
    ) -> Generator[str, None, str]:
        """Stream LLM response token by token.

        Yields individual tokens. Returns full processed response.

        Usage:
            full = ""
            for token in service.stream_response(...):
                full += token
                send_sse(token)
        """
        conv = session.conversation
        mem = session.memory
        aff = session.affection
        scene = session.scene

        # Build contexts
        memory_ctx = self.build_memory_context(session, user_name, message)
        scene_ctx = scene.get_context() if hasattr(scene, 'get_context') else ""
        affection_ctx = aff.get_prompt_block() if hasattr(aff, 'get_prompt_block') else ""

        # Add user message
        conv.add_user(message)

        # Build LLM messages
        messages = build_messages_full(
            character_key=character_id,
            conversation_window=conv.get_window(has_memory=bool(memory_ctx)),
            user_name=user_name,
            total_turns=conv.total_turns,
            memory_context=memory_ctx,
            scene_context=scene_ctx,
            affection_context=affection_ctx,
        )

        # Stream
        full_response = ""
        for chunk in chat_stream(messages):
            full_response += chunk
            yield chunk

        # Post-process
        processed = post_process_response(full_response)

        # Finalize
        conv.add_assistant(processed)

        if hasattr(scene, 'update'):
            scene.update(message, processed)

        return processed

    def finalize_turn(self, session, character_id: str,
                      user_msg: str, assistant_msg: str):
        """Background work after response is sent.

        Call this in a background thread after streaming is done.
        """
        mem = session.memory
        aff = session.affection
        conv = session.conversation

        all_chars = get_all_characters()
        char_name = all_chars.get(character_id, {}).get("name", character_id)

        try:
            # 1. Extract facts
            existing = [m["text"] for m in mem.get_all()]
            facts = extract_facts(user_msg, assistant_msg, existing,
                                  character_name=char_name)
            light_facts = extract_facts_lightweight(user_msg)
            all_facts = facts + [f for f in light_facts
                                 if not any(f["text"] == ef["text"] for ef in facts)]

            if all_facts:
                mem.add(all_facts)
                logger.info(f"Stored {len(all_facts)} facts")

            # 2. Affection update
            if hasattr(aff, 'update'):
                try:
                    aff_update = extract_affection_update(
                        user_msg, assistant_msg,
                        current_score=aff.score if hasattr(aff, 'score') else 0,
                    )
                    if aff_update:
                        aff.apply(aff_update)
                except Exception as e:
                    logger.warning(f"Affection update error: {e}")

            # 3. Summarize every 10 turns
            if conv.total_turns > 0 and conv.total_turns % 10 == 0:
                old_summary = mem.get_summary()
                new_summary = summarize_conversation(
                    conv.history,
                    existing_summary=old_summary,
                    character_name=char_name,
                )
                if new_summary:
                    mem.update_summary(new_summary)
                    logger.info(f"Updated summary ({len(new_summary)} chars)")

        except Exception as e:
            logger.error(f"Finalize turn error: {e}")

    def finalize_turn_async(self, session, character_id: str,
                            user_msg: str, assistant_msg: str):
        """Fire-and-forget background finalization."""
        thread = threading.Thread(
            target=self.finalize_turn,
            args=(session, character_id, user_msg, assistant_msg),
            daemon=True,
        )
        thread.start()
