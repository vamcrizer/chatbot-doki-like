# BÁO CÁO CHI PHÍ PRODUCTION — DokiChat (v3 — final)
### RunPod Pricing Verified + Capacity/Traffic Assumption Model
### Ngày: 16/03/2026
### Model: huihui-ai/Huihui-Qwen3-8B-abliterated-v2 (FP8)
### Platform: RunPod GPU Cloud

> Mỗi số liệu được đánh dấu:
> - ✅ **Verified** — xác minh từ RunPod docs/pricing page
> - 🔶 **Assumption** — suy diễn từ benchmark hoặc giả định kinh doanh
> - 🔬 **Needs Test** — cần kiểm tra thực tế trên RunPod console

---

## 1. TÓM TẮT QUYẾT ĐỊNH

| Hạng mục | Quyết định | Nguồn |
|----------|-----------|-------|
| Model | huihui-ai/Huihui-Qwen3-8B-abliterated-v2 | ✅ HuggingFace |
| Quantization | FP8 (weight + KV cache) | ✅ Đã benchmark H100 |
| Framework | vLLM + OpenAI-compatible API | ✅ RunPod docs |
| GPU sản xuất | **L40S 48GB** (on-demand hoặc commit) | ✅ Pricing page |
| Commit plan | 6-month hoặc 1-year (pricing page hiển thị, cần confirm qua console/sales) | 🔬 Cần xác nhận |
| Kiến trúc | Self-managed Pods + auto-scaling qua API | ✅ RunPod API docs |
| Serverless | Có giá chính thức; hiệu quả kinh tế phụ thuộc utilization và throughput thực tế | ✅ Pricing verified / 🔶 TCO |

---

## 2. GIÁ RUNPOD ĐÃ XÁC MINH

### 2.1 Pods — ✅ Verified

| GPU | On-Demand | 6-month | 1-year | Nguồn |
|-----|-----------|---------|--------|-------|
| H100 SXM 80GB | **$2.69/hr** | *(trống trên pricing page)* | *(trống)* | ✅ |
| H100 PCIe 80GB | **$1.99/hr** | $2.08/hr ⚠️ | $2.03/hr ⚠️ | ✅ *(số cao hơn OD, bất thường)* |
| **L40S 48GB** | **$0.79/hr** | **$0.731/hr** | **$0.705/hr** | ✅ |

> ⚠️ H100 PCIe commit prices ($2.08, $2.03) hiện **cao hơn on-demand** ($1.99) trên pricing page — pricing anomaly, **KHÔNG dùng làm cơ sở ký ngân sách**.

> ⚠️ **Mâu thuẫn docs vs pricing page**: Docs Pods mô tả savings plans là **3 hoặc 6 tháng upfront**. Nhưng pricing page hiển thị cột "1-year" cho L40S ($0.705). **Cần xác nhận trực tiếp qua console hoặc sales trước khi cam kết tài chính.**

### 2.2 Serverless Workers — ✅ Verified

| GPU Tier | Flex ($/s) | Active ($/s) | Flex $/hr | Active $/hr |
|----------|-----------|-------------|-----------|-------------|
| **L40S / L40 / 6000 Ada PRO 48GB** | **$0.00053/s** | **$0.00037/s** | **$1.91/hr** | **$1.33/hr** |
| H100 PRO 80GB | $0.00116/s | $0.00093/s | $4.18/hr | $3.35/hr |

> **Flex**: Scale to zero khi idle, trả khi xử lý
> **Active**: Luôn chạy 24/7, rẻ hơn Flex ~30%

### 2.3 Lưu trữ — ✅ Verified

| Loại | Giá |
|------|-----|
| Container disk (đang chạy) | $0.10/GB/tháng |
| Volume disk (đang chạy) | $0.10/GB/tháng |
| Volume disk (stopped) | $0.20/GB/tháng |
| Network volume <1TB | $0.07/GB/tháng |
| Network volume >1TB | $0.05/GB/tháng |
| Model weights (~16GB) | ~$1.12/tháng |

### 2.4 Pod Lifecycle — ✅ Verified

| Thao tác | Kết quả |
|----------|---------|
| **Stop pod** | GPU released, /workspace preserved, container disk XÓA |
| **Terminate pod** | Mọi thứ bị xóa |
| ⚠️ **Stop pod có network volume** | **KHÔNG THỂ** — chỉ có thể terminate |
| Billing | Theo GIÂY, không làm tròn giờ |

> ⚠️ **Caveat quan trọng**: Pods gắn network volume **không thể stop**, chỉ có thể terminate. Điều này ảnh hưởng kiến trúc burst pods.

---

## 3. BENCHMARK — 🔶 Assumption (từ test thực tế)

### 3.1 Kết quả H100 SXM — ✅ Benchmark thực

| Chỉ số | Kết quả | Nguồn |
|--------|---------|-------|
| Tốc độ đơn luồng | **207 tok/s** | ✅ Kaggle H100 |
| TTFT | **66ms** | ✅ Kaggle H100 |
| Concurrent p95<5s | **224** | ✅ Kaggle H100 |
| VRAM | 77,695 / 81,559 MiB | ✅ Kaggle H100 |

### 3.2 Ước tính GPU khác — 🔶 Assumption

| GPU | Concurrent p95<5s | Cơ sở | Độ tin cậy |
|-----|-------------------|-------|-----------|
| H100 SXM | 224 | ✅ Benchmark | Cao |
| H100 PCIe | ~190 | 🔶 ~85% SXM | Trung bình |
| **L40S** | **~78** | 🔶 ~35% SXM | **Thấp — cần test** |

> 🔬 **L40S ~78 concurrent là GIẢ ĐỊNH.** Cần benchmark thực ($0.79 cho 1 giờ test).

---

## 4. MÔ HÌNH LƯU LƯỢNG — 🔶 Assumption

| Tham số | Giá trị | Loại |
|---------|---------|------|
| DAU/MAU | 30% | 🔶 Giả định kinh doanh |
| Peak concurrent (% DAU) | 8% | 🔶 Giả định vận hành |
| Tỷ lệ đang chat | 50% | 🔶 Giả định |
| Think time giữa tin nhắn | 90 giây | 🔶 Giả định |
| GPU time/msg (FP8) | 0.97 giây | ✅ Từ benchmark |
| Duty cycle | 1.08% | ✅ Tính toán |
| Hệ số burst | 1.3× | 🔶 Giả định |

### Peak GPU Concurrent:

| MAU | Burst Concurrent | Loại |
|-----|-----------------|------|
| 100K | 17 | 🔶 |
| 1M | 169 | 🔶 |
| 5M | 843 | 🔶 |
| 10M | 1,685 | 🔶 |

---

## 5. SO SÁNH PODS vs SERVERLESS — 🔶 So sánh đơn giá (chưa phải TCO)

> ⚠️ **Lưu ý quan trọng**: Bảng dưới so sánh **đơn giá uptime** giữa Pod L40S và Serverless Active L40S-tier. Đây **KHÔNG** phải so sánh throughput-normalized hay TCO hoàn chỉnh, vì docs chỉ xác nhận giá serverless và vLLM support, chưa xác nhận hiệu năng thực tế/worker sẽ giống pod tự quản lý.

### 5.1 Pods L40S vs Serverless L40S — Đơn giá

| Hạng mục | Pod L40S | Serverless L40S Active |
|----------|---------|----------------------|
| Giá/giờ | **$0.79** (OD) / **$0.705** (1yr 🔬) | **$1.33** |
| Billing | Toàn bộ uptime | Toàn bộ uptime worker |
| Auto-scaling | ❌ Tự build | ✅ Native |
| FP8 weights | ✅ Verified trên Pods | 🔬 Chưa xác minh trên Serverless |
| Custom config | ✅ Full control | ✅ Qua env vars |
| Scale to zero | ❌ | ✅ (Flex) |
| Throughput/worker | 🔶 Cần benchmark | 🔬 Cần benchmark |

### 5.2 Break-even (chỉ dựa trên đơn giá)

```
Pod L40S OD:        $0.79/hr (cố định)
Serverless L40S Flex: $1.91/hr (chỉ khi xử lý)

Break-even: $0.79 / $1.91 = 41%
→ Utilization > 41% → Pods rẻ hơn VỀ ĐƠN GIÁ

Serverless Active:   $1.33/hr (luôn chạy)
Break-even vs Pod:   $0.79 / $1.33 = 59%
→ Utilization > 59% → Pods rẻ hơn VỀ ĐƠN GIÁ

⚠️ Nếu throughput/worker Serverless khác Pods, break-even thực tế sẽ khác.
```

### 5.3 Kết luận chọn kiểu — 🔶 Dựa trên đơn giá

| Scale | Utilization (ước tính) | Lựa chọn tốt nhất |
|-------|----------------------|-------------------|
| <10K MAU | <5% | **Serverless Flex** (scale to zero) |
| 10K-100K | 5-15% | **Serverless Flex** (vẫn thấp) |
| 100K-500K | 15-55% | **Tùy** — gần break-even, cần throughput data |
| 500K+ | 60%+ | **Pods** (rẻ hơn về đơn giá, cần verify throughput) |

---

## 6. BẢNG CHI PHÍ — ĐÃ SỬA SỐ HỌC

### 6.1 Pods L40S — Traffic Pattern

| Thời gian | Khoảng | % capacity |
|-----------|--------|-----------|
| Cao điểm | 6h (20h-02h) | 100% |
| Ban ngày | 12h (08h-20h) | 50% |
| Đêm khuya | 6h (02h-08h) | 25% |

### 6.2 Số pods cần (L40S ~78 concurrent/pod) — 🔶

| MAU | Burst | Cao điểm | Ban ngày | Đêm |
|-----|-------|---------|---------|-----|
| 100K | 17 | 1 | 1 | 1 |
| 500K | 85 | 2 | 1 | 1 |
| **1M** | **169** | **3** | **2** | **1** |
| **5M** | **843** | **11** | **6** | **3** |
| **10M** | **1,685** | **22** | **11** | **4** |

### 6.3 Pod-hours và chi phí — ✅ Số học đúng / 🔶 Capacity model là giả định

**Công thức**: `(Peak×6 + Day×12 + Night×6) × 30`

| MAU | Pods P/D/N | Pod-hours/tháng | L40S OD ($0.79) | L40S 1yr ($0.705) |
|-----|-----------|----------------|-----------------|-------------------|
| 100K | 1/1/1 | (6+12+6)×30 = **720** | **$569** | **$508** |
| 500K | 2/1/1 | (12+12+6)×30 = **900** | **$711** | **$635** |
| **1M** | **3/2/1** | (18+24+6)×30 = **1,440** | **$1,138** | **$1,015** |
| **5M** | **11/6/3** | (66+72+18)×30 = **4,680** | **$3,697** | **$3,299** |
| **10M** | **22/11/4** | (132+132+24)×30 = **8,640** | **$6,826** | **$6,091** |

### 6.4 So với v1 (sai):

| MAU | v1 (sai) | **v2 (đúng)** | Chênh lệch |
|-----|---------|-------------|-----------|
| 1M | $1,015 | **$1,015** | = *(đúng từ đầu)* |
| 5M | $6,091 | **$3,299** | **-46%** ← v1 tính quá cao |
| 10M | $8,122 | **$6,091** | **-25%** ← v1 tính quá cao |

### 6.5 So sánh đơn giá uptime: Pods vs Serverless Active — 🔶

> ⚠️ Bảng này so sánh **đơn giá uptime** ($0.705 vs $1.33), giả định cùng pod-hours. **Không phải** so sánh throughput-normalized. Nếu Serverless worker có throughput khác → tổng tiền thực tế sẽ khác.

| MAU | Pods L40S 1yr 🔬 | Serverless Active | Pods rẻ hơn (đơn giá) |
|-----|-------------|------------------|------------|
| 100K | $508 | $958 | **47%** |
| 1M | $1,015 | $1,915 | **47%** |
| 5M | $3,299 | $6,224 | **47%** |
| 10M | $6,091 | $11,491 | **47%** |

> 🔶 Con số 47% là tỷ lệ đơn giá ($0.705/$1.33 = 53%). **Cần benchmark Serverless throughput** để xác nhận TCO thực tế.

---

## 7. KIẾN TRÚC SẢN XUẤT — Đã sửa cho network volume caveat

```
┌──────────────────────────────────────────────┐
│             DokiChat Production              │
├──────────────────────────────────────────────┤
│                                              │
│   FastAPI Gateway → Redis Queue              │
│         │                                    │
│   Queue Monitor (cron 30s)                   │
│         │                                    │
│   ┌─────┴──────────────────────┐             │
│   │ depth > threshold?         │             │
│   │   HIGH → RunPod API:       │             │
│   │         create-pod()       │             │
│   │   LOW  → RunPod API:       │             │
│   │         terminate-pod()    │ ← KHÔNG     │
│   │         (không phải stop!) │   DÙNG STOP │
│   └────────────────────────────┘             │
│                                              │
│   Base Pods (luôn chạy, commit plan)         │
│   ├── L40S #1 — volume disk /workspace      │
│   └── L40S #2 — volume disk /workspace      │
│                                              │
│   Burst Pods (tạo/hủy theo demand)           │
│   ├── L40S #N — tải model từ HF cache       │
│   └── Hoặc: bake model vào Docker image     │
│                                              │
│   ⚠️ Network volume KHÔNG dùng cho burst    │
│      (vì pod + NV → không thể stop)         │
│                                              │
│   Thay thế: Cached models hoặc baked image  │
│                                              │
└──────────────────────────────────────────────┘
```

### Giải pháp cho burst pods không dùng network volume:

| Option | Cách | Thời gian khởi động | Ưu/nhược |
|--------|------|---------------------|----------|
| **HF cache** | Tải model từ HF mỗi lần create | ~3-5 phút | 🔬 Cần test |
| **Baked Docker** | Model đóng sẵn trong image | ~1-2 phút | ✅ Nhanh nhưng image lớn |
| **Network volume** | Gắn NV → chỉ terminate được | N/A | ⚠️ Mất /workspace khi terminate |

> 🔬 **Cần test**: Thời gian tạo burst pod + tải model trên RunPod thực tế

---

## 8. LỘ TRÌNH TRIỂN KHAI

| Giai đoạn | MAU | Kiến trúc | $/tháng | VND |
|-----------|-----|-----------|---------|-----|
| **Alpha** | 0-10K | Serverless Flex L40S | **$50-200** | 1-5M |
| **Beta** | 10K-100K | 1 L40S Pod | **$508** | 12.7M |
| **Ra mắt** | 100K-500K | 1-2 L40S Pods | **$508-635** | 12.7-16M |
| **Tăng trưởng** | 500K-1M | 2-3 L40S + burst | **$635-1,015** | 16-25M |
| **Quy mô** | 1M-5M | 3-11 L40S + burst | **$1,015-3,299** | 25-82M |
| **Đại trà** | 5M-10M | 11-22 L40S + burst | **$3,299-6,091** | 82-152M |

---

## 9. PHÂN TÍCH DOANH THU

### Gói premium 20.000 VND/user/tháng (~$0.80):

| MAU | 1% convert | Doanh thu | GPU cost | **Biên LN** |
|-----|-----------|----------|---------|------------|
| 100K | 1,000 | $800 | $508 | **36%** |
| 500K | 5,000 | $4,000 | $635 | **84%** |
| **1M** | **10,000** | **$8,000** | **$1,015** | **87%** |
| 5M | 50,000 | $40,000 | $3,299 | **92%** |
| **10M** | **100,000** | **$80,000** | **$6,091** | **92%** |

> 📊 **Với bảng chi phí đã sửa, biên lợi nhuận CÒN TỐT HƠN v1:**
> - 5M MAU: 92% (v1: 85%)
> - 10M MAU: 92% (v1: 90%)

---

## 10. TỔNG HỢP ĐỘ TIN CẬY

### ✅ Verified (an toàn để gửi)

| Claim | Nguồn |
|-------|-------|
| L40S $0.79/hr OD | Pricing page |
| H100 SXM $2.69/hr OD | Pricing page |
| H100 PCIe $1.99/hr OD | Pricing page |
| Billing theo giây | Docs |
| Storage pricing | Docs |
| L40S Serverless $0.00053/s Flex, $0.00037/s Active | Serverless pricing |
| H100 Serverless $0.00116/s Flex, $0.00093/s Active | Serverless pricing |
| Serverless hỗ trợ vLLM + autoscale | Docs |
| Pod + NV → không thể stop, chỉ terminate | Docs Pod lifecycle |
| Pod-hours & cost math | ✅ Verified arithmetic (v2+v3) |

### 🔬 Needs Test / Needs Confirmation (KHÔNG gửi như fact)

| Claim | Lý do |
|-------|-------|
| L40S $0.705/hr **1-year commit** | Pricing page hiển thị, nhưng docs mô tả 3/6 tháng — **cần confirm qua console/sales** |
| H100 SXM commit prices | Pricing page **để trống** — không có data |
| H100 PCIe commit $2.08/$2.03 | **Cao hơn OD** — pricing anomaly, không dùng |
| Serverless không hỗ trợ FP8 weight | **Không thấy trong docs** — chưa chứng minh |
| MAX_CONCURRENCY=30 mặc định | Từ env vars docs nhưng chưa verify thực tế |
| Network volume shared multi-pod | Docs không nói rõ |
| Serverless throughput vs Pod throughput | **Chưa benchmark** — ảnh hưởng mọi TCO comparison |

### 🔶 Assumption (mô hình suy diễn)

| Claim | Cơ sở |
|-------|-------|
| L40S ~78 concurrent/pod | ~35% H100 SXM — **cần benchmark $0.79** |
| Traffic model (DAU 30%, peak 8%, etc.) | Business assumptions |
| Bảng MAU → concurrent → pods | Capacity model dựa trên assumption |
| Pods rẻ hơn Serverless 47% | So sánh đơn giá — **không throughput-normalized** |
