````markdown
# Memory System — Mem0 & Mem0g
> Stack: Qdrant (dense) + Neo4j (graph) + gpt-4o-mini (extraction)
> Two-tier architecture based on user maturity

---

## Table of Contents
1. [What Mem0 Does](#1-what-mem0-does)
2. [User Tier Classification](#2-user-tier-classification)
3. [New User Pipeline — Mem0 Only](#3-new-user-pipeline--mem0-only)
4. [Veteran User Pipeline — Mem0 + Mem0g](#4-veteran-user-pipeline--mem0--mem0g)
5. [Upgrade Job — New → Veteran](#5-upgrade-job--new--veteran)
6. [Token & Latency Budget](#6-token--latency-budget)
7. [Database Schema](#7-database-schema)

---

## 1. What Mem0 Does

Mem0 solves two problems simultaneously — memory quality and token cost.

**Memory quality:**
Unlike naive RAG that stores raw conversation chunks, Mem0 extracts and
consolidates facts into minimal memory units before storing them.

```
RAG naive:
  Stored: "hôm qua minh nói anh ấy thích jazz khi làm việc
           khuya và đang dùng macbook pro và anh ấy sống..."
  → 200 tokens to express 3 facts

Mem0:
  Stored: "thích jazz khi làm việc khuya"  → 6 tokens
          "dùng macbook pro m3"             → 5 tokens
          "sống ở Hà Nội"                  → 4 tokens
```

**Token cost:**
Because only top-k memories are retrieved per request (not full history),
context size stays flat regardless of conversation length.

```
Without Mem0 (full history, 100 turns):  ~40,000 tokens/request
With Mem0    (top-10 memories):           ~1,700 tokens/request
Reduction: >90%
```

**Mem0g (graph layer)** adds relationship-aware retrieval on top of
dense vector search — used only for Veteran users where enough data
exists to make the graph meaningful.

---

## 2. User Tier Classification

```
NEW USER    → total_messages < 50  OR   account_age < 7 days
VETERAN     → total_messages >= 50 AND  account_age >= 7 days
```

The `AND` condition for Veteran is intentional — prevents users who
spam 50 messages in one day from triggering graph construction before
enough meaningful data has accumulated.

| Property | New User | Veteran |
|---|---|---|
| Memory store | Qdrant only | Qdrant + Neo4j |
| Memory retrieval | Dense vector search | Dense + graph subgraph + triplet search |
| Context size | ~1,764 tokens | ~3,616 tokens |
| Latency p50 | ~720ms | ~1,006ms |
| Graph history | None | Backfilled from day 1 |

---

## 3. New User Pipeline — Mem0 Only

```
 USER SENDS MESSAGE m_t[1]
        ↓
 EMOTION CLASSIFIER  (parallel, ~50ms)[2]
    Input:  m_t
    Model:  xlm-roberta-base fine-tuned GoEmotions
    Output: {joy: 0.1, sadness: 0.8, neutral: 0.1}
    Action: select tone_instruction accordingly
        ↓
 SLIDING WINDOW[3]
    Fetch last 10 messages: {m_t-9, ..., m_t-1, m_t}
    Include conversation summary S (if exists)
        ↓
 MEM0 SEARCH  (~0.148s p50)[4]
    Query: embed(m_t) → vector
    Search Qdrant: top_k=10 nearest memories
    Output: ["Minh thích jazz", "Minh sống Hà Nội", ...]
        ↓
 CONTEXT ASSEMBLY[5]
    ┌──────────────────────────────────────┐
    │ LAYER 1: Narrator system prompt      │
    │ LAYER 2: Character card (JSON)       │
    │ LAYER 3: tone_instruction (step 2)   │
    │ LAYER 4: Mem0 memories   (step 4)    │
    │ LAYER 5: Sliding window  (step 3)    │
    └──────────────────────────────────────┘
    Estimated total: ~1,764 tokens
        ↓
 LLM INFERENCE  (streaming)[6]
    Model: gpt-oss-120b / Claude / GPT-4o
    User sees first token in ~0.5–1s
        ↓
 RESPONSE → USER  ✅[7]
        ↓
 ASYNC: MEM0 UPDATE  (background, does not block step 7)[8]
    Input: (S, {m_t-9..m_t-1}, m_t-1, m_t)

    [8a] EXTRACTION
         gpt-4o-mini extracts facts Ω = {ω1, ω2, ...}
         Custom prompt filters: real_fact vs character_note vs noise

    [8b] UPDATE  (per fact ωi)
         → Embed ωi
         → Search top-10 similar existing memories
         → gpt-4o-mini decides:
            ADD    → insert into Qdrant
            UPDATE → merge and update existing
            DELETE → remove contradicted memory
            NOOP   → discard

    [8c] SUMMARY UPDATE  (if > 20 new messages since last summary)
         → gpt-4o-mini summarizes full session
         → Overwrite S in DB
        ↓
 CHECK UPGRADE TRIGGER[9]
    IF total_messages >= 50 AND account_age >= 7 days:
        → Trigger UPGRADE JOB (see section 5)
    ELSE:
        → Continue Mem0 Only
```

---

## 4. Veteran User Pipeline — Mem0 + Mem0g

```
 USER SENDS MESSAGE m_t[1]
        ↓
 EMOTION CLASSIFIER  (~50ms, parallel)[2]
        ↓
 SLIDING WINDOW  (last 10 messages + summary S)[3]
        ↓
┌──────────────────────────────────────────────────────┐
│  [4A] MEM0 SEARCH (~0.148s)  ║  [4B] MEM0G SEARCH (~0.476s)  │
│  Run in parallel via asyncio.gather                  │
│                                                      │
│  embed(m_t) → Qdrant         ║  i.  Entity extraction from m_t    │
│  top_k=10 dense memories     ║      gpt-4o-mini: "Minh", "Hà Nội" │
│                              ║  ii. Entity-centric search          │
│                              ║      → find node "Minh" in Neo4j   │
│                              ║      → traverse incoming/outgoing   │
│                              ║        edges → return subgraph      │
│                              ║  iii. Semantic triplet search       │
│                              ║      → embed(m_t) vs all triplets   │
│                              ║      → sort by cosine similarity    │
│                              ║      → top-k relevant triplets      │
└──────────────────────────────────────────────────────┘
        ↓
 MERGE & RE-RANK[5]
    Input:  Dense memories (4A) + Graph context (4B)
    Steps:
    - De-duplicate overlapping results
    - Combine into unified context block
    - Re-rank by composite relevance score
    Output: ~3,616 tokens
        ↓
 CONTEXT ASSEMBLY[6]
    ┌────────────────────────────────────────────┐
    │ LAYER 1: Narrator system prompt            │
    │ LAYER 2: Character card (JSON)             │
    │ LAYER 3: tone_instruction                  │
    │ LAYER 4: Dense memories (Mem0)             │
    │ LAYER 5: Graph context  (Mem0g)            │
    │          (Minh)→[làm_tại]→(AI Startup)    │
    │          (Minh)→[sợ]→(độ cao)             │
    │          (Minh)→[thích]→(Jazz)             │
    │ LAYER 6: Sliding window                    │
    └────────────────────────────────────────────┘
        ↓
 LLM INFERENCE  (streaming)[7]
        ↓
 RESPONSE → USER  ✅[8]
        ↓
[8A] ASYNC: MEM0 UPDATE
     Same ADD/UPDATE/DELETE/NOOP flow as New User step 8

[8B] ASYNC: MEM0G UPDATE
     i.   Extract entities from (m_t-1, m_t)
     ii.  Generate relationship triplets:
          (Minh) --[nhắc đến]--> (jazz) --[khi]--> (mệt mỏi)
     iii. Conflict detection:
          → embed source + destination nodes
          → compare against existing nodes (similarity threshold t)
          → if conflict: mark old edge INVALID (kept for temporal queries)
          → insert new edge with current timestamp
     iv.  Upsert into Neo4j

[8C] ASYNC: SUMMARY UPDATE
     If > 20 new messages since last summary:
     → gpt-4o-mini summarizes, overwrites S
```

> **Why keep INVALID edges instead of deleting?**
> Enables temporal queries like *"where did Minh work before?"*
> without losing historical data. The `valid: false` flag marks
> superseded edges while keeping them accessible.

---

## 5. Upgrade Job — New → Veteran

Runs **once** when threshold is reached. Not triggered on every request.
Estimated duration: 30–60 seconds (background task).

```
[U1] Load all Mem0 memories for this user from Qdrant
     (All facts accumulated since registration)
        ↓
[U2] Init Neo4j user namespace
     CREATE (u:User {user_id: "minh_001"})
        ↓
[U3] BACKFILL GRAPH from existing memories
     For each memory in Qdrant:
     → Extract entities + relationships via gpt-4o-mini
     → Insert nodes and edges into Neo4j
     → Assign timestamp = memory.created_at
     Result: graph has temporal history from day 1,
             not just from upgrade date
        ↓
[U4] Update user profile flag
     { mem0_tier: "veteran", graph_enabled: true }
        ↓
[U5] Next request automatically routes to Veteran pipeline
```

---

## 6. Token & Latency Budget

### Token cost per request

```
NEW USER
  System prompt (character):   ~800  tokens  (fixed)
  tone_instruction:             ~50  tokens  (dynamic)
  Mem0 top-10 memories:        ~300  tokens  (dynamic)
  Sliding window (10 turns):   ~600  tokens  (dynamic)
  ─────────────────────────────────────────────────────
  Total:                      ~1,750 tokens  ✅

VETERAN
  System prompt (character):   ~800  tokens  (fixed)
  tone_instruction:             ~50  tokens  (dynamic)
  Mem0 top-10 memories:        ~300  tokens  (dynamic)
  Mem0g graph context:       ~1,800  tokens  (dynamic)
  Sliding window (10 turns):   ~600  tokens  (dynamic)
  ─────────────────────────────────────────────────────
  Total:                      ~3,550 tokens  ✅

WITHOUT Mem0 (full history at 100 turns):
  ~20,000–40,000 tokens/request  ❌
  Reduction with Mem0: >90%
```

### Latency p50

```
NEW USER
  Emotion classifier:   ~50ms   (parallel)
  Mem0 search:         ~148ms   (p50)
  Context assembly:     ~20ms
  LLM first token:     ~500ms   (streaming)
  ──────────────────────────────────────────
  User sees first char: ~720ms  ✅

VETERAN
  Emotion classifier:   ~50ms   (parallel with search)
  Mem0 search:         ~148ms   (parallel with Mem0g)
  Mem0g graph search:  ~476ms   (bottleneck)
  Merge + assembly:     ~30ms
  LLM first token:     ~500ms   (streaming)
  ──────────────────────────────────────────
  User sees first char: ~1,006ms ✅  (< 1.1s acceptable)
```

---

## 7. Database Schema

### Qdrant — Mem0 (both tiers)

```
Collection: companion_memories

{
  id:         uuid
  vector:     float        ← BGE-M3 or text-embedding-3-small
  payload: {
    user_id:    "minh_001"
    memory:     "thích nghe jazz khi làm việc khuya"
    created_at: timestamp
    updated_at: timestamp
    source:     "real_fact" | "character_note"
    confidence: float            ← set by extraction step
  }
}
```

`source` field separates facts about the **real user** (`real_fact`)
from things the character has noted in-universe (`character_note`),
preventing cross-contamination during retrieval.

### Neo4j — Mem0g (Veteran only)

```
Nodes:
  (Minh   : Person  { user_id, embedding })
  (HaNoi  : City    { embedding })
  (Jazz   : Music   { embedding })
  (Startup: Company { embedding })

Edges:
  (Minh)-[:LIVES_IN  { timestamp, valid: true  }]->(HaNoi)
  (Minh)-[:LIKES     { timestamp, valid: true  }]->(Jazz)
  (Minh)-[:WORKS_AT  { timestamp, valid: false }]->(OldJob)  ← superseded
  (Minh)-[:WORKS_AT  { timestamp, valid: true  }]->(Startup) ← current
```

**Querying current state:**
```cypher
MATCH (u:Person {user_id: $uid})-[r]->(target)
WHERE r.valid = true
RETURN u, r, target
```

**Querying temporal history:**
```cypher
MATCH (u:Person {user_id: $uid})-[r:WORKS_AT]->(company)
RETURN company.name, r.timestamp, r.valid
ORDER BY r.timestamp ASC
```

---

## Key Design Decisions

| Decision | Reason |
|---|---|
| `AND` for Veteran threshold | Prevents graph trigger from message spam in first 7 days |
| `valid: false` instead of delete | Preserves temporal history for past-tense queries |
| Async Mem0 update after response | Does not block streaming — user never waits for memory write |
| Backfill graph on upgrade | Graph has full history from day 1, not just post-upgrade |
| `source: real_fact / character_note` | Prevents in-universe character notes polluting user fact retrieval |
| Parallel Mem0 + Mem0g search | Veteran latency = max(148ms, 476ms), not 148+476ms |
````

Nguồn
[1] Dokichat - Romantic AI Chats - Apps on Google Play https://play.google.com/store/apps/details?id=app.doki.dokichat&hl=en
[2] Dokichat – Romantic AI Chat - App Store https://apps.apple.com/us/app/dokichat-romantic-ai-chat/id6642711442
[3] Dokichat AI: The Future of AI Chat and Virtual Companions (2025 ... https://ai.dogas.info/blog/dokichat-ai-the-future-of-ai-chat-and-virtual-companions-2025-guide/
[4] Dokichat AI - Romantic AI Chat - Download https://dokichat-ai-romantic-ai-chat.updatestar.com
[5] Dokichat - Romantic AI Chats https://www.reddit.com/r/ChatbotRefugees/comments/1nlpkiw/dokichat_romantic_ai_chats/
[6] 5 Best Roleplay Apps Like Replika: The Free, The Uncensored, and ... https://www.nastia.ai/blog/best-ai-roleplay-apps-like-replika
[7] Best AI Companions 2025 – Top Chatbots to Talk, Vent & Learn https://aidigitalspace.com/best-ai-companions-2025/
[8] Dokichat - Romantic AI Chats – Apps on Google Play https://play.google.com/store/apps/details?id=app.doki.dokichat&hl=en_IN
[9] Top 12 Ai Companion Apps... https://www.luvr.ai/blog/best-ai-companion-app
