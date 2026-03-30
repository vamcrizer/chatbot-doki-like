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
      ├── asyncio.gather ──► Upstash Redis   (session, rate limit)
      └── asyncio.gather ──► Neon PostgreSQL (profile/bio)
      │
      │ POST /v1/chat/completions
      │ header: x-user-id: {user_id}
      ▼
VLLM ROUTER — RunPod CPU $0.03/hr
  (Rust, ~50MB RAM)
  đọc vllm:num_requests_waiting mỗi 1s
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
   [TODO: Phase 2] Parallel fetch Neon PG SELECT bio FROM users
        │
⑤ Build prompt (4 Layers)
   [system]:    bio của user + Character Prompt (~3500 tok) + Affection/Scene (~130 tok)
   [messages]:  Sliding Window từ Redis (7 turns)
   [user]:      tin nhắn mới
        │
⑥ POST → vLLM Router                        ~1ms
   header x-user-id → session affinity (route về đúng GPU có sẵn Cache)
        │
⑦ Router chọn GPU ít waiting nhất
   route vào GPU, ghi nhớ callback URL của API Pod
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
   - [Đã có]: Gọi save_session() đè lại state vào Redis, update TTL 30 phút.
   - [Đã có]: Hàm extract_affection_update chạy Async Background (asyncio.create_task).
   - [Đã có]: DB Write-Behind — enqueue() vào buffer, flush mỗi 30s xuống Neon PostgreSQL.
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
- **Load Balancing**: 2 pods qua Cloudflare DNS round-robin hoặc Nginx nhỏ.

### 4.3 Upstash Redis (Session & Rate Limit)
Trái tim của hệ thống **Zero Server Memory**. Tất cả RAM của server là trống, state nằm ở đây.
- **TTL Session**: 30 phút (Tiết kiệm cực độ tài nguyên bộ nhớ).
- **Global Anchor**: Cache mỏ neo ngôn ngữ (`immersion:{char}:{lang}`). 10k users xài chung tốn 1 lần prompt.
- **Rate limit (sliding window counter)**: `[Đã implement — core/rate_limit.py]`
  ```python
  ZADD   ratelimit:{user_id}  {now}  {msg_id}
  ZREMRANGEBYSCORE ratelimit:{user_id}  0  {now-60}
  ZCARD  ratelimit:{user_id}            # > 30 → 429
  EXPIRE ratelimit:{user_id}  61
  ```

### 4.4 Neon PostgreSQL (Source of Truth)
- **Connection**: dùng **pooled URL** (`-pooler` trong hostname) — PgBouncer built-in, transaction mode.
- **Write-Behind Pattern**: `core/db_buffer.py` enqueue() mỗi request, background worker flush() mỗi 30s hoặc khi queue > 100 messages.
- **Schema Cốt Lõi**:
  ```sql
  CREATE TABLE users (id UUID PRIMARY KEY, bio TEXT);
  CREATE TABLE messages (
      id UUID PRIMARY KEY, conv_id UUID NOT NULL, 
      role TEXT, content TEXT, created_at TIMESTAMPTZ
  );
  CREATE INDEX ON messages (conv_id, created_at DESC);
  ```

### 4.5 vLLM Router (RunPod CPU Pod)
- **Image**: `lmcache/lmstack-router:latest`
- **Routing**: `session` mode — cùng `x-user-id` → cùng GPU → tái sử dụng KV Cache → giảm TTFT 30–50%.
- **Fallback**: Tự chuyển request sang GPU khác nếu `waiting > threshold`.

### 4.6 GPU Pod (RunPod On-Demand)
- **Model**: `google/gemma-3-4b-it` (BF16). 4B params, VRAM ~8GB.
- **Rules**: 
  - `--enable-prefix-caching` (Siêu quan trọng để tái sử dụng ~3500 token System Prompt).
  - `--api-key YOUR_SECRET` (Khóa endpoint, chặn ai cũng có thể query lậu).
- **Network Volume**: mount `/root/.cache/huggingface` để các pod GPU share chung file weights, giúp cold start Boot pod mới mất ~20s thay vì 3 phút tải weights.

### 4.7 Cloudflare R2 & Grafana Cloud
- **R2**: $0 Egress fee. File upload trực tiếp từ Mobile App qua Presigned URL.
- **Grafana**:
  - Alert nếu TTFT p95 > 3s.
  - Alert nếu HTTP 500 rate > 5%.
  - Alert nếu queue_waiting GPU > 50.

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
│ Output Buffer (max_tokens)                 │     ~500  │
├────────────────────────────────────────────┼───────────┤
│ TOTAL (max_model_len = 4096 / Context 8k)  │  ~6,450   │
└────────────────────────────────────────────┴───────────┘
```

---

## 6. Security (5 Lớp Bảo Vệ)

1. **Input Filter**: Cấm các từ khóa nhạy cảm phi pháp ngay từ đầu (Regex).
2. **Prompt Hard Rules**: 7 rules chìm trong từng prompt ngăn chặn AI break-character liên quan đến underage, violence.
3. **Content Mode Toggle**:
   - `romantic`: Chặn ở mức ôm hôn, fade to black (Default).
   - `explicit`: Opt-in 18+, miêu tả graphic, nhưng vẫn tuân thủ luật 1 & 2.
4. **Model Level Alignment**: Gemma 3 IT đã được tune an toàn từ base.
5. **Crisis Response**: Tự động vứt bỏ Persona và chèn hotline hỗ trợ tinh thần nếu phát hiện ý định tự hại (self-harm).

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
- [ ] GPU Pod: --api-key set, port không expose public
- [ ] GPU Pod: --enable-prefix-caching ON
- [ ] Network Volume mount cho LLM model weights

**Database & Cache:**
- [ ] Neon: dùng pooled connection string (-pooler)
- [ ] Messages index: `(conv_id, created_at DESC)`
- [ ] Redis: Cài đặt script đếm Rate Limit ZCARD
- [ ] API: Worker batch flush DB chạy ngầm bằng `asyncio.create_task`

**Observability:**
- [ ] Grafana alert TTFT p95 > 3s
- [ ] Grafana alert HTTP 500 > 5%
- [ ] Grafana alert queue_waiting > 50
