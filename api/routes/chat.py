"""
Chat routes — SSE streaming with sliding window.

Flow:
  1. JWT auth  — user_id extracted from Bearer token (NOT from request body)
  2. Rate limit check (Redis ZSET)
  3. Safety check input
  4. Load session from Redis
  5. Build prompt (system + conversation window)
  6. Stream LLM response via SSE
  7. Post-process (POV fix)
  8. Save session to Redis (resets 30-min TTL)
  9. Enqueue messages for DB persistence (write-behind buffer)
  10. Background: update affection state (async, may call LLM)

# TODO: Memory context (Qdrant semantic recall)
"""
import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from api.schemas import (
    ChatRequest, ChatHistoryResponse, ChatMessage, SessionState,
    RegenerateRequest, GreetingResponse,
)
from api.deps import get_current_user, get_session, save_session, destroy_session
from characters import get_all_characters
from core.llm_client import chat_stream
from core.prompt_engine import build_messages_full
from core.rate_limit import check_rate_limit
from core.response_processor import post_process_response
from core.safety import check_input
from core.db_buffer import enqueue as db_enqueue

logger = logging.getLogger("dokichat.chat")
router = APIRouter(prefix="/chat", tags=["chat"])


# ── Background Tasks ──────────────────────────────────────────

async def _update_affection_bg(session, user_msg: str, assistant_msg: str, char_name: str):
    """Update affection state in background (non-blocking).

    Runs extract_affection_update (may call LLM) then saves
    the updated session back to Redis. If it fails, the session
    still has the correct conversation — only affection score
    misses this one update.
    """
    try:
        from state.affection import AffectionState, extract_affection_update
        if isinstance(session.affection, AffectionState):
            session.affection = await asyncio.to_thread(
                extract_affection_update,
                state=session.affection,
                user_msg=user_msg,
                assistant_msg=assistant_msg,
                character_name=char_name,
            )
            save_session(session)
            logger.debug(f"Affection updated: {session.affection.score}")
    except Exception as e:
        logger.warning(f"Background affection update error: {e}")


# ── Routes ────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream_endpoint(
    req: ChatRequest,
    current_user: str = Depends(get_current_user),
):
    """Stream chat response via Server-Sent Events.

    Requires: Authorization: Bearer <access_token>
    user_id is derived from JWT — the body field is ignored.

    Events:
      - type=token: {"t": "chunk text"}
      - type=done:  {"full": "complete response", "turn": N}
      - type=error: {"error": "message"}
    """
    user_id = current_user  # authoritative — from JWT

    # Rate limit check (Redis ZSET sliding window)
    if not check_rate_limit(user_id):
        raise HTTPException(429, "Too many requests. Please wait a moment.")

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

    # Load session from Redis
    session = get_session(user_id, req.character_id)
    session.user_name = req.user_name
    conv = session.conversation
    aff = session.affection
    scene = session.scene

    conv.add_user(req.message)

    messages = build_messages_full(
        character_key=req.character_id,
        conversation_window=conv.get_window(),
        user_name=req.user_name,
        total_turns=conv.total_turns,
        memory_context="",  # TODO: Qdrant
        scene_context=scene.get_context_block() if hasattr(scene, 'get_context_block') else "",
        affection_context=aff.to_prompt_block() if hasattr(aff, 'to_prompt_block') else "",
        user_message=req.message,
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
            char_name = all_chars[req.character_id].get("name", req.character_id)
            char_gender = all_chars[req.character_id].get("gender")
            processed = post_process_response(full_response, char_name, char_gender)

            # Update session state (sync — fast operations)
            conv.add_assistant(processed)

            if hasattr(scene, 'update'):
                scene.update(req.message)

            # Save session immediately (resets 30-min TTL)
            save_session(session)

            # Enqueue for DB persistence (non-blocking, flushed every 30s)
            db_enqueue(user_id, req.character_id, "user", req.message, conv.total_turns)
            db_enqueue(user_id, req.character_id, "assistant", processed, conv.total_turns)

            # Background: affection update (async — may call LLM)
            asyncio.create_task(_update_affection_bg(
                session, req.message, processed, char_name,
            ))

            yield {
                "event": "done",
                "data": json.dumps({
                    "full": processed,
                    "turn": conv.total_turns,
                    "emotion": "neutral",
                    "affection": session.affection.score if hasattr(session.affection, 'score') else 0,
                }, ensure_ascii=False),
            }

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


@router.get("/history/{character_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    character_id: str,
    current_user: str = Depends(get_current_user),
):
    """Get conversation history for the authenticated user with a character."""
    session = get_session(current_user, character_id)
    messages = [
        ChatMessage(role=m["role"], content=m["content"])
        for m in session.conversation.history
    ]
    return ChatHistoryResponse(
        character_id=character_id,
        messages=messages,
        total_turns=session.conversation.total_turns,
    )


@router.get("/state/{character_id}", response_model=SessionState)
async def get_session_state(
    character_id: str,
    current_user: str = Depends(get_current_user),
):
    """Get current session state for the authenticated user."""
    session = get_session(current_user, character_id)
    aff = session.affection
    return SessionState(
        user_id=current_user,
        character_id=character_id,
        total_turns=session.conversation.total_turns,
        emotion="neutral",
        affection_score=aff.score if hasattr(aff, 'score') else 0,
        affection_stage=aff.stage if hasattr(aff, 'stage') else "stranger",
        scene=session.scene.current if hasattr(session.scene, 'current') else "",
    )


@router.post("/reset/{character_id}")
async def reset_conversation(
    character_id: str,
    current_user: str = Depends(get_current_user),
):
    """Reset conversation history for the authenticated user."""
    destroy_session(current_user, character_id)
    return {"status": "ok", "message": "Conversation reset"}


@router.post("/regenerate")
async def regenerate_response(
    req: RegenerateRequest,
    current_user: str = Depends(get_current_user),
):
    """Regenerate the last assistant response with variation.

    Requires: Authorization: Bearer <access_token>
    """
    user_id = current_user  # authoritative — from JWT

    all_chars = get_all_characters()
    if req.character_id not in all_chars:
        raise HTTPException(404, f"Character '{req.character_id}' not found")

    session = get_session(user_id, req.character_id)
    conv = session.conversation

    if conv.total_turns < 1:
        raise HTTPException(400, "No message to regenerate")

    old_response = conv.pop_last_assistant()
    if not old_response:
        raise HTTPException(400, "No assistant message found")

    last_user_msg = conv.get_last_user_message() or ""

    messages = build_messages_full(
        character_key=req.character_id,
        conversation_window=conv.get_window(),
        user_name=req.user_name,
        total_turns=conv.total_turns,
        memory_context="",  # TODO: Qdrant
        scene_context=session.scene.get_context_block() if hasattr(session.scene, 'get_context_block') else "",
        affection_context=session.affection.to_prompt_block() if hasattr(session.affection, 'to_prompt_block') else "",
        user_message=last_user_msg,
    )

    old_snippet = old_response[:150].replace('\n', ' ')
    messages.append({
        "role": "system",
        "content": (
            f"[VARIATION] The previous response was rejected by the user. "
            f"Write a COMPLETELY DIFFERENT response. Do NOT repeat any phrases, "
            f"sentences, or ideas from this: '{old_snippet}...'. "
            f"Use different actions, different dialogue, different emotions."
        ),
    })

    async def event_generator():
        full_response = ""
        try:
            for chunk in chat_stream(messages, temperature=1.0):
                full_response += chunk
                yield {
                    "event": "token",
                    "data": json.dumps({"t": chunk}, ensure_ascii=False),
                }

            char_data = all_chars[req.character_id]
            processed = post_process_response(
                full_response,
                char_data.get("name", req.character_id),
                char_data.get("gender"),
            )
            conv.add_assistant(processed)

            # Save session to Redis (resets 30-min TTL)
            save_session(session)

            # Enqueue regenerated response for DB persistence
            db_enqueue(user_id, req.character_id, "assistant", processed, conv.total_turns)

            yield {
                "event": "done",
                "data": json.dumps({
                    "full": processed,
                    "turn": conv.total_turns,
                    "regenerated": True,
                }, ensure_ascii=False),
            }

        except Exception as e:
            logger.error(f"Regenerate stream error: {e}")
            conv.add_assistant(old_response)
            save_session(session)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}),
            }

    return EventSourceResponse(event_generator())


@router.get("/greeting/{character_id}", response_model=GreetingResponse)
async def get_greeting(character_id: str, user_name: str = "bạn"):
    """Get a random greeting from the character's greeting pool.

    Public endpoint — no auth required.
    """
    import random

    all_chars = get_all_characters()
    if character_id not in all_chars:
        raise HTTPException(404, f"Character '{character_id}' not found")

    char = all_chars[character_id]
    greetings = [char.get("opening_scene", "")]
    greetings.extend(char.get("greetings_alt", []))
    greetings = [g for g in greetings if g and g.strip()]

    if not greetings:
        raise HTTPException(500, "Character has no greetings")

    selected = random.choice(greetings)
    selected = selected.replace("{{user}}", user_name)

    return GreetingResponse(
        character_id=character_id,
        greeting=selected,
        total_greetings=len(greetings),
    )
