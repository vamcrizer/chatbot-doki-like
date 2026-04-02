# API & Services Đặc Tả (Detailed Specification)

> Lớp Giao diện & Điều phối nghiệp vụ (Gateway). Xử lý cầu nối giữa Client Request và các Core Engine/Model DB.

## 1. FastAPI Kiến Trúc & Application Lifespan (`api/main.py`)

- **Lifespan Context**: Sử dụng chuẩn `asynccontextmanager` của FastAPI v0.100+.
  - Khởi động: Nạp Database, Kết nối Redis, Warm-up Router. Cài đặt `asyncio.create_task` kích hoạt Worker Background chuyên móc `db_buffer` flush về Neon PostgreSQL sau mỗi khoảng thời gian 30s.
  - Shutdown: Cleanup connections gracefull.
- **Middleware**: Gắn các logic cơ sở, chặn CORS và bắt Rate Limit đối với các đường truyền tạo Character (tránh khai thác API Key phi nguyên tắc).

## 2. Dependency Injection (`api/deps.py`)

Gắn chặt Design Pattern DI thông minh dựa trên FastAPI:
- `get_current_user`: Bắt Require `Bearer Token`, decode JWT, trả về `user_id` sạch. Nếu thất bại -> Throw 401. Tranh chặn bất cứ API thao tác nào không có ủy quyền thực.
- `get_session`: Đọc Session Manager từ Redis (Kéo DB Conversaton ra). Trả về Object Session phức hợp. 
- Ngăn chặn triệt để thao tác Hardcode truy xuất DB trong Controller. Tất cả truyền qua Parameters.

## 3. Chat Router (Streaming SSE - `api/routes/chat.py`)

Phức hợp lõi. Phục vụ `POST /chat/stream`.

### 3.1 Flow Bảo Mật & Xác Thực
1. Validate JWT.
2. Kiểm tra Rate Limit. Nếu bóp cổ -> HTTP 429.
3. Validate đầu vào `check_safety(message)` -> Ngăn chặn tấn công bằng Regex & Blacklist. Ném 400 Content Blocked nếu phát hiện.

### 3.2 Build Context & Generator
1. Trích xuất Object `Conversation`, `Affection`, `Scene` từ `Session`.
2. Push User Message vào Window Array (`conv.add_user()`).
3. Dựng Context mảng gửi LLM bằng `build_messages_full()`.
4. Gọi `chat_stream()` để thiết lập Iterative Streaming.
5. Vòng lặp `yield`: Sinh ra Server-Sent Events (SSE) packet. Format: Dành riêng cho Frontend đọc.
   - Event `token`: `{"t": "chữ tiếp theo"}`
   - Event `done`: Full Block, Nén kèm thông số cảm xúc Affection mới nhất. Cực kỳ tiện cho Mobile/Web cập nhật thanh trạng thái giao diện UI.
   - Event `error`: Bắt lỗi đứt cáp.

### 3.3 Hậu Kì & Zero-Blocking Writes
- Sau khi Streaming xong ở Main Thread, toàn bộ tác vụ DB được "chôn" vào Background:
  1. Set lại Session xuống Redis (Làm mới TTL 30 Giờ).
  2. Bắn 2 Enqueue `User` và `Assistant` Message xuống Background Write-Buffer (0ms Delay).
  3. Bắn 1 `asyncio.create_task()` gọi đến LLM Phụ trong `_update_affection_bg` để phân tích cảm xúc ẩn của câu trả lời vừa sinh ra mà không làm chậm Client Connection (vì Client đã nhận được Event `done`).

## 4. Auth & Character Controller
- Các Route còn lại phục vụ Login, Sign Up, Token refresh (chuẩn hóa auth_tokens table ở Database). Cùng với CRUD Characters lấy từ bảng `characters`. Phục vụ Front-end Dashboard Explore Characters.
