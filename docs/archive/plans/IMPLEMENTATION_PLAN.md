# IMPLEMENTATION PLAN — DokiChat Production Backend
### Chuyển từ Streamlit Prototype → FastAPI Production API
### 10/03/2026

***

## Tổng quan

Chuyển đổi codebase hiện tại (Streamlit + LM Studio local) thành production backend API (FastAPI + vLLM + RunPod). Giữ nguyên 100% logic AI, chỉ thay đổi lớp vỏ bọc và data layer.

**Timeline:** ~3 tuần (15 ngày làm việc)
**Team:** 1-2 backend dev

***

## Phase 1: FastAPI Core + LLM Client (Ngày 1-3)

### 1.1 Khởi tạo project structure

```
dokichat-api/
├── app/
│   ├── main.py                  # FastAPI app, CORS, middleware
│   ├── config.py                # Environment variables, URLs
│   ├── routers/
│   │   ├── chat.py              # POST /api/chat (SSE streaming)
│   │   ├── characters.py        # CRUD characters
│   │   ├── auth.py              # Login, JWT
│   │   └── health.py            # Health check
│   ├── services/
│   │   ├── llm_client.py        # ← refactor từ cerebras_client.py
│   │   ├── prompt_builder.py    # ← copy từ prototype
│   │   ├── safety_filter.py     # ← copy từ prototype
│   │   ├── response_processor.py # ← copy từ prototype
│   │   ├── affection.py         # ← refactor từ affection_state.py
│   │   ├── emotion.py           # ← copy từ prototype
│   │   └── intimacy.py          # ← copy từ prototype
│   ├── memory/
│   │   ├── mem0_store.py        # ← copy từ prototype
│   │   ├── fact_extractor.py    # ← copy từ prototype
│   │   ├── scene_tracker.py     # ← copy từ prototype
│   │   └── summarizer.py        # ← copy từ prototype
│   ├── models/
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── database.py          # SQLAlchemy models
│   ├── middleware/
│   │   ├── auth.py              # JWT verification
│   │   └── rate_limit.py        # Redis rate limiter
│   └── workers/
│       ├── vllm_worker.py       # Poll Redis Streams → call vLLM
│       └── autoscaler.py        # Monitor queue → RunPod API
├── characters/                   # ← copy built-in characters
├── tests/
├── Dockerfile.api
├── Dockerfile.primary
├── Dockerfile.worker
├── docker-compose.yml            # Local dev
├── requirements.txt
└── .env.example
```

### 1.2 Refactor LLM client — tách 3 endpoints

**File:** `app/services/llm_client.py`

```python
# Từ cerebras_client.py → tách thành 3 client
CHAT_URL    = os.getenv("VLLM_CHAT_URL", "http://localhost:8001/v1")
CHARGEN_URL = os.getenv("VLLM_CHARGEN_URL", "http://localhost:8000/v1")
EMBED_URL   = os.getenv("VLLM_EMBED_URL", "http://localhost:8002/v1")

chat_client   = OpenAI(base_url=CHAT_URL)
chargen_client = OpenAI(base_url=CHARGEN_URL)
embed_client   = OpenAI(base_url=EMBED_URL)
```

Thay đổi so với hiện tại: chỉ đổi URL, logic gọi API giữ nguyên.

### 1.3 FastAPI app cơ bản + SSE streaming

**File:** `app/routers/chat.py`

```python
@router.post("/api/chat")
async def chat(request: ChatRequest):
    # Build prompt (dùng prompt_builder.py hiện tại)
    # Push Redis Streams
    # Subscribe response channel
    # Return StreamingResponse (SSE)
```

### Deliverable Phase 1:
- [ ] Project structure tạo xong
- [ ] `llm_client.py` 3 endpoints hoạt động
- [ ] `POST /api/chat` trả SSE stream (test với LM Studio local)
- [ ] Copy + verify tất cả AI modules hoạt động trong FastAPI context

***

## Phase 2: PostgreSQL + Data Migration (Ngày 4-6)

### 2.1 Database schema

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    tier VARCHAR(20) DEFAULT 'free',  -- free / premium
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE characters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),  -- NULL = built-in
    name VARCHAR(100) NOT NULL,
    system_prompt TEXT NOT NULL,
    emotional_states JSONB,
    immersion_prompt TEXT,
    immersion_response TEXT,
    opening_scene TEXT,
    is_builtin BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE chat_history (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    character_id UUID REFERENCES characters(id),
    role VARCHAR(10) NOT NULL,  -- 'user' / 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE affection_state (
    user_id UUID REFERENCES users(id),
    character_id UUID REFERENCES characters(id),
    stage VARCHAR(20) DEFAULT 'stranger',
    score FLOAT DEFAULT 0,
    mood VARCHAR(20) DEFAULT 'neutral',
    desire FLOAT DEFAULT 0,
    violation_count INT DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, character_id)
);

-- Indexes
CREATE INDEX idx_chat_history_user_char ON chat_history(user_id, character_id, created_at DESC);
CREATE INDEX idx_affection_user_char ON affection_state(user_id, character_id);
```

### 2.2 Seed built-in characters

```python
# Load Sol, Kael, Seraphine, Ren, Linh Đan từ characters/*.py → INSERT vào PostgreSQL
# Chạy 1 lần khi deploy
```

### 2.3 Refactor services đọc từ DB thay vì session/JSON

| Hiện tại | Thay bằng |
|---|---|
| `st.session_state.messages` | `SELECT FROM chat_history WHERE user_id=... ORDER BY created_at DESC LIMIT 20` |
| `st.session_state.affection` | `SELECT FROM affection_state WHERE user_id=... AND character_id=...` |
| `characters/__init__.py` load dict | `SELECT FROM characters WHERE id=...` |
| `custom_characters/*.json` | `SELECT FROM characters WHERE user_id=... AND is_builtin=false` |

### Deliverable Phase 2:
- [ ] PostgreSQL schema tạo xong
- [ ] SQLAlchemy models
- [ ] Migration script (Alembic)
- [ ] Seed built-in characters
- [ ] Chat history đọc/ghi từ DB
- [ ] Affection state đọc/ghi từ DB

***

## Phase 3: Redis Integration (Ngày 7-8)

### 3.1 Redis connections

```python
# app/config.py
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

redis_client = redis.Redis.from_url(REDIS_URL)
```

### 3.2 Session + Rate Limit

```python
# Rate limit middleware
async def check_rate_limit(user_id: str, tier: str):
    key = f"ratelimit:{user_id}:{date.today()}"
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, 86400)
    limit = 50 if tier == "free" else 500
    if count > limit:
        raise HTTPException(429, "Rate limit exceeded")
```

### 3.3 Redis Streams — Request Queue

```python
# Push request
redis_client.xadd("request_queue", {
    "request_id": request_id,
    "user_id": user_id,
    "prompt": json.dumps(messages),
    "priority": "normal",
    "timestamp": time.time()
})

# Worker poll
messages = redis_client.xreadgroup(
    "workers", f"worker-{pod_id}",
    {"request_queue": ">"},
    count=1, block=5000
)
```

### 3.4 Redis Pub/Sub — Stream response tokens

```python
# Worker publish mỗi token
redis_client.publish(f"response:{request_id}", token)

# FastAPI subscribe + SSE
async def stream_response(request_id: str):
    pubsub = redis_client.pubsub()
    pubsub.subscribe(f"response:{request_id}")
    for message in pubsub.listen():
        if message["type"] == "message":
            token = message["data"].decode()
            if token == "[DONE]":
                break
            yield f"data: {token}\n\n"
```

### Deliverable Phase 3:
- [ ] Redis session/rate limit hoạt động
- [ ] Redis Streams push/poll hoạt động
- [ ] Pub/Sub streaming tokens end-to-end
- [ ] `active_requests` counter cho autoscaler

***

## Phase 4: Auth + API Endpoints hoàn chỉnh (Ngày 9-10)

### 4.1 JWT Auth

```python
# POST /api/auth/login → return JWT
# Middleware verify JWT on all /api/* routes (except /health)
```

### 4.2 Hoàn thiện endpoints

| Endpoint | Logic |
|---|---|
| `POST /api/chat` | Auth → rate limit → safety → build prompt → Redis Streams → SSE |
| `POST /api/characters/create` | Auth → gọi 9B chargen → save DB → return |
| `GET /api/characters` | Auth → query DB → return list |
| `GET /api/characters/{id}` | Auth → query DB → return detail |
| `GET /api/chat/history` | Auth → query DB → return messages |
| `GET /api/user/memory` | Auth → query Qdrant → return facts |
| `GET /api/health` | Return 200 + system status |

### 4.3 Pydantic schemas

```python
class ChatRequest(BaseModel):
    character_id: str
    message: str

class CharacterCreateRequest(BaseModel):
    name: str
    bio: str

class ChatHistoryResponse(BaseModel):
    messages: list[MessageItem]
    total_turns: int
```

### Deliverable Phase 4:
- [ ] JWT login/verify hoạt động
- [ ] Tất cả endpoints hoạt động + Swagger docs tự động
- [ ] Request/response validation Pydantic

***

## Phase 5: vLLM Worker + Docker (Ngày 11-12)

### 5.1 vLLM Worker process

**File:** `app/workers/vllm_worker.py`

```python
# Chạy trên mỗi GPU pod
# Loop: poll Redis Streams → gọi vLLM local → publish tokens
while True:
    messages = redis.xreadgroup(...)
    for msg in messages:
        request_id = msg["request_id"]
        prompt = json.loads(msg["prompt"])
        
        # Gọi vLLM local (localhost:8001)
        stream = openai.ChatCompletion.create(
            base_url="http://localhost:8001/v1",
            messages=prompt,
            stream=True
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content
            redis.publish(f"response:{request_id}", token)
        
        redis.publish(f"response:{request_id}", "[DONE]")
        redis.xack("request_queue", "workers", msg.id)
```

### 5.2 Dockerfiles

**Dockerfile.api** — FastAPI server
```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Dockerfile.primary** — GPU pod (9B + 4B + Embed + Worker)
```dockerfile
FROM vllm/vllm-openai:latest
COPY start_primary.sh /start.sh
COPY app/workers/vllm_worker.py /worker.py
COPY requirements.worker.txt .
RUN pip install -r requirements.worker.txt
CMD ["/start.sh"]
```

**Dockerfile.worker** — GPU pod (4B + Embed + Worker)
```dockerfile
FROM vllm/vllm-openai:latest
COPY start_worker.sh /start.sh
COPY app/workers/vllm_worker.py /worker.py
COPY requirements.worker.txt .
RUN pip install -r requirements.worker.txt
CMD ["/start.sh"]
```

### 5.3 docker-compose.yml cho local dev

```yaml
services:
  api:
    build: { dockerfile: Dockerfile.api }
    ports: ["8080:8080"]
    depends_on: [redis, postgres]
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: dokichat
      POSTGRES_PASSWORD: dev
    ports: ["5432:5432"]
```

> Local dev: vLLM chạy trên LM Studio như hiện tại, FastAPI gọi localhost.

### Deliverable Phase 5:
- [ ] vLLM worker poll + stream hoạt động
- [ ] 3 Dockerfiles build thành công
- [ ] docker-compose local dev chạy end-to-end
- [ ] API test: gửi chat request → nhận SSE stream

***

## Phase 6: RunPod Deploy + Autoscaler (Ngày 13-14)

### 6.1 RunPod setup

```
a. Tạo Network Volume 20GB → upload 3 model weights
b. Tạo Template "dokichat-primary" → Dockerfile.primary
c. Tạo Template "dokichat-worker" → Dockerfile.worker
d. Tạo Pod 1 từ Template A (primary)
e. Tạo Pod 2-3 từ Template B (worker)
f. Verify: curl pod-ip:8001/v1/models → thấy Qwen3.5-4B
```

### 6.2 Autoscaler

**File:** `app/workers/autoscaler.py`

```python
# Cronjob chạy mỗi 30s
queue_depth = redis_client.xlen("request_queue")
active_requests = int(redis_client.get("active_requests") or 0)
pods = runpod_api.list_pods(name="dokichat-worker")

if queue_depth > 50:
    runpod_api.create_pod(template="dokichat-worker", gpu="L40S")
elif queue_depth < 10 and len(pods) > MIN_PODS:
    runpod_api.stop_pod(pods[-1].id)
```

### 6.3 Monitoring

```
a. Grafana Cloud free account
b. Prometheus config scrape vLLM /metrics
c. Dashboard: GPU util, queue depth, TTFT, error rate
d. Alert rules → Slack/Telegram webhook
```

### Deliverable Phase 6:
- [ ] RunPod pods chạy vLLM với 3 models
- [ ] API server kết nối thành công với RunPod pods
- [ ] Autoscaler scale up/down hoạt động
- [ ] Grafana dashboard hiển thị metrics
- [ ] End-to-end test: app gửi request → nhận stream response

***

## Phase 7: Testing + Handoff (Ngày 15)

### 7.1 Integration tests

| Test | Mô tả |
|---|---|
| Chat flow | Gửi 10 tin liên tiếp, verify history + memory update |
| Safety | Gửi nội dung bất hợp pháp, verify bị chặn |
| Character create | Tạo nhân vật mới, verify prompt + emotional states |
| Rate limit | Gửi 51 tin free tier, verify bị chặn |
| Concurrent | 50 request cùng lúc, verify không đá vào nhau |
| Failover | Kill pod, verify autoscaler tạo mới |

### 7.2 API documentation

FastAPI tự generate Swagger UI tại `/docs` — team app đọc trực tiếp.

### 7.3 Handoff cho team app

```
Cung cấp:
├── API base URL
├── Swagger docs URL  
├── Auth flow (login → JWT → header)
├── SSE streaming example code (JS/Swift/Kotlin)
└── Rate limit rules
```

### Deliverable Phase 7:
- [ ] Tất cả tests pass
- [ ] API docs hoàn chỉnh
- [ ] Team app có thể gọi API thành công

***

## Tổng kết Timeline

| Phase | Ngày | Nội dung | Effort |
|---|---|---|---|
| **1** | 1-3 | FastAPI + LLM client + SSE | 3 ngày |
| **2** | 4-6 | PostgreSQL + data migration | 3 ngày |
| **3** | 7-8 | Redis (session, queue, pub/sub) | 2 ngày |
| **4** | 9-10 | Auth + API endpoints | 2 ngày |
| **5** | 11-12 | vLLM worker + Docker | 2 ngày |
| **6** | 13-14 | RunPod deploy + autoscaler + monitoring | 2 ngày |
| **7** | 15 | Testing + handoff | 1 ngày |
| | | **Tổng** | **15 ngày** |

***

## Dependencies

| Cần trước khi bắt đầu | Trạng thái |
|---|---|
| RunPod account + API key | ✅ Đã có |
| PostgreSQL server | ✅ Đã có sẵn |
| Qdrant Cloud account | Cần tạo |
| Redis (GalaxyCloud) account | Cần tạo |
| Docker Hub account (push images) | Cần tạo |
| Grafana Cloud account | Cần tạo (free tier) |
| Domain + SSL cho API | Cần setup |

***

*Implementation Plan — DokiChat Production Backend — 10/03/2026*
