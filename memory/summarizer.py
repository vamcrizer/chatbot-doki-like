"""
Session Summarizer — compresses old conversation turns into summary.
Adapted from agent-smart-memo's mid-term session summary mechanism.

Triggered every N turns to prevent context loss.
"""
# Lazy import: cerebras_client loaded inside functions


SUMMARY_PROMPT = """\
Bạn là trợ lý tóm tắt phiên trò chuyện cho chatbot AI companion.
Tóm tắt cuộc trò chuyện dưới đây, TẬP TRUNG vào:

1. Cảm xúc và tâm trạng của user qua các giai đoạn
2. Facts cá nhân user đã chia sẻ (tên, sở thích, hoàn cảnh)
3. Mức độ thân mật hiện tại (xa lạ → quen → thân)
4. Các topic/hook chưa kết thúc (để tiếp tục tự nhiên)
5. Scene hiện tại (đang ở đâu, đang làm gì)
6. Điều gì đã được nhân vật reveal về quá khứ/bản thân

GIỮ DƯỚI 200 từ. Viết bằng tiếng Việt.
Chỉ tóm tắt, không thêm ý kiến.
"""


def summarize_conversation(
    messages: list[dict],
    existing_summary: str = "",
    character_name: str = "",
) -> str:
    """Summarize conversation messages into concise context.

    Args:
        messages: list of {role, content} dicts
        existing_summary: previous summary to merge with
        character_name: name of the character for context

    Returns:
        Summary string (~200 words)
    """
    # Format messages for LLM
    formatted = []
    for msg in messages:
        role = "User" if msg["role"] == "user" else character_name or "Character"
        # Truncate very long messages
        content = msg["content"][:500] if len(msg["content"]) > 500 else msg["content"]
        formatted.append(f"{role}: {content}")

    conversation_text = "\n".join(formatted)

    merge_ctx = ""
    if existing_summary:
        merge_ctx = f"\n\nTÓM TẮT TRƯỚC ĐÓ (merge vào):\n{existing_summary}"

    user_prompt = f"""{merge_ctx}

CUỘC TRÒ CHUYỆN CẦN TÓM TẮT:
---
{conversation_text}
---

Tóm tắt dưới 200 từ. Viết tiếng Việt."""

    try:
        from cerebras_client import client, MODEL
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            max_completion_tokens=1024,
        )

        content = response.choices[0].message.content
        return content.strip() if content else ""

    except Exception as e:
        print(f"[Summarizer] Error: {e}")
        return existing_summary or ""
