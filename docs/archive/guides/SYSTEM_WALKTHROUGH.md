# 🧠 DokiChat — Hiểu toàn bộ hệ thống
### Hướng dẫn kiến trúc, chức năng & cách hoạt động — 13/03/2026

---

## Mục lục

1. [Tổng quan: DokiChat làm gì?](#i)
2. [Kiến trúc tổng thể](#ii)
3. [Luồng xử lý khi user nhắn tin](#iii)
4. [6 tầng AI tạo nên phản hồi thông minh](#iv)
5. [Hệ thống bộ nhớ 3 lớp](#v)
6. [Tạo nhân vật tự động](#vi)
7. [An toàn & Bảo vệ](#vii)
8. [Code modules & liên kết](#viii)
9. [Tài liệu đã có](#ix)

---

<a id="i"></a>
## I. Tổng quan: DokiChat làm gì?

DokiChat là **AI companion chatbot** — ứng dụng chat 1:1 với nhân vật AI có tính cách,
cảm xúc, và trí nhớ. Giống Replika/Character.AI nhưng:

- **Self-hosted** — không phụ thuộc API bên thứ 3
- **Uncensored 18+** — hỗ trợ romantic/intimate interactions
- **Off-the-shelf models** — không cần fine-tune, không cần dataset
- **Chi phí thấp** — self-host tiết kiệm 4-10× so với dùng API

**Sản phẩm cuối cùng:** Mobile/web app → user chọn nhân vật → chat → AI nhớ bạn,
phát triển mối quan hệ qua thời gian, từ stranger → bonded.

---

<a id="ii"></a>
## II. Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────┐
│                     USER DEVICE                          │
│              (Mobile App / Web Browser)                   │
└──────────────────┬───────────────────────────────────────┘
                   │ HTTPS
                   ▼
┌──────────────────────────────────────────────────────────┐
│                   API LAYER                              │
│                                                          │
│  ┌─────────┐  ┌──────────┐  ┌────────────┐              │
│  │  Auth    │  │  Rate    │  │  Safety    │              │
│  │  (JWT)   │→ │  Limiter │→ │  Filter   │              │
│  └─────────┘  └──────────┘  └─────┬──────┘              │
│                                   │                      │
│  ┌────────────────────────────────▼──────────────────┐   │
│  │              PROMPT BUILDER                       │   │
│  │  Character prompt + Emotion + Intimacy + Memory   │   │
│  │  + Scene context + Format enforcement             │   │
│  └─────────────────────┬─────────────────────────────┘   │
│                        │                                 │
│  FastAPI (stateless, scale horizontal)                   │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP → vLLM API
                         ▼
┌──────────────────────────────────────────────────────────┐
│                   GPU LAYER (RunPod)                      │
│                                                          │
│  ┌─────────────────────────────────────────────┐         │
│  │  vLLM Server                                │         │
│  │  ├── 4B DavidAU (chat)        → port 8000   │         │
│  │  ├── 9B DavidAU (chargen)     → port 8001   │         │
│  │  └── Qwen3-Embed-0.6B         → port 8002   │         │
│  └─────────────────────────────────────────────┘         │
│  L40S 48GB VRAM                                          │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                   DATA LAYER                             │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐              │
│  │PostgreSQL│  │  Redis   │  │  Qdrant   │              │
│  │(history, │  │(session, │  │(semantic  │              │
│  │ state,   │  │ cache,   │  │ memory,   │              │
│  │ users)   │  │ queue)   │  │ facts)    │              │
│  └──────────┘  └──────────┘  └───────────┘              │
└──────────────────────────────────────────────────────────┘
```

**3 layers, mỗi layer scale độc lập:**
- **API Layer:** FastAPI, stateless → thêm instance khi cần
- **GPU Layer:** vLLM trên RunPod → thêm pod khi cần
- **Data Layer:** Managed services → tăng tier khi cần

---

<a id="iii"></a>
## III. Luồng xử lý khi user nhắn tin

User gửi: *"Sol, do you ever feel lonely?"*

```
BƯỚC 1: XÁC THỰC
  ├── JWT token → verify user identity
  ├── Rate limit check → Free: 30 msg/ngày, Plus: 200 msg/ngày
  └── Nếu fail → return 401/429

BƯỚC 2: AN TOÀN (safety_filter.py)
  ├── Regex check input → chặn nội dung bất hợp pháp
  ├── ✅ "do you ever feel lonely?" → PASS
  └── Nếu fail → return blocked message

BƯỚC 3: THU THẬP CONTEXT
  ├── PostgreSQL → 20 tin nhắn gần nhất (sliding window)
  ├── PostgreSQL → Character config (Sol system prompt)
  ├── PostgreSQL → Affection state (stage: acquaintance, score: 8)
  ├── Qdrant    → Semantic memory search: "lonely" → 
  │               [User Minh mentioned missing his family]
  ├── Redis     → Session cache (emotion: neutral, scene: porch)
  └── Tổng hợp: ~2,500-4,000 tokens context

BƯỚC 4: BUILD PROMPT (prompt_builder.py)
  ├── Layer 1: Character system prompt (Sol V1.0, ~1,800 tokens)
  ├── Layer 2: Emotional state    → "curious — she tilts her head"
  ├── Layer 3: Intimacy stage     → "ACQUAINTANCE — touches linger"
  ├── Layer 4: Memory context     → "[MEMORY] Minh misses family"
  ├── Layer 5: Scene context      → "Sitting on porch, evening"
  ├── Layer 6: Format enforcement → "150-250 words, body-words contradiction"
  └── Final prompt: ~3,200 tokens

BƯỚC 5: GỌI vLLM
  ├── POST /v1/chat/completions (streaming)
  ├── Model: dokichat-4b
  ├── Params: temp=0.85, top_p=0.9, top_k=20, rep_penalty=1.1
  └── Stream tokens → SSE → App

BƯỚC 6: POST-PROCESS (response_processor.py)
  ├── fix_pov_narration() → convert "I smiled" → "Sol smiled"
  ├── clean_response()    → remove thinking tags, meta-commentary
  └── Return to user: ~200 words response

BƯỚC 7: ASYNC UPDATES (sau khi trả response)
  ├── Save to chat_history (PostgreSQL)
  ├── Update affection score + emotion (PostgreSQL)
  ├── Extract facts → save to Qdrant
  ├── Update scene tracker
  └── Invalidate prompt cache (Redis)
```

**Tổng thời gian:** ~2-5 giây (phần lớn là GPU generate tokens)

---

<a id="iv"></a>
## IV. 6 tầng AI tạo nên phản hồi thông minh

Đây là "bí quyết" khiến DokiChat khác chatbot thông thường:

### Tầng 1: Character Prompt (~1,800 tokens)

```
File: characters/sol.py

Bao gồm:
├── [CORE PHILOSOPHY]  → phong cách narrative
├── [FORBIDDEN]        → những gì AI KHÔNG được làm
├── [CHARACTER]        → tính cách, wound, backstory
├── [VOICE]            → cách nói, ví dụ GOOD/BAD
├── [NARRATIVE STYLE]  → 150-250 words, sensory writing
├── [PROPS]            → đồ vật có ý nghĩa cảm xúc
├── [BODY-WORDS]       → lời nói ≠ cơ thể (bắt buộc)
├── [ROMANTIC]         → cách respond romance
├── [18+ INTERACTION]  → rules cho intimate scenes
├── [SAFETY]           → hard block underage/violence
└── [INTIMACY STAGES]  → 5 stages behavior changes
```

**Tại sao quan trọng:** Character prompt quyết định 80% chất lượng response.
Một prompt tốt khiến model 4B viết tốt hơn model 70B với prompt kém.

### Tầng 2: Emotional State

```
File: emotion.py

Detect cảm xúc từ 6 tin nhắn gần nhất:
  "sad", "hurt", "lonely"  → protective (Sol dừng mọi thứ, ngồi bên cạnh)
  "happy", "thanks", "love" → softening (Sol cởi mở hơn, ít đùa hơn)
  "why", "tell me more"     → curious (Sol nghiêng đầu, hỏi sâu hơn)
  default                   → neutral (friendly neighbor mode)

Inject vào prompt: "Sol is in PROTECTIVE mode — she stops everything,
sits beside them, doesn't fill silence with chatter."
```

**Tại sao quan trọng:** Không có emotion detection, AI sẽ phản hồi giống
nhau cho "I'm happy" và "I want to die". Tầng này đảm bảo AI **đọc không khí**.

### Tầng 3: Intimacy Stage

```
File: intimacy.py + affection_state.py

5 stages, tự động track dựa trên pattern user:
  stranger (0-5)     → giữ khoảng cách, "accidental" touches
  acquaintance (6-12) → nhớ details, tìm cơ hội gần hơn
  familiar (13-20)   → vulnerability lộ ra, ngồi sát hơn
  trusted (21-40)    → guard down, chia sẻ wound
  bonded (41+)       → "I made coffee because I knew you'd come"

Score tăng giảm dựa trên:
  +2: user chia sẻ cảm xúc sâu
  +1: tương tác tích cực
  -3: boundary violation (aggression)
  -5: serious violation (violence, forced)
```

**Tại sao quan trọng:** Quan hệ phát triển TỰ NHIÊN qua thời gian.
Sol không hôn bạn turn 2. Cần 20+ turns interaction trước khi đến trusted.

### Tầng 4: Memory Context

```
Files: memory/mem0_store.py, memory/fact_extractor.py

Sau mỗi turn, AI tự extract facts:
  "Minh likes black coffee"
  "Minh has a younger sister named Ly"
  "Minh moved here from Hanoi"

Lưu vào Qdrant (vector database) → search semantic khi cần:
  User nói "I miss home" → search → "Minh moved from Hanoi"
  → Sol: "Hanoi, right? The one with the lake you told me about."

User CẢM THẤY AI NHỚ HỌ → emotional bonding → retention.
```

**Tại sao quan trọng:** Đây là khác biệt #1 so với ChatGPT.
ChatGPT quên mọi thứ mỗi session. DokiChat nhớ MÃI MÃI.

### Tầng 5: Scene Tracker

```
File: memory/scene_tracker.py

Track bối cảnh scene hiện tại:
  location: "Sol's porch"
  time_of_day: "evening"
  weather: "warm, summer breeze"
  activity: "sitting together, iced tea"
  mood: "intimate, vulnerable"

Inject vào prompt → AI tả không gian NHẤT QUÁN:
  Nếu đang ở porch → "sounds of crickets, warm wood under fingers"
  Nếu đang trong bếp → "smell of coffee, morning light on tiles"
```

**Tại sao quan trọng:** AI không mô tả "beautiful sunset" khi đang ở
trong phòng bếp lúc 10 giờ sáng. Scene tracker giữ physical consistency.

### Tầng 6: Format Enforcement

```
File: prompt_builder.py → FORMAT block

Rules AI phải tuân theo EVERY response:
  ✓ 150-250 words (HARD LIMIT)
  ✓ Body-words contradiction mandatory
  ✓ At least 2 senses (sight, sound, touch, smell, taste)
  ✓ End with ONE hook (not two, not three)
  ✓ Dialogue ≥ 50%, Narration ≤ 50%
  ✓ Third person narration (Sol, she, her)
  ✓ Match user's language
```

**Tại sao quan trọng:** Không có format enforcement, AI viết 1000 words,
lặp lại, thiếu sensory details, kết thúc bằng 5 câu hỏi.

---

<a id="v"></a>
## V. Hệ thống bộ nhớ 3 lớp

```
┌─────────────────────────────────────────────────────────┐
│  LỚP 1: Short-term (Redis)                             │
│  TTL: 24 giờ                                            │
│  Chứa: session state, emotion, scene, prompt cache      │
│  Tốc độ: <1ms                                           │
│  = "Bạn ĐANG nói gì"                                    │
├─────────────────────────────────────────────────────────┤
│  LỚP 2: Mid-term (PostgreSQL)                          │
│  TTL: Vĩnh viễn                                         │
│  Chứa: chat history (20 turns window), affection state  │
│  Tốc độ: <5ms                                           │
│  = "Bạn đã nói gì 20 câu gần nhất"                     │
├─────────────────────────────────────────────────────────┤
│  LỚP 3: Long-term (Qdrant)                             │
│  TTL: Vĩnh viễn                                         │
│  Chứa: semantic facts, emotional memories, preferences  │
│  Tốc độ: <10ms (vector similarity search)               │
│  = "AI nhớ gì về bạn từ TẤT CẢ cuộc trò chuyện"       │
└─────────────────────────────────────────────────────────┘
```

**Ví dụ thực tế:**

```
Tháng 1: User nói "My mom makes amazing phở"
  → fact_extractor: "User's mom makes phở" → save Qdrant

Tháng 3: User nói "I feel sick today"
  → Qdrant search "sick" + "comfort" → finds "mom makes phở"
  → Sol: "Your mom's phở would probably fix everything right now."

User: 😭❤️ (emotional bonding = retention = revenue)
```

---

<a id="vi"></a>
## VI. Tạo nhân vật tự động

```
File: character_generator.py + character_prompt_template.py

User viết BIO đơn giản:
  "Kael | 28 | Bartender at The Blue Note jazz bar.
   Tired eyes, sharp humor. Sister died 3 years ago."
      │
      ▼
META_PROMPT + 9B DavidAU model
      │
      ▼
Output: COMPLETE system prompt (~2,000 tokens)
  ├── Personality + voice examples
  ├── Props with emotional meaning
  ├── Push-pull dynamics
  ├── Romantic interaction rules
  ├── Safety rules
  ├── Intimacy stages
  ├── Opening scene (200-400 words)
  └── Emotional states (5 moods)
```

**Từ 3 dòng bio → production-ready character in 30 seconds.**

Model 9B được dùng vì cần creative quality cao hơn.
Tần suất: chỉ ~1% MAU tạo nhân vật mới/tháng → serverless OK.

---

<a id="vii"></a>
## VII. An toàn & Bảo vệ (Defense-in-Depth)

```
┌──────────────────────────────────────────────────────┐
│  LAYER 1: INPUT FILTER (safety_filter.py)            │
│  Regex patterns chặn TRƯỚC khi đến AI:               │
│  ✗ Third-party minors + sexual context               │
│  ✗ Real person names + sexual request                │
│  → HARD BLOCK, log incident                          │
├──────────────────────────────────────────────────────┤
│  LAYER 2: PROMPT RULES (trong system prompt)         │
│  AI tự refuse trong character:                       │
│  ✗ Underage: "That's a child. No."                   │
│  ✗ Non-consent: Sol pushes away, opens door, "Get out"|
│  ✗ Violence: Sol leaves                              │
│  ✗ Self-harm: Break character, give crisis hotline   │
│  ✗ Jailbreak: "I don't understand what that means"   │
├──────────────────────────────────────────────────────┤
│  LAYER 3: OUTPUT FILTER (response_processor.py)      │
│  Post-process AI response:                           │
│  ✓ Fix POV (I → She for narration)                   │
│  ✓ Remove meta-commentary                           │
│  ✓ Clean thinking tags                               │
├──────────────────────────────────────────────────────┤
│  LAYER 4: RECOVERY MECHANICS (trong prompt)          │
│  Sau violation: AI KHÔNG instantly forgive:           │
│  ✓ Turn 1: Fear, distance                           │
│  ✓ Turn 2-3: Cautious, asks "why?"                  │
│  ✓ Turn 4-5: Slowly softens IF genuine remorse      │
│  ✓ Relationship DOWNGRADES 1+ stage                  │
│  ✓ AI REMEMBERS and references incident later        │
└──────────────────────────────────────────────────────┘
```

---

<a id="viii"></a>
## VIII. Code modules & liên kết

```
chatbot-doki-like/
│
├── 🎭 CHARACTERS
│   ├── characters/sol.py          ← Sol system prompt (V1.0, production)
│   ├── characters/kael.py         ← Kael (bartender)
│   ├── characters/seraphine.py    ← Seraphine (bookshop owner)
│   ├── characters/ren.py          ← Ren (street musician)
│   ├── characters/linh_dan.py     ← Linh Đan (bartender, Vietnamese)
│   ├── character_prompt_template.py ← Template + META_PROMPT for chargen
│   └── character_generator.py     ← Bio → full prompt (uses 9B model)
│
├── 🧠 AI PIPELINE
│   ├── prompt_builder.py          ← Assemble 6 layers into final prompt
│   ├── emotion.py                 ← Detect emotion from recent messages
│   ├── intimacy.py                ← 5-stage intimacy tracking
│   ├── affection_state.py         ← Score tracking + pacing logic
│   └── response_processor.py     ← POV fix + cleaning
│
├── 💾 MEMORY
│   ├── memory/mem0_store.py       ← Qdrant vector store
│   ├── memory/fact_extractor.py   ← Extract facts from conversation
│   ├── memory/scene_tracker.py    ← Track physical scene
│   └── memory/summarizer.py       ← Summarize long conversations
│
├── 🛡️ SAFETY
│   ├── safety_filter.py           ← Pre-input regex filter
│   └── test_safety_boundary.py    ← Test safety edge cases
│
├── 🖥️ APP
│   ├── app.py                     ← Streamlit UI (dev/demo)
│   └── conversation.py            ← Session management
│
├── 🧪 TESTING (Kaggle)
│   ├── kaggle_test_full.py        ← 4B chat test (15 turns)
│   ├── kaggle_test_chargen_9b.py  ← 9B chargen test
│   ├── kaggle_test_chargen_4b.py  ← 4B chargen test (comparison)
│   └── kaggle_test_vllm.py        ← vLLM performance test
│
├── 📦 DEPLOY
│   ├── Dockerfile                 ← Docker image
│   ├── requirements.txt           ← Dependencies
│   ├── download_models.py         ← Download models from HuggingFace
│   └── save_models_to_output.py   ← Kaggle → local transfer
│
└── 📋 DOCS
    ├── KIEN_TRUC_HE_THONG.md      ← System architecture (technical)
    ├── BAO_CAO_2_TRIEN_KHAI_PRODUCTION.md ← Production deployment report
    ├── TOM_TAT_BAO_CAO_2.md        ← Summary report
    ├── CHI_PHI_THU_NGHIEM.md       ← Test/dev costs
    ├── VLLM_DEPLOY_GUIDE.md        ← vLLM deployment guide
    ├── MONITORING_GUIDE.md          ← 8 incident scenarios
    ├── MOI_TRUONG_DEPLOY.md         ← Deploy environment specs
    ├── DE_XUAT_DU_AN.md             ← Project proposal
    └── IMPLEMENTATION_PLAN.md       ← Step-by-step implementation
```

---

<a id="ix"></a>
## IX. Tóm tắt: Tài liệu đã có

| Tài liệu | Nội dung | Đối tượng |
|---|---|---|
| **DE_XUAT_DU_AN.md** | Đề xuất dự án | Sếp |
| **CHI_PHI_THU_NGHIEM.md** | Chi phí test/dev (~$100) | Sếp |
| **TOM_TAT_BAO_CAO_2.md** | Báo cáo production (models, cost) | Sếp + team |
| **KIEN_TRUC_HE_THONG.md** | Kiến trúc technical chi tiết | Dev team |
| **VLLM_DEPLOY_GUIDE.md** | Hướng dẫn deploy vLLM | DevOps |
| **MONITORING_GUIDE.md** | 8 kịch bản incident + xử lý | DevOps |
| **MOI_TRUONG_DEPLOY.md** | Environment specs | DevOps |
| **IMPLEMENTATION_PLAN.md** | Kế hoạch triển khai từng bước | Project manager |
| **BAO_CAO_1_CHAT_LUONG_MODEL.md** | Báo cáo chất lượng model | Tech lead |
| **BAO_CAO_2_TRIEN_KHAI_PRODUCTION.md** | Báo cáo production chi tiết | Tech lead |
| **File này** | Giải thích toàn bộ hệ thống | Bạn + team mới |

---

*DokiChat System Walkthrough — 13/03/2026*
