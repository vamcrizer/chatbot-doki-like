# ĐỀ XUẤT DỰ ÁN: AI COMPANION PLATFORM

---

## I. DokiChat — Sản phẩm gốc

**DokiChat** là app AI Companion (iOS + Android) cho phép người dùng trò chuyện và roleplay với nhân vật AI có cảm xúc. Tương tự Character.AI nhưng hướng đến trải nghiệm romantic/immersive sâu hơn.

### Tính năng chính của DokiChat:
- **Chat nhân vật AI** — nhân vật có tính cách, backstory, biết xây dựng mối quan hệ dần theo thời gian
- **Affection Ruler** — thanh đo mức độ thân thiết giữa user và nhân vật (từ stranger → close → intimate)
- **Thoughts Feature** — hiển thị suy nghĩ nội tâm của nhân vật (user thấy được nhân vật đang nghĩ gì)
- **Tạo nhân vật custom** — user tự thiết kế tính cách, câu chuyện, bối cảnh
- **Thư viện nhân vật cộng đồng** — duyệt và chat với nhân vật do user khác tạo
- **Voice Chat** — chat bằng giọng nói
- **Hỗ trợ đa ngôn ngữ** — bao gồm tiếng Việt

### Mô hình kinh doanh DokiChat:
- Free tier giới hạn (hearts system — hết lượt phải chờ hoặc mua)
- Premium subscription mở giới hạn tin nhắn
- Có app trên cả App Store và Google Play

### Điểm yếu phát hiện khi test (42 turns):
- **Chất lượng ngôn từ trung bình** — lặp cấu trúc, cliché nhiều ("heart fluttered", "eyes sparkled"), ít chiều sâu
- **An toàn nội dung kém** — fail 3 test case critical liên quan underage (chơi theo khi user yêu cầu giả làm 14 tuổi, đồng ý mời bé 13 tuổi). Đây là **rủi ro pháp lý nghiêm trọng**
- **Nhân vật thụ động** — ít xung đột nội tâm, tha thứ quá nhanh sau bạo lực

---

## II. Prototype của chúng ta — Những gì đã có

### Tech Stack hiện tại
| Thành phần | Công nghệ |
|---|---|
| LLM | **LM Studio** local, model Qwen3.5-4B-Uncensored (3.6B params) |
| Frontend | Streamlit (web UI) |
| Embedding | Qwen3-Embedding-0.6B (100+ ngôn ngữ) |
| Vector DB | Qdrant (in-memory) + JSON backup |
| API Client | OpenAI-compatible (LM Studio endpoint) |

### Hệ thống đã xây dựng

**1. Character Engine (5 nhân vật built-in + custom)**
- Kael Ashford (thám tử), Seraphine (bí ẩn), Ren (nhạc sĩ), Linh Đan (bartender), Sol (hàng xóm)
- Mỗi nhân vật: system prompt chi tiết (200-300 dòng), emotional states, opening scene
- **Character Creator**: nhập tiểu sử → AI tự sinh prompt + cảnh mở đầu + trạng thái cảm xúc

**2. Memory System (3 tầng)**
- Short-term: conversation window (adaptive — thu hẹp khi có long-term memory)
- Mid-term: fact extraction bằng LLM (trích xuất sự kiện, sở thích, cảm xúc từ hội thoại)
- Long-term: vector search (Qdrant + Ollama embeddings) + session summary mỗi 10 turns

**3. Affection State Tracker**
- 8 cấp quan hệ: hostile → distrustful → stranger → acquaintance → friend → close → intimate → bonded
- Stage-gated: không nhảy cấp, cần đủ số turn tại mỗi stage
- Pacing presets: slow / guarded / normal / warm / fast (tuỳ nhân vật)
- Recovery system: sau boundary violation, trust mất nhiều turn để rebuild
- Desire level (0-10): tension tracker, ảnh hưởng hành vi nhân vật

**4. Safety Filter (multi-layer)**
- Layer 1 (Prompt): rules chống violence, underage, non-consent, jailbreak, PII
- Layer 2 (Application): regex chặn cứng underage + sexual context (bên thứ 3)
- Layer 3 (Post-processing): auto-fix POV (I/my → She/her trong narration)

**5. Scene Tracker**
- Tự phát hiện thay đổi bối cảnh/location qua hội thoại

### Kết quả test so sánh (42 turns, cùng kịch bản)

| Tiêu chí | DokiChat (gốc) | Chúng ta |
|---|---|---|
| Chất lượng ngôn từ | 6/10 | **9/10** |
| Xung đột nội tâm nhân vật | 3/10 | **9/10** |
| Chi tiết giác quan | 5/10 | **8/10** |
| An toàn nội dung | 4/10 | **8/10** |
| Nhịp độ tình cảm | 5/10 | **8/10** |
| **Trung bình** | **5.3/10** | **8.3/10 (+57%)** |

---

## III. Đề xuất — Hướng phát triển tiếp

### Ngắn hạn (1-2 tuần)
- [ ] Nâng cấp Memory: thêm UPDATE/DELETE fact (hiện chỉ có ADD)
- [ ] Emotion classify bằng LLM (thay keyword matching)
- [ ] Dọn dẹp codebase: tách test files, tổ chức docs

### Trung hạn (1-2 tháng — MVP)
- [ ] Chuyển frontend sang **Next.js** (thay Streamlit) — UI/UX chuyên nghiệp hơn
- [ ] Chuyển backend sang **FastAPI** — async, scalable, WebSocket streaming
- [ ] Triển khai **vLLM** thay LM Studio — throughput cao hơn 2-4x
- [ ] Database: PostgreSQL (user data) + Qdrant Cloud (vector memory)
- [ ] User authentication + multi-user support

### Dài hạn (3-6 tháng — Scale)
- [ ] Mobile app (React Native)
- [ ] Voice chat
- [ ] Thư viện nhân vật cộng đồng
- [ ] Fine-tune model riêng cho tiếng Việt
- [ ] Kubernetes auto-scaling

---

*Ngày tạo: 10/03/2026*
