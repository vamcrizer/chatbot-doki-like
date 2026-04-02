# AI Companion — System Architecture
### Version 6.0 | Scale Target: 1M → 10M+ MAU

---

## 1. Tổng Quan Hệ Thống

AI Companion là nền tảng chat với các nhân vật ảo có tính cách, cảm xúc và trí nhớ. Hệ thống hỗ trợ 2 content mode: `romantic` (SFW) và `explicit` (NSFW 18+).

Stack gồm **8 components**, mỗi component làm đúng 1 việc, tối ưu cho High-Performance & High-Scalability trên RunPod + Managed Cloud Services.

| Component | Provider | Vai Trò | Chi Phí/Tháng (100K MAU) |
|---|---|---|---|
| Edge / CDN | Cloudflare (free) | SSL, DDoS, serve avatar | $0 |
| API Server | RunPod CPU ×2 | HTTP, SSE, build prompt | ~$230 |
| Inference Router | RunPod CPU ×1 | Route GPU thông minh | ~$22 |
| GPU Worker | RunPod GPU Pod (On-Demand) | LLM inference (Gemma-3-4B BF16) | ~$0.89/hr |
| Cache & Session | Upstash Redis | Sliding window + rate limit + State | ~$50 |
| Database | Neon PostgreSQL | Profile, auth, lịch sử | ~$120 |
| Object Storage | Cloudflare R2 | Avatar (zero egress) | ~$15 |
| Monitoring | Grafana Cloud | TTFT, tok/s, alert | ~$29 |
| **Tổng (không GPU)** | | | **~$466/tháng** |

---

## 2. Kiến Trúc Tổng Thể

```text
USER (Việt Nam)
      │ HTTPS (~5ms đến edge SG)
      ▼
CLOUDFLARE EDGE
  ├── GET /avatar/*  ──────────────────────► Cloudflare R2 (CDN cache)
  ├── SSL terminate                           trả về ngay, không về server
  ├── DDoS filter
  └── POST /chat, /api/*
      │
      ▼ (~130ms về US)
API POD ×2 — RunPod CPU $0.16/hr
  (FastAPI async, uvicorn 4 workers)
      │
      ├── asyncio.gather ──► Upstash Redis   (session, rate limit, bio)
      └── [Phase 2] ───────► Neon PostgreSQL (profile/bio realtime)
      │
      │ POST /v1/chat/completions
      │ header: x-user-id: {user_id}
      ▼
VLLM ROUTER [Mục tiêu Phase 2] — RunPod CPU $0.03/hr
  đọc vllm:num_requests_waiting mỗi 300ms
      │
      ├── GPU #1 waiting=2  ◄── route vào đây ✅ (Session Affinity)
      └── GPU #2 waiting=15
      │
      ▼ HTTP chunked stream
GPU POD #N — RunPod GPU Pod (On-Demand qua API)
  vLLM (gemma-3-4b-it) + prefix caching ON
  Network Volume (shared model weights)
      │
      └── callback HTTP stream ──► API Pod ──► SSE ──► User
```

---

## 3. Flow Chi Tiết Một Request (Zero Blocking)

Hệ thống được thiết kế để xử lý toàn bộ logic trong vòng `< 20ms` trước khi chạm đến LLM. Bất kỳ tác vụ lưu trữ/cập nhật nào đều diễn ra **sau khi stream xong (ngầm)**.

```text
① User gửi tin nhắn
        │
② Cloudflare forward về API Pod (SSL đã terminate)
        │
③ Rate limit check (Redis ZSET)              ~0.5ms
   Redis ZCARD ratelimit:{user_id}
   > 30 tin/phút → 429 Too Many Requests
        │
④ Load Session (Redis)                      ~5ms
   Redis GET session:{user_id}:{char_id} ← Load Session định dạng JSON
   [Phân vùng dữ liệu Bio]:
    - Phase 1: `bio` được load thẳng ra cùng json session từ Redis (có được cache lúc user update profile).
    - Phase 2: Parallel fetch (Neon PG `SELECT bio FROM users`) để lấy thông tin mới nhất bỏ qua cache nếu cần.
        │
⑤ Build prompt (4 Layers)
   [system]:    bio của user + Character Prompt (~3500 tok) + Affection/Scene (~130 tok)
   [summary]:   session_summaries gần nhất (nếu có - tóm tắt bối cảnh cũ)
   [messages]:  Sliding Window từ Redis (7 turns)
   [user]:      tin nhắn mới
        │
⑥ POST → GPU Pod (hoặc Router trong Phase 2)  ~1ms
   API Pod đính kèm `X-Callback-URL: http://pod-X.internal:8000/stream/{request_id}`
        │
⑦ GPU Pod (hoặc Router) xử lý chọn luồng
   GPU biết chính xác gọi về API Pod nào nhờ URL truyền ở bước 6
        │
⑧ vLLM stream tokens                        TTFT ~200–500ms
   qua runpod.internal (private network)
   về callback URL của đúng API Pod
        │
⑨ API Pod forward SSE về user               token hiện dần
   header X-Accel-Buffering: no
   header Cache-Control: no-cache
        │
⑩ Hậu kỳ (Background Tasks — KHÔNG BLOCK USER)
   - [Đã có]: Gọi save_session() đè lại state vào Redis, update TTL 30 giờ.
   - [Đã có]: Hàm extract_affection_update chạy Async Background (asyncio.create_task).
   - [Đã có]: DB Write-Behind — `XADD` vào Redis Streams (`db_write:stream:messages` & `db_write:stream:affections`). Consumer Group Worker `XREADGROUP` mỗi 30s, flush xuống Postgres bằng UPSERT, chỉ `XACK` sau khi ghi thành công. Pod crash không mất data vì message vẫn chờ trong stream.
   - [Memory]: Nếu turn_count % 50 == 0 → trigger background job gọi LLM tóm tắt 50 turns vừa qua → `XADD` vào stream tương ứng → flush xuống bảng `session_summaries`.
```

---

## 4. Chi Tiết Các Component Infrastructure

### 4.1 Cloudflare (Edge)
- **SSL**: terminate tại edge gần user nhất, API Pod nhận HTTP thuần.
- **DDoS**: filter tự động, RunPod IP không bao giờ lộ ra internet.
- **CDN Avatar**: R2 bucket bind vào subdomain `cdn.yourdomain.com`, cache tại edge.
- **SSE config bắt buộc**: tắt response buffering để token stream real-time.
  *(Cloudflare Dashboard → Speed → Optimization → Disable Response Buffering)*

### 4.2 API Server (RunPod CPU Pod)
- **Image**: Python 3.12 + FastAPI + uvicorn.
- **Start command**: `gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --timeout 120`
- **OS tuning bắt buộc**: `nofile limit = 65535` (không tune → crash ở 1024 connections).
- **Port**: expose 8000 public qua Cloudflare.
- **Load Balancing**: Sử dụng Cloudflare Tunnel bật Session Affinity (Cookie-based / Sticky Session) trỏ cứng về 1 API Pod. Chặn triệt để DNS Round-robin làm đứt gãy Stream kết nối SSE dở dang.

### 4.3 Upstash Redis (Session & Rate Limit)
Trái tim của hệ thống **Zero Server Memory**. Tất cả RAM của server là trống, state nằm ở đây.
- **TTL Session**: 30 giờ (Đủ khoảng không thời gian cho user dừng chat lâu không bị timeout mất luồng cảm xúc).
- **Global Anchor**: Cache mỏ neo ngôn ngữ (`immersion:{char}:{lang}`). 10k users xài chung tốn 1 lần prompt.
- **Rate limit (sliding window counter)**: `[Đã implement — core/rate_limit.py]`
  ```python
  ZADD   ratelimit:{user_id}  {now}  {msg_id}
  ZREMRANGEBYSCORE ratelimit:{user_id}  0  {now-60}
  ZCARD  ratelimit:{user_id}            # > 30 → 429
  EXPIRE ratelimit:{user_id}  61
  ```

### 4.4 Neon PostgreSQL (Source of Truth)
- **Connection**: dùng **transaction pooled mode** (`-pooler`, PgBouncer built-in). Do dùng **SQLAlchemy ORM**, bắt buộc cấu hình `NullPool` và vô hiệu hóa *prepared statements* để tương thích.
- **Write-Behind Pattern**: Dịch chuyển sang cấu trúc queue phân tán bền vững. Luồng ghi được đẩy `XADD` vào **Redis Streams**. Một Consumer Group Worker chạy ngầm, cứ 30s `XREADGROUP` một mẻ và flush xuống Postgres bằng UPSERT. Chỉ khi record vào DB thành công, Worker mới gọi `XACK` để xóa message khỏi Redis Stream. Đảm bảo cấu trúc an toàn tuyệt đối ngay cả khi Worker rớt kết nối hay Pod đột ngột crash giữa chừng.
- **Schema**: Xem `migrations/001_init.sql`. Gồm 8 bảng: `users`, `auth_tokens`, `characters`, `conversations`, `chat_messages`, `memories`, `session_summaries`, `affection_states`.

### 4.5 vLLM Router (RunPod CPU Pod) — [Mục tiêu Infra Phase 2]
*(Bản hiện tại kết nối LLM trực tiếp. Router sẽ được build Infra khi MAU scale)*
- **Image**: `lmcache/lmstack-router:latest`
- **Routing**: `session` mode — cùng `x-user-id` → cùng GPU → tái sử dụng KV Cache → giảm TTFT 30–50%.
- **Fallback**: Tự chuyển request sang GPU khác nếu `waiting > threshold`.

### 4.6 GPU Pod (RunPod On-Demand)
- **Model**: `google/gemma-3-4b-it` (BF16). 4B params, VRAM ~8GB.
- **Rules**: 
  - `--enable-prefix-caching` (Siêu quan trọng để tái sử dụng ~3500 token System Prompt).
  - `--api-key YOUR_SECRET` (Khóa endpoint, chặn ai cũng có thể query lậu).
- **Network Volume**: mount `/root/.cache/huggingface` để các pod GPU share chung file weights, giúp cold start Boot pod mới mất ~20s thay vì 3 phút tải weights.

### 4.7 Cloudflare R2 & Grafana Cloud — [Mục tiêu Mở rộng Phase 2]
*(Chưa tích hợp API vào Source code hiện tại)*
- **R2**: $0 Egress fee. Lưu trữ CDN Avatar, File upload trực tiếp qua Presigned URL.
- **Grafana (Dự kiến)**:
  - Cảnh báo TTFT p95 > 3s.
  - Cảnh báo HTTP 500 rate > 5%.
  - Cảnh báo xếp hàng chờ queue_waiting GPU > 50.

---

## 5. Character System & Prompt Engine

18 section prompt (~3500 token), quy định tính cách, quá khứ, giọng nói và 5 giai đoạn tình cảm thân mật. Hỗ trợ META_PROMPT v3 (Tạo nhân vật từ 1 đoạn Bio).

### Token Budget
```text
┌────────────────────────────────────────────┬───────────┐
│ Component                                  │ Tokens    │
├────────────────────────────────────────────┼───────────┤
│ Character system prompt (V3.2.3)           │   ~3,500  │
│ Emotional state & Affection Stage          │     ~130  │
│ User Profile (from Settings)               │     ~150  │
│ FORMAT_ENFORCEMENT                         │     ~170  │
├────────────────────────────────────────────┼───────────┤
│ FIXED OVERHEAD (System Payload)            │   ~3,950  │
│ Chat history (Sliding Window 7 turns)      │   ~2,000  │
│ Session Summary (mid-term memory)          │     ~100  │
│ Output Buffer (max_tokens)                 │     ~500  │
├────────────────────────────────────────────┼───────────┤
│ TOTAL (max_model_len = 8192)               │  ~6,550   │
└────────────────────────────────────────────┴───────────┘
```

---

## 6. Security (6 Lớp Bảo Vệ)

1. **Auth & Input Filter**: API Server dùng JWT Middleware để parse và verify User Identity. Header `x-user-id` truyền về vLLM là tuyệt đối an toàn và không bị giả mạo. Sau đó, chạy Regex cấm các từ khóa nhạy cảm phi pháp.
2. **Internal Network Isolation**: Máy chủ vLLM Router và GPU Nodes không bao giờ mở Public Port. Chỉ có API Server được truy cập qua VPN nội bộ RunPod.
3. **Prompt Hard Rules**: 7 rules chìm trong từng prompt ngăn chặn AI break-character liên quan đến underage, violence.
4. **Content Mode Toggle**:
   - `romantic`: Chặn ở mức ôm hôn, fade to black (Default).
   - `explicit`: Opt-in 18+, miêu tả graphic, nhưng vẫn tuân thủ luật 1 & 2.
5. **Model Level Alignment**: Gemma 3 IT đã được tune an toàn từ base.
6. **Crisis Response**: Tự động vứt bỏ Persona và chèn hotline hỗ trợ tinh thần nếu phát hiện ý định tự hại (self-harm).


---

## 7. Lộ Trình Scale

| MAU | Khuyến nghị Thay đổi Kiến trúc | Chi phí ước tính |
|---|---|---|
| **0 → 100K** | 1 GPU pod (RTX 5090), 2 API CPU Pods | ~$466 + GPU |
| **100K → 500K** | Upstash PAYG → Fixed $10/mo | ~$480 + GPU |
| **500K → 1M** | Neon Scale plan, cố định 2 API pods | ~$580 + GPU |
| **1M → 3M** | Upstash read replica us-west-2 (+$5) | ~$590 + GPU |
| **3M → 10M** | Neon read replica us-west-2, Bật Qdrant/Mem0 (Ký ức dài hạn) | ~$900+ + GPU |

---

## 8. Checklist Trước Khi Production

**Infrastructure:**
- [ ] Cloudflare response buffering OFF
- [ ] Cloudflare R2 bucket bind CDN subdomain
- [ ] API Pod: nofile limit = 65535
- [ ] API Pod: gunicorn --timeout 120
- [ ] Tất cả pods bật Global Networking cùng Data Center (RunPod)
- [ ] GPU Pod: --api-key set, port không expose public, chỉ expose cho API Router in internal network
- [ ] GPU Pod: --enable-prefix-caching ON, sử dụng --max-model-len 8192
- [ ] Network Volume mount cho LLM model weights

**Database & Cache:**
- [ ] Neon: dùng pooled connection string (-pooler)
- [ ] SQLAlchemy: NullPool + statement_cache_size=0 (vì dùng Pgbouncer transaction mode)
- [ ] Messages index: `(conv_id, created_at DESC)`
- [ ] chat_messages: UNIQUE(conversation_id, turn_number) (chặn duplicate khi flush retry)
- [ ] Redis: Cài đặt script đếm Rate Limit ZCARD
- [ ] API: Worker batch flush DB chạy ngầm bằng `asyncio.create_task`
- [ ] affection_states: write-behind qua Redis Streams (giống chat_messages)

**Observability:**
- [ ] Grafana alert TTFT p95 > 3s
- [ ] Grafana alert HTTP 500 > 5%
- [ ] Grafana alert queue_waiting > 50
