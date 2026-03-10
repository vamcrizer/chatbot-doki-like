"""
LM Studio Client — Uses OpenAI-compatible endpoint for local inference.
Replaces Cerebras cloud inference with local LM Studio server.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── LM Studio Configuration ──────────────────────────────────
LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_API_KEY = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")

# Model identifier — use the model key from LM Studio
# e.g. "qwen2.5-7b-instruct", "gemma-3-12b-it", etc.
MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen2.5-7b-instruct")

client = OpenAI(
    base_url=LM_STUDIO_BASE_URL,
    api_key=LM_STUDIO_API_KEY,
)


def chat_stream(messages: list[dict], temperature: float = 0.85):
    """Generator — yield từng chunk text để Streamlit write_stream dùng.

    Sử dụng OpenAI-compatible streaming endpoint của LM Studio.
    """
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        temperature=temperature,
        max_tokens=4096,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def chat_complete(messages: list[dict], temperature: float = 0.3,
                  max_tokens: int = 2048) -> str:
    """Non-streaming completion — used for fact extraction, summarization, etc."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""
