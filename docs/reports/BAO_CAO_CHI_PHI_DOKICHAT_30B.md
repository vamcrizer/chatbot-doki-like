# BÁO CÁO CHI PHÍ PRODUCTION — DokiChat
## Model: Qwen3-30B-A3B-FP8 (BASE — thinking OFF)
## Nền tảng: RunPod Secure Cloud
## Cập nhật: 19/03/2026

---

> Độ tin cậy của từng số liệu:
> - [V] Verified — xác minh từ RunPod console, docs, hoặc model card
> - [B] Benchmarked — đo thực tế trên H100 80GB (19/03/2026)
> - [E] Estimate — ước tính từ benchmark hoặc giả định kinh doanh
> - [T] Needs Test — cần kiểm tra thực tế

---

## 1. QUYẾT ĐỊNH

| Hạng mục | Quyết định | Độ tin cậy |
|----------|-----------|------------|
| Model | Qwen/Qwen3-30B-A3B-FP8 (BASE, thinking OFF) | [V] HuggingFace |
| Kiến trúc | MoE — 30B tổng, 3B active per token | [V] Model card |
| Weights | FP8 checkpoint (official) | [V] HuggingFace |
| KV cache | BF16 (FP8 KV bị block trên FP8 checkpoint) | [B] Confirmed |
| Thinking | OFF — chat_template hoặc chat_template_kwargs | [V] Qwen docs |
| Framework | vLLM + OpenAI-compatible API | [V] |
| Cloud | Secure Cloud (SOC2, dedicated) | [V] Console |
| GPU chiến lược | L40S (< 1M MAU), RTX PRO 6000 (1M+ MAU) | [E] |

Tại sao BASE thay vì Instruct: Instruct model bị English narration bias nghiêm trọng
cho đa ngôn ngữ (ES 4/10, ID 3/10). BASE model đạt 8.5-9/10 cho tất cả 6 ngôn ngữ.

---

## 2. THÔNG SỐ MODEL

| Thông số | Giá trị | Độ tin cậy |
|----------|---------|------------|
| Tổng parameters | 30B | [V] Model card |
| Active parameters/token | 3B (MoE routing) | [V] Model card |
| Kích thước FP8 model (VRAM) | ~16 GB | [B] Đo trên H100 |
| vLLM overhead | ~3 GB | [B] Đo trên H100 |
| Tổng VRAM cơ bản | ~19 GB | [B] |
| KV cache dtype | BF16 (FP8 bị block) | [B] Confirmed |
| KV cache / user @4K context (BF16) | ~0.8 GB | [E] |
| KV cache / user @8K context (BF16) | ~1.6 GB | [E] |

Lưu ý:
- MoE: Toàn bộ 30B params load vào VRAM. Chỉ tiết kiệm COMPUTE (3B active/token).
- VRAM model ~16GB, không phải ~30GB.
- FP8 KV cache BỊ BLOCK: vLLM báo lỗi "ValueError: fp8_e5m2 kv-cache not supported
  with fp8 checkpoints". Chưa có workaround chính thức (confirmed 19/03/2026).

---

## 3. HỖ TRỢ PHẦN CỨNG FP8

| GPU | Kiến trúc | Native FP8 | vLLM mode | KV cache FP8 |
|-----|-----------|-----------|-----------|-------------|
| L40S 48GB | Ada Lovelace (CC 8.9) | Có | W8A8 native | Có (với BF16 checkpoint) |
| A100 SXM 80GB | Ampere (CC 8.0) | Không | W8A16 Marlin | Cần test |
| H100 SXM 80GB | Hopper (CC 9.0) | Có | W8A8 native | Có (với BF16 checkpoint) |
| RTX PRO 6000 96GB | Blackwell (CC 12.0) | Có | W8A8 native | Có (với BF16 checkpoint) |

Lưu ý A100: Weights lưu FP8 (~16GB) — tiết kiệm bộ nhớ. Compute dequantize sang
BF16 nên chậm hơn native FP8.

---

## 4. GIÁ SECURE CLOUD — [V] Từ RunPod Console (18/03/2026)

### 4.1 Pods

| GPU | VRAM | On-Demand | 3-Month | 6-Month | 1-Year | Spot |
|-----|------|-----------|---------|---------|--------|------|
| L40S | 48GB | $0.86/hr | $0.75/hr | $0.73/hr | $0.71/hr | $0.26/hr |
| A100 SXM | 80GB | $1.49/hr | $1.30/hr | $1.27/hr | $1.22/hr | $0.95/hr |
| RTX PRO 6000 | 96GB | $1.69/hr | $1.59/hr | $1.47/hr | $1.44/hr | $1.19/hr |
| H100 SXM | 80GB | $2.69/hr | — | — | — | $1.75/hr |

Tất cả giá verified trực tiếp từ RunPod Console deploy page.
H100 SXM: Không có savings plan — chỉ On-Demand và Spot.
Billing theo GIÂY.

### 4.2 Tổng Savings Plan

| GPU | 3 tháng | 6 tháng | 1 năm |
|-----|---------|---------|-------|
| L40S | $1,651.58 | $3,228.10 | $6,175.80 |
| A100 SXM | $2,870.40 | $5,608.32 | $10,687.20 |
| RTX PRO 6000 | $3,510.72 | $6,491.52 | $12,614.40 |

### 4.3 Lưu trữ — [V]

| Loại | Giá |
|------|-----|
| Container/Volume disk (đang chạy) | $0.10/GB/tháng |
| Volume disk (đã dừng) | $0.20/GB/tháng |
| Network volume (<1TB) | $0.07/GB/tháng |
| Network volume (>1TB) | $0.05/GB/tháng |
| Model weights (~16GB FP8) | ~$1.12/tháng |

### 4.4 Vòng đời Pod — [V]

| Quy tắc | Chi tiết |
|---------|---------|
| Billing | Theo GIÂY |
| Stop pod | GPU giải phóng, /workspace giữ lại, container disk XÓA |
| Terminate | Mọi thứ xóa |
| Pod + network volume | Chỉ terminate, không stop được |

---

## 5. HIỆU NĂNG — [B] H100 Benchmark + [E] Ước tính

### 5.1 H100 SXM — [B] Đo thực tế 19/03/2026

| Chỉ số | Giá trị |
|--------|---------|
| Single tok/s | 164 |
| TTFT | 76ms |
| E2E (200 token) | 1.2s |
| Peak throughput | 6,011 tok/s @ N=96 |
| Max concurrent (p95 < 5s) | 128 |
| Max concurrent (p95 < 10s) | 128+ (chưa đạt trần) |
| Cấu hình | FP8 checkpoint, BF16 KV, thinking OFF |

### 5.2 Tốc độ — Tất cả GPU

| GPU | Chế độ FP8 | Tok/s (single) | TTFT | E2E (200 tok) | Độ tin cậy |
|-----|-----------|---------------|------|--------------|------------|
| L40S | Native | ~87 | ~140ms | ~2.3s | [E] 0.53x H100 |
| A100 SXM | Marlin W8A16 | ~70 | ~200ms | ~2.9s | [E] |
| H100 SXM | Native | 164 | 76ms | 1.2s | [B] |
| RTX PRO 6000 | Native | ~87 | ~140ms | ~2.3s | [E] 0.53x H100 BW |

PRO 6000 scaling = tỷ lệ băng thông (1.79TB/s / 3.35TB/s = 0.53x) cho MoE decode.

### 5.3 Khả năng xử lý đồng thời — BF16 KV cache

| GPU | VRAM | Model+OH | KV khả dụng | KV/user @4K | Đồng thời | Độ tin cậy |
|-----|------|---------|------------|------------|-----------|------------|
| L40S | 48GB | 19GB | 29GB | 0.8GB | ~36 | [E] |
| A100 SXM | 80GB | 19GB | 61GB | 0.8GB | ~76 | [E] |
| H100 SXM | 80GB | 19GB | 61GB | 0.8GB | 128 | [B] Đo thực tế |
| RTX PRO 6000 | 96GB | 19GB | 77GB | 0.8GB | ~96 | [E] |

H100 đo thực tế: 128 concurrent p95 < 5s.
PRO 6000 có nhiều VRAM nhất (77GB KV) nhưng băng thông thấp hơn,
nên concurrent bị giới hạn bởi compute, không phải VRAM.

---

## 6. MÔ HÌNH LƯU LƯỢNG — [E]

| Tham số | Giá trị |
|---------|---------|
| DAU/MAU | 30% |
| Peak concurrent (% DAU) | 8% |
| Tỷ lệ đang chat | 50% |
| Duty cycle | ~1.5% |
| Hệ số burst | 1.3x |

### Burst Concurrent cần xử lý:

| MAU | Burst Concurrent |
|-----|-----------------|
| 100K | 17 |
| 500K | 85 |
| 1M | 169 |
| 5M | 843 |
| 10M | 1,685 |

---

## 7. CHI PHÍ THEO GPU — Secure Cloud Pods

### Mô hình lưu lượng

| Thời gian | Khoảng | % công suất |
|-----------|--------|------------|
| Cao điểm | 6h (20h-02h) | 100% |
| Ban ngày | 12h (08h-20h) | 50% |
| Đêm khuya | 6h (02h-08h) | 25% |

Công thức: (Peak x 6 + Day x 12 + Night x 6) x 30 = pod-hours/tháng

---

### 7.1 L40S 48GB — ~36 đồng thời (BF16 KV) — $0.86/hr SC

| MAU | Cao điểm | Ban ngày | Đêm | Pod-hrs/tháng | $0.86 OD | $0.71 1yr |
|-----|---------|---------|-----|-------------|----------|----------|
| 100K | 1 | 1 | 1 | 720 | $619 | $511 |
| 500K | 3 | 2 | 1 | 1,260 | $1,084 | $895 |
| 1M | 5 | 3 | 1 | 2,160 | $1,858 | $1,534 |
| 5M | 22 | 11 | 4 | 8,280 | $7,121 | $5,879 |
| 10M | 43 | 22 | 7 | 15,660 | $13,468 | $11,119 |

---

### 7.2 A100 SXM 80GB — ~76 đồng thời (BF16 KV) — $1.49/hr SC

| MAU | Cao điểm | Ban ngày | Đêm | Pod-hrs/tháng | $1.49 OD | $1.22 1yr |
|-----|---------|---------|-----|-------------|----------|----------|
| 100K | 1 | 1 | 1 | 720 | $1,073 | $878 |
| 500K | 2 | 1 | 1 | 900 | $1,341 | $1,098 |
| 1M | 3 | 2 | 1 | 1,260 | $1,877 | $1,537 |
| 5M | 15 | 8 | 3 | 5,580 | $8,314 | $6,808 |
| 10M | 29 | 15 | 5 | 10,260 | $15,287 | $12,517 |

---

### 7.3 RTX PRO 6000 96GB — ~96 đồng thời (BF16 KV) — $1.69/hr SC

| MAU | Cao điểm | Ban ngày | Đêm | Pod-hrs/tháng | $1.69 OD | $1.44 1yr |
|-----|---------|---------|-----|-------------|----------|----------|
| 100K | 1 | 1 | 1 | 720 | $1,217 | $1,037 |
| 500K | 1 | 1 | 1 | 720 | $1,217 | $1,037 |
| 1M | 2 | 1 | 1 | 900 | $1,521 | $1,296 |
| 5M | 6 | 3 | 1 | 2,520 | $4,259 | $3,629 |
| 10M | 11 | 6 | 2 | 4,500 | $7,605 | $6,480 |

---

### 7.4 H100 SXM 80GB — 128 đồng thời (BF16 KV, [B]) — $2.69/hr SC

Không có savings plan — chỉ On-Demand.

| MAU | Cao điểm | Ban ngày | Đêm | Pod-hrs/tháng | $2.69 OD |
|-----|---------|---------|-----|-------------|----------|
| 100K | 1 | 1 | 1 | 720 | $1,937 |
| 500K | 1 | 1 | 1 | 720 | $1,937 |
| 1M | 2 | 1 | 1 | 900 | $2,421 |
| 5M | 8 | 4 | 2 | 3,360 | $9,038 |
| 10M | 15 | 8 | 3 | 5,580 | $15,010 |

---

## 8. SO SÁNH TỔNG — SECURE CLOUD

### 8.1 Chi phí On-Demand / tháng

| MAU | L40S | A100 SXM | RTX PRO 6000 | H100 SXM | Lựa chọn |
|-----|------|----------|-------------|----------|----------|
| 100K | $619 | $1,073 | $1,217 | $1,937 | L40S |
| 500K | $1,084 | $1,341 | $1,217 | $1,937 | L40S |
| 1M | $1,858 | $1,877 | $1,521 | $2,421 | RTX PRO |
| 5M | $7,121 | $8,314 | $4,259 | $9,038 | RTX PRO |
| 10M | $13,468 | $15,287 | $7,605 | $15,010 | RTX PRO |

### 8.2 Chi phí cam kết 1 năm / tháng

| MAU | L40S 1yr | A100 1yr | RTX PRO 1yr | H100 OD |
|-----|----------|----------|------------|---------|
| 100K | $511 | $878 | $1,037 | $1,937 |
| 500K | $895 | $1,098 | $1,037 | $1,937 |
| 1M | $1,534 | $1,537 | $1,296 | $2,421 |
| 5M | $5,879 | $6,808 | $3,629 | $9,038 |
| 10M | $11,119 | $12,517 | $6,480 | $15,010 |

### 8.3 Hiệu quả chi phí trên mỗi concurrent user

| GPU | $/hr OD | Đồng thời | $/concurrent/hr | KV cache |
|-----|---------|----------|----------------|----------|
| L40S | $0.86 | ~36 | $0.024 | BF16 |
| A100 SXM | $1.49 | ~76 | $0.020 | BF16 |
| H100 SXM | $2.69 | 128 | $0.021 | BF16 [B] |
| RTX PRO 6000 | $1.69 | ~96 | $0.018 (tốt nhất) | BF16 |

RTX PRO 6000 có hiệu quả chi phí tốt nhất nhờ 96GB VRAM + giá hợp lý.

### 8.4 Điểm chuyển đổi L40S sang RTX PRO 6000

```
L40S:    $0.86/hr, ~36 concurrent/pod
RTX PRO: $1.69/hr, ~96 concurrent/pod (2.7x capacity)

1 pod:  L40S $0.86 < RTX PRO $1.69  -->  L40S rẻ hơn
2 pods: L40S $1.72 > RTX PRO $1.69  -->  RTX PRO rẻ hơn

Điểm chuyển đổi: ~36 burst concurrent ~ 400K-600K MAU
```

---

## 9. SO SÁNH VỚI MODEL CŨ (Qwen3-8B FP8 trên L40S CC)

| MAU | 8B L40S CC | 30B L40S SC | 30B RTX PRO SC | Tăng (best) |
|-----|-----------|------------|----------------|-------------|
| 100K | $569 | $619 | $1,217 | +9% (L40S) |
| 500K | $711 | $1,084 | $1,217 | +52% (L40S) |
| 1M | $1,138 | $1,858 | $1,521 | +34% (RTX PRO) |
| 5M | $3,697 | $7,121 | $4,259 | +15% (RTX PRO) |
| 10M | $6,826 | $13,468 | $7,605 | +11% (RTX PRO) |

Ở quy mô lớn (5-10M), nâng cấp từ 8B lên 30B-A3B chỉ tăng 11-15% chi phí
nhưng chất lượng tốt hơn rất nhiều (6-7/10 lên 8.5-9/10).

---

## 10. SERVERLESS vs PODS

| | Pods (vLLM tự quản lý) | Serverless |
|--|------------------------|-----------|
| Concurrent/GPU | Full vLLM batching (36-128) | MAX_CONCURRENCY=30 mặc định |
| Mở rộng | Thủ công/API | Tự động |
| Độ tin cậy | Chuyên dụng, ổn định | Có thể bị trễ hàng đợi |
| Cold start | Không (luôn chạy) | Có (Flex workers) |
| Kiểm soát | Toàn quyền cấu hình vLLM | Giới hạn biến môi trường |

Serverless worker xử lý ít concurrent hơn do MAX_CONCURRENCY=30 mặc định,
overhead hàng đợi + cold starts, và không kiểm soát toàn bộ tối ưu vLLM.
Pods được khuyến nghị cho production DokiChat.

Serverless phù hợp giai đoạn Alpha (scale to zero, < 10K MAU).

---

## 11. DOANH THU vs CHI PHÍ

### Gói premium $0.80/user/tháng (20.000 VND), 1% chuyển đổi:

| MAU | Người trả phí | Doanh thu | Chi phí GPU tốt nhất (SC) | Biên lợi nhuận |
|-----|-------------|---------|--------------------------|---------------|
| 100K | 1,000 | $800 | $619 (L40S) | 23% |
| 500K | 5,000 | $4,000 | $1,084 (L40S) | 73% |
| 1M | 10,000 | $8,000 | $1,521 (RTX PRO) | 81% |
| 5M | 50,000 | $40,000 | $4,259 (RTX PRO) | 89% |
| 10M | 100,000 | $80,000 | $7,605 (RTX PRO) | 90% |

Điểm hòa vốn: ~100K MAU (1% chuyển đổi) -> $800 doanh thu vs $619 GPU (L40S SC)

---

## 12. LỘ TRÌNH TRIỂN KHAI

| Giai đoạn | MAU | GPU | $/tháng OD |
|-----------|-----|-----|-----------|
| Alpha | 0-10K | Serverless Flex | $50-200 |
| Beta | 10K-100K | 1x L40S SC | $619 |
| Ra mắt | 100K-500K | 1-3x L40S SC | $619-1,084 |
| Tăng trưởng | 500K-1M | Chuyển sang RTX PRO 6000 1-2x | $1,217-1,521 |
| Quy mô | 1M-5M | 2-6x RTX PRO 6000 | $1,521-4,259 |
| Đại trà | 5M-10M | 6-11x RTX PRO 6000 | $4,259-7,605 |

---

## 13. CẤU HÌNH vLLM — Production (Cập nhật 19/03/2026)

Dựa trên H100 benchmark + nghiên cứu Perplexity:
- Nút điều chỉnh chính: --max-num-batched-tokens (không phải --max-num-seqs)
- Thinking OFF: khuyến nghị custom template (phía server) thay vì per-request
- FP8 KV cache: KHÔNG dùng trên FP8 checkpoint

### L40S / RTX PRO 6000 / H100 (FP8 checkpoint, BF16 KV):

```
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-30B-A3B-FP8 \
  --served-model-name dokichat \
  --port 8000 \
  --chat-template ./qwen3_nonthinking.jinja \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-seqs 128 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --trust-remote-code
```

Không dùng --kv-cache-dtype fp8_e5m2 (bị block trên FP8 checkpoint).
gpu-memory-utilization 0.90 (mặc định an toàn), tăng dần nếu ổn định.
max-num-batched-tokens 8192: sweep giá trị này để tối ưu (đang test).

### A100 SXM (W8A16 Marlin):

```
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-30B-A3B-FP8 \
  --served-model-name dokichat \
  --port 8000 \
  --quantization fp8 \
  --chat-template ./qwen3_nonthinking.jinja \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-seqs 128 \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --trust-remote-code
```

### Nhánh nâng cấp (BF16 base + FP8 KV — cần test):

```
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-30B-A3B \
  --served-model-name dokichat \
  --port 8000 \
  --quantization fp8 \
  --kv-cache-dtype fp8_e5m2 \
  --chat-template ./qwen3_nonthinking.jinja \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-seqs 128 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 8192 \
  --trust-remote-code
```

BF16 base + runtime FP8 = FP8 KV cache có thể hoạt động, tăng 2x concurrent.
Cần benchmark chất lượng + throughput so với FP8 checkpoint.

---

## 14. KIẾN TRÚC SẢN XUẤT

```
+----------------------------------------------+
|         DokiChat Production (SC)             |
|        Model: 30B-A3B FP8 BASE (MoE)        |
+----------------------------------------------+
|                                              |
|   FastAPI Gateway -> Redis Queue             |
|         |                                    |
|   Queue Monitor (cron 30s)                   |
|         |                                    |
|   +----------------------------+             |
|   | depth > nguong?            |             |
|   |   CAO -> RunPod API:       |             |
|   |          create-pod()      |             |
|   |   THAP -> RunPod API:      |             |
|   |          terminate-pod()   |             |
|   +----------------------------+             |
|                                              |
|   Giai doan 1 (<1M): L40S SC Fleet          |
|   +-- L40S #1 — base (1yr $0.71)            |
|   +-- L40S #N — burst (OD $0.86)            |
|                                              |
|   Giai doan 2 (1M+): RTX PRO 6000 SC Fleet  |
|   +-- RTX PRO #1 — base (1yr $1.44)         |
|   +-- RTX PRO #2 — base                     |
|   +-- RTX PRO #N — burst (OD $1.69)         |
|                                              |
|   Burst pods: baked Docker image             |
|      (NV pods khong stop duoc)               |
|                                              |
+----------------------------------------------+
```

---

## 15. TỔNG HỢP ĐỘ TIN CẬY

### [V] Verified

| Khẳng định | Nguồn |
|-----------|-------|
| L40S SC: $0.86 OD, $0.75/3mo, $0.73/6mo, $0.71/1yr, $0.26 spot | Console |
| A100 SXM SC: $1.49 OD, $1.30/3mo, $1.27/6mo, $1.22/1yr, $0.95 spot | Console |
| RTX PRO 6000 SC: $1.69 OD, $1.59/3mo, $1.47/6mo, $1.44/1yr, $1.19 spot | Console |
| H100 SXM SC: $2.69 OD, $1.75 spot, không có savings plan | Console |
| RTX PRO 6000: 96GB GDDR7 | RunPod listing |
| Billing theo giây | Docs |
| Giá lưu trữ | Docs |
| Pod + NV: chỉ terminate | Docs |
| Qwen3-30B-A3B: 30B tổng, 3B active | Model card |
| A100 W8A16 Marlin kernel cho FP8 model | vLLM docs |
| L40S, H100, RTX PRO 6000 có native FP8 | NVIDIA specs |
| Thinking OFF = hard switch (không chỉ ẩn tag) | Qwen docs |
| --max-num-batched-tokens là nút điều chỉnh chính | vLLM maintainers |

### [B] Benchmarked (19/03/2026)

| Khẳng định | Giá trị |
|-----------|---------|
| H100 single stream | 164 tok/s, TTFT 76ms |
| H100 peak throughput | 6,011 tok/s @ N=96 |
| H100 max concurrent p95<5s | 128 |
| H100 VRAM khi load model | ~16 GB (không phải 30GB) |
| FP8 KV cache + FP8 checkpoint | KHÔNG hoạt động (ValueError) |
| BASE model ngôn ngữ thuần | 100% cho 8 ngôn ngữ |
| BASE model vs Instruct | BASE tốt hơn nhiều cho đa ngôn ngữ |

### [T] Cần kiểm tra

| Khẳng định | Lý do |
|-----------|-------|
| RTX PRO 6000: ~96 concurrent | Cần benchmark thực tế |
| L40S: ~36 concurrent | Cần benchmark thực tế |
| A100: FP8 KV cache | Giả lập phần mềm — cần test |
| Ước tính tốc độ (70-87 tok/s) | Cần benchmark |
| BF16 base + runtime FP8 + FP8 KV | Cần test chất lượng + throughput |
| --max-num-batched-tokens tối ưu | Đang chạy tuning sweep |
| Giá Serverless SC | Chưa xác minh từ console |

### [E] Ước tính

| Khẳng định | Cơ sở |
|-----------|-------|
| L40S ~36 concurrent @4K | 29GB KV BF16 / 0.8GB mỗi user |
| A100 ~76 concurrent @4K | 61GB KV BF16 / 0.8GB mỗi user |
| RTX PRO ~96 concurrent @4K | Giới hạn compute (0.53x băng thông H100) |
| PRO 6000 ~87 tok/s single | Tỷ lệ BW 1.79/3.35 = 0.53x |
| Mô hình lưu lượng (DAU 30%, peak 8%) | Giả định kinh doanh |
| Chuyển đổi L40S sang RTX PRO ~ 400K-600K MAU | Capacity x pricing |
| Bảng chi phí (số pod) | Tính toán từ burst concurrent / GPU capacity |
