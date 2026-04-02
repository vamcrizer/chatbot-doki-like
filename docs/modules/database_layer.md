# Database Layer Đặc Tả (Detailed Specification)

> Module cung cấp Cấu trúc Dữ Liệu Persistent và Caching In-Memory để hỗ trợ Zero Server Memory. 

## 1. Relational Mapping - SQLAlchemy (`db/models.py`)

Hệ thống mô phỏng 1:1 các Entity của hệ thống dưới chuẩn Schema của PosgreSQL JSONB/UUID:

### Ánh xạ Entities
1. **`User` (Users Table)**: ID bằng UUID. Lưu `email`, password_hash, preferences, language (dùng để map với Immersion Anchor). Đặc biệt có trường `bio`: tiểu sử người sử dụng để Inject vào Memory System (giúp Character nhớ User làm nghề gì, sống ở đâu dễ hơn).
2. **`Character` (Characters Table)**: Lõi chia sẻ Nhân vật. Flag `is_builtin` quyết định nhân vật cứng (System) hay `creator_id` quyết định User tạo. JSONB `tags`, `greetings_alt`, `emotional_states` chứa các mảng logic động không cố định Schema. Hỗ trợ Search bằng `is_public`.
3. **`Conversation`**: Phiên hội thoại. Chứa `turn_count` để quản lí Limit Token window. `last_message_at` để sort Inbox.
4. **`ChatMessage`**: Lưu dòng chat con.
5. **`AffectionState`**: Bảng Snapshot. Mỗi bản ghi quy chiếu Mối quan hệ Unique của cặp 1 `user_id` và 1 `character_id`. Lưu lại `score`, `stage`, `scene_state` (JSONB cho phép phục dựng Scene Tracker Object).
6. **`Memory` / `SessionSummary`**: Lưu trữ dạng Text Block của Fact_Extractor phục vụ cho vector-search Phase 2 với Mem0 / Qdrant.  Kiểu phân giã: Memory `type` = `user_fact`.

### Connection Pooling
Hệ CSDL được deploy trên Neon (Serverless Postgres), model kết nối thông qua URL param có gắn dấu hiệu pooled (`-pooler`). Đảm bảo hệ thống sử dụng PGBouncer từ xa, quản trị 10,000 connection từ API Server qua một số lượng Socket backend giới hạn.

## 2. In-Memory Key Value - Redis (`core/redis_client.py`)

Thùng chứa State duy nhất có giới hạn thời gian (TTL) sống sót ngắn, cho phép hệ thống "bay" cùng hàng trăm ngàn Request/s và sập không thương tiếc mà ảnh hưởng ít nhất tới Persistence.

### Các Phân vùng Redis sử dụng:
1. **Prefix `session:{user_id}:{character_id}`**
   - Loại Value: String / JSON Serialized object (chứa ChatHistory Array 7 dòng cuối, Scene Object, Affection Object).
   - TTL: 30 Giờ (Thường xuyên reset mỗi khi nhắn câu mới).
2. **Prefix `immersion:{char}:{lang_code}`**
   - Loại Value: String JSON (Anchor Prompt User + Anchor Response Assistant).
   - TTL: Dài hạn (hoặc Persistent cache tuỳ Cấu hình). Tái cung cấp lại 0.05ms cho LLM System builder mà không phải Call Generate Anchor tốn kém nữa.
3. **Prefix `ratelimit:{user_id}`**
   - Loại Value: `ZSET`. 
   - Quản trị Time Series số lượng tác động dựa theo Unix Timestamp score đóng vai trò Sliding Window counter thần tốc.

## 3. Repositories Pattern (Dual Implementation)

Triển khai DI (Dependency Injection) của Repositories ở mức Adapter để bảo đảm Graceful Degradation (Fallback):
- Triển khai **Postgres Repository**: Đẩy data bằng SQLAlchemy xuống Prod DB.
- Triển khai **InMemory Repository**: Kích hoạt khi Postgres không trỏ tới hoặc đứt nối. Lưu mọi thứ ở `dict()`. Hệ thống chat *vô tư* hoạt động (Dù Refesh trang là mất lịch sử). Mục tiêu này giúp Local Developement trên Macbook chỉ mất 30 giây để setup mà không cần dựng container Docker Postgres cồng kềnh.
