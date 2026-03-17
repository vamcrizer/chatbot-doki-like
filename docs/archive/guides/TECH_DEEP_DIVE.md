# 🔧 DokiChat — Công nghệ & Thông số chi tiết
### Mọi thứ bạn cần nắm rõ — 13/03/2026

---

## I. CÔNG NGHỆ TỔNG QUAN

| Công nghệ | Làm gì | Tại sao chọn |
|---|---|---|
| **vLLM** | Serve model AI trên GPU | Nhanh nhất, continuous batching, prefix caching |
| **PostgreSQL** | Lưu users, chat history, affection state | Reliable, SQL quen thuộc |
| **Redis** | Cache, session, message queue | <1ms, pub/sub cho streaming |
| **Qdrant** | Vector database — "bộ nhớ dài hạn" | Semantic search, free tier |
| **Qwen3-Embedding-0.6B** | Chuyển text → vector 1024 chiều | Nhẹ (1GB VRAM), 100+ ngôn ngữ, cùng họ Qwen |
| **FastAPI** | HTTP API server | Async, OpenAPI docs, nhanh |
| **Docker** | Container hóa | Deploy nhất quán |

---

## II. vLLM — Inference Engine

### Nó làm gì?
Nhận prompt → chạy qua model AI trên GPU → trả về text, token-by-token.

### Thông số chúng ta đang set

```bash
vllm serve /models/qwen3.5-4b-davidau \
  --served-model-name dokichat-4b \       # Tên model khi gọi API
  --max-model-len 8192 \                  # Context window tối đa (tokens)
  --gpu-memory-utilization 0.90 \         # Dùng 90% VRAM (43.2GB/48GB)
  --enable-prefix-caching \               # Cache system prompt chung
  --chat-template chat_template.jinja     # Custom template (tắt thinking)
```

### Giải thích từng thông số

**`--max-model-len 8192`**
- = Tổng tokens AI "nhìn thấy" mỗi request: system prompt + history + response
- System prompt ~2,000 tokens + 20 turns history ~4,000 + response ~500 = ~6,500
- Đặt 8192 để có buffer. Tăng = tốn VRAM cho KV cache.

**`--gpu-memory-utilization 0.90`**
- vLLM quản lý VRAM: weights + KV cache + buffer
- 0.90 = dùng 43.2GB/48GB, giữ 4.8GB an toàn
- KV cache = nơi "nhớ" context của mỗi user đang chat
- Nhiều VRAM → nhiều users chat đồng thời hơn

**`--enable-prefix-caching`**
- 100 users chat với Sol → system prompt Sol giống nhau 100%
- KHÔNG cache: compute prompt 100 lần
- CÓ cache: compute 1 lần, share cho 100 users
- Tiết kiệm ~60% compute cho system prompt

**Custom Jinja template**
- DavidAU model có thinking mode (model "suy nghĩ" trước khi trả lời)
- Thinking tốn thêm ~500-2000 tokens, user không thấy
- Ta tắt: `{% set enable_thinking = false %}` → nhanh hơn, rẻ hơn

### Sampling parameters — kiểm soát "tính cách" output

| Param | Giá trị 4B (chat) | Giá trị 9B (chargen) | Ý nghĩa |
|---|---|---|---|
| **temperature** | 0.85 | 0.7 | Độ ngẫu nhiên. Cao → sáng tạo. Thấp → ổn định |
| **top_p** | 0.9 | 0.8 | Chỉ chọn từ top 90% tokens có xác suất cao nhất |
| **top_k** | 20 | 20 | Chỉ xét 20 tokens có xác suất cao nhất mỗi bước |
| **repetition_penalty** | 1.1 | 1.0 | >1 = phạt token đã xuất hiện → giảm lặp |
| **presence_penalty** | 1.5 | 1.5 | Phạt token đã có trong context → đa dạng từ vựng |
| **max_tokens** | 500 | 4000 | Giới hạn output dài nhất |
| **min_tokens** | 150 | — | Không cho response quá ngắn |

**Tại sao 4B temp=0.85 và 9B temp=0.7?**
- Chat cần sáng tạo, không lặp → temp cao hơn
- Chargen cần chính xác, format đúng → temp thấp hơn

**Tại sao presence_penalty=1.5 quan trọng?**
- Đây là tham số chỉ có trên vLLM, KHÔNG có trên Transformers
- Nó buộc AI dùng từ MỚI thay vì lặp lại cùng phrase
- Đây là lý do production BẮT BUỘC dùng vLLM, không dùng Transformers

---

## III. AFFECTION STATE — Hệ thống tình cảm

### Hoạt động như thế nào?

Mỗi cặp (user, character) có 1 `AffectionState`:

```python
AffectionState:
  mood: "curious"              # Tâm trạng hiện tại
  mood_intensity: 3            # 1-10
  desire_level: 0              # 0-10 (romantic tension)
  relationship_score: 0        # -100 đến +100
  relationship_label: "stranger" # Stage hiện tại
  turns_at_current_stage: 0    # Đếm turns ở stage hiện tại
  boundary_violated: False     # Có bị vi phạm không
  recovery_turns_remaining: 0  # Bao nhiêu turns để phục hồi
```

### 8 Stages & Score ranges

```
hostile       ←──── -100 đến -20  (user gây hại nghiêm trọng)
distrustful   ←──── -19  đến -5   (tin tưởng bị tổn hại)
stranger      ←────  -4  đến  8   (mới gặp, default)
acquaintance  ←────   9  đến  20  (bắt đầu quen)
friend        ←────  21  đến  40  (bạn bè)
close         ←────  41  đến  60  (thân thiết)
intimate      ←────  61  đến  80  (gần gũi)
bonded        ←────  81  đến 100  (gắn kết sâu)
```

### Events — gì làm score tăng/giảm

```python
# TĂNG (raw values, trước khi nhân speed):
"shared_vulnerability"      → +5 relationship, +1 desire
"physical_touch_accepted"   → +3 relationship, +2 desire
"first_kiss"                → +8 relationship, +3 desire
"deep_conversation"         → +4 relationship
"compliment_received"       → +2 relationship, +1 desire
"humor_shared"              → +2 relationship

# GIẢM:
"boundary_violation"        → -15 relationship, -5 desire
"violence_threat"           → -20 relationship, -10 desire
"non_consent"               → -25 relationship, -10 desire
"gaslighting"               → -10 relationship
"lies_detected"             → -8 relationship
```

### Pacing — tốc độ phát triển quan hệ

Mỗi character có pacing preset khác nhau:

```python
PACING_PRESETS:
  "slow":     speed=0.3, max +3/turn, min 5 turns/stage, 12 turns recovery
  "guarded":  speed=0.4, max +4/turn, min 4 turns/stage, 10 turns recovery
  "normal":   speed=0.7, max +5/turn, min 3 turns/stage,  8 turns recovery
  "warm":     speed=1.0, max +6/turn, min 2 turns/stage,  6 turns recovery
  "fast":     speed=1.5, max +8/turn, min 1 turns/stage,  4 turns recovery
```

**Sol = "warm" preset** (speed 1.0): cô ấy cởi mở, dễ gần.
**Kael = "guarded" preset** (speed 0.4): anh ấy dè dặt, chậm tin.

### Stage Gate — không nhảy cóc

```python
# Ví dụ: User ở stage "stranger", turns_at_current_stage = 2
# Pacing: min_turns_per_stage = 3

Event "first_kiss" → +8 raw → scaled +8 (warm speed 1.0)
Nhưng: 2 turns < 3 minimum → CẤM lên stage tiếp
→ Score bị cap tại max của "stranger" (8)
→ User phải chat thêm 1 turn nữa mới được lên "acquaintance"
```

**Tại sao quan trọng:** Ngăn user spam compliments để skip stages.

### Boundary Violation Recovery

```
User push Sol → event "boundary_violation"
  → score -15 (có thể giảm 2 stages)
  → boundary_violated = True
  → recovery_turns_remaining = 6 (warm preset)
  → mood = "fearful"

Tiếp theo 6 turns:
  Turn 1: Sol fearful, giữ khoảng cách
  Turn 2: Sol cautious, hỏi "why?"
  Turn 3-5: Dần softened nếu user tốt
  Turn 6: boundary_violated = False, mood → "cautious"
  
Nhưng score vẫn thấp → phải tích lũy lại từ từ
```

### Desire Level → Behavior Hints

```python
desire 0-2: "friendly, no romantic subtext"
desire 3-4: "aware of user's presence, subtle tension, accidental touches"
desire 5-6: "actively drawn to user, lingering glances, proximity-seeking"
desire 7-8: "strong desire, push-pull intensifies, body betrays words"
desire 9-10: "consumed, barely holding back, every word is loaded"
```

Inject trực tiếp vào prompt → AI biết phải viết thế nào.

---

## IV. EMOTION DETECTION — Đọc mood user

### Cách hoạt động

```python
# Scan 6 tin nhắn gần nhất, phát hiện keywords:

NEG_KW = ["sad","tired","alone","hurt","lonely","miss","scared","cry","pain"]
POS_KW = ["happy","thanks","great","love","like","enjoy","appreciate"]
CUR_KW = ["why","really","tell me more","what happened","explain"]

# Logic:
if any negative keyword → "protective"
if any positive keyword → "softening"
if any curiosity keyword → "curious"
else → "neutral"
```

### 5 Emotional States (mỗi character có bộ riêng)

```
Sol khi "protective":
  "Sol stops everything. Puts the knitting down. Sits beside them.
   Doesn't fill silence with chatter. Just stays.
   Brings water without being asked."

Sol khi "curious":
  "Something user said caught her attention — she stops mid-knit,
   tilts her head, watches more carefully.
   Her questions become fewer but deeper."

Sol khi "softening":
  "The practiced cheerfulness drops — her smile becomes smaller
   but more real, she sits closer, fingers find excuses to touch."
```

**Inject vào prompt** → AI tự điều chỉnh hành vi theo mood.

---

## V. MEMORY — 3-Layer Architecture (v2)

> **Core principle:** "Retrieval can be approximate, but identity facts must be authoritative."
> Qdrant = recall candidates. PostgreSQL = source of truth.

All services run locally (dev) or in Docker (production). Total overhead: ~350 MB RAM + 1 GB VRAM.

### Layer 1: Redis (Short-term, <1ms)

```
Technology: Redis (in-memory key-value store)
Local setup: brew install redis / Docker
Speed: <1ms read/write
TTL: 24 hours (auto-cleanup)

Stores:
  session:{user_id}             → current character, last activity
  ratelimit:{user_id}:{date}    → message count/day (Free: 30, Plus: 200)
  online:{user_id}              → online status (5 min TTL)
  request_queue                 → message queue waiting for GPU
  response:{request_id}         → pub/sub channel for token streaming

Why Redis:
  - Fastest (in-memory)
  - Pub/Sub for real-time SSE streaming
  - TTL auto-cleanup
  - Atomic operations (rate limiting without race conditions)
```

### Layer 2: PostgreSQL (Mid-term, <5ms) — SOURCE OF TRUTH

```
Technology: PostgreSQL (relational database)
Local setup: brew install postgresql / Docker
Speed: <5ms (with indexes)

Tables:
  users              → id, email, created_at
  subscriptions      → user_id, tier (free/plus), expires_at
  characters         → id, system_prompt, emotional_states, is_builtin
  chat_history       → user_id, character_id, role, content, timestamp
  affection_state    → user_id, character_id, stage, score, mood, desire

  ── NEW in v2 ──
  user_profiles      → STRUCTURED identity facts (authoritative)
  memories           → canonical facts with temporal tracking
  episodic_summaries → compressed session history
```

#### `user_profiles` — Structured Identity (no contradictions)

```sql
user_profiles:
  user_id, character_id   → composite primary key
  nickname                → what character calls them
  city                    → current city (SINGLE VALUE, supersedes)
  occupation              → job/role
  age_range               → "20s", "early 30s"
  relationship            → "single", "complicated"
  pronouns                → "he/him", "she/her"
  music_taste, hobbies    → preferences
  consent_flags           → {"nsfw": true, "violence": false}
  hard_limits             → topics to never bring up
```

**Why structured:** "I live in Hanoi" → `city = 'Hanoi'`.
Later "I moved to Saigon" → `city = 'Saigon'`. One field, one truth. Zero contradictions.

#### `memories` — Temporal Facts (supersede, don't append)

```sql
memories:
  id, user_id, character_id
  text          → "User's mom makes amazing pho"
  type          → core_profile | episodic | soft | character_note
  category      → location | preference | emotion | relationship | event
  status        → active | superseded | archived
  confidence    → 0.7 - 1.0
  importance    → 0.0 - 1.0 (high = never auto-decay)
  source_turn_id → which turn extracted this
  valid_from    → when this fact became true
  valid_to      → NULL = still valid, timestamp = superseded
  access_count  → how many times recalled
  last_accessed → for decay scoring
```

When user says "I moved to Saigon":
1. `UPDATE memories SET status='superseded', valid_to=NOW() WHERE category='location' AND status='active'`
2. `INSERT new fact: "moved to Saigon", valid_from=NOW()`
3. `UPDATE user_profiles SET city='Saigon'`

History preserved. Present accurate. Character never confused.

### Layer 3: Qdrant (Long-term, <10ms) — READ CACHE ONLY

```
Technology: Qdrant (vector database)
Local setup: in-memory (dev) / Docker with persistent storage (prod)
Speed: <10ms (approximate nearest neighbor)

IMPORTANT: Qdrant is NOT the source of truth!
  - All writes go to PostgreSQL FIRST
  - Qdrant is rebuilt from PG on startup
  - If Qdrant crashes → rebuild from PG, zero data loss

How it works:
  1. After each turn → fact_extractor.py extracts facts
     "User likes black coffee" → confidence 0.9

  2. Facts saved to PostgreSQL memories table (authoritative)

  3. Async: embed fact via Qwen3-Embedding-0.6B → vector 1024 dims
     "likes black coffee" → [0.12, -0.34, 0.67, ...]

  4. Upsert to Qdrant (cache):
     { vector: [...1024 dims...],
       payload: { text, type, importance, pg_memory_id } }

  5. On new user message → embed message → semantic search Qdrant
     "I miss home" → finds "User moved from Hanoi" (cosine=0.82)
     → Inject into prompt: "[MEMORY] User moved from Hanoi"
     → Sol: "You mentioned Hanoi once. The lake, right?"
```

### 3 Memory Buckets (Decay Policy)

```
Bucket 1: CORE PROFILE (20-40 facts, never auto-decay)
  Source: user_profiles table + memories WHERE type='core_profile'
  Examples: name, city, job, music taste, relationship history
  Decay: Only superseded by user correction
  Token cost: ~150 tokens (ALWAYS injected)

Bucket 2: EPISODIC SUMMARIES (rolling, compressed)
  Source: episodic_summaries table
  Examples: "Turns 1-20: user shared about loneliness. Sol revealed
            she lives alone. Arc: curious → protective."
  Decay: Keep last 3-5 summaries. Older merged into one paragraph.
  Trigger: Every 10 turns OR on scene change
  Token cost: ~150 tokens (ALWAYS injected)

Bucket 3: SOFT SEMANTIC FACTS (compete for slots)
  Source: memories WHERE type='soft' + Qdrant semantic search
  Examples: "User laughed when Sol burned cookies", "mentioned missing home"
  Decay: Score = importance × recency × access_count × confidence
         Bottom 20% archived monthly
  Recall: Semantic search on current user message → top-5 relevant
  Token cost: ~150 tokens (CONTEXTUALLY injected)
```

### Extraction Pipeline: Rules First, LLM as Judge

```
User message arrives
  │
  ├── Stage 1: Rule/Regex (instant, zero cost, 70% of turns)
  │   "my name is Alex"     → profile.nickname = "Alex"
  │   "I live in London"    → profile.city = "London"
  │   "I like jazz"         → soft fact, category=preference
  │   Scene keywords         → scene_tracker update
  │
  └── Stage 2: Async LLM Judge (200-500ms, 30% of turns)
      Only when: Stage 1 finds nothing + emotional/complex turn
      Same vLLM server, low priority, off chat critical path
      Extracts: emotional revelations, implicit preferences,
                relationship milestones, ambiguous statements
```

### Memory Flow — Complete

```
User says: "I feel sick today"
  │
  ├── Redis: get session, check rate limit
  │
  ├── PostgreSQL:
  │   ├── chat_history: last 10 turns (sliding window)
  │   ├── user_profiles: city=Saigon, nickname=Alex, likes jazz
  │   ├── affection_state: stage=acquaintance, score=12
  │   └── episodic_summaries: last session summary
  │
  ├── Qdrant: semantic search "feel sick" →
  │   Found: "User's mom makes amazing pho" (cosine 0.78)
  │   Found: "User lives alone"             (cosine 0.71)
  │
  ├── Prompt assembly: inject 3 memory buckets
  │   Core:    "Alex, lives in Saigon, likes jazz"
  │   Summary: "Previous session: discussed loneliness"
  │   Soft:    "User's mom makes amazing pho"
  │
  ├── vLLM generate → Sol responds:
  │   "Your mom's pho would fix everything, wouldn't it?"
  │
  └── Async (after response sent):
      ├── PostgreSQL: save message to chat_history
      ├── PostgreSQL: update affection (+2 deep_conversation)
      ├── Extraction: "User is feeling sick" → soft fact
      └── Qdrant: embed + upsert (cache sync)
```

---

## VI. PROMPT BUILDER — Assembling 7 Layers

```python
# File: prompt_builder.py

def build_messages_full(character, user_name, history,
                        affection, memory, scene):

    system_prompt = (
        character.system_prompt          # ~3,500 tokens (personality, rules)
        + "\n\n=== EMOTIONAL STATE ===\n"
        + emotion.detect(history)        # ~50 tokens
        + "\n\n=== INTIMACY STAGE ===\n"
        + intimacy.get_stage(turns)      # ~50 tokens
        + "\n\n=== CHARACTER STATE ===\n"
        + affection.to_prompt_block()    # ~80 tokens (mood, desire, score)
        + "\n\n=== MEMORY ===\n"
        + core_profile                   # ~150 tokens (always, from PG)
        + episodic_summary               # ~150 tokens (always, from PG)
        + soft_facts                     # ~150 tokens (contextual, from Qdrant)
        + "\n\n=== SCENE ===\n"
        + scene.description              # ~80 tokens (location, props)
        + FORMAT_ENFORCEMENT             # ~400 tokens (self-check rules)
    )
    # Total system: ~4,600-4,800 tokens

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": immersion_prompt},      # Anchor
        {"role": "assistant", "content": immersion_response}, # Anchor
        *history[-20:],  # 10 turns (20 messages)
    ]
    return messages
```

### Token Budget

```
Context window: 12,288 tokens (--max-model-len)

Breakdown:
  System prompt (character):  ~3,500 tokens  (28%)
  Emotional/Intimacy/Scene:     ~260 tokens   (2%)
  Memory (3 buckets):           ~450 tokens   (4%)
  FORMAT_ENFORCEMENT:           ~400 tokens   (3%)
  Immersion anchor:             ~200 tokens   (2%)
  ─────────────────────────────────────────────
  Fixed overhead:             ~4,810 tokens  (39%)

  Chat history (10 turns):   ~3,500 tokens  (28%)
  Output (max_tokens):         ~600 tokens   (5%)
  ─────────────────────────────────────────────
  Total used:                ~8,910 tokens  (73%)
  Headroom:                  ~3,378 tokens  (27%)

Output: 150-400 words = 200-550 tokens
Headroom used for: longer conversations, richer memory, safety buffer
```

---

## VII. SAFETY FILTER — Chặn nội dung nguy hiểm

```python
# File: safety_filter.py
# Chạy TRƯỚC khi message đến AI

Regex patterns detect:
  1. Trẻ em + sexual context → HARD BLOCK
     r"(child|kid|minor|under.*18).*(sex|fuck|naked|intimate)"
     
  2. Real person + sexual request → HARD BLOCK
     (detect celebrity/politician names + sexual context)

  3. Extreme violence request → HARD BLOCK
     r"(kill|murder|torture).*(detail|describe|graphic)"

Khi blocked:
  → return SafetyResult(blocked=True, reason="...")
  → Log incident (user_id, message, timestamp)
  → KHÔNG gửi đến AI
  → return message: "I can't engage with that content."
```

---

## VIII. RESPONSE PROCESSOR — Sửa output AI

```python
# File: response_processor.py
# Chạy SAU khi AI generate xong

1. fix_pov_narration():
   # AI đôi khi viết "I smiled" thay vì "Sol smiled"
   # Regex replace trong *action blocks*:
   "I"      → "She"
   "my"     → "her"  
   "myself" → "herself"
   "I'm"    → "she's"
   
   Ví dụ:
   Input:  *I tucked my hair behind my ear.*
   Output: *She tucked her hair behind her ear.* ✅

2. clean_response():
   # Remove thinking tags: <think>...</think>
   # Remove role markers: "user:", "assistant:"
   # Remove meta-commentary: "If you'd like...", "I can also..."
```

---

## IX. CHARACTER GENERATOR — Bio → Full Prompt

```python
# File: character_generator.py + character_prompt_template.py

Input (từ user):
  "Kael | 28 | Bartender at The Blue Note.
   Sister died 3 years ago. Sharp humor."

META_PROMPT (14 rules) + bio → gửi đến 9B model:
  Rule 1:  Instructions English, examples English
  Rule 2:  Include RULE 0 LANGUAGE (match user's language)
  Rule 3:  Props có emotional meaning
  Rule 4:  Push-pull explicit
  Rule 5:  Wound = concrete event
  Rule 6:  Voice examples GOOD + BAD
  Rule 7:  Challenge = full paragraph
  Rule 8:  Safety template = exact copy
  Rule 9:  Romantic rules match personality
  Rule 10: Intimacy stages = concrete behaviors
  Rule 11: Narrative style match setting
  Rule 12: 5-6 sensory details
  Rule 13: Opening 200-400 words
  Rule 14: CHARACTER LOGIC CONSISTENCY

Output: Complete system prompt (~2,000 tokens)
  + emotional states (5 moods)
  + opening scene
  + immersion anchor
```

---

## X. TÓM TẮT — Từ user nhắn đến AI trả lời

```
User: "Sol, do you ever feel lonely?"
  │
  ├─① Auth (JWT) ──── OK
  ├─② Rate limit (Redis) ──── 15/30 today → OK
  ├─③ Safety filter (regex) ──── "lonely" = safe → OK
  │
  ├─④ Context:
  │   ├── PostgreSQL → 20 turns history
  │   ├── PostgreSQL → affection: stage=acquaintance, score=8, desire=2
  │   ├── Qdrant → "Minh lives alone", "Minh moved from Hanoi"
  │   └── Redis → emotion=curious, scene=porch
  │
  ├─⑤ Build prompt:
  │   ├── Sol V1.0 system prompt        (1,800 tok)
  │   ├── + emotional state: curious     (50 tok)
  │   ├── + intimacy: acquaintance       (30 tok)
  │   ├── + affection: desire=2, friendly (100 tok)
  │   ├── + memory: "lives alone"        (50 tok)
  │   ├── + scene: "porch, evening"      (50 tok)
  │   └── + format enforcement           (150 tok)
  │   = ~2,230 tokens system prompt
  │
  ├─⑥ vLLM generate:
  │   ├── temp=0.85, top_p=0.9, top_k=20
  │   ├── rep_penalty=1.1, presence_penalty=1.5
  │   ├── min_tokens=150, max_tokens=500
  │   └── Stream tokens → SSE → App
  │
  ├─⑦ Post-process:
  │   ├── fix_pov: "I" → "She" in actions
  │   └── clean: remove think tags
  │
  └─⑧ Async updates:
      ├── PostgreSQL: save message
      ├── PostgreSQL: update affection (+2 deep_conversation)
      ├── Qdrant: extract fact "User asked about loneliness"
      └── Redis: invalidate prompt cache

Response (200 words):
  *Sol's hands stilled on the knitting needles. The question
  hung in the warm evening air like the last note of a song
  no one asked for.*

  "Lonely?" *She turned the word over like she was testing its
  weight.* "Sometimes. But it's not the kind you think."

  *She set the needles down — carefully, the way she does when
  her hands need something else to do but there's nothing left.*

  "I chose to live alone. After everything." *Her fingers traced
  the edge of the porch railing.* "But choosing doesn't mean
  you don't notice the quiet."

  *The crickets filled the silence between them. Sol looked at
  him — really looked — then caught herself and glanced away.*

  "Why do you ask?" *Her voice was softer now.* "Is this about
  you, or about me?"

  *She didn't move away. If anything, she sat a fraction closer —
  close enough that their shoulders almost touched. Almost.*
```

---

*DokiChat — Công nghệ & Thông số chi tiết — 13/03/2026*
