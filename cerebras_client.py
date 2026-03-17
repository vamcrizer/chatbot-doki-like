"""
LLM Client — OpenAI-compatible adapter for vLLM / LM Studio.

Supports both:
  - Local: LM Studio at localhost:1234
  - Production: vLLM on RunPod at custom endpoint

Provides:
  - chat_stream() — streaming generator for chat responses
  - chat_complete() — single completion (for extraction/analysis tasks)
"""
import os
from typing import Generator
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "lm-studio")
MODEL = os.environ.get("LLM_MODEL", "dokichat-8b")

_client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def chat_stream(
    messages: list[dict],
    temperature: float = 0.85,
    max_tokens: int = 1024,
) -> Generator[str, None, None]:
    """Stream chat completion — yields text chunks.

    Usage:
        for chunk in chat_stream(messages):
            print(chunk, end="")
    """
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
        print(f"[LLM] Stream error: {e}")
        yield f"*[Connection error: {e}]*"


def chat_complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    """Single chat completion — returns full text.

    Used for:
    - Fact extraction (fact_extractor.py)
    - Affection analysis (affection_state.py)
    - Session summarization (summarizer.py)
    - Character generation (character_generator.py)
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
        print(f"[LLM] Complete error: {e}")
        return ""
