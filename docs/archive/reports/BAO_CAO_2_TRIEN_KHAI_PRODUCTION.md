# 🚀 BÁO CÁO: AI INFERENCE, DATA, SCALING — DEPLOY & CHI PHÍ
### DokiChat AI Companion | 10/03/2026

***

## I. MODELS

### Chat Model — Qwen3.5-4B (uncensored fine-tune)

| Thông số | Giá trị |
|---|---|
| **Params** | 4B (text model) / 5B tổng với vision encoder |
| **Quantization** | Q8 |
| **VRAM weights** | ~5 GB |
| **Context window** | 262,144 tokens native (~1M với YaRN) |
| **Kiến trúc** | Hybrid Gated DeltaNet + Sparse MoE, 32 layers |

### Char-gen Model — Qwen3.5-9B (uncensored fine-tune)

| Thông số | Giá trị |
|---|---|
| **Params** | 9B (text model) / 10B tổng với vision encoder |
| **Quantization** | Q8 |
| **VRAM weights** | ~10 GB |
| **Context window** | 262,144 tokens native |
| **Tần suất** | Chỉ gọi khi tạo nhân vật (~1% MAU/tháng) |
| **Tokens/lần tạo** | ~7,644 tokens (2 LLM calls) |

Cả hai model co-locate trên cùng L40S: **5GB + 10GB = 15GB VRAM**, còn lại **33GB** cho KV cache .

### Embedding Model — Qwen3-Embedding-0.6B

| Thông số | Giá trị |
|---|---|
| **Dims** | 1,024 |
| **VRAM** | ~1.2 GB |
| **Dùng cho** | Tìm kiếm memory ngữ nghĩa trong Qdrant |

***

### Workload mỗi request (Chat Model)

| Thành phần | Tokens |
|---|---|
| System prompt (V2 compact) | ~1,200 |
| Memory context (facts + relevant memories) | ~500–800 |
| Chat history (sliding window) | ~500–2,000 |
| User message | ~50–100 |
| **Tổng input** | **~2,300–4,100** |
| Model response (output) | ~200–400 |
| **Tổng/turn** | **~2,500–4,500** |

***

## II. INFERENCE ENGINE — vLLM

### Tại sao vLLM?

| Tính năng | Tác dụng |
|---|---|
| **PagedAttention** | Quản lý KV cache hiệu quả, không lãng phí VRAM |
| **Continuous Batching** | 1 model instance phục vụ 50–80 users song song |
| **Prefix Caching** | System prompt giống nhau → cache 1 lần, dùng cho mọi user cùng nhân vật |
| **Streaming** | Trả token từng cái, user thấy chữ chạy ra real-time |

| **OpenAI-compatible API** | Đổi từ LM Studio sang vLLM chỉ cần đổi URL |

### Throughput trên các GPU (Qwen3.5-4B Q8, vLLM)

| GPU | VRAM | 4B Q8 tok/s | 9B Q8 tok/s | Concurrent users |
|---|---|---|---|---|
| **L40S** *(khuyến nghị)* | 48 GB | **~1,200** | ~500 | 50–80 |
| A100 80GB | 80 GB | ~900 | ~700 | 60–100 |
| H100 | 80 GB | ~1,800 | ~1,200 | 80–120 |
| RTX 4090 | 24 GB | ~550 | — | 30–50 |
| A10G | 24 GB | ~420 | — | 25–40 |

[1][2]

### KV Cache Management

- **Tự động**: vLLM quản lý hoàn toàn, không cần cronjob/clean
- **Eviction**: VRAM đầy → đuổi cache user idle lâu nhất (LRU)
- **User quay lại**: Prefill lại ~200ms, không mất data
- **Giới hạn thực**: Context window **262,144 tokens** (~6,500 turns) — đủ cho hàng tháng trò chuyện liên tục 

***

## III. ƯỚC TÍNH TẢI

| Quy mô | MAU | DAU | Turns/ngày | Peak concurrent | Peak RPS |
|---|---|---|---|---|---|
| **10K** | 10,000 | 2,000 | 100K | 300 | 5 |
| **100K** | 100,000 | 20,000 | 1M | 3,000 | 50 |
| **1M** | 1,000,000 | 200,000 | 10M | 30,000 | 500 |
| **10M** | 10,000,000 | 2,000,000 | 100M | 300,000 | 5,000 |

***

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

| Phase | Setup | Nhà cung cấp | Lý do |
|---|---|---|---|
| 10K | Single managed | **Supabase Pro** $25/tháng | Tích hợp Auth + Storage, dễ dùng |
| 100K | Managed | **DigitalOcean** $60/tháng | Giá rõ ràng, ít ops |
| 1M | 1 primary + 2 read replicas | **DigitalOcean** $180/tháng | Chat history là read-heavy |
| 10M | Distributed SQL | **CockroachDB** 3-region $3,000/tháng | Global, self-healing |

[3][4][5]

### Qdrant — Vector Memory

| Lưu gì | Ví dụ |
|---|---|
| Facts về user | "User thích nhạc RPG", "User sống với bố" |
| Emotional memories | "User từng kể chuyện buồn về ex" |
| Character knowledge | Backstory, relationships |

**Scale theo phase:**

| Phase | Setup | Nhà cung cấp |
|---|---|---|
| 10K | In-memory | **Qdrant Free tier** $0 (~1M vectors) |
| 100K | Cloud | **Qdrant Cloud** $50/tháng |
| 1M | Cloud | **Qdrant Cloud** $200/tháng |
| 10M | Sharded cluster 3-region | **Qdrant Cloud** $3,000/tháng |

[6][7]

### Redis — Cache & Session & Queue

| Lưu gì | TTL | Ý nghĩa |
|---|---|---|
| Session state | 24h | `user_123 → { char: "sol", affection: 45 }` |
| Rate limit counter | 24h | `user_123_msgs → 47` (chặn Free >50/ngày) |
| Prompt cache | 1h | System prompt đã build sẵn |
| Online status | 5min | Ai đang online |
| **Request queue** | Real-time | Xếp hàng requests khi GPU bận |

**Scale theo phase:**

| Phase | Setup | Nhà cung cấp |
|---|---|---|
| 10K | Managed | **GalaxyCloud Starter** 1GB — $14.99/tháng |
| 100K | Managed HA | **GalaxyCloud Standard** 2GB — $34.99/tháng |
| 1M | Sentinel 3-node | **GalaxyCloud Premium** 8GB — $94.99/tháng |
| 10M | Cluster 6-node 64GB/node | **Redis Enterprise** — $2,000/tháng |

[8][9]

***

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

### Auto-scale triggers

| Condition | Action |
|---|---|
| Queue depth > 50, liên tục 2 phút | Spin up thêm GPU |
| Queue depth > 200 | Spin up 2 GPU + alert |
| Queue < 10 VÀ GPU util < 20%, 15 phút | Shutdown GPU thừa |
| Queue = 0 VÀ GPU util < 10%, 30 phút | Shutdown tới minimum |

**Khi nào chuyển Redis Streams → Kafka:** 1M+ MAU (throughput cao hơn, replay log).

***

## VI. GPU DEPLOY THEO TỪNG MỨC

### 🟢 10K MAU — Single Server

```
1× L40S (RunPod Secure Cloud)
├── vLLM: Qwen3.5-4B Q8 (~5GB) + Qwen3.5-9B Q8 (~10GB)
│   └── 4B: ~1,200 tok/s | 9B: ~500 tok/s
├── Embedding: Qwen3-Embedding-0.6B (GPU, ~1GB)
├── PostgreSQL: Supabase Pro
├── Redis: GalaxyCloud 1GB
└── Qdrant: Free tier (in-memory)
    Không cần queue — request đi thẳng vào vLLM.
```

| Dịch vụ | /tháng |
|---|---|
| L40S × 1 ($0.79/hr × 720h) | $569 |
| App Server | $20 |
| PostgreSQL (Supabase Pro) | $25 |
| Redis (GalaxyCloud 1GB) | $15 |
| Qdrant (Free) | $0 |
| Grafana (Free) | $0 |
| **TỔNG** | **$629** |

***

### 🔵 100K MAU — Small Cluster

```
4× L40S (vLLM workers)
├── Load balancer phân request đều
│   └── Tổng: ~4,800 tok/s, ~250 concurrent
├── Embedding: 1 CPU server
├── PostgreSQL Managed (DigitalOcean)
├── Redis (GalaxyCloud 2GB, HA)
└── Qdrant Cloud (10GB)
```

| Dịch vụ | /tháng |
|---|---|
| L40S × 4 ($0.79/hr × 720h) | $2,276 |
| App Server | $60 |
| PostgreSQL (DigitalOcean) | $60 |
| Redis (GalaxyCloud 2GB) | $35 |
| Qdrant Cloud | $50 |
| Grafana (Free) | $0 |
| **TỔNG** | **$2,481** |

***

### 🟡 1M MAU — Production Cluster

```
12× L40S
├── 9× L40S (24/7 base)
│   └── Tổng base: ~10,800 tok/s
├── Prefix Caching ON

├── Embedding: 1× GPU T4
├── PostgreSQL (1 primary + 2 read replicas, DigitalOcean)
├── Redis (GalaxyCloud Premium 8GB, Sentinel)
├── Qdrant Cloud (50GB, sharded)
└── Request queue: Redis Streams với priority
```

| Dịch vụ | /tháng |
|---|---|
| L40S × 9 ($0.79/hr × 720h) | $5,121 |
| App Server | $150 |
| PostgreSQL (DO cluster) | $180 |
| Redis (GalaxyCloud 8GB) | $95 |
| Qdrant Cloud | $200 |
| Grafana Pro | $19 |
| **TỔNG** | **$5,765** |

***

### 🔴 10M MAU — Global Scale

#### Multi-model tiers

| Tier | Model | Users | GPU L40S cần |
|---|---|---|---|
| Free | Qwen3.5-4B Q8 | 8.5M (85%) | 120–150 |
| Plus | Qwen3-8B FP8 | 1.2M (12%) | 80–100 |
| Ultra | Qwen3.5-14B Q8 | 300K (3%) | 40–50 |
| **Tổng** | | **10M** | **240–300** |
| **+ Buffer 20%** | | | **~300–360** |

#### Tối ưu GPU

| Kỹ thuật | Tiết kiệm |
|---|---|
| Prefix Caching | −30–40% compute |
| Q8 Quantization | −40% VRAM vs FP16 |
| Continuous Batching | +3× vs static |

| Speculative Decoding | +1.5–2× speed |

Áp dụng đủ → giảm xuống còn **~250 GPU**.

#### Chi phí GPU (Mixed 70/30 on-demand/reserved)

| Option | /tháng |
|---|---|
| On-demand thuần ($0.79 × 350 GPU) | $199,080 |
| Reserved thuần ($0.55 × 350 GPU) | $138,600 |
| **Mixed 70/30 (sau tối ưu 250 GPU)** | **$111,960** |

175 GPU reserved × $0.55 × 720h = $69,300 + 75 GPU on-demand × $0.79 × 720h = $42,660[10][11]

#### Chi phí Data layer 10M MAU

| Hạng mục | /tháng |
|---|---|
| CockroachDB (3-region, 5TB) | $3,000 |
| Redis Enterprise Cluster (6-node, 64GB/node) | $2,000 |
| Qdrant Cloud (500GB, 3-region) | $3,000 |
| Kafka (3 brokers) | $1,500 |
| Embedding (3× T4) | $432 |
| **Subtotal Data** | **$9,932** |

#### Tổng 10M MAU

| Category | /tháng |
|---|---|
| GPU Inference | $111,960 |
| Data layer | $9,932 |
| Monitoring (Grafana Pro) | $5,000 |
| **TỔNG** | **~$126,892** |

***

## VII. GPU PROVIDER SO SÁNH

| Provider | GPU | Giá/giờ | Độ ổn định | Phù hợp giai đoạn |
|---|---|---|---|---|
| **RunPod Secure Cloud** *(khuyến nghị)* | L40S | **$0.79** | Cao — SOC 2 | MVP → 1M MAU |
| RunPod Community Cloud | L40S | $0.40 | Thấp | Dev/staging |
| Vast.ai | L40S | $0.47–0.65 | Trung bình | Thử nghiệm |
| CoreWeave | L40S | $0.74 | Rất cao — enterprise SLA | 1M+ MAU |
| Lambda Labs | L40S | $1.29 | Rất cao | Khi cần SLA chặt |
| AWS / GCP | L40S equiv | $1.50–2.00+ | Enterprise | Compliance/Enterprise |

[11][12][13][10]

Lộ trình: **RunPod** (MVP → 100K) → **CoreWeave** (1M) → **Mixed CoreWeave + Dedicated** (10M).

***

## VIII. MONITORING

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
vLLM /metrics → Prometheus (15s interval) → Grafana Cloud
                                             ├── Dashboard: GPU cluster health
                                             ├── Dashboard: Latency & queue
                                             ├── Alert → Slack/Telegram
                                             └── Alert → Auto-scale trigger
```

| Plan Grafana | Giá | Phù hợp |
|---|---|---|
| Free | $0 | 10K–100K MAU |
| Pro | $19/tháng | 1M MAU |
| Enterprise | ~$5,000/tháng | 10M MAU |

[14][15]

***

## IX. TỔNG HỢP CHI PHÍ

| Scale | GPU | Data | Monitor | **Tổng/tháng** | **Chi phí/user** |
|---|---|---|---|---|---|
| **10K** | $569 | $60 | $0 | **$629** | $0.063 |
| **100K** | $2,276 | $205 | $0 | **$2,481** | $0.025 |
| **1M** | $5,121 | $625 | $19 | **$5,765** | $0.006 |
| **10M** | $111,960 | $9,932 | $5,000 | **$126,892** | $0.013 |

***

## X. TỔNG KẾT

| Câu hỏi | Trả lời |
|---|---|
| **Chat model?** | Qwen3.5-4B Q8 (4B params, context 262K tokens) |
| **Char-gen model?** | Qwen3.5-9B Q8 (chỉ dùng khi tạo nhân vật) |
| **Embedding?** | Qwen3-Embedding-0.6B (1024 dims, 100+ languages) |
| **Serving?** | vLLM — continuous batching, prefix cache, streaming |
| **GPU?** | L40S $0.79/hr (RunPod) — sweet spot giá/hiệu năng |
| **Database?** | Supabase → DigitalOcean → CockroachDB (10M) |
| **Vector memory?** | Qdrant: Free → Cloud → Sharded 3-region |
| **Cache + Queue?** | Redis GalaxyCloud → Redis Enterprise |
| **Monitor?** | Prometheus + Grafana Cloud, alert Slack, auto-scale |
| **Cost 10K?** | **$629/tháng** |
| **Cost 1M?** | **$5,765/tháng** |
| **Cost 10M?** | **$126,892/tháng** |

