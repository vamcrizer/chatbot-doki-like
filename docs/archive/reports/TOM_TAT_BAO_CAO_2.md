# BÁO CÁO 2: TRIỂN KHAI & CHI PHÍ

***

## Model AI

### Model Chat chính — Qwen3.5-4B (DavidAU, BF16 Safetensors)

| Thông số | Giá trị |
|---|---|
| Model | DavidAU/Qwen3.5-4B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING |
| Format | **BF16 Safetensors** (sẵn có, không cần convert) |
| Context length | 262,144 tokens native (~1M với YaRN) |
| VRAM (đo thực tế H100) | **~9 GB** (weights + KV cache inference) |
| Throughput trên L40S (dự kiến) | ~1,200 tok/s (vLLM, batch mode) |
| Tokens per turn | 2,500–4,500 tokens |
| Custom Jinja | ✅ Bắt buộc — anti-repeat + enable_thinking=false |
| Trạng thái | ✅ **Đã test 5 runs trên H100** — production ready |

### Model Tạo nhân vật — Qwen3.5-9B (DavidAU HighIQ-INSTRUCT, BF16 Safetensors)

| Thông số | Giá trị |
|---|---|
| Model | DavidAU/Qwen3.5-9B-Claude-4.6-HighIQ-INSTRUCT-HERETIC-UNCENSORED |
| Format | **BF16 Safetensors** (sẵn có, không cần convert) |
| Context length | 262,144 tokens native |
| VRAM (đo thực tế H100) | **~18 GB** (tại load) |
| Throughput trên L40S (dự kiến) | ~500 tok/s |
| Tokens per lần tạo nhân vật | ~2,600–3,400 tokens (1 LLM call) |
| Tần suất sử dụng | Thấp — chỉ khi tạo nhân vật mới (~1% MAU/tháng) |
| Trạng thái | ✅ **Đã test 2 runs trên H100** — chargen chất lượng cao |

### Embedding Model — Qwen3-Embedding-0.6B

| Thông số | Giá trị |
|---|---|
| Embedding dimensions | 1,024 |
| VRAM | ~1.0 GB |
| Dùng cho | Tìm kiếm memory ngữ nghĩa trong Qdrant |
| Trạng thái | ✅ Co-locate cùng 4B + 9B trên L40S, không cần server riêng |

> **Cả 3 model đều off-the-shelf BF16 Safetensors** — tải về chạy ngay trên vLLM, không cần convert, không cần fine-tune, không cần GPU training.

```
L40S 48GB VRAM — Co-locate 3 model (đo thực tế trên H100)
├── 4B  process: weights + KV cache          =  ~9GB
├── 9B  process: weights (load khi cần)      = ~18GB
├── Embed process: weights + buffer          =  ~2GB
└── Còn lại: headroom cho concurrent users   = ~19GB ✅
    Tổng: ~28GB / 48GB — 0 OOM risk
```

***

## Kiến trúc Triển khai

| Thành phần | Công nghệ | Chức năng |
|---|---|---|
| AI Inference | **vLLM** | Chạy model, stream token, continuous batching, tự quản lý KV cache (LRU) |
| Database | **PostgreSQL** *(đã có sẵn)* | Nguồn dữ liệu build prompt: chat history, character config, affection state |
| Vector DB | **Qdrant Cloud** | Lưu + tìm kiếm memory ngữ nghĩa — nâng tier trực tiếp đến 10M MAU |
| Cache & Queue | **Redis (GalaxyCloud)** | Session, rate limit, queue — nâng tier trực tiếp đến 10M MAU |
| Monitoring | **Prometheus + Grafana Cloud** | Theo dõi GPU utilization, latency, auto-scale |
| GPU | **NVIDIA L40S — RunPod Secure Cloud** | Thêm instance qua API, không cần migrate |

> **Toàn bộ stack từ 500K → 10M MAU chỉ nâng tier trên dashboard, không cần migrate hay self-host.** PostgreSQL là hạ tầng hiện có, không phát sinh chi phí mới.

***

## Nhà cung cấp dịch vụ

### GPU — NVIDIA L40S (RunPod Secure Cloud)

| Loại | Giá/giờ | Giá/tháng | Cam kết | Phù hợp |
|---|---|---|---|---|
| **On-Demand** | $0.86 | $619 | Không | Linh hoạt, thử nghiệm |
| **3 Month Savings** | $0.75 | $540 | 3 tháng | 500K MAU |
| **6 Month Savings** | $0.73 | $526 | 6 tháng | 1M MAU |
| **1 Year Savings** | $0.71 | $511 | 1 năm | 5M–10M MAU (baseline reserved) |
| **Spot** | $0.26 | $187 | Không | Dev/staging only — interruptible |

**Nhà cung cấp khác:**

| Provider | Giá/giờ | Ổn định | Ghi chú |
|---|---|---|---|
| RunPod Community Cloud | $0.44 | Thấp | Dev/staging |
| Vast.ai | $0.47–0.65 | Trung bình | Community hardware |
| CoreWeave | $2.25 | Rất cao | Enterprise SLA, cluster 8× |
| AWS g6e reserved 3-yr | $0.70 | Enterprise | AWS compliance |
| Azure / GCP | ❌ | — | Không có L40S |

> L40 (không phải L40S) trên RunPod **$0.99/hr** — đắt hơn nhưng hiệu năng AI kém hơn. Không nên dùng.

### Redis — GalaxyCloud *(nâng tier, không migrate)*

| Plan | RAM | Giá/tháng | Phù hợp |
|---|---|---|---|
| **Standard** | 2 GB | $34.99 | 500K MAU |
| **Premium** | 8 GB | $94.99 | 1M MAU |
| **Plus** | 16 GB | $194.99 | 5M MAU |
| **Ultra** | 32 GB | $394.99 | 10M MAU |

### Vector DB — Qdrant Cloud *(nâng tier, không migrate)*

| Plan | Giá/tháng | Phù hợp |
|---|---|---|
| **Standard** | $50 | 500K MAU (~2.5M vectors) |
| **Standard** | $75 | 1M MAU (~5M vectors) |
| **Standard scale** | $200 | 5M MAU (~25M vectors) |
| **Standard scale** | $400 | 10M MAU (~50M vectors) |

### Monitoring — Grafana Cloud *(nâng tier, không migrate)*

| Plan | Giá/tháng | Phù hợp |
|---|---|---|
| **Free** | $0 | 500K MAU |
| **Pro** | $19 | 1M MAU |
| **Pro + usage** | $54 | 5M–10M MAU |

***

## Auto-scaling GPU

Không dùng Serverless — **Secure Cloud + script Python gọi RunPod API** theo queue depth Redis:

- **500K–1M MAU:** On-demand + Savings Plan, scale thủ công khi cần
- **5M–10M MAU:** 1-Year Savings (baseline 24/7) + warm pool + auto-scale lúc peak

```
Queue > 50 requests   → spin up thêm GPU (RunPod API)
GPU util < 20%, 15ph  → shutdown instance thừa
vLLM KV cache         → tự quản lý LRU, không can thiệp
```

***

## Chi phí theo Quy mô

**GPU breakdown 5M và 10M MAU:**

**5M MAU:**
```
1-Year reserved:  15 GPU × $0.71 × 720h  = $7,668
Warm pool:         5 GPU × $0.86 × 720h  = $3,096
Auto-scale peak: ~15 avg × $0.86 × 180h  = $2,322
Tổng GPU 5M:                              = $13,086
```

**10M MAU:**
```
1-Year reserved:  30 GPU × $0.71 × 720h  = $15,336
Warm pool:        10 GPU × $0.86 × 720h  = $6,192
Auto-scale peak: ~30 avg × $0.86 × 180h  = $4,644
Tổng GPU 10M:                             = $26,172
```

| Dịch vụ | 500K MAU | 1M MAU | 5M MAU | 10M MAU |
|---|---|---|---|---|
| GPU — L40S | $1,620 *(3× 3-month)* | $4,731 *(9× 6-month)* | $13,086 *(15 reserved + auto-scale)* | $26,172 *(30 reserved + auto-scale)* |
| PostgreSQL | *(đã có sẵn)* | *(đã có sẵn)* | *(đã có sẵn)* | *(đã có sẵn)* |
| Redis (GalaxyCloud) | $35 | $95 | $195 | $395 |
| Qdrant Cloud | $50 | $75 | $200 | $400 |
| Monitoring — Grafana | $0 | $19 | $54 | $54 |
| **Tổng/tháng** | **$1,705** | **$4,920** | **$13,535** | **$27,021** |
| **Chi phí/user** | **$0.003** | **$0.005** | **$0.003** | **$0.003** |
| Số GPU (min/max) | 3/5 | 9/9 | 20/45 | 40/90 |

*Chi phí/user ổn định quanh $0.003–0.005 từ 500K trở lên — hệ thống scale hiệu quả.*

***

*Báo cáo 2 — 10/03/2026*

Nguồn
