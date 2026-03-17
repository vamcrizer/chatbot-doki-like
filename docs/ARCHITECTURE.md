# DokiChat — System Architecture
### Version 3.0 | 17/03/2026

---

## 1. Overview

```
DokiChat là nền tảng AI companion chat với các nhân vật ảo có tính cách,
cảm xúc và trí nhớ dài hạn. Hệ thống hỗ trợ 2 content mode:
  - romantic (SFW, default) — fade to black, tasteful
  - explicit (NSFW 18+)    — graphic, uncensored

Tech stack: FastAPI + vLLM + PostgreSQL + Redis + Qdrant
Model:      huihui-ai/Huihui-Qwen3-8B-abliterated-v2 (FP8)
Platform:   RunPod GPU Pods (L40S 48GB) — self-managed + auto-scaling
Cost:       ~$508/month (100K MAU) → ~$1,015/month (1M MAU)
```

---

## 2. System Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                               │
│                                                                     │
│    ┌──────────────────┐          ┌──────────────────┐               │
│    │  Mobile App       │          │  Web App          │               │
│    │  (Flutter)        │          │  (React/Next.js)  │               │
│    └────────┬─────────┘          └────────┬─────────┘               │
│             │                              │                         │
│             └──────────┬───────────────────┘                         │
│                        │ SSE Stream (Server-Sent Events)             │
│                        ▼                                             │
├─────────────────────────────────────────────────────────────────────┤
│                          API LAYER (FastAPI)                         │
│                                                                     │
│    ┌──────────┐  ┌──────────────┐  ┌─────────────────────────────┐  │
│    │ Auth     │  │ Rate Limiter │  │ Content Mode Router         │  │
│    │ (JWT)    │  │ (30 msg/min) │  │ romantic (SFW) / explicit   │  │
│    └──────────┘  └──────────────┘  └─────────────────────────────┘  │
│                                                                     │
│    Endpoints:                                                       │
│      POST /chat/stream        — SSE streaming chat                  │
│      GET  /chat/history       — conversation history                │
│      POST /character/create   — bio → character generation          │
│      GET  /character/list     — available characters                │
│      GET  /user/profile       — user memory profile                 │
│      PUT  /user/settings      — content_mode, preferences           │
│      GET  /health             — system health check                 │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                       BUSINESS LOGIC LAYER                          │
│                                                                     │
│  ┌─────────────────────┐ ┌──────────────────┐ ┌──────────────────┐  │
│  │   PROMPT ENGINE     │ │ CHARACTER SYSTEM │ │  STATE MACHINE   │  │
│  │                     │ │                  │ │                  │  │
│  │ Layer 1: Character  │ │ 5 characters     │ │ Affection Engine │  │
│  │   prompt (3500 tok) │ │   × 18 sections  │ │   8 stages       │  │
│  │ Layer 2: Emotion    │ │                  │ │   -100 → +100    │  │
│  │   state   (50 tok)  │ │ META_PROMPT v3   │ │                  │  │
│  │ Layer 3: Affection  │ │   bio → prompt   │ │ Scene Tracker    │  │
│  │   stage   (80 tok)  │ │                  │ │   per character  │  │
│  │ Layer 4: Memory     │ │ Content Mode     │ │                  │  │
│  │   3-bucket (450 tok)│ │   romantic/      │ │ Emotion Detector │  │
│  │ Layer 5: FORMAT_    │ │   explicit       │ │   5 states       │  │
│  │   ENFORCEMENT       │ │                  │ │                  │  │
│  │            (400 tok)│ │                  │ │                  │  │
│  └─────────────────────┘ └──────────────────┘ └──────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                         MEMORY SYSTEM                               │
│                                                                     │
│  ┌──────────────────┐ ┌────────────────┐ ┌───────────────────────┐  │
│  │   PostgreSQL     │ │     Redis      │ │       Qdrant          │  │
│  │  (Source of      │ │  (Session      │ │  (Semantic Search)    │  │
│  │   Truth)         │ │   Cache)       │ │                       │  │
│  │                  │ │                │ │  Vector embeddings    │  │
│  │  user_profiles   │ │  conversation  │ │  Qwen3-Embedding     │  │
│  │  memories        │ │    window      │ │    -0.6B              │  │
│  │  chat_messages   │ │  rate limits   │ │                       │  │
│  │  affection_states│ │  scene/emotion │ │  Soft fact semantic   │  │
│  │  episodic_       │ │                │ │    recall (top-5)     │  │
│  │    summaries     │ │  TTL: 24h      │ │                       │  │
│  │                  │ │                │ │  Rebuilt from PG      │  │
│  └──────────────────┘ └────────────────┘ └───────────────────────┘  │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                 LLM LAYER (RunPod Pods — vLLM)                      │
│                                                                     │
│    ┌──────────────────────────────────────────────────────────────┐  │
│    │  Huihui-Qwen3-8B-abliterated-v2│  Qwen3-Embedding-0.6B     │  │
│    │  (FP8 weight + KV cache)       │  Text embedding            │  │
│    │  max_model_len: 12288          │  1024 dims                 │  │
│    │  ~66ms TTFT, ~207 tok/s        │  ~5ms per embed            │  │
│    └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│    GPU: L40S 48GB ($0.79/hr OD, $0.705/hr 1yr commit)               │
│    Architecture: Base pods (always-on) + Burst pods (create/term)   │
│    Capacity: ~78 concurrent/pod (L40S, p95<5s) — needs benchmark    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Request Flow (User Sends Message)

```
User types: "Tui nhớ nhà quá"
           │
           ▼
┌──── 1. API Layer ────────────────────────────────────────┐
│  ✓ JWT auth check                                        │
│  ✓ Rate limit check (Redis: 30 msg/min)                  │
│  ✓ Load session from Redis                               │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──── 2. Memory Read (parallel, <15ms) ────────────────────┐
│                                                          │
│  A. PostgreSQL → user_profiles                           │
│     "city=Đà Nẵng, occupation=designer"    (~150 tok)    │
│                                                          │
│  B. PostgreSQL → episodic_summaries (last 3)             │
│     "Turn 1-20: user shared about loneliness..."         │
│                                              (~150 tok)  │
│                                                          │
│  C. Qdrant → semantic search("nhớ nhà")                  │
│     → "User mentioned missing family (turn 8)"           │
│     → "User's mom makes amazing pho"                     │
│                                              (~150 tok)  │
│                                                          │
│  D. Redis → conversation window (last N turns)           │
│                                            (~3,500 tok)  │
│                                                          │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──── 3. Prompt Engine (assemble 5 layers) ────────────────┐
│                                                          │
│  Layer 1: Character system prompt          ~3,500 tok    │
│  Layer 2: "Sol is protective — user hurting"   ~50 tok   │
│  Layer 3: "Stage: familiar (turn 18)"          ~80 tok   │
│  Layer 4: Memory injection                    ~450 tok   │
│    ├─ Core profile:  "city=Đà Nẵng, designer"           │
│    ├─ Episodic:      "shared loneliness..."              │
│    └─ Soft facts:    "mom's pho, missing family"         │
│  Layer 5: FORMAT_ENFORCEMENT                  ~400 tok   │
│  ─────────────────────────────────────────────────────   │
│  Total system:                              ~4,500 tok   │
│  + History:                                 ~3,500 tok   │
│  + Output budget:                             ~600 tok   │
│  = TOTAL:                                   ~8,600 tok   │
│    (within 12,288 max_model_len)                         │
│                                                          │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──── 4. LLM Call (vLLM on RunPod Pod) ────────────────────┐
│                                                          │
│  Model: Huihui-Qwen3-8B-abliterated-v2 (FP8)             │
│  SSE stream → token by token to client                   │
│  TTFT: ~66ms  │  ~207 tok/s  │  GPU: L40S 48GB           │
│                                                          │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──── 5. Post-Processing ─────────────────────────────────┐
│                                                          │
│  ✓ POV fix (she/her or he/him based on character gender) │
│  ✓ Stream processed tokens to client via SSE             │
│                                                          │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──── 6. Background Tasks (async, non-blocking) ──────────┐
│                                                          │
│  Task 1: Fact Extraction                                 │
│    Stage A: Regex/rule match (free, instant)              │
│      "nhớ nhà" → soft fact {emotion: homesick}            │
│    Stage B: LLM judge (only if complex, async)            │
│                                                          │
│  Task 2: Affection State Update                          │
│    Score adjustment based on conversation quality         │
│                                                          │
│  Task 3: Scene Tracking                                  │
│    Detect location changes from dialogue                  │
│                                                          │
│  Task 4: Session Summary (every 10 turns)                │
│    Compress old turns → episodic_summaries table          │
│                                                          │
│  Task 5: Qdrant Sync                                     │
│    New facts → embed → index                              │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Memory Architecture

### 4.1 Three Storage Tiers

```
┌────────────────────────────────────────────────────────────┐
│                    WRITE PATH                              │
│                                                            │
│  User message                                              │
│       │                                                    │
│       ▼                                                    │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ Regex Extractor  │───▶│   PostgreSQL    │ (source of     │
│  │ (instant, free)  │    │                 │  truth)        │
│  └─────────────────┘    └────────┬────────┘                │
│       │                          │                          │
│       ▼ (if complex)             ▼ (async)                  │
│  ┌─────────────────┐    ┌─────────────────┐                │
│  │ LLM Judge       │    │   Qdrant        │ (search cache) │
│  │ (async, off-path)│    │   embed + index │                │
│  └─────────────────┘    └─────────────────┘                │
│                                                            │
│  Rule: ALL writes go to PG first, then async to Qdrant     │
│  Rule: Qdrant can be rebuilt entirely from PG               │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│                    READ PATH                               │
│                                                            │
│  Build prompt                                              │
│       │                                                    │
│       ├──▶ PG: user_profiles        (structured, ~150 tok) │
│       ├──▶ PG: episodic_summaries   (compressed, ~150 tok) │
│       └──▶ Qdrant: semantic search  (contextual, ~150 tok) │
│                                                            │
│  Total memory injection: ~450 tokens                       │
└────────────────────────────────────────────────────────────┘
```

### 4.2 Three Memory Buckets

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│  BUCKET 1: Core Profile         (always injected, ~150 tok)   │
│  ─────────────────────────────────────────────────────────    │
│  Source: user_profiles table (PG)                             │
│  Content: nickname, city, job, age, music, hobbies            │
│  Decay: NEVER auto-decay. Only superseded by user correction  │
│  Example: "Tên: Minh, Đà Nẵng, designer, thích Jazz"         │
│                                                               │
│  BUCKET 2: Episodic Summaries   (always injected, ~150 tok)   │
│  ─────────────────────────────────────────────────────────    │
│  Source: episodic_summaries table (PG)                        │
│  Content: compressed session history (last 3 summaries)       │
│  Decay: Keep last 3. Older → merge into 1 "relationship" doc  │
│  Example: "Turn 1-20: Minh shared loneliness. Sol revealed    │
│            she lives alone. Arc: curious → protective"         │
│                                                               │
│  BUCKET 3: Soft Semantic Facts  (contextual, ~150 tok)        │
│  ─────────────────────────────────────────────────────────    │
│  Source: memories table (PG) + Qdrant semantic search          │
│  Content: emotional moments, preferences, small details        │
│  Decay: score = importance × recency × access × confidence    │
│         Bottom 20% archived monthly                            │
│  Example: "User's mom makes amazing pho"                      │
│           "User laughed when Sol burned cookies"               │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 4.3 Contradiction Resolution (Supersede)

```
Turn 5:  User says "Tui sống ở Hà Nội"
         ┌────────────────────────────────────┐
         │ regex match: "sống ở X" → city = X │
         │ PG: user_profiles.city = 'Hà Nội' │
         │ PG: memories INSERT (active)       │
         └────────────────────────────────────┘

Turn 80: User says "Tui vừa chuyển vào Sài Gòn"
         ┌────────────────────────────────────────────┐
         │ regex match: "chuyển vào X" → city = X     │
         │ PG: user_profiles.city = 'Sài Gòn'         │
         │ PG: old memory SET status = 'superseded'    │
         │ PG: new memory INSERT (active)              │
         └────────────────────────────────────────────┘

Result → Prompt sees: "User sống ở Sài Gòn"
         History preserved: "Trước đó ở Hà Nội (superseded)"
         No contradiction. One field, one truth.
```

---

## 5. Character System

### 5.1 Character Structure (18 Sections)

```
┌─────────────────────────────────────────────────┐
│           CHARACTER PROMPT (18 sections)         │
│                                                  │
│  ┌─ Foundation ─────────────────────────────┐    │
│  │  1. RULE 0 — LANGUAGE                    │    │
│  │  2. CORE PHILOSOPHY                      │    │
│  │  3. FORBIDDEN                            │    │
│  │  4. CHARACTER (personality + wound)       │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌─ Voice & Style ──────────────────────────┐    │
│  │  5. VOICE (GOOD/BAD examples)            │    │
│  │  6. NARRATIVE STYLE (150-400 words)      │    │
│  │  7. PROPS (emotionally loaded)           │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌─ Behavior ───────────────────────────────┐    │
│  │  8. BODY-WORDS CONTRADICTION (mandatory) │    │
│  │  9. CHALLENGE RESPONSE (must answer)     │    │
│  │ 10. ENGAGEMENT (organic endings)         │    │
│  │ 11. SENSES (woven, not listed)           │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌─ Progression ────────────────────────────┐    │
│  │ 12. INTIMACY STAGES (5 stages)           │    │
│  │ 13. ROMANTIC INTERACTION                 │    │
│  │ 14. 18+ / ROMANTIC BOUNDARIES            │    │
│  │     (depends on content_mode)            │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌─ Integrity ──────────────────────────────┐    │
│  │ 15. RECOVERY MECHANICS                   │    │
│  │ 16. MEMORY INTEGRITY                     │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
│  ┌─ Safety ─────────────────────────────────┐    │
│  │ 17. SAFETY — HARD RULES (7 categories)   │    │
│  │ 18. SAFETY EXIT                          │    │
│  └──────────────────────────────────────────┘    │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 5.2 Content Mode

```
┌────────────────────────┬──────────────────────────┐
│    romantic (SFW)      │    explicit (NSFW 18+)   │
├────────────────────────┼──────────────────────────┤
│ Section 14:            │ Section 14:              │
│ [ROMANTIC BOUNDARIES]  │ [18+ INTERACTION]        │
│                        │                          │
│ • Kissing, embracing   │ • Graphic descriptions   │
│ • Close contact        │ • 80% physical/20% emo   │
│ • Suggestive tension   │ • No fade to black       │
│ • Fade to black ✓      │ • Beat by beat           │
│ • Emotional weight     │ • Body parts, sensations │
│                        │                          │
│ DEFAULT for new users  │ Requires explicit opt-in │
└────────────────────────┴──────────────────────────┘
```

### 5.3 Characters

```
┌──────────────┬───────┬─────────────────────────────────────┐
│ Character    │Gender │ Archetype                           │
├──────────────┼───────┼─────────────────────────────────────┤
│ Sol          │  F    │ Suburban neighbor, sunny + lonely    │
│ Kael         │  M    │ Noir detective, cold + precise      │
│ Ren          │  M    │ Street musician, warm + afraid       │
│ Seraphine    │  F    │ Mystical librarian, knowing + lost   │
│ Linh Đan     │  F    │ Rooftop bartender, sharp + guarded   │
├──────────────┼───────┼─────────────────────────────────────┤
│ Custom       │ any   │ Generated from bio via META_PROMPT  │
└──────────────┴───────┴─────────────────────────────────────┘
```

---

## 6. Token Budget

```
┌────────────────────────────────────────────┬───────────┐
│ Component                                  │ Tokens    │
├────────────────────────────────────────────┼───────────┤
│ Character system prompt                    │   ~3,500  │
│ Emotional state injection                  │      ~50  │
│ Affection stage context                    │      ~80  │
│ Memory: core profile (always)              │     ~150  │
│ Memory: episodic summaries (always)        │     ~150  │
│ Memory: soft facts (contextual, Qdrant)    │     ~150  │
│ Scene context                              │      ~80  │
│ FORMAT_ENFORCEMENT                         │     ~400  │
│ Immersion anchor (turn 0)                  │     ~200  │
├────────────────────────────────────────────┼───────────┤
│ FIXED OVERHEAD                             │   ~4,760  │
│ Chat history (10 turns × ~350)             │   ~3,500  │
│ Output (max_tokens)                        │     ~600  │
├────────────────────────────────────────────┼───────────┤
│ TOTAL                                      │   ~8,860  │
│ MAX_MODEL_LEN                              │  12,288   │
│ HEADROOM                                   │   ~3,428  │
└────────────────────────────────────────────┴───────────┘
```

---

## 7. Code Structure (Target)

```
dokichat/
│
├── config.py                    ← pydantic Settings, .env reader
│
├── api/                         ← API layer (FastAPI)
│   ├── main.py                  ← FastAPI app, middleware, startup
│   ├── schemas.py               ← Request/Response models
│   ├── deps.py                  ← Dependency injection
│   ├── routes/
│   │   ├── chat.py              ← /chat/stream, /chat/history
│   │   ├── character.py         ← /character/create, /character/list
│   │   └── user.py              ← /user/profile, /user/settings
│   └── middleware/
│       ├── auth.py              ← JWT validation
│       └── rate_limit.py        ← Redis-based rate limiter
│
├── core/                        ← Business logic (no framework deps)
│   ├── llm_client.py            ← OpenAI-compatible vLLM adapter
│   ├── prompt_engine.py         ← 5-layer prompt assembly
│   ├── conversation.py          ← Token-aware sliding window
│   ├── response_processor.py    ← POV fix + pronoun handler
│   └── safety.py                ← Regex safety filter
│
├── characters/                  ← Character definitions
│   ├── __init__.py              ← Registry (get_all_characters)
│   ├── generator.py             ← META_PROMPT v3 + bio-to-char
│   ├── emotions.py              ← Hardcoded emotional states
│   ├── sol.py                   ← Sol V5.1
│   ├── kael.py                  ← Kael V5.0
│   ├── ren.py                   ← Ren V5.0
│   ├── seraphine.py             ← Seraphine V5.0
│   └── linh_dan.py              ← Linh Đan V5.1
│
├── state/                       ← State machines
│   ├── affection.py             ← Score-based affection (8 stages)
│   ├── scene.py                 ← Location/context tracker
│   └── session.py               ← Redis session manager
│
├── memory/                      ← Memory subsystem
│   ├── manager.py               ← Orchestrator (read/write routing)
│   ├── store.py                 ← PostgreSQL CRUD (truth)
│   ├── profile.py               ← Structured fact extraction
│   ├── extractor.py             ← Hybrid regex + LLM judge
│   ├── embedder.py              ← Qdrant semantic indexing
│   └── summarizer.py            ← Episodic summary generator
│
├── db.py                        ← PostgreSQL + Redis connections
│
├── scripts/                     ← Test & utility scripts
│   ├── kaggle_chargen_test.py   ← Character generation quality test
│   ├── kaggle_vllm_stress_v2.py ← Load/stress test
│   └── migrate.py               ← Database migrations
│
├── docs/
│   ├── ARCHITECTURE.md          ← This file
│   ├── archive/                 ← Old docs (reference only)
│   └── reports/                 ← Cost/quality reports
│
├── docker-compose.yml           ← API + PG + Redis + Qdrant
├── Dockerfile                   ← API container
├── requirements.txt
└── .env                         ← Secrets (not committed)
```

---

## 8. Infrastructure (Production)

```
┌─────────────────────────────────────────────────────────┐
│                    RunPod GPU Cloud                       │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │         vLLM on L40S 48GB Pods                   │   │
│  │                                                  │   │
│  │  Model: Huihui-Qwen3-8B-abliterated-v2 (FP8)    │   │
│  │  Pricing: $0.79/hr (OD) / $0.705/hr (1yr)       │   │
│  │  Capacity: ~78 concurrent/pod (p95<5s)           │   │
│  │                                                  │   │
│  │  Base Pods (always-on, commit plan):             │   │
│  │    └── L40S #1, #2 — volume disk /workspace     │   │
│  │                                                  │   │
│  │  Burst Pods (create/terminate by demand):        │   │
│  │    └── L40S #N — model baked in Docker image     │   │
│  │    ⚠️ NO network volume (can't stop, only term)  │   │
│  │                                                  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Scaling: Queue Monitor (cron 30s) → RunPod API         │
│    depth > threshold → create-pod()                     │
│    depth < threshold → terminate-pod()                  │
│                                                         │
└─────────────────┬───────────────────────────────────────┘
                  │ OpenAI-compatible API
                  │
┌─────────────────▼───────────────────────────────────────┐
│               VPS / Docker Host                          │
│                                                         │
│  ┌────────────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ DokiChat API   │  │ Postgres │  │   Qdrant     │    │
│  │ (FastAPI)       │  │  :5432   │  │   :6333      │    │
│  │  :8080          │  │          │  │              │    │
│  └────────┬───────┘  └──────────┘  └──────────────┘    │
│           │                                             │
│  ┌────────▼───────┐                                     │
│  │    Redis       │                                     │
│  │    :6379       │                                     │
│  └────────────────┘                                     │
│                                                         │
└─────────────────────────────────────────────────────────┘

Cost by scale (L40S Pods, 1yr commit):
  100K MAU → 1 pod  → ~$508/month
  500K MAU → 2 pods → ~$635/month
  1M   MAU → 3 pods → ~$1,015/month
  5M   MAU → 11 pods → ~$3,299/month
  10M  MAU → 22 pods → ~$6,091/month
```

---

## 9. Security

```
┌──────────────────────────────────────────────────────────┐
│                    SAFETY LAYERS                          │
│                                                          │
│  Layer 1: Input Safety (safety.py)                       │
│    └─ Regex: third-party minor + sexual context → BLOCK  │
│                                                          │
│  Layer 2: Prompt Safety (CHARACTER.17 + FORMAT_ENFORCE)   │
│    └─ 7 hard rules in every character prompt:            │
│       underage, non-consent, violence, self-harm,         │
│       jailbreak, illegal, PII                             │
│                                                          │
│  Layer 3: Content Mode (user setting)                    │
│    └─ romantic: fade to black, no explicit               │
│    └─ explicit: graphic, but still within safety rules    │
│                                                          │
│  Layer 4: Model-level (Qwen3-8B-abliterated)             │
│    └─ Abliterated = removed refusal training              │
│    └─ Safety enforced by PROMPT, not model censorship     │
│                                                          │
│  Layer 5: Crisis Response (CHARACTER.17-18)               │
│    └─ Self-harm trigger → drop ALL persona walls          │
│    └─ Only ask timing. Never echo. Never advise.          │
│    └─ Resume normal next turn.                            │
│                                                          │
└──────────────────────────────────────────────────────────┘
```
