# 🚀 BÁO CÁO: AI INFERENCE, DATA, SCALING — DEPLOY & CHI PHÍ
### DokiChat AI Companion | 10/03/2026

***

## I. MODELS

### Chat Model — Qwen3.5-4B (uncensored fine-tune)

| Thông số | Giá trị |
|---|---|
| **Params** | 4B (text model) / 5B tổng với vision encoder |
| **Quantization** | GGUF Q8 |
| **VRAM weights** | ~4.5 GB |
| **Context window** | 262,144 tokens native (~1M với YaRN) |
| **Kiến trúc** | Hybrid Gated DeltaNet + Sparse MoE, 32 layers |
| **Trạng thái** | ✅ Dùng sẵn, không cần fine-tune. Đã kiểm chứng — chất lượng ngang ngửa, một số trường hợp vượt app gốc |

### Char-gen Model — Qwen3.5-9B (uncensored fine-tune)

| Thông số | Giá trị |
|---|---|
| **Params** | 9B (text model) / 10B tổng với vision encoder |
| **Quantization** | GGUF Q8 |
| **VRAM weights** | ~9.5 GB |
| **Context window** | 262,144 tokens native |
| **Tần suất** | Chỉ gọi khi tạo nhân vật (~1% MAU/tháng) |
| **Tokens/lần tạo** | ~7,644 tokens (2 LLM calls: generate_character + generate_emotional_states) |
| **Trạng thái** | ✅ Co-locate cùng 4B trên L40S — không cần GPU riêng ở bất kỳ scale nào |

### Embedding Model — Qwen3-Embedding-0.6B

| Thông số | Giá trị |
|---|---|
| **Dims** | 1,024 |
| **Precision** | BF16 |
| **VRAM** | ~1.0 GB |
| **Dùng cho** | Tìm kiếm memory ngữ nghĩa trong Qdrant |
| **Trạng thái** | ✅ Co-locate cùng 4B + 9B trên L40S — không cần server riêng |

> **Cả 3 model đều off-the-shelf** — tải về chạy ngay, không phát sinh chi phí fine-tune, không cần dataset, không cần GPU training.

***

### VRAM Layout — L40S 48GB (3 process vLLM độc lập)

```
L40S 48GB VRAM
├── 9B  process  --gpu-memory-utilization 0.35
│   ├── Weights:     9.5 GB
│   └── KV Cache:    7.3 GB  (đủ cho char-gen, tần suất thấp)
│
├── 4B  process  --gpu-memory-utilization 0.35
│   ├── Weights:     4.5 GB
│   └── KV Cache:   12.3 GB  ← lớn hơn vì chat liên tục, ~50–60 concurrent
│
├── Embed process  --gpu-memory-utilization 0.10
│   ├── Weights:     1.0 GB
│   └── Buffer:      3.8 GB
│
└── System buffer (20%):     9.6 GB  ← tránh OOM, CUDA Graphs, nền
    ─────────────────────────────────
    Tổng: 48GB — 0 OOM risk ✅
```

**Lệnh khởi động:**
```bash
# 9B — Char-gen
vllm serve <path_9b> --port 8000 \
  --gpu-memory-utilization 0.35 \
  --max-model-len 8192

# 4B — Chat chính
vllm serve <path_4b> --port 8001 \
  --gpu-memory-utilization 0.35 \
  --max-model-len 8192

# Embedding
vllm serve <path_embed> --port 8002 \
  --gpu-memory-utilization 0.10 \
  --enforce-eager
```

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
| **OpenAI-compatible API** | Đổi từ LM Studio sang vLLM chỉ cần đổi base URL |

### Throughput trên các GPU (Qwen3.5-4B Q8, vLLM)

| GPU | VRAM | 4B Q8 tok/s | 9B Q8 tok/s | Concurrent users |
|---|---|---|---|---|
| **L40S** *(khuyến nghị)* | 48 GB | **~1,200** | ~500 | 50–80 |
| A100 80GB | 80 GB | ~900 | ~700 | 60–100 |
| H100 | 80 GB | ~1,800 | ~1,200 | 80–120 |
| RTX 4090 *(dev/staging)* | 24 GB | ~550 | — | 30–50 |

### Tại sao không dùng RunPod Serverless?

| Tiêu chí | Serverless | Secure Cloud Pods |
|---|---|---|
| Cold start | 30–90s load 3 model | ❌ Chat real-time không chấp nhận được |
| Giá baseline (30 warm workers) | $1.33 × 30 × 720 = **$28,728** | $0.71 × 30 × 720 = **$15,336** |
| KV cache prefix caching | ❌ Kém hiệu quả | ✅ Tối ưu persistent server |
| **Kết luận** | ❌ Đắt hơn 1.9×, UX kém | ✅ Dùng Secure Cloud Pods |

### KV Cache — Hoàn toàn tự động

| Tình huống | Kết quả |
|---|---|
| User quay lại sau vài phút | Cache còn nguyên → prefill ~200ms |
| User quay lại sau vài giờ, VRAM đầy | Cache bị đuổi → prefill bình thường, không mất data |
| System prompt cùng nhân vật | Shared cache toàn bộ user cùng nhân vật |
| **Giới hạn thực** | **Context window 262K tokens (~6,500 turns), không phải VRAM** |

***

## III. ƯỚC TÍNH TẢI

| Quy mô | MAU | DAU (20%) | Peak concurrent | Peak RPS | Concurrent thực tế |
|---|---|---|---|---|---|
| **500K** | 500,000 | 100,000 | 15,000 | 17 | **~7 request** |
| **1M** | 1,000,000 | 200,000 | 30,000 | 35 | ~14 request |
| **5M** | 5,000,000 | 1,000,000 | 150,000 | 174 | ~72 request |
| **10M** | 10,000,000 | 2,000,000 | 300,000 | 347 | ~144 request |

*Giả định: 20% DAU/MAU, 5 lượt chat/ngày/user, 7 phút/lượt. Mỗi request ~2.9s (3,500 tokens ÷ 1,200 tok/s).*

**GPU cần thiết:**

| Scale | Req/s trung bình | GPU baseline | GPU peak (3×) |
|---|---|---|---|
| 500K | ~6 | 2 GPU | 5 GPU |
| 1M | ~12 | 3 GPU | 9 GPU |
| 5M | ~58 | 15 GPU | 45 GPU |
| 10M | ~116 | 30 GPU | 90 GPU |

***

## IV. GPU PROVIDER

### Novita AI vs RunPod — Phân vai rõ ràng

| Tiêu chí | Novita AI | RunPod Secure Cloud |
|---|---|---|
| Giá on-demand L40S | **$0.55/hr** | $0.86/hr |
| Subscription 12 tháng | **$344/tháng** | $511/tháng |
| **Giới hạn GPU** | **Max 3 GPU** | Không giới hạn (raise quota) |
| REST API scale | ❌ Không | ✅ Có đầy đủ |
| Model image có sẵn | ✅ Qwen3.5 pre-built | ❌ Tự build Docker |
| SLA/SOC 2 | Chưa rõ | ✅ SOC 2 |
| **Dùng cho** | **Dev/staging** | **Production** |

> Novita rẻ hơn 36% nhưng bị giới hạn 3 GPU — không thể dùng cho production.[1][2]

### RunPod Secure Cloud — Pricing L40S

| Loại | Giá/giờ | Giá/tháng | Cam kết | Dùng khi |
|---|---|---|---|---|
| **On-Demand** | $0.86 | $619 | Không | Linh hoạt, thử nghiệm |
| **3 Month Savings** | $0.75 | $540 | 3 tháng | 500K MAU |
| **6 Month Savings** | $0.73 | $526 | 6 tháng | 1M MAU |
| **1 Year Savings** | $0.71 | $511 | 1 năm | 5M–10M (reserved baseline) |
| **Spot** | $0.26 | $187 | Không | Dev/staging — interruptible |

**Các provider khác:**

| Provider | Giá/giờ | Ổn định | Ghi chú |
|---|---|---|---|
| RunPod Community | $0.44 | Thấp | Dev/staging |
| Vast.ai | $0.47–0.65 | Trung bình | Community hardware |
| CoreWeave | $2.25 | Rất cao | Enterprise SLA, cluster 8× |
| AWS g6e reserved 3-yr | $0.70 | Enterprise | AWS compliance |
| Azure / GCP | ❌ | — | Không có L40S |

***

## V. AUTO-SCALING — RUNPOD REST API

### Tại sao không dùng Serverless để auto-scale?

Serverless cold start 30–90s load model → **UX thảm họa** cho chat real-time. Thay vào đó dùng **Secure Cloud Pods + REST API**:[3][4]

```python
# Autoscaler — cronjob 30s, ~20 dòng Python
import redis, requests, os

RUNPOD_TOKEN = os.getenv("RUNPOD_TOKEN")
queue_depth  = redis_client.llen("request_queue")
gpu_util     = get_gpu_utilization()  # từ Prometheus

# Scale UP
if queue_depth > 50:
    requests.post(
        "https://rest.runpod.io/v1/pods",
        headers={"Authorization": f"Bearer {RUNPOD_TOKEN}"},
        json={
            "gpuTypeIds": ["NVIDIA L40S"],
            "imageName":  "your-vllm-image:latest",
            "name":       "dokichat-worker-auto"
        }
    )

# Scale DOWN
elif queue_depth == 0 and gpu_util < 20:
    requests.delete(
        f"https://rest.runpod.io/v1/pods/{idle_pod_id}",
        headers={"Authorization": f"Bearer {RUNPOD_TOKEN}"}
    )
```

**Billing:** Per-minute — DELETE Pod ngay lập tức dừng tính tiền[5]

### Auto-scale triggers

| Condition | Action |
|---|---|
| Queue > 50, liên tục 2 phút | Spin up thêm 1 GPU |
| Queue > 200 | Spin up 2 GPU + alert Slack/Telegram |
| Queue < 10 VÀ util < 20%, 15 phút | Shutdown GPU thừa |
| Queue = 0 VÀ util < 10%, 30 phút | Shutdown về minimum reserved |

### Warm Pool — Tránh spin-up delay

| Vấn đề | Chi tiết |
|---|---|
| Spin-up time Pod | ~1–3 phút |
| Load 3 model vào VRAM | ~90 giây thêm |
| **Tổng từ trigger → ready** | **~4–5 phút** |
| **Giải pháp** | Giữ warm pool 5–10 GPU luôn sẵn sàng |
| Warm pool sẵn sàng | Scale ngay lập tức, không cần chờ |

### Raise GPU Quota

RunPod giới hạn quota mặc định khi mới tạo account. Để có 45–90 GPU lúc cần:[6]
- Liên hệ RunPod support từ giai đoạn 500K MAU
- Cung cấp lịch sử chi tiêu và forecast scale
- Hoặc ký commitment spend/tháng để raise limit

***

## VI. DATABASE & CACHING

### PostgreSQL — *(Đã có sẵn, không phát sinh chi phí mới)*

| Bảng | Vai trò trong AI pipeline |
|---|---|
| `character_configs` | System prompt, personality, safety rules — "linh hồn" nhân vật |
| `affection_state` | Stage inject vào prompt → nhân vật nói chuyện khác theo level |
| `chat_history` | Sliding window context — model cần biết hội thoại vừa rồi |
| `subscriptions` | Route request đến đúng tier |
| `users` | Rate limiting — chặn Free user >50 tin/ngày |

***

### Qdrant Cloud — Vector Memory *(nâng tier, không migrate)*

**Lưu gì:**

| Loại memory | Ví dụ |
|---|---|
| Facts về user | "User thích nhạc RPG", "User sống với bố" |
| Emotional memories | "User từng kể chuyện buồn về ex" |
| Character knowledge | Backstory, relationships |

**PostgreSQL vs Qdrant:**

| | PostgreSQL | Qdrant |
|---|---|---|
| Lưu gì | Cấu trúc cứng: history, config, score | Memory ngữ nghĩa: facts, cảm xúc |
| Truy xuất | ID, SQL filter | Similarity search (vector) |
| Câu hỏi | "20 tin nhắn gần nhất?" | "User đã kể gì về gia đình?" |
| Khi nào | **Mọi request** | Khi cần memory dài hạn |

**Scale:**

| Scale | Plan | Giá/tháng |
|---|---|---|
| 500K | Standard (~2.5M vectors) | $50 |
| 1M | Standard (~5M vectors) | $75 |
| 5M | Standard scale (~25M vectors) | $200 |
| 10M | Standard scale (~50M vectors) | $400 |

***

### Redis — GalaxyCloud *(nâng tier, không migrate)*

| Lưu gì | TTL | Ý nghĩa |
|---|---|---|
| Session state | 24h | `user_123 → { char: "sol", affection: 45 }` |
| Rate limit counter | 24h | `user_123_msgs → 47` |
| Prompt cache | 1h | System prompt đã build sẵn |
| Online status | 5min | Ai đang active |
| **Request queue** | Real-time | Xếp hàng khi GPU bận + trigger auto-scale |

**Scale:**

| Scale | Plan | RAM | Giá/tháng |
|---|---|---|---|
| 500K | **Standard** | 2 GB | $34.99 |
| 1M | **Premium** | 8 GB | $94.99 |
| 5M | **Plus** | 16 GB | $194.99 |
| 10M | **Ultra** | 32 GB | $394.99 |

***

## VII. REQUEST QUEUE — LOGIC XỬ LÝ

```
① User gửi message
    ↓
② API Server → validate → build prompt (query PostgreSQL + Qdrant)
    ↓
③ Push vào Redis Streams
    { request_id, user_id, prompt, timestamp, priority }
    ↓
④ vLLM Worker poll queue
    - Slot trống → xử lý ngay
    - Đầy slot → request chờ (không crash, không timeout)
    ↓
⑤ vLLM stream tokens → Redis pub/sub
    Channel: "response:{request_id}"
    ↓
⑥ API Server subscribe → stream token về User real-time
    ↓
⑦ Cronjob 30s kiểm tra queue depth
    → Gọi RunPod REST API spin up/down GPU
```

**Khi nào chuyển Redis Streams → Kafka:** 5M+ MAU nếu cần replay log, dead-letter queue và observability nâng cao.

***

## VIII. GPU DEPLOY THEO TỪNG MỨC

### 🟢 500K MAU — Bootstrap Production

```
3× L40S RunPod (3-month savings, $0.75/hr)
├── Baseline: 2 GPU luôn chạy
├── Auto-scale: +1 GPU lúc peak
├── Throughput: ~3,600 tok/s, xử lý ~7 concurrent thực tế
├── PostgreSQL: Đã có sẵn
├── Redis: GalaxyCloud Standard $34.99
└── Qdrant: Cloud Standard $50
    Dev/Staging: Novita AI $0.55/hr (max 3 GPU — đủ cho môi trường test)
```

| Dịch vụ | Chi phí/tháng |
|---|---|
| L40S × 3 (3-month savings) | $1,620 |
| PostgreSQL | *(đã có sẵn)* |
| Redis (GalaxyCloud Standard) | $35 |
| Qdrant Cloud Standard | $50 |
| Grafana (Free) | $0 |
| **TỔNG** | **$1,705** |
| **Chi phí/user** | **$0.003** |

***

### 🔵 1M MAU — Production Cluster

```
9× L40S RunPod (6-month savings, $0.73/hr)
├── Load balancer phân request đều 9 node
├── Throughput tổng: ~10,800 tok/s
├── Prefix Caching ON — system prompt shared theo nhân vật
├── PostgreSQL: Đã có sẵn (+ read replicas nếu cần)
├── Redis: GalaxyCloud Premium $94.99
└── Qdrant Cloud Standard $75
    Bắt đầu raise GPU quota với RunPod từ giai đoạn này.
```

| Dịch vụ | Chi phí/tháng |
|---|---|
| L40S × 9 (6-month $0.73/hr) | $4,731 |
| PostgreSQL | *(đã có sẵn)* |
| Redis (GalaxyCloud Premium) | $95 |
| Qdrant Cloud Standard | $75 |
| Grafana Pro | $19 |
| **TỔNG** | **$4,920** |
| **Chi phí/user** | **$0.005** |

***

### 🟡 5M MAU — Scale Cluster

```
15 GPU 1-Year Savings (baseline 24/7)
+ 5 GPU warm pool (on-demand, luôn sẵn sàng)
+ 0–25 GPU auto-scale (lúc peak ~6h/ngày)
─────────────────────────────────────────
Baseline:    15 × $0.71 × 720h   = $7,668
Warm pool:    5 × $0.86 × 720h   = $3,096
Auto-scale: ~15 avg × $0.86 × 180h = $2,322
Tổng GPU:                          = $13,086
```

| Dịch vụ | Chi phí/tháng |
|---|---|
| GPU (15 reserved + auto-scale) | $13,086 |
| PostgreSQL | *(đã có sẵn)* |
| Redis (GalaxyCloud Plus 16GB) | $195 |
| Qdrant Cloud Standard scale | $200 |
| Grafana Pro + usage | $54 |
| **TỔNG** | **$13,535** |
| **Chi phí/user** | **$0.003** |
| GPU (min/max) | 20 / 45 |

***

### 🔴 10M MAU — Global Scale

```
30 GPU 1-Year Savings (baseline 24/7)
+ 10 GPU warm pool (on-demand, luôn sẵn sàng)
+ 0–50 GPU auto-scale (lúc peak ~6h/ngày)
─────────────────────────────────────────
Baseline:    30 × $0.71 × 720h   = $15,336
Warm pool:   10 × $0.86 × 720h   = $6,192
Auto-scale: ~30 avg × $0.86 × 180h = $4,644
Tổng GPU:                          = $26,172
```

| Dịch vụ | Chi phí/tháng |
|---|---|
| GPU (30 reserved + auto-scale) | $26,172 |
| PostgreSQL | *(đã có sẵn)* |
| Redis (GalaxyCloud Ultra 32GB) | $395 |
| Qdrant Cloud Standard scale | $400 |
| Grafana Pro + usage | $54 |
| **TỔNG** | **$27,021** |
| **Chi phí/user** | **$0.003** |
| GPU (min/max) | 40 / 90 |

***

## IX. MONITORING

### Metrics cần track

| Metric | Alert khi | Lý do |
|---|---|---|
| **TTFT** (Time To First Token) | p95 > 500ms | User cảm thấy lag |
| **Queue depth** | > 100 requests | Cần thêm GPU ngay |
| **GPU utilization** | > 90% hoặc < 20% | Quá tải hoặc lãng phí |
| **VRAM usage** | > 95% | Sắp OOM |
| **Throughput** (tok/s) | < 80% capacity | Sắp cần scale |
| **Error rate** | > 1% | Vấn đề hệ thống |
| **p95 latency** | > 5s | UX kém |

### Stack

```
vLLM /metrics → Prometheus (15s scrape) → Grafana Cloud
                                           ├── Dashboard: GPU cluster health
                                           ├── Dashboard: Latency & queue depth
                                           ├── Alert → Slack/Telegram
                                           └── Alert → RunPod auto-scale script
```

| Plan | Giá | Phù hợp |
|---|---|---|
| Free | $0 | 500K MAU |
| Pro | $19/tháng | 1M MAU |
| Pro + usage | $54/tháng | 5M–10M MAU |

***

## X. GPU PROVIDER SO SÁNH ĐẦY ĐỦ

| Provider | GPU | Giá/giờ | Giới hạn | Dùng cho |
|---|---|---|---|---|
| **Novita AI** | L40S | $0.55 | **Max 3 GPU** | Dev/staging |
| RunPod Community | L40S | $0.44 | Không đảm bảo | Dev/staging |
| Vast.ai | L40S | $0.47–0.65 | Không đảm bảo | Thử nghiệm |
| **RunPod On-Demand** | L40S | $0.86 | Không (raise quota) | Production linh hoạt |
| **RunPod 3M Savings** | L40S | $0.75 | Không | 500K MAU |
| **RunPod 6M Savings** | L40S | $0.73 | Không | 1M MAU |
| **RunPod 1Y Savings** | L40S | $0.71 | Không | 5M–10M baseline |
| CoreWeave | L40S | $2.25 | Cluster 8× min | Enterprise SLA |
| AWS g6e reserved 3-yr | L40S | $0.70 | Enterprise | AWS compliance |
| Azure / GCP | ❌ | — | — | Không có L40S |

***

## XI. TỔNG HỢP CHI PHÍ

| Scale | GPU | Redis | Qdrant | Monitor | **Tổng/tháng** | **$/user** | GPU count |
|---|---|---|---|---|---|---|---|
| **500K** | $1,620 | $35 | $50 | $0 | **$1,705** | $0.003 | 3/5 |
| **1M** | $4,731 | $95 | $75 | $19 | **$4,920** | $0.005 | 9/9 |
| **5M** | $13,086 | $195 | $200 | $54 | **$13,535** | $0.003 | 20/45 |
| **10M** | $26,172 | $395 | $400 | $54 | **$27,021** | $0.003 | 40/90 |

*PostgreSQL không tính vào chi phí mới. Chi phí/user ổn định $0.003–0.005 xuyên suốt.*

***

## XII. TỔNG KẾT

| Câu hỏi | Trả lời |
|---|---|
| **Cần fine-tune?** | ❌ Không — cả 3 model off-the-shelf |
| **GPU riêng cho 9B/Embed?** | ❌ Không — co-locate cùng 1 L40S |
| **Serverless RunPod?** | ❌ Không — cold start 90s, đắt hơn 1.9× |
| **Novita AI cho production?** | ❌ Không — max 3 GPU, không có auto-scale API |
| **Novita AI cho dev/staging?** | ✅ Có — $0.55/hr, tiết kiệm 36% vs RunPod |
| **Auto-scale cơ chế?** | Script Python gọi RunPod REST API theo Redis queue |
| **Raise GPU quota khi nào?** | Liên hệ RunPod từ giai đoạn 1M MAU |
| **Migrate khi scale?** | ❌ Không — toàn bộ stack nâng tier trên dashboard |
| **GPU pricing tốt nhất?** | On-demand → 3M → 6M → 1-Year theo scale |
| **Cost 500K?** | **$1,705/tháng** ($0.003/user) |
| **Cost 1M?** | **$4,920/tháng** ($0.005/user) |
| **Cost 5M?** | **$13,535/tháng** ($0.003/user) |
| **Cost 10M?** | **$27,021/tháng** ($0.003/user) |

***

*Báo cáo AI + Data + Scaling — Team phát triển DokiChat — 10/03/2026*

Nguồn
[1] image.jpeg https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/images/171777705/3fab632f-3ded-4238-b37a-22fd5e7b8f71/image.jpeg
[2] L40S Balances AI, Graphics, and HPC Performance https://blogs.novita.ai/l40s-on-novita-ai-a-versatile-gpu-for-ai-graphics-and-hpc/
[3] Cost-Effective AI with Autoscaling on RunPod https://www.runpod.io/blog/runpod-autoscaling-cost-savings
[4] Streamline GPU Cloud Management with RunPod's New REST API https://www.runpod.io/blog/runpod-rest-api-gpu-management
[5] Cost-effective Computing with Autoscaling on RunPod https://runpod.ghost.io/cost-effective-computing-with-autoscaling-on-runpod-2/
[6] docs/docs/serverless/references/endpoint-configurations.md at main · runpod/docs https://github.com/runpod/docs/blob/main/docs/serverless/references/endpoint-configurations.md
