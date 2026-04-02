# Tài Liệu Đặc Tả Tổng Quan (General Specification Document)
**Dự án**: DokiChat / AI Companion
**Phiên bản Architecture**: 6.0 | **Quy mô mục tiêu**: 1M → 10M+ MAU

---

## 1. Giới Thiệu & Mục Tiêu (Overview & Objectives)

**DokiChat** là nền tảng AI Companion hướng tới trải nghiệm nhập vai (immersive) sâu sắc. Khác với các mô hình Chatbot hỏi-đáp thông thường, hệ thống tập trung vào tính cách rõ nét của nhân vật, sự phát triển tình cảm qua các giai đoạn, mô phỏng phản ứng thể chất và khả năng duy trì trí nhớ dài hạn.

**Mục tiêu thiết kế hệ thống:**
- **High-Fidelity Roleplay:** Cung cấp trải nghiệm văn bản phong phú về giác quan, với tỷ lệ đối thoại và tường thuật nghiêm ngặt (60% đối thoại, 40% hành động/cảm xúc).
- **High-Performance & Scalability:** Thiết kế hạ tầng dựa trên kiến trúc **Zero Server Memory** (State lưu trên Redis trong vòng 30 giờ), kết hợp Write-Behind Buffer nhằm đạt tính sẵn sàng cao, đáp ứng độ trễ siêu thấp (TTFT < 500ms) và tối ưu chi phí phục vụ (target: 1M - 10M+ MAU).
- **Content Flexibility:** Hệ thống bao gồm 2 chế độ `romantic` (SFW - 16+) và `explicit` (NSFW - 18+, Opt-in), với cơ chế kiểm duyệt chặt chẽ nhiều lớp.

---

## 2. Kiến Trúc Khái Quát (System Architecture)

Hệ thống được thiết kế theo hướng **Event-Driven & Stateless** tại tầng API, giao tiếp với các dịch vụ chuyên biệt.

### Luồng xử lý chính (Zero Blocking Data Flow)
1. **Edge Network & Traffic (Cloudflare Edge):** Xử lý SSL, ngăn chặn Tấn công chối từ dịch vụ (DDoS) và Cấu hình **Session Affinity (Cookie-based)** thay vì DNS tĩnh để giữ Stream kết nối ổn định. Response Buffering bị VÔ HIỆU HÓA để phục vụ Server-Sent Events (SSE) mượt mà.
2. **API Layer (FastAPI trên RunPod CPU):** Tiếp nhận request, kiểm tra Rate Limit và load Session Data cực nhanh từ Redis Cache.
3. **Prompt Builder:** Dựng Prompt nhiều lớp cực kỳ phức tạp (~3500 - 6450 tokens) dựa trên bối cảnh hiện tại.
4. **Inference Router (vLLM Router bằng Rust):** Điều hướng request thông minh với cơ chế **Session Affinity**. Cùng một người dùng sẽ được điều hướng đến cùng GPU Pod nhằm tận dụng KV Cache, tối ưu Token generation rate.
5. **GPU Inference (vLLM trên RunPod GPU):** Chạy Model LLM (`google/gemma-3-4b-it`) ở chuẩn BF16 với chunked streaming callback trực tiếp về API Pod.
6. **Background Tasks:** Các tác vụ phân tích tình cảm (`extract_affection_update`), cập nhật Scene, và Write-behind xuống Database (Neon Postgres) đều diễn ra ngầm (async tasks), bảo đảm không gây trễ cho người dùng.

---

## 3. Các Thành Phần Cốt Lõi (Core Engines)

### 3.1. Prompt Engine (Kiến trúc 5++ Lớp)
Cơ chế Prompt Engine (`core/prompt_engine.py`) chịu trách nhiệm xây dựng bộ nhớ tạm và tư duy của nhân vật tại thời điểm hiện hành:
- **Layer 1 - System Prompt:** Tiểu sử cốt lõi, tính cách, vết thương lòng, push/pull tension. Dài khoảng 3500 tokens.
- **Layer 2 - Affection State Focus:** Block trạng thái cảm xúc, bao gồm `Mood`, `Desire level` (0-10) và mức độ tin tưởng, được nhúng trực tiếp vào prompt để nhân vật phản ứng đúng context.
- **Layer 3 - Memory & Scene Context:** Ký ức về ngữ cảnh liên quan và Scene hiện tại (Ví dụ: Đang ở quán Bar, phòng riêng, v.v.).
- **Layer 4 - Format Enforcement:** Bộ luật bắt buộc (60% đối thoại, không ngắt quãng câu hỏi đóng, hành động đi kèm mô tả thể chất).
- **Layer 5 - Language & Immersion Anchor:** Bắt buộc ngôn ngữ ngặt nghèo (VD: Trả lời 100% bằng Tiếng Việt). Sử dụng "Few-shot priming" - cấy tin nhắn kỹ thuật giả (Immersion anchor) để khóa cứng văn phong nhân vật.

### 3.2. Affection System (Hệ Thống Quan Hệ & Tình Cảm)
Quản lý trong `state/affection.py` với cấu trúc **8 giai đoạn mối quan hệ**:
`Hostile → Distrustful → Stranger → Acquaintance → Friend → Close → Intimate → Bonded`

- **Pacing Config (Tốc độ):** Đa dạng cấu hình thay đổi (slow, guarded, normal, warm, fast). Các nhân vật khác nhau có tốc độ mở lòng khác nhau.
- **Rule Khóa Giai Đoạn:** Không được nhảy vọt mức độ (Ví dụ: Từ Stranger lên Intimate bắt buộc phải qua các nấc trung gian). Yêu cầu `min_turns_per_stage`.
- **Boundary Violation & Recovery:** Xâm phạm ranh giới hoặc đe dọa vũ lực làm giảm Trust trầm trọng, bắt buộc rơi vào "Recovery Mode" - nhân vật phòng thủ và từ chối mọi thân mật cho đến khi qua đủ số lượng "turns" bù đắp.
- **Cập nhật bằng AI (LLM Extraction):** Một LLM phụ chạy ngầm đánh giá mỗi lượt thoại và gán điểm (score_delta), mood, event và desire.

### 3.3. Scene Tracker
Phát hiện và chuyển đổi cảnh tự động dựa trên giao tiếp (dựa vào từ khóa động hoặc phân tích tình huống ngầm). Character sẽ điều chỉnh behavior và công cụ mô tả tùy theo `vị trí` (location).

---

## 4. Mô Hình Dữ Liệu (Data Model)

Sử dụng **PostgreSQL (Neon DB)** kết nối bằng **transaction pooled mode** (`-pooler`, PgBouncer built-in). Do hệ thống đang dùng **ORM SQLAlchemy** (`db/models.py`), kết nối được cấu hình **`NullPool`** và vô hiệu hóa prepared statements. Toàn bộ luồng ghi đi qua **Write-Behind Buffer** (Hiện tại cấu trúc dùng cấu trúc bền vững **Redis Streams** `XADD`), đẩy xuống DB theo batch hoặc flush interval 30s. Nếu quá trình đẩy bị lỗi/crash, do chưa gửi `XACK` nên dữ liệu sẽ luôn được đọc lại và bảo toàn.

**Các Entities Chính:**
- **Users:** Lưu trữ thông tin cá nhân, tuỳ chọn ngôn ngữ, content mode, preferences, và bio.
- **AuthTokens:** Refresh token cho JWT sessions.
- **Characters:** Danh mục nhân vật. Từ Builtin đến UGC (User Generated Content). Lưu trữ các tham số System Prompt, Avatar, Pacing configs. Tích hợp bảng thống kê `chat_count`, `like_count`.
- **Conversations:** Trạng thái Room chat tương ứng 1 cặp (User + Character), tracking turn_count và timestamps.
- **ChatMessages:** Từng đoạn tin nhắn của User và AI.
- **AffectionStates:** Lưu trữ tiến trình tình cảm cá nhân hoá (Score, Desire level, Track record bị phạm lỗi "boundary") tương ứng của 1 User với 1 Character.
- **Memories / SessionSummaries:** Trích xuất Memory Facts và nén Context khi đoạn hội thoại quá dài (chuẩn bị cho module Memory / Qdrant Integration).

---

## 5. API & Integration

### Chuẩn API
Ứng dụng sử dụng framework **FastAPI** chia thành các module mạch lạc tại `api/routes`:
- **Giao thức:** REST API + Server-Sent Events (SSE) Streaming.
- **Auth Flow (`/auth`):**
  - Hỗ trợ Native (Email/Password) và OAuth (Google, Apple).
  - Sử dụng JWT (Access token 30 phút, Refresh token dài hạn lưu DB).
- **Chat Flow (`/chat`):**
  - API trọng tâm `POST /chat/stream` trả luồng chunked JSON chứa SSE tokens.
  - Các endpoint lấy state, reset log, re-roll response (`/regenerate`).
- **Character Flow (`/character`):**
  - Trả danh mục, detail, tích hợp `/character/generate-prompt` tự động tạo nhân vật bằng LLM META_PROMPT.

---

## 6. Bảo Mật & An Toàn Tiêu Chuẩn (Security & Safety)

Hệ thống được bảo vệ qua **5 lớp hàng rào kiểm duyệt**:
1. **Input Filter Regex (Safety check):** Check các từ khoá nguy hiểm chết người, khủng bố hoặc bạo lực tĩnh tại lớp API trước khi call LLM.
2. **LLM Hard Rules:** System prompt có block lệnh cấm tuyệt đối việc break-character hoặc mô tả underage/non-consent.
3. **Content Mode Toggles:** 
   - `romantic`: Chặn SFW strict, fade-to-black khi tới điểm "nhạy cảm".
   - `explicit`: Opt-in cho trả tiền / xác thực tuổi, cho phép Graphic descriptions.
4. **Model Level Alignment:** Được fine-tune trên base Google Gemma-3-4B-IT vốn đã có sẵn Guardrails tốt.
5. **Crisis Intervention (Can Thiệp Khẩn Cấp):** Nếu bộ extract phát hiện ý định `self-harm` (tự tử, hại bản thân), Persona bị thả nổi và tiêm thẳng link hỗ trợ đường dây nóng vào hệ thống phản hồi.

---

## 7. Hạ Tầng & Vận Hành (Infrastructure & Deployment)

### 7.1 Tech Stack Tiêu Chuẩn
- **Application Server:** Python 3.12, FastAPI, Gunicorn (Uvicorn workers).
- **Inference Engine:** vLLM Server + LLM Base gemma-3-4b-it BF16.
- **Caching & Rate limit:** Upstash Redis Serverless.
- **Database:** Neon PostgreSQL Serverless.
- **CDN & Media:** Cloudflare Edge + R2 Object Storage.

### 7.2 Checklist Vận hành cấu hình bắt buộc
Đảm bảo **Global Networking (Same DC)** trên RunPod.
- **API Pods:** Cấu hình OS open-file limits `ulimit -n 65535` và gunicorn `timeout 120` để không ngắt SSE kết nối dài.
- **GPU Pods:**
  - `vLLM` khởi chạy đi kèm flag `--enable-prefix-caching` (Tối quan trọng cho hiệu năng vì System Prompt chung chiếm tới 3500 token, sử dụng Prefix Cache sẽ giảm thời gian sinh token đến 50%).
  - Bật network volume shares để tránh 3 phút cold-start load model weights từ HuggingFace.
- **Observability:** Tích hợp Grafana Dashboard đo lường TTFT p95 (< 3s), tỷ lệ HTTP 500 và log Request Queue level để sẵn sàng auto-scale.
