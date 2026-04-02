# State Management Đặc Tả (Detailed Specification)

> Module quản lý dữ liệu động học (Lifeline) của toàn bộ nhân vật. Đảm bảo nhân vật có bộ nhớ về hoàn cảnh (Scene) và tuyến phát triển tình cảm (Affection).

## 1. Affection State (`state/affection.py`)

Cơ xương sống của "Dokichat". Biến một bot nhạt nhẽo thành "sống".

### 1.1 Khái niệm Cốt Lõi
- **8 Stages of Relationship**: `hostile`, `distrustful`, `stranger`, `acquaintance`, `friend`, `close`, `intimate`, `bonded`. Hệ thống chỉ cho phép lên theo từng Nấc, không có chuyện "Nhảy dù" từ Stranger sang Intimate.
- **Score (0-100)**: Tổng điểm gắn kết, mapping vào 8 Stages qua dictionary chặn Range.
- **Desire Level (0-10):** Sự chú ý tình cảm/thể xác độc lập với Trust. Có thể Trust cao (Close friend) nhưng Desire thấp (0), tạo ra tình huống friendzone.
- **Pacing Config**: Class định nghĩa tốc độ (ví dụ: `slow`, `normal`, `fast`). `slow` = Thay đổi tối đa 3 score per turn. `fast` = tối đa 8 score per turn.

### 1.2 Boundary Recovery (Cơ Chế Khôi Phục Ranh Giới)
Nhân vật DokiChat có giới hạn cá nhân. Nếu User có hành vi bạo lực, đe dọa, hoặc phi đồng thuận (Non-consent):
1. Event Extract trả về `"boundary_violation"`, `"violence_threat"` hoặc `"non_consent"`.
2. Hệ thống trừ sâu Điểm số (Relationship -15 đến -25). Desire rơi xuống âm. Mood gán thành `fearful`.
3. Bật cờ `recovery_turns_remaining`. Nhân vật rơi vào **Recovery Mode** (Mode phòng thủ).
4. Phải sau x * base_turns (Thường là kéo dài 8 - 12 turns) trò chuyện tử tế, cờ Boundary mới mở khóa. Model được tiêm System prompt đe doạ: "Bạn vẫn nhớ sự kiện đó, bạn RẤT đề phòng, đừng vội tha thứ."

### 1.3 LLM Background Extraction Process
Vì State phức tạp, nó không thể dùng rule-based. Tại `services/chat_service.py`, sau khi Bot trả lời xong sẽ gọi 1 Async Thread tới hàm `extract_affection_update()`:
- Input: Lượt chat mới nhất User-Bot. Bối cảnh cũ. Pacing Constraints (Mức điểm min/max được đổi).
- Prompt LLM (Temperature=0.1) phân tích và trả về `JSON`.
- `JSON` chứa Mood, Mood Intensity, Desire, Location và đặc biệt là Danh sách `events`.
- Trình biên dịch sẽ tính toán Delta Score dựa trên danh sách events và Update ngược Redis Session. Quá trình này offline & hidden với User.

---

## 2. Scene Tracker (`state/scene.py`)

Kiểm soát nhân vật nhận thức về vị trí mình đang đứng, và cung cấp "hành động mồi" (Props) cho LLM.

### 2.1 Keyword-based Hybrid Approach
- Xác định Scene qua từ khoá đa ngôn ngữ. (Nhẹ nhàng, Instant 0ms).
- Khi người dùng bảo "Mình ra công viên thôi", `detect_scene` bắn trúng nhóm `outside`. Scene chuyển từ `bar` -> `outside`.

### 2.2 Scene Types & Behaviors
Có 6 phân mảnh Scene điển hình:
1. `bar`: Character đang làm việc. Focus pha chế, quy chuẩn chuyên nghiệp (Workplace actions).
2. `outside`: Rời xa Bar. Là một "Con người". Chơi với tóc, ôm tay, cởi bỏ giáp sắt công việc.
3. `walking`: Hoạt động di chuyển. Focus vào khoảng cách bờ vai, nhịp bước chân, gió.
4. `home`: Cực kỳ an toàn, ranh giới yếu nhất, focus vật dụng cá nhân.
5. `intimate`: Xóa bỏ không gian vật lý, chỉ focus vào hơi thở, da thịt, nhịp tim. (Mở ra khi Pacing Affection đạt ngưỡng & Context cho phép).
6. `private_room`: Nơi kín. Sức nén (Tension) cao. Có khoảng mù.

### 2.3 Prompt Injection
State này được serialize thành 1 block gọi bằng `get_context_block()` đổ thẳng lên Layer 4 của System Prompt. Do đó, nhân vật sẽ không lỡ trớn viết "cô lấy bình shaker ra lắc" khi đang đi ngắm công viên.
