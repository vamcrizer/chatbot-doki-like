# 🚀 BÁO CÁO: AI INFERENCE, DATA, SCALING — DEPLOY & CHI PHÍ
### DokiChat AI Companion | 09/03/2026

---

## I. MODEL HIỆN TẠI

| Thông số | Giá trị |
|---|---|
| **Model** | Qwen3.5-4B-Uncensored (fine-tune hauhaucs) |
| **Params** | 3.6B |
| **Quantization** | Q8 |
| **VRAM weights** | ~5GB |
| **Context window** | 32K tokens |
| **Embedding model** | Snowflake Arctic Embed L v2.0 (1024 dims, ~1.2GB) |

### Workload mỗi request

| Thành phần | Tokens |
|---|---|
| System prompt (V2 compact) | ~1,200 |
| Memory context (facts + relevant memories) | ~500-800 |
| Chat history (sliding window) | ~500-2,000 |
| User message | ~50-100 |
| **Tổng input** | **~2,300-4,100** |
| Model response (output) | ~200-400 |
| **Tổng/turn** | **~2,500-4,500** |

---

## II. INFERENCE ENGINE — vLLM

### Tại sao vLLM?

| Tính năng | Tác dụng |
|---|---|
| **PagedAttention** | Quản lý KV cache hiệu quả, không lãng phí VRAM |
| **Continuous Batching** | 1 model instance phục vụ 50-80 users song song |
| **Prefix Caching** | System prompt giống nhau → cache 1 lần, dùng cho mọi user cùng nhân vật |
| **Streaming** | Trả token từng cái, user thấy chữ chạy ra real-time |
| **Multi-LoRA** | 1 base model + nhiều LoRA adapters = nhiều nhân vật trên 1 GPU |
| **OpenAI-compatible API** | Đổi từ LM Studio sang vLLM chỉ cần đổi URL |

### Throughput trên các GPU

| GPU | VRAM | Qwen3-4B Q8 tok/s | Qwen3-8B FP8 tok/s | Concurrent users |
|---|---|---|---|---|
| **L40S** | 48GB | ~800 | ~580 | 50-80 |
| **A100 80GB** | 80GB | ~750 | ~600 | 60-100 |
| **H100** | 80GB | ~1,200 | ~900 | 80-120 |
| **RTX 4090** | 24GB | ~500 | ~300 | 30-50 |
| **A10G** | 24GB | ~400 | ~250 | 25-40 |

### KV Cache Management

- **Tự động**: vLLM quản lý hoàn toàn, không cần cronjob/clean
- **Eviction**: VRAM đầy → đuổi cache user idle lâu nhất (LRU)
- **User quay lại**: Prefill lại ~200ms, không mất data
- **Giới hạn thực**: Context window 32K tokens (~75 turns), không phải VRAM

---

## III. ƯỚC TÍNH TẢI

| Quy mô | MAU | DAU | Turns/ngày | Peak concurrent | Peak RPS |
|---|---|---|---|---|---|
| **10K** | 10,000 | 2,000 | 100K | 300 | 5 |
| **100K** | 100,000 | 20,000 | 1M | 3,000 | 50 |
| **1M** | 1,000,000 | 200,000 | 10M | 30,000 | 500 |
| **10M** | 10,000,000 | 2,000,000 | 100M | 300,000 | 5,000 |

---

## IV. DATABASE & CACHING

### PostgreSQL — Dữ liệu vĩnh viễn

| Lưu gì | Ví dụ |
|---|---|
| User profiles | id, name, email, plan, created_at |
| Chat history | user_id, character_id, role, content, timestamp |
| Character configs | system prompt, pacing config, safety rules |
| Affection state | user_id, character_id, score, stage, mood |
| Subscriptions | plan, start_date, payment_status |

**Scale theo phase:**

| Phase | Setup | Lý do |
|---|---|---|
| 10K | PostgreSQL local (single) | Đủ cho vài nghìn users |
| 100K | Managed (Supabase/Neon) | Backup tự động, giảm ops |
| 1M | 1 primary + 2 read replicas | Chat history là read-heavy |
| 10M | CockroachDB (3-region) | Distributed SQL, global |

### Qdrant — Vector Memory

| Lưu gì | Ví dụ |
|---|---|
| Facts về user | "User thích nhạc RPG", "User sống với bố" |
| Emotional memories | "User từng kể chuyện buồn về ex" |
| Character knowledge | Backstory, relationships |

**Scale:** In-memory (10K) → Qdrant Cloud (100K+) → Sharded cluster (1M+)

### Redis — Cache & Session & Queue

| Lưu gì | TTL | Ý nghĩa |
|---|---|---|
| Session state | 24h | `user_123 → { char: "sol", affection: 45 }` |
| Rate limit counter | 24h | `user_123_msgs → 47` (chặn Free >50/ngày) |
| Prompt cache | 1h | System prompt đã build sẵn |
| Online status | 5min | Ai đang online |
| **Request queue** | Real-time | Xếp hàng requests khi GPU bận |

**Scale:** Local (10K) → Redis Cloud HA (100K) → Redis Sentinel (1M) → Redis Cluster 6-node (10M)

---

## V. REQUEST QUEUE — LOGIC XỬ LÝ

### Tại sao cần Queue?

```
KHÔNG có queue (10K — chấp nhận được):
  User request → thẳng vào vLLM → response

CÓ queue (100K+ — bắt buộc):
  User request → Queue → vLLM lấy ra xử lý → response
                  ↑
          Nếu GPU bận, request chờ ở đây
          thay vì bị timeout/crash
```

### Queue flow chi tiết

```
① User gửi message
    ↓
② API Server nhận → validate → build prompt
    ↓
③ Push vào Redis Streams (queue)
    Message: { request_id, user_id, prompt, timestamp }
    ↓
④ vLLM Worker poll queue
    - Có slot trống → lấy request, xử lý ngay
    - Đầy slot → request nằm chờ trong queue (không crash)
    ↓
⑤ vLLM stream tokens → push vào Redis pub/sub channel
    Channel: "response:{request_id}"
    ↓
⑥ API Server subscribe channel → stream về cho User
```

**Mục đích duy nhất:** GPU chỉ xử lý được N requests cùng lúc. Nếu đến N+1, thay vì crash/timeout → request chờ trong queue rồi xử lý khi có slot.

### Auto-scale triggers (dựa trên queue)

| Condition | Action |
|---|---|
| Queue depth > 50, liên tục 2 phút | Spin up thêm GPU |
| Queue depth > 200 | Spin up 2 GPU + alert |
| Queue < 10 VÀ GPU util < 20%, 15 phút | Shutdown GPU thừa |
| Queue = 0 VÀ GPU util < 10%, 30 phút | Shutdown tới minimum |

**Khi nào chuyển Redis Streams → Kafka:**
- 1M+ MAU: throughput cao hơn, replay log
- Dưới 1M: Redis Streams đủ và đơn giản hơn

---

## VI. GPU DEPLOY THEO TỪNG MỨC

---

### � 10K MAU — Single Server

```
1× L40S (RunPod, $0.80/hr)
├── vLLM (Qwen3-4B Q8, ~5GB)
│   └── ~800 tok/s, ~50 concurrent
├── Embedding model (CPU, ~1.2GB)
├── PostgreSQL (local)
├── Redis (local)
└── Qdrant (in-memory)

Không cần queue — request đi thẳng vào vLLM.
```

| Chi phí AI+Data | /tháng |
|---|---|
| L40S 24/7 | $576 |
| Misc | $224 |
| **TỔNG** | **$800** |

---

### 🔵 100K MAU — Small Cluster

```
4× L40S (vLLM workers)
├── Load balancer phân request đều
│   └── Tổng: ~3,200 tok/s, ~200 concurrent
│
├── Embedding: 1 CPU server
├── PostgreSQL Managed (Supabase)
├── Redis Cloud (4GB, HA) — session + queue
└── Qdrant Cloud (10GB)
```

| Chi phí | /tháng |
|---|---|
| L40S × 4 (24/7) | $2,304 |
| Embedding (CPU) | $50 |
| PostgreSQL managed | $25 |
| Redis Cloud | $60 |
| Qdrant Cloud | $100 |
| **TỔNG** | **~$2,539** |

---

### 🟡 1M MAU — Production Cluster

```
12× L40S
├── 8× L40S (24/7 base)
├── 4× L40S (auto-scale peak 8h/ngày)
│   └── Tổng: ~6,400-9,600 tok/s, ~500 concurrent
│
├── Prefix caching ON
├── Multi-LoRA ON
│
├── Embedding: 1× GPU T4
├── PostgreSQL (1 primary + 2 read replicas)
├── Redis Sentinel (3-node, 16GB) — session + queue + pub/sub
├── Qdrant Cloud (50GB, sharded)
└── Request queue: Redis Streams với priority
```

| Chi phí | /tháng |
|---|---|
| L40S × 8 (24/7) | $4,608 |
| L40S × 4 (peak 8h/d) | $768 |
| Embedding T4 | $144 |
| PostgreSQL cluster | $200 |
| Redis Sentinel | $100 |
| Qdrant Cloud | $300 |
| **TỔNG** | **~$6,120** |

---

### 🔴 10M MAU — Global Scale

#### Multi-model tiers

| Tier | Model | Quant | Users | GPU L40S cần |
|---|---|---|---|---|
| Free | Qwen3-4B | Q8 | 8.5M (85%) | 120-150 |
| Plus | Qwen3-8B | FP8 | 1.2M (12%) | 80-100 |
| Ultra | Qwen3.5-14B | Q8 | 300K (3%) | 40-50 |
| **Tổng** | | | **10M** | **240-300** |
| **+ Buffer 20%** | | | | **300-360** |

#### Multi-region

```
ASIA-HCM (primary):  150-200 L40S
ASIA-SG (secondary):  80-120 L40S
US-WEST (overseas):    20-30 L40S
```

#### Tối ưu GPU

| Kỹ thuật | Tiết kiệm |
|---|---|
| Prefix Caching | -30-40% compute |
| Q8 Quantization | -40% VRAM vs FP16 |
| Continuous Batching | +3× vs static |
| Multi-LoRA | -70% VRAM multi-char |
| Speculative Decoding | +1.5-2× speed |

Áp dụng đủ → giảm ~350 GPU → **~200-250 GPU**.

#### Chi phí GPU

| Option | /tháng |
|---|---|
| On-demand ($0.80/hr × 350) | $201,600 |
| Reserved ($0.55/hr × 350) | $138,600 |
| Dedicated ($800/server × 175) | $140,000 |
| **Mixed 70/30 (đề xuất)** | **$125,000** |

#### Chi phí Data layer 10M MAU

| Hạng mục | /tháng |
|---|---|
| CockroachDB (3-region, 5TB) | $3,000 |
| Redis Cluster (6-node, 64GB/node) | $2,000 |
| Qdrant Cloud (500GB, 3-region) | $3,000 |
| Kafka (3 brokers) | $1,500 |
| Embedding (3× T4) | $432 |
| **Subtotal Data** | **$9,932** |

#### Tổng 10M MAU

| Category | /tháng |
|---|---|
| GPU Inference | $125,000 |
| Data layer | $9,932 |
| Monitoring | $5,000 |
| **TỔNG** | **~$139,932** |

---

## VII. MONITORING

### Metrics cần track

| Metric | Alert khi |
|---|---|
| **Throughput** (tok/s toàn cluster) | < 80% capacity |
| **TTFT** (chờ chữ đầu tiên) | p95 > 500ms |
| **Queue depth** | > 100 requests |
| **GPU utilization** | > 90% (cần scale) hoặc < 20% (lãng phí) |
| **VRAM usage** | > 95% |
| **Error rate** | > 1% |
| **p95 latency** (toàn request) | > 5s |

### Stack

```
vLLM /metrics → Prometheus (15s interval) → Grafana
                                             ├── Dashboard: GPU cluster health
                                             ├── Dashboard: Latency & queue
                                             ├── Alert → Slack/Telegram
                                             └── Alert → Auto-scale trigger
```

### Alerting rules

| Rule | Condition | Action |
|---|---|---|
| ScaleUp | queue > 50, 2min | Thêm GPU |
| ScaleDown | GPU util < 20%, 15min | Shutdown GPU thừa |
| HighLatency | TTFT p95 > 2s, 5min | Alert + investigate |
| GPUDead | Worker không respond 30s | Auto-restart + alert |

---

## VIII. GPU PROVIDER SO SÁNH

| Provider | GPU | Giá/hr | Ưu | Nhược |
|---|---|---|---|---|
| **RunPod** | L40S | $0.80 | Linh hoạt, spot pricing | Không stable 100% |
| **Lambda** | L40S | $0.85 | Enterprise support | Đắt hơn |
| **Vast.ai** | L40S | $0.50-0.70 | Rẻ nhất | Unreliable |
| **CoreWeave** | L40S | $0.74 | Enterprise, SLA | Min commitment |
| **Hetzner** | Dedicated | ~$800/server/mo | Stable, rẻ dài hạn | Ít options |

Đề xuất: RunPod (MVP) → CoreWeave (1M) → Dedicated+On-demand mix (10M)

---

## IX. TỔNG HỢP CHI PHÍ

| Scale | GPU | Data | Monitor | **Tổng/tháng** | **Chi phí/user** |
|---|---|---|---|---|---|
| **10K** | $576 | $224 | $0 | **$800** | $0.080 |
| **100K** | $2,354 | $185 | $0 | **$2,539** | $0.025 |
| **1M** | $5,520 | $600 | incl. | **$6,120** | $0.006 |
| **10M** | $125,432 | $9,500 | $5,000 | **$139,932** | $0.014 |

---

## X. TỔNG KẾT

| Câu hỏi | Trả lời |
|---|---|
| **Model?** | Qwen3-4B Q8 (đã verify 42 turns) |
| **Serving?** | vLLM — continuous batching, prefix cache, streaming |
| **GPU?** | L40S ($0.80/hr) — sweet spot giá/hiệu năng |
| **Database?** | PostgreSQL → CockroachDB (10M) |
| **Vector memory?** | Qdrant in-memory → Cloud → Sharded |
| **Cache + Queue?** | Redis — session, rate limit, request queue |
| **Queue logic?** | Priority (Ultra>Plus>Free), auto-scale theo depth |
| **Monitor?** | Prometheus + Grafana, alert Slack, auto-scale |
| **Cost 10K?** | **$800/tháng** |
| **Cost 1M?** | **$6,120/tháng** |
| **Cost 10M?** | **$139,932/tháng** |

---

*Báo cáo AI + Data + Scaling — Team phát triển DokiChat — 09/03/2026*
