# Core Engine Đặc Tả (Detailed Specification)

> Trọng tâm khối xử lý luồng AI giao tiếp, nơi xây dựng nhận thức, ngôn ngữ và khả năng điều hướng dòng chảy (flow) hội thoại.

## 1. Prompt Engine (`core/prompt_engine.py`)

`prompt_engine.py` giữ vai trò sống còn trong việc tạo ra "tư duy" của AI cho mỗi lượt hội thoại. Nó ghép nối các dữ kiện rời rạc để dựng thành 1 payload duy nhất gửi đi Inference LLM.

### Kiến trúc Context đa tầng (Multi-layer Context)
Luồng khởi tạo Prompt phải tuân thủ thứ tự xây dựng vì các layer sau có độ ưu tiên về Token Attention lớn hơn (Recency Bias):
1. **Character System Prompt (`char["system_prompt"]`)**: Chứa bio cơ bản, style, tính cách và các hooks.
2. **Affection State (`affection_context`)**: Trạng thái cảm xúc nội bộ cập nhật real-time. Nêu rõ mood, intensity, desire level và số vòng chat đã trải qua tại stage đó. 
3. **Memory Context (`memory_context`)**: Ký ức về User (Fact Extraction query từ Qdrant) - (TODO Phase 2).
4. **Scene Context (`scene_context`)**: Đặc tả lại môi trường xung quanh (Props, không gian, chỉ dẫn hành động). Ví dụ: "bạn đang ở bên ngoài, không có bar shaker đâu".
5. **Format Enforcement (`FORMAT_ENFORCEMENT`)**: Ràng buộc cấu trúc Output. 60% hội thoại, 40% tường thuật ngôi thứ ba. Luôn để lại open-tension, body conflict.
6. **Language Enforcement (`LANGUAGE_ENFORCEMENT`)**: Luật thép 100% target language. Khóa chặt ngoại ngữ cấm kị.

### Immersion Anchor Lifecycle
Xử lý lỗi rò rỉ ngôn ngữ (Language Leakage) khi Users chat ngôn ngữ khác tiếng Anh.
- **Tiến trình:** 
  - Detect user language -> Gọi Redis kiểm tra `immersion:{char}:{lang}`. 
  - Có Cache -> Sử dụng. Không Cache -> Gen on the fly thông qua `characters.generator.generate_immersion_anchor`.
  - Cấy anchor fake history (User: (Hello) / Assistant: [Anchor_Response]).
  - Kết thúc toàn bộ history bằng `[REMINDER] Respond ENTIRELY in {lang_name}.` chặn đuôi Model Attention.

---

## 2. Các Thành phần Hỗ Trợ (Supporting Engines)

### 2.1. LLM Client (`core/llm_client.py`)
- Wrapper tương thích chuẩn OpenAI API cho Stream & Complete.
- Trỏ direct endpoint về vLLM Router / Inference Pod. Xúc tiến stream output với chunk JSON parsing.

### 2.2. Rate Limiting (`core/rate_limit.py`)
- Sử dụng thuật toán Sliding Window với cấu trúc dữ liệu `ZSET` của Redis.
- Tính toán Score: Unix Thờigian. Loại bỏ các timestamps `< (Now - Window)`.
- Chống spam abuse API generation ở tầng ngoài. Cung cấp O(1) read check.

### 2.3. DB Write-Behind Buffer (`core/db_buffer.py`)
Để giữ độ trễ TTFT (Time-to-first-token) bằng 0 trong việc Write logs xuống DB:
- Cung cấp hàm `enqueue(user_id, character_id, role, message_content, turn_number)` đẩy dữ liệu vào **Redis Streams (`XADD`)**.
- Worker Async trong `/api/main.py` đóng vai trò Consumer Group, tự động pop tin nhắn và Bulk Insert xuống PostgreSQL (NeonDB) sau mỗi `flush_interval (30s)` hoặc khi đạt `batch_size`. Pacer này cứu Neon từ viển cảnh cạn Connection Socket và chặn dứt điểm tình trạng Data-loss.

### 2.4. Processing Hậu Kỳ (`core/response_processor.py`)
Đảm bảo Output không làm gãy Immersive roleplay do dính POV thứ nhất.
- Parse và replace lỗi xưng hô "I" / "My" ở phần *tường thuật*. Rất khó, cần bộ regex chuyên nghiệp và cẩn trọng để không sửa chữ "I" trong đoạn Quotes `"..."`.
