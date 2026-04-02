# Character System Đặc Tả (Detailed Specification)

> Module vận hành "Giao diện tâm hồn" của DokiChat. Xử lý toàn bộ logic chuyển hóa Text Bio của User (C.AI Card Format) sang System Prompt chuẩn cấu trúc siêu chặt của hệ thống.

## 1. Kiến Trúc META_PROMPT V3 (`characters/generator.py`)

Cốt lõi sử dụng kĩ năng Prompt Engineering cao cấp - Framework **Fill-in-the-blank**. Thay vì yêu cầu LLM viết lại 1 prompt dài từ đầu đến cuối (dễ mất mát structure format), Generator chia nhỏ thành 8 Job Request song song đổ về LLM, rồi Assemble lại vào 1 file TEMPLATE tĩnh V3.2.3 cứng.

### 1.1 Parallel Worker Architecture
Hàm `generate_system_prompt()` tận dụng `ThreadPoolExecutor`:
- Khởi tạo 8 threads đồng thời chọc LLM_Base tạo 8 Sections.
- **Section 1 (Character Section)**: Bio đa tầng, hiển lộ "Wound" (Vết thương tâm lý).
- **Section 2 (Voice Critical)**: Các cơ chế phòng vệ giao tiếp (Tấu hài, Sarcastic, Câm nín).
- **Section 3 (Sense Examples)**: 3-4 keyword giác quan vật lý mồi.
- **Section 4 (Voice Hook)**: Signature moment của bot.
- **Section 5 (Voice Hook Short)**: Keyword verify cho self-check list.
- **Section 6 (Genre Style)**: Mood bối cảnh.
- **Section 7 (Intimacy Stages)**: Sinh 5 đoạn mô tả hành vi ứng với độ mặn nồng tình cảm.
- **Section 8 (NSFW / Intimate Scenes)**: Phân hóa theo content-mode (Romantic vs Explicit). Điểm chạm, fade-to-black hay graphic details.

Tổng thời gian tạo System Prompt 3500 token: Trôi xuống dưới 4-6s thay vì 30s so với Prompting tuyến tính.

### 1.2 Format Enforcement
Quy cách Template Template V3.2.3 có Block **SELF-CHECK (READ LAST)**. Nó ghim 6 luật kim cương cho Character ở cuối Context Window, triệt để khai thác recency bias của LLMs Model:
1. 100% Target language.
2. Third-person POV.
3. Quotes vs Italics format.
4. Body Contradicts words (Sự bất nhất của cơ thể và lời nói - tạo tension cao).
5. Ít nhất 1 voice hook.
6. Ngưỡng dài (200 - 450 words) và Không nói thay User (`{{user}}`).

## 2. Dynamic Greeting ("Viết Cho Tôi")

Sử dụng hàm `generate_single_greeting()`.
- Chức năng chuyên biệt hỗ trợ người tạo Bot khi bị bí ý tưởng viết "Lời Chào Ban Đầu / First Message".
- Lấy System Prompt + Tính cách + Rule ("Tránh viết lại thứ đã viết nếu reroll").
- Trả ra một Scene ngắn gọn, 150 words. Mồi bối cảnh ban đầu, cung cấp một hành động bỏ lửng (Hook) yêu cầu sự kiện phản hồi của user.

## 3. Immersion Anchor Generator
Sinh mồi hội thoại `generate_immersion_anchor()`.
Xử lý ngôn ngữ: Lắp vào 1 LLM request mồi: "Viết 1 response greeting ngẫu nhiên 100% ngôn ngữ tiếng `Lang_name` theo system_prompt sau.". Xử lý và trả về Cache tại Memory System nhằm lock ngôn ngữ của VLLM vào đúng rãnh đa ngôn ngữ một cách tự nhiên bằng Few-shot prompting.

## 4. Quản Lý Nhân Vật Động (UGC)
Nhân vật chia thành 2 tệp:
- **Built-in Characters**: Hard-coded tại thư mục `characters/*.py` (Ví dụ: `kael.py`, `sol.py`, `ren.py`). Mang sẵn Immersion_lang và Greetings thủ công tốt nhất.
- **User-Generated Content (UGC)**: Persist vào Database `characters` Neon với cấu trúc UUID và `creator_id`. Backend đọc từ `db.models.Character` và mapping lên in-memory format để parse qua `chat_service.py`.
