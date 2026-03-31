# DokiChat — AI Companion Platform

Nền tảng AI Companion Chat với nhân vật ảo có **tính cách sâu**, **cảm xúc tiến triển**, **trí nhớ dài hạn**, và **mối quan hệ 8 giai đoạn** — mô phỏng trải nghiệm trò chuyện immersive với nhân vật sống động.

## Kiến trúc Production

```
Mobile/Web ──→ Cloudflare ──→ FastAPI (SSE Streaming)
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼             ▼
              Redis Cache   PostgreSQL    LLM Inference
              (Session,     (Users,       (vLLM / LM Studio)
               Rate Limit)  Messages,
                             Affection)
```

### Zero Server Memory Design

Mọi state được offload ra external services:
- **Redis**: Session (30min TTL), rate limiting (ZSET sliding window), immersion cache
- **PostgreSQL**: Users, conversations, messages, affection states, memories
- **Write-Behind Buffer**: Chat messages được queue rồi batch-flush mỗi 30s — không block user

## Hệ thống Prompt — 4 Layer Context

```
┌─────────────────────────────────────────┐
│ 1. System Prompt (nhân vật + tính cách) │
│ 2. Affection State (mood, desire, bond) │
│ 3. Scene Context (vị trí + hành vi)     │
│ 4. Format Enforcement (60% thoại/40%)   │
├─────────────────────────────────────────┤
│ Immersion Anchor + Conversation Window  │
└─────────────────────────────────────────┘
```

## Affection System — 8 Giai Đoạn Quan Hệ

```
hostile (-100) → distrustful → stranger → acquaintance → friend → close → intimate → bonded (+100)
```

- **Pacing presets**: slow, guarded, normal, warm, fast — mỗi character có tốc độ riêng
- **Stage-gated**: Không thể nhảy giai đoạn, cần đủ turns tại mỗi stage
- **Boundary recovery**: Vi phạm → trust damage → cần nhiều turns rebuild
- **LLM-based extraction**: Phân tích mỗi turn (temperature=0.1) → update state tự động

## Scene Tracker

Phát hiện thay đổi bối cảnh **tức thì** bằng keyword đa ngôn ngữ:

```
Quán bar    →  "ra ngoài"  →  Ngoài trời    →  "ôm"  →  Thân mật
(pha rượu)     (keyword)      (tay run, gió)            (hơi thở, nhịp tim)
```

6 scene types: `bar`, `outside`, `walking`, `home`, `intimate`, `private_room`
Mỗi scene có behavior rules + available props riêng.

## Tạo Nhân Vật (META_PROMPT V3)

Nhập tiểu sử dạng C.AI fields → LLM tự sinh:
- System prompt 18 sections (tính cách, vết thương, push-pull)
- Cảnh mở đầu (sensory-rich)
- Greetings (nhiều variant)
- Trạng thái cảm xúc (neutral, vulnerable, playful, angry...)

5 builtin characters: **Kael**, **Seraphine**, **Ren**, **Linh Đan**, **Sol**

## API Endpoints

### Chat (JWT required)
| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/chat/stream` | SSE streaming chat |
| `GET` | `/chat/history/{char_id}` | Lịch sử chat |
| `GET` | `/chat/state/{char_id}` | Session state |
| `POST` | `/chat/reset/{char_id}` | Reset conversation |
| `POST` | `/chat/regenerate` | Regenerate response |
| `GET` | `/chat/greeting/{char_id}` | Random greeting (public) |

### Auth
| Method | Endpoint | Mô tả |
|---|---|---|
| `POST` | `/auth/register` | Đăng ký email/password |
| `POST` | `/auth/login` | Đăng nhập |
| `POST` | `/auth/refresh` | Rotate refresh token |
| `POST` | `/auth/logout` | Logout (single device) |
| `GET` | `/auth/oauth/{provider}` | OAuth URL (Google/Apple) |

### Character
| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/character/list` | List characters (public) |
| `POST` | `/character/generate-prompt` | Generate system prompt (public) |
| `POST` | `/character/create` | Save character (JWT) |

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| API Framework | **FastAPI** + SSE Streaming (`sse-starlette`) |
| LLM Inference | **vLLM** (production) / **LM Studio** (local dev) |
| Model | **google/gemma-3-4b-it** |
| Session & Cache | **Redis** (Upstash production / local brew) |
| Database | **PostgreSQL** (Neon production / local brew) |
| Auth | **JWT** (access 30min + refresh 7 days) + **OAuth** (Google, Apple) |
| Deployment | **Docker** + **RunPod Serverless** (GPU) |

## Local Development

### Prerequisites
- Python 3.12+
- LM Studio hoặc Ollama (chạy model `gemma-3-4b-it`)
- PostgreSQL (optional — fallback in-memory)
- Redis (optional — fallback in-memory)

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start services (nếu có)
brew services start postgresql@17
brew services start redis
# Hoặc manual: pg_ctl -D ... start / redis-server

# 3. Create database (nếu dùng PostgreSQL)
createdb dokichat
psql dokichat < scripts/migrations/001_init.sql

# 4. Start LM Studio → load gemma-3-4b-it → Start server (port 1234)

# 5. Run API
uvicorn api.main:app --reload --port 8000
```

### Graceful Degradation

| Service | Không có? | Hệ thống vẫn chạy? |
|---|---|---|
| Redis | Session lưu in-memory, skip rate limit | ✅ Có |
| PostgreSQL | Dùng InMemoryRepository | ✅ Có |
| LLM Server | Chat trả lỗi connection | ❌ Cần có |

## Project Structure

```
├── api/                    # FastAPI application
│   ├── main.py             # App entry + lifespan + DB flush worker
│   ├── deps.py             # Session DI, lazy repos
│   ├── schemas.py          # Pydantic models
│   ├── auth.py             # JWT + password hashing
│   ├── oauth.py            # Google/Apple OAuth
│   ├── routes/
│   │   ├── chat.py         # SSE streaming chat
│   │   ├── character.py    # Character CRUD + generation
│   │   ├── auth.py         # Register/login/refresh/logout
│   │   └── user.py         # Profile & settings
│   └── middleware/
│       └── rate_limit.py   # Character generation rate limit
│
├── core/                   # Core engine
│   ├── prompt_engine.py    # 4-layer prompt builder
│   ├── llm_client.py       # OpenAI-compatible adapter
│   ├── redis_client.py     # Session + cache helpers
│   ├── rate_limit.py       # Redis ZSET sliding window
│   ├── db_buffer.py        # Write-behind message queue
│   ├── conversation.py     # Token-aware sliding window
│   ├── safety.py           # Input content filter
│   └── response_processor.py # POV narration fix
│
├── state/                  # State tracking
│   ├── affection.py        # 8-stage relationship + pacing
│   └── scene.py            # Scene detection + behavior rules
│
├── services/               # Business logic
│   ├── chat_service.py     # Chat pipeline orchestrator
│   └── character_service.py # Character management
│
├── db/                     # Data layer
│   ├── database.py         # SQLAlchemy engine + session factory
│   ├── models.py           # 8 ORM tables
│   └── repositories/       # Dual impl (InMemory + Postgres)
│       ├── user_repo.py
│       └── chat_repo.py
│
├── characters/             # Character system
│   ├── kael.py, seraphine.py, ren.py, linh_dan.py, sol.py
│   ├── generator.py        # META_PROMPT V3 pipeline
│   ├── storage.py          # JSON persistence for custom chars
│   └── custom/             # User-generated characters (JSON)
│
├── memory/                 # Memory system (partial — TODO)
│   ├── scene_tracker.py    # ✅ Implemented
│   ├── fact_extractor.py   # ⏳ Stub
│   ├── mem0_store.py       # ⏳ Stub
│   └── summarizer.py       # ⏳ Stub
│
├── config.py               # Central settings (env vars)
├── Dockerfile              # Production container
├── requirements.txt        # Python dependencies
└── scripts/migrations/
    └── 001_init.sql        # Database schema
```
