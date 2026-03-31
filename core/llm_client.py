"""
LLM Client — OpenAI-compatible adapter for vLLM / LM Studio.

Supports both:
  - Local: LM Studio at localhost:1234
  - Production: vLLM on RunPod at custom endpoint

Provides:
  - chat_stream() — streaming generator for chat responses
  - chat_complete() — single completion (for extraction/analysis tasks)
"""
import logging
from typing import Generator
from openai import OpenAI

from config import get_settings

logger = logging.getLogger("ai_companion.llm")

_settings = get_settings()

# ── Singleton client ──────────────────────────────────────────
_client = OpenAI(base_url=_settings.LLM_BASE_URL, api_key=_settings.LLM_API_KEY)

# Export for backward compat
MODEL = _settings.LLM_MODEL


def chat_stream(
    messages: list[dict],
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Generator[str, None, None]:
    """Stream chat completion — yields text chunks.

    Usage:
        for chunk in chat_stream(messages):
            print(chunk, end="")
    """
    if temperature is None:
        temperature = _settings.LLM_TEMPERATURE
    if max_tokens is None:
        max_tokens = _settings.LLM_MAX_TOKENS

    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        logger.error("LLM stream error: %s", e)
        yield f"*[Connection error: {e}]*"


def chat_complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Single chat completion — returns full text.

    Used for:
    - Fact extraction
    - Affection analysis
    - Session summarization
    - Character generation
    """
    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("LLM complete error: %s", e)
        return ""
