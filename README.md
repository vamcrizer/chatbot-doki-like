# DokiChat — AI Companion Chatbot

Chatbot nhân vật AI với khả năng **ghi nhớ dài hạn**, **thích ứng bối cảnh**, và **cá nhân hóa cảm xúc** — mô phỏng trải nghiệm trò chuyện với nhân vật sống động.

## Kiến trúc

```
User ──→ Streamlit UI ──→ Prompt Builder ──→ Cerebras LLM ──→ Streamed Response
                              ↑                                      ↓
                     ┌────────┴────────┐                    Async Fact Capture
                     │  Context Layers │                    (background thread)
                     ├─────────────────┤                         ↓
                     │ Scene Tracker   │               Ollama Embedding (1024d)
                     │ Memory Recall   │                         ↓
                     │ Emotional State │                  Qdrant Vector DB
                     │ Intimacy Stage  │                         ↓
                     └─────────────────┘                  JSON Persistence
```

## Hệ thống nhớ 3 tầng

| Tầng | Chức năng | Cách hoạt động |
|---|---|---|
| **Ngắn hạn** | Cửa sổ trượt 5-10 lượt gần nhất | Giảm từ 10→5 khi có memory (tiết kiệm ~30% token) |
| **Trung hạn** | Tóm tắt phiên (~200 từ) | LLM nén mỗi 10 lượt, giữ cảm xúc + hooks chưa kết |
| **Dài hạn** | Facts trích xuất (tên, sở thích, quá khứ) | Qdrant vector search + Ollama embedding + JSON backup |

**Chống trùng lặp**: Hybrid cosine similarity (≥0.95) kết hợp word overlap (≥0.5) — xử lý tốt tiếng Việt ngắn.

## Scene Tracker

Phát hiện thay đổi bối cảnh **tức thì** bằng keyword, tự điều chỉnh hành vi nhân vật:

```
Quán bar    →  "ra ngoài"  →  Ngoài trời    →  "ôm"  →  Thân mật
(pha rượu)     (keyword)      (tay run, gió)            (hơi thở, nhịp tim)
```

Khi rời quán bar → nhân vật **ngừng pha rượu**, chuyển sang cử chỉ cá nhân. Tránh lặp hành vi cũ.

## Prompt Builder — 5 lớp context

```
┌─────────────────────────────────────────┐
│ 1. System Prompt (nhân vật + tính cách) │
│ 2. Emotional State (vui/buồn/tức giận) │
│ 3. Intimacy Stage (xa lạ → thân thiết) │
│ 4. Memory Context (facts + tóm tắt)    │
│ 5. Scene Context (vị trí + hành vi)    │
│ 6. FORMAT_ENFORCEMENT (60% thoại/40%)  │
├─────────────────────────────────────────┤
│ Immersion prompt + Conversation window  │
└─────────────────────────────────────────┘
```

## Tạo nhân vật tự động

Nhập tiểu sử dạng text → LLM tự sinh:
- System prompt (tính cách, vết thương, push-pull)
- Cảnh mở đầu (sensory-rich)
- Trạng thái cảm xúc (neutral, vulnerable, playful, angry ...)

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Giao diện | **Streamlit** |
| LLM chính | **Cerebras Inference** (`gpt-oss-120b`) |
| Embedding | **Ollama** (`snowflake-arctic-embed2`, 1024d) |
| Vector DB | **Qdrant** (in-memory, qdrant-client) |
| Lưu trữ | **JSON** files (persistence qua restart) |
