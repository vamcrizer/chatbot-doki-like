import os
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv

load_dotenv()

client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

MODEL = "gpt-oss-120b"


def chat_stream(messages: list[dict], temperature: float = 0.85):
    """Generator — yield từng chunk text để Streamlit write_stream dùng.

    gpt-oss-120b là reasoning model: stream delta.reasoning trước,
    rồi mới stream delta.content. max_completion_tokens phải đủ lớn
    để còn token sau khi reasoning xong.
    """
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        temperature=temperature,
        max_completion_tokens=8192,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
