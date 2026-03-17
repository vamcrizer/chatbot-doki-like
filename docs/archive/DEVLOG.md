# AI Companion Demo — Devlog

## Tổng quan
Demo app chat với nhân vật AI kiểu Dokichat/companion, dùng Streamlit UI + Cerebras Inference (gpt-oss-120b) + streaming realtime.

---

## Stack
- **LLM backend**: Cerebras Cloud SDK — model `gpt-oss-120b`
- **UI**: Streamlit (`st.write_stream` cho streaming)
- **Env**: conda environment `companion-demo` / Python 3.11
- **Dependencies**: `cerebras-cloud-sdk`, `python-dotenv`, `streamlit`

---

## Cấu trúc dự án

```
companion-demo/
├── app.py              # Streamlit UI — chat interface
├── characters.py       # 3 nhân vật + immersion fields + opening scenes
├── conversation.py     # Sliding window 10 turns + total_turns counter
├── emotion.py          # Emotional state detection từ keyword
├── intimacy.py         # 5 giai đoạn intimacy arc theo total_turns
├── prompt_builder.py   # build_messages_full — tích hợp toàn bộ kỹ thuật
├── cerebras_client.py  # Streaming generator cho Cerebras API
├── .env                # CEREBRAS_API_KEY (không commit)
└── requirements.txt
```

---

## 3 Nhân vật

| Nhân vật | Persona | Bối cảnh |
|---|---|---|
| **Kael Ashford** | Thám tử tư lạnh lùng, cựu tình báo | Thành phố noir, mưa, sau nửa đêm |
| **Seraphine Voss** | Thủ thư bí ẩn canh giữ kho lưu trữ cấm | Thư viện Liminal — giữa giấc ngủ và thức |
| **Ren Hayashi** | Nhạc sĩ đường phố, barista part-time | Thành phố châu Á — hẻm đèn lồng, chợ đêm |

---

## Kỹ thuật Prompt Engineering đã tích hợp (từ prompt_engineering.md)

### 6 kỹ thuật gốc
1. **Two-Stage Role Immersion** — inject cặp user/assistant giả lập trước conversation window để model vào vai ngay
2. **Emotional State Tracking** — detect keyword âm/dương/tò mò → inject emotional instruction phù hợp
3. **Plot Hook System** — 5 loại hook xoay vòng: Question → Mystery → Tension → Callback → Vulnerability
4. **Micro-Unique Behaviors** — signature behaviors lặp lại mỗi 2-3 turns để tạo memorability
5. **Graduated Intimacy Arc** — 5 giai đoạn (stranger → acquaintance → familiar → trusted → bonded) theo total_turns
6. **Sensory Scoring** — bắt buộc 3/5 giác quan mỗi response (sight/sound/smell/touch/taste)

### 8 fix từ fix.md (Dokichat style matching)
| # | Vấn đề | Fix áp dụng |
|---|---|---|
| 1 | Action dùng ngôi thứ nhất | `PERSPECTIVE RULE`: action = tên nhân vật + ngôi thứ ba |
| 2 | Action/dialogue lẫn lộn | `ALTERNATING STRUCTURE`: `*action*` → `"dialogue"` → lặp |
| 3 | Dialogue như văn xuôi | `DIALOGUE IS SPEECH`: ≤20 chữ/câu, dùng "..." |
| 4 | Không dùng thông tin user | `USER INFO TURN 1`: gọi tên + reference ngay lập tức |
| 5 | Quá nhiều metaphor abstract | `PROSE RATIO`: 80% vật lý / 20% metaphor |
| 6 | Không có physical props | `PROPS`: 1-2 props/response, ít nhất 1 tương tác với user |
| 7 | Plot hook yếu | `PLOT HOOK`: 4 loại hợp lệ (lời mời / câu hỏi / vật bí ẩn / tình huống) |
| 8 | User là người quan sát | `PROXIMITY & CONTACT`: nhân vật chủ động di chuyển về phía user |

---

## Opening Scene
Mỗi nhân vật có `opening_scene` — cảnh mở đầu render ngay khi load app, trước khi user nhắn tin. Đúng format Dokichat: cấu trúc luân phiên `*action*`/`"dialogue"`, ngôi thứ ba trong action, props xuất hiện ngay, kết thúc bằng hook.

---

## Chạy app

```bash
conda activate companion-demo
cd companion-demo
streamlit run app.py
```

Tạo file `.env` với:
```
CEREBRAS_API_KEY=your_key_here
```
