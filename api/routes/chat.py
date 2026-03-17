"""
Chat routes — SSE streaming + memory pipeline.

Flow:
  1. Safety check input
  2. Build memory context (semantic recall + recent facts)
  3. Build prompt (5-layer assembly)
  4. Stream LLM response via SSE
  5. Post-process (POV fix)
  6. Background: extract facts, update affection, summarize
"""
import json
import logging
import threading
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from api.schemas import ChatRequest, ChatHistoryResponse, ChatMessage, SessionState
from api.deps import get_session
from characters import get_all_characters
from core.llm_client import chat_stream
from core.prompt_engine import build_messages_full
from core.response_processor import post_process_response
from core.safety import check_input
from memory.fact_extractor import extract_facts, extract_facts_lightweight
from memory.summarizer import summarize_conversation
from state.affection import extract_affection_update

logger = logging.getLogger("dokichat.chat")
router = APIRouter(prefix="/chat", tags=["chat"])


# ── Helpers ───────────────────────────────────────────────────

def _build_memory_context(mem_store, user_name: str, current_msg: str = "") -> str:
    """Build [MEMORY] block — semantic recall + recent facts."""
    all_facts = mem_store.get_all()
    summary = mem_store.get_summary()

    if not all_facts and not summary:
        return ""

    parts = []

    # Semantic recall
    relevant_texts = set()
    if current_msg:
        relevant_texts = set(mem_store.search(current_msg, top_k=5))

    # Recent facts (always include last 5)
    recent_texts = {f["text"] for f in all_facts[-5:]}

    # Merge, dedup
    user_facts = [f for f in all_facts if f.get("type") in ("user_fact", "emotional_state")]
    seen = set()
    ordered_facts = []

    for f in user_facts:
        if f["text"] in relevant_texts and f["text"] not in seen:
            ordered_facts.append(f["text"])
            seen.add(f["text"])

    for f in user_facts:
        if f["text"] in recent_texts and f["text"] not in seen:
            ordered_facts.append(f["text"])
            seen.add(f["text"])

    ordered_facts = ordered_facts[:10]

    if ordered_facts:
        parts.append(f"[MEMORY — what you know about {user_name}]")
        for text in ordered_facts:
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


def _async_memory_update(mem_store, user_msg, assistant_msg, character_name,
                         conversation_history, total_turns, summarize_every=10):
    """Background: extract facts + summarize."""
    try:
        existing = [m["text"] for m in mem_store.get_all()]
        facts = extract_facts(user_msg, assistant_msg, existing, character_name=character_name)
        light_facts = extract_facts_lightweight(user_msg)

        all_facts = facts + [f for f in light_facts
                             if not any(f["text"] == ef["text"] for ef in facts)]

        if all_facts:
            mem_store.add(all_facts)
            logger.info(f"Stored {len(all_facts)} facts")

        if total_turns > 0 and total_turns % summarize_every == 0:
            old_summary = mem_store.get_summary()
            new_summary = summarize_conversation(
                conversation_history,
                existing_summary=old_summary,
                character_name=character_name,
            )
            if new_summary:
                mem_store.update_summary(new_summary)
                logger.info(f"Updated summary ({len(new_summary)} chars)")

    except Exception as e:
        logger.error(f"Memory update error: {e}")


# ── Routes ────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """Stream chat response via Server-Sent Events.

    Events:
      - type=token: {"t": "chunk text"}
      - type=done: {"full": "complete response", "turn": N}
      - type=error: {"error": "message"}
    """
    # Validate character exists
    all_chars = get_all_characters()
    if req.character_id not in all_chars:
        raise HTTPException(404, f"Character '{req.character_id}' not found")

    # Safety check
    safety = check_input(req.message)
    if safety.blocked:
        raise HTTPException(
            400,
            detail={
                "error": "content_blocked",
                "reason": safety.reason,
                "message": safety.user_message,
            }
        )

    # Get session
    session = get_session(req.user_id, req.character_id)
    session.user_name = req.user_name
    session.content_mode = req.content_mode
    conv = session.conversation
    mem = session.memory
    aff = session.affection
    scene = session.scene

    # Build contexts
    memory_context = _build_memory_context(mem, req.user_name, req.message)
    scene_context = scene.get_context() if hasattr(scene, 'get_context') else ""
    affection_context = aff.get_prompt_block() if hasattr(aff, 'get_prompt_block') else ""

    # Add user message to conversation
    conv.add_user(req.message)

    # Build LLM messages
    messages = build_messages_full(
        character_key=req.character_id,
        conversation_window=conv.get_window(has_memory=bool(memory_context)),
        user_name=req.user_name,
        total_turns=conv.total_turns,
        memory_context=memory_context,
        scene_context=scene_context,
        affection_context=affection_context,
    )

    async def event_generator():
        full_response = ""
        try:
            for chunk in chat_stream(messages):
                full_response += chunk
                yield {
                    "event": "token",
                    "data": json.dumps({"t": chunk}, ensure_ascii=False),
                }

            # Post-process
            processed = post_process_response(full_response)

            # Add to conversation
            conv.add_assistant(processed)

            # Update scene
            if hasattr(scene, 'update'):
                scene.update(req.message, processed)

            # Update affection (background)
            if hasattr(aff, 'update'):
                try:
                    aff_update = extract_affection_update(
                        req.message, processed,
                        current_score=aff.score if hasattr(aff, 'score') else 0,
                    )
                    if aff_update:
                        aff.apply(aff_update)
                except Exception as e:
                    logger.warning(f"Affection update error: {e}")

            # Background memory update
            char_name = all_chars[req.character_id].get("name", req.character_id)
            thread = threading.Thread(
                target=_async_memory_update,
                args=(mem, req.message, processed, char_name,
                      conv.history, conv.total_turns),
                daemon=True,
            )
            thread.start()

            # Final event
            yield {
                "event": "done",
                "data": json.dumps({
                    "full": processed,
                    "turn": conv.total_turns,
                    "emotion": "neutral",  # TODO: detect
                    "affection": aff.score if hasattr(aff, 'score') else 0,
                }, ensure_ascii=False),
            }

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


@router.get("/history/{user_id}/{character_id}", response_model=ChatHistoryResponse)
async def get_chat_history(user_id: str, character_id: str):
    """Get conversation history for a user-character pair."""
    session = get_session(user_id, character_id)
    messages = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in session.conversation.history
    ]
    return ChatHistoryResponse(
        character_id=character_id,
        messages=messages,
        total_turns=session.conversation.total_turns,
    )


@router.get("/state/{user_id}/{character_id}", response_model=SessionState)
async def get_session_state(user_id: str, character_id: str):
    """Get current session state."""
    session = get_session(user_id, character_id)
    aff = session.affection
    return SessionState(
        user_id=user_id,
        character_id=character_id,
        total_turns=session.conversation.total_turns,
        emotion="neutral",
        affection_score=aff.score if hasattr(aff, 'score') else 0,
        affection_stage=aff.stage if hasattr(aff, 'stage') else "stranger",
        scene=session.scene.current if hasattr(session.scene, 'current') else "",
    )


@router.post("/reset/{user_id}/{character_id}")
async def reset_conversation(user_id: str, character_id: str):
    """Reset conversation history (keep memories)."""
    session = get_session(user_id, character_id)
    session.conversation.clear()
    return {"status": "ok", "message": "Conversation reset"}
