# KIẾN TRÚC HỆ THỐNG — DokiChat AI Companion
### Backend API Architecture | 10/03/2026

***

## I. TỔNG QUAN

Hệ thống cung cấp **REST API + SSE streaming** cho team app (mobile/web). Không bao gồm frontend.

```
App (mobile/web)
    ↓  HTTPS
API Gateway (Nginx)
    ↓
FastAPI Backend (stateless, N instances)
    ├── Auth middleware (JWT verify)
    ├── Rate limiter (Redis counter)
    ├── Safety filter
    ├── Prompt builder ← PostgreSQL + Qdrant + Redis cache
    ├── Push request → Redis Streams
    └── Subscribe response ← Redis pub/sub → SSE stream về app
                ↓
        vLLM GPU Cluster (RunPod Secure Cloud)
            ├── Chargen Pod: RTX 4090 24GB — 9B + Embed
            ├── Chat Pod 1:  L40S 48GB   — 4B + Embed
            ├── Chat Pod 2:  L40S 48GB   — 4B + Embed
            └── Chat Pod N:  L40S 48GB   — auto-scale
                ↓
        Autoscaler (cronjob 30s)
            └── Đọc Redis queue depth → RunPod REST API scale up/down
```

***

## II. REQUEST FLOW — Chat

```
① App gửi POST /api/chat
   { user_id, character_id, message }
       ↓
② FastAPI:
   a. JWT verify → xác thực user
   b. Rate limit check → Redis INCR user:{id}:msgs (TTL 24h)
   c. Safety filter → regex chặn nội dung bất hợp pháp
   d. Query PostgreSQL → chat history (sliding window 20 turns)
   e. Query PostgreSQL → character config + affection state
   f. Query Qdrant → semantic memory search (facts, emotional memories)
   g. Query Redis → prompt cache hit? (TTL 1h)
   h. Prompt builder → assembled prompt (~2,300–4,100 tokens)
   i. Push → Redis Streams "request_queue"
      { request_id, user_id, prompt, priority, timestamp }
       ↓
③ vLLM Worker (trên mỗi GPU pod):
   a. Poll Redis Streams → lấy request
   b. Gọi vLLM /v1/chat/completions (streaming)
   c. Mỗi token → PUBLISH Redis pub/sub channel "response:{request_id}"
       ↓
④ FastAPI:
   a. SUBSCRIBE Redis pub/sub "response:{request_id}"
   b. Mỗi token → SSE stream về app
   c. Khi done → post-process response (POV fix)
   d. Ghi response vào PostgreSQL chat_history
       ↓
⑤ Async (non-blocking, sau khi response xong):
   a. Update affection state → PostgreSQL
   b. Extract facts → Qdrant
   c. Update scene tracker
   d. Emotion classification
   e. Invalidate Redis prompt cache
```

***

## III. REQUEST FLOW — Tạo nhân vật

```
① App gửi POST /api/characters/create
   { user_id, name, bio }
       ↓
② FastAPI:
   a. JWT verify
   b. Gọi thẳng Chargen Pod port 8000 (9B model)
      → generate_character_from_bio (LLM call 1: ~5,120 tokens output)
      → generate_emotional_states  (LLM call 2: ~512 tokens output)
   c. Lưu character config → PostgreSQL
   d. Return JSON { character_id, name, opening_scene }
```

> Không qua Redis queue — char-gen tần suất thấp (~1% MAU/tháng), gọi thẳng đơn giản hơn.

***

## IV. API ENDPOINTS

| Method | Endpoint | Mô tả | Response |
|---|---|---|---|
| `POST` | `/api/chat` | Gửi tin nhắn, nhận SSE stream | SSE tokens |
| `POST` | `/api/characters/create` | Tạo nhân vật từ bio | JSON character |
| `GET` | `/api/characters` | List nhân vật (built-in + custom) | JSON array |
| `GET` | `/api/characters/{id}` | Chi tiết nhân vật | JSON |
| `GET` | `/api/chat/history` | Lịch sử chat | JSON messages |
| `GET` | `/api/user/memory` | Facts AI nhớ về user | JSON facts |
| `POST` | `/api/auth/login` | Login → JWT token | JWT |
| `GET` | `/api/health` | Health check | 200 OK |

***

## V. GPU CLUSTER

### Pod Types — 2 Docker templates

**Template "dokichat-chargen" (1 pod cố định — RTX 4090)**
```
RTX 4090 24GB — $0.59/hr ($425/tháng)
├── vLLM 9B BF16 (port 8000)  --gpu-memory-utilization 0.78  --max-model-len 8192  (weights 18GB)
├── Embed 0.6B   (port 8002)  --gpu-memory-utilization 0.05  --enforce-eager       (weights 1GB)
└── Free: ~5GB
    Việc: tạo nhân vật + embed cho chargen pipeline
    Tok/s: ~700-900 (4090 clock cao, single-stream nhanh)
```

**Template "dokichat-chat" (N pods auto-scale — L40S)**
```
L40S 48GB — $0.86/hr ($619/tháng/pod)
├── vLLM 4B BF16 (port 8001)  --gpu-memory-utilization 0.80  --max-model-len 8192  (weights 9GB)
├── Embed 0.6B   (port 8002)  --gpu-memory-utilization 0.03  --enforce-eager       (weights 1GB)
└── KV cache: ~38GB → ~95 concurrent users/pod
    Worker process: poll Redis Streams → gọi localhost:8001
```

> L40S cho chat: 38GB KV cache = ~95 concurrent users/pod. Giá $6.52/concurrent user/tháng — hiệu quả nhất.

### Tại sao tách?

| | Chat (L40S) | Chargen (4090) |
|---|---|---|
| **Traffic** | 99% requests | 1% requests |
| **Cần** | Max concurrent (KV cache lớn) | Max tok/s đơn lẻ (clock cao) |
| **Scale** | Thêm pod khi users tăng | Cố định 1 pod mọi scale |
| **Embed** | Có (search memory mỗi turn) | Có (embed facts khi chargen) |

### Chargen Failover

| Sự cố | Xử lý |
|---|---|
| Chargen pod crash | Monitor detect → RunPod API reboot pod |
| Chargen pod restart | 9B load lại ~60-90s → chargen tạm unavailable |
| **Impact** | Chỉ ảnh hưởng tạo nhân vật mới. **Chat không bị ảnh hưởng.** |

### Chi phí theo scale

| MAU | Chat (L40S) | Chargen (4090) | Tổng GPU/tháng |
|---|---|---|---|
| 10K | 1× on-demand = $619 | 1× $425 | **$1,044** |
| 500K | 3× savings = $1,620 | 1× $425 | **$2,045** |
| 1M | 9× savings = $4,731 | 1× $425 | **$5,156** |
| 5M | reserved+auto = $13,086 | 1× $425 | **$13,511** |
| 10M | reserved+auto = $26,172 | 1× $425 | **$26,597** |

> Chi tiết savings plan và auto-scale: xem `TOM_TAT_BAO_CAO_2.md`

***

## VI. DATA LAYER

### PostgreSQL (đã có sẵn)

```sql
-- Tables cần thiết cho AI pipeline
users            (id, email, created_at)
subscriptions    (user_id, tier, expires_at)
characters       (id, user_id, name, system_prompt, emotional_states, is_builtin)
chat_history     (id, user_id, character_id, role, content, created_at)
affection_state  (user_id, character_id, stage, score, mood, desire)
```

### Qdrant Cloud (managed)

```
Collection: "user_memories"
├── Vector: 1024 dims (Qwen3-Embedding-0.6B)
├── Payload: { user_id, character_id, fact_type, content, timestamp }
└── Index: user_id filter + vector similarity search
```

### Redis (GalaxyCloud managed)

| Key pattern | Kiểu | TTL | Dùng cho |
|---|---|---|---|
| `session:{user_id}` | Hash | 24h | Character đang chat, affection state |
| `ratelimit:{user_id}:{date}` | Counter | 24h | Đếm tin nhắn/ngày |
| `prompt_cache:{user_id}:{char_id}` | String | 1h | System prompt đã build |
| `online:{user_id}` | String | 5min | Online status |
| `request_queue` | Stream | — | Request queue cho vLLM workers |
| `response:{request_id}` | Pub/Sub | — | Stream tokens về FastAPI |
| `active_requests` | Counter | — | Autoscaler đọc để quyết định scale |

***

## VII. AUTO-SCALING

### Autoscaler — Python script, cronjob 30s

```python
# Logic đơn giản, chạy trên API server hoặc pod riêng
queue_depth    = redis.xlen("request_queue")
active_pods    = runpod.list_pods(name="dokichat-worker")
gpu_util       = prometheus.query("avg(gpu_utilization)")

# Scale UP
if queue_depth > 50 and liên_tục_2_phút:
    runpod.create_pod(template="dokichat-worker", gpu="L40S")

if queue_depth > 200:
    runpod.create_pod(template="dokichat-worker", gpu="L40S", count=2)
    alert_slack("⚠️ Queue > 200, scaling +2 GPU")

# Scale DOWN
if queue_depth < 10 and gpu_util < 20% and liên_tục_15_phút:
    runpod.stop_pod(idle_pod_id)  # Stop để giữ data

if queue_depth == 0 and gpu_util < 10% and liên_tục_30_phút:
    # Shutdown về minimum reserved, không xoá
    shutdown_to_minimum()
```

### GPU theo scale

| Scale | Reserved (24/7) | Warm pool | Auto-scale peak | Tổng min/max |
|---|---|---|---|---|
| 500K | 2 GPU (Template B) | — | +1-3 | 3/5 |
| 1M | 8 GPU (Template B) | — | +0-1 | 9/9 |
| 5M | 15 GPU (Template B) | 5 GPU | +0-25 | 20/45 |
| 10M | 30 GPU (Template B) | 10 GPU | +0-50 | 40/90 |

> Pod 1 (Template A) luôn chạy ở mọi scale — 1 bản duy nhất.

***

## VIII. DEPLOYMENT

### Docker Images

```
Image 1: dokichat-primary
├── Base: vllm/vllm-openai:latest
├── start_primary.sh → 3 vLLM processes + worker
└── Models: mount từ RunPod Network Volume

Image 2: dokichat-worker
├── Base: vllm/vllm-openai:latest
├── start_worker.sh → 2 vLLM processes + worker
└── Models: mount từ RunPod Network Volume

Image 3: dokichat-api
├── Base: python:3.12-slim
├── FastAPI + uvicorn
└── Stateless — scale horizontal
```

### Network Volume (RunPod)

```
/models/
├── qwen3.5-4b-uncensored-safetensors/  (~8 GB BF16)
├── qwen3.5-9b-uncensored-safetensors/  (~18 GB BF16)
└── qwen3-embedding-0.6b/                (~1 GB)
    Tổng: ~27 GB → RunPod Network Volume 30 GB ($6/tháng)
```

> Model weights lưu trên Network Volume → pod restart không cần download lại.

***

## IX. MONITORING

```
vLLM /metrics ──→ Prometheus (15s scrape) ──→ Grafana Cloud
FastAPI metrics ─┘                             ├── Dashboard: GPU health
Redis info ──────┘                             ├── Dashboard: Queue depth + latency
                                               ├── Alert → Slack/Telegram
                                               └── Alert → Autoscaler trigger
```

| Metric | Alert threshold | Action |
|---|---|---|
| TTFT p95 | > 500ms | Investigate |
| Queue depth | > 100 | Scale up |
| GPU util | > 90% | Scale up |
| GPU util | < 20% (15 phút) | Scale down |
| Error rate | > 1% | Alert team |
| Pod health | Unreachable | Auto-restart via RunPod API |

***

## X. MODULES HIỆN CÓ → API MAPPING

| Module hiện tại | File | Dùng ở đâu trong API |
|---|---|---|
| `cerebras_client.py` | LLM client | Đổi URL → vLLM endpoints |
| `prompt_builder.py` | Build prompt | `/api/chat` step (h) |
| `safety_filter.py` | Chặn nội dung | `/api/chat` step (c) |
| `affection_state.py` | Tracking cảm xúc | `/api/chat` step (e) + async |
| `memory/mem0_store.py` | Qdrant memory | `/api/chat` step (f) |
| `memory/fact_extractor.py` | Extract facts | Async step (b) |
| `memory/scene_tracker.py` | Scene context | Async step (c) |
| `emotion.py` | Emotion classify | Async step (d) |
| `intimacy.py` | Intimacy logic | `/api/chat` prompt inject |
| `response_processor.py` | POV fix | `/api/chat` step ④(c) |
| `character_generator.py` | Bio → prompt | `/api/characters/create` |
| `characters/*.py` | Built-in chars | Load vào PostgreSQL lần đầu |

> Logic AI giữ nguyên 100%. Chỉ bọc FastAPI bên ngoài + đổi data source từ JSON/session → PostgreSQL/Redis.

***

*Kiến trúc hệ thống — DokiChat — 10/03/2026*
