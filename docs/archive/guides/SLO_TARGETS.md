# 🎯 Service Level Objectives (SLOs) — DokiChat
### Mục tiêu phục vụ & cam kết chất lượng — 13/03/2026

---

## I. Tổng quan

SLO = mục tiêu chất lượng nội bộ mà hệ thống phải đạt.
Nếu SLO bị vi phạm → team phải hành động NGAY.

---

## II. SLOs theo từng hạng mục

### 🟢 Availability (Uptime)

| Metric | Target | Ý nghĩa |
|---|---|---|
| **Chat service uptime** | **99.5%** | Tối đa ~3.6 giờ downtime/tháng |
| **API uptime** | **99.9%** | Tối đa ~43 phút downtime/tháng |
| **Chargen uptime** | **95%** | Cho phép offline khi maintenance (ít dùng) |
| **Scheduled maintenance** | <2 giờ/tháng | Thông báo trước 24h |

```
99.5% uptime = tối đa 3.6 giờ/tháng hệ thống chat không khả dụng
  Gồm: planned maintenance + unplanned outage
  Tại sao không 99.9%? Vì startup, 1 GPU pod, chấp nhận rủi ro.
  Khi scale 100K+ → nâng lên 99.9% (redundancy 2 pods)
```

---

### ⚡ Latency (Tốc độ phản hồi)

| Metric | Target p50 | Target p95 | Target p99 |
|---|---|---|---|
| **TTFT** (time to first token) | <200ms | <500ms | <1.5s |
| **E2E latency** (toàn bộ response) | <3s | <5s | <10s |
| **API response** (non-AI endpoints) | <50ms | <100ms | <200ms |
| **Chargen** (tạo nhân vật) | <15s | <30s | <60s |

```
TTFT = thời gian từ khi user bấm Send → chữ đầu tiên xuất hiện
  - User cảm nhận: <200ms = "instant", <500ms = "nhanh", >2s = "chậm"
  - Target p95 <500ms: 95% requests chữ đầu tiên trong 0.5 giây

E2E = thời gian toàn bộ response (150-250 words)
  - Phụ thuộc output length, trung bình ~200 tokens
  - Ở 1,200 tok/s: 200 tokens = ~0.17s compute
  - Cộng TTFT + streaming overhead → ~3s tổng
```

---

### 📊 Throughput (Năng lực xử lý)

| Scale | Concurrent users | Requests/phút | GPU pods |
|---|---|---|---|
| **10K MAU** | 50-80 | ~200 | 1 |
| **100K MAU** | 400-600 | ~1,500 | 3-4 |
| **1M MAU** | 2,000-3,000 | ~8,000 | 8-9 |

```
Concurrent user = đang chờ response cùng lúc
  10K MAU ÷ 30 ngày ÷ 24 giờ × 5 msg/session × 0.2 peak factor
  = ~50-80 concurrent peak

Mỗi L40S serve ~80-120 concurrent users (4B model, vLLM)
  → 10K MAU = 1 GPU đủ
```

---

### 🛡️ Safety & Security

| Metric | Target |
|---|---|
| **Safety filter catch rate** | >99% cho hard-block categories |
| **False positive rate** | <1% (không block user vô tội) |
| **Safety response time** | <10ms (regex, không qua AI) |
| **Audit log coverage** | 100% blocked requests đều logged |
| **Incident response** | <15 phút từ detect → action |

---

### 💬 Response Quality

| Metric | Target | Cách đo |
|---|---|---|
| **In-character rate** | >95% | Random audit 50 responses/tuần |
| **POV consistency** | >98% | Automated check (no "I" outside quotes) |
| **Language match** | >99% | User Việt → response Việt |
| **Repetition rate** | <5% | Phát hiện phrase lặp >2x/session |
| **Format compliance** | >90% | 150-250 words, body-words contradiction |
| **User satisfaction** | >4.0/5 | In-app feedback (👍👎) |

```
In-character = AI duy trì tính cách nhân vật, không "thoát vai"
  Sol KHÔNG nói: "As an AI, I can't feel lonely"
  Sol NÊN nói:   *She paused.* "Sometimes the quiet gets loud."
```

---

### 💾 Data & Memory

| Metric | Target |
|---|---|
| **Chat history persistence** | 100% (không mất tin nhắn) |
| **Memory recall accuracy** | >80% (facts được retrieve đúng context) |
| **Fact extraction quality** | >70% precision (facts extracted correct) |
| **Database backup** | Daily automated, 7-day retention |
| **Data loss tolerance** | 0 (zero data loss for chat history) |

---

### 💰 Cost Efficiency

| Metric | Target | Cách tính |
|---|---|---|
| **Cost per 1K messages** | <$0.50 | GPU cost ÷ messages served |
| **GPU utilization** | 40-80% average | Prometheus metric |
| **Wasted GPU** (util <10%) | <10% thời gian | Alert nếu idle quá lâu |
| **Revenue per GPU hour** | >$0.86 ở break-even | Subscription revenue ÷ GPU hours |

```
10K MAU target:
  GPU: $619/tháng
  Messages: ~10K × 5 msg/ngày × 30 ngày = 1.5M msg/tháng
  Cost per 1K msg = $619 ÷ 1,500 = $0.41 ✅
```

---

## III. SLO Dashboard — Metrics cần monitor

| # | Metric | Source | Alert khi |
|---|---|---|---|
| 1 | Uptime | Health check probe (30s) | Down > 30s |
| 2 | TTFT p95 | vLLM `/metrics` | > 500ms liên tục 3ph |
| 3 | E2E p95 | FastAPI middleware | > 8s liên tục 3ph |
| 4 | Error rate | FastAPI logs | > 1% trong 5ph |
| 5 | GPU util | vLLM `/metrics` | > 90% liên tục 5ph |
| 6 | KV cache usage | vLLM `/metrics` | > 95% |
| 7 | Queue depth | Redis XLEN | > 50 liên tục 2ph |
| 8 | Safety blocks | safety_filter logs | Mỗi lần block (info) |
| 9 | Response length | Post-process check | > 400 words hoặc < 50 words |
| 10 | POV violations | Regex check output | Mỗi lần "I"/"my" in action |

---

## IV. Error Budget

```
Uptime SLO: 99.5%
  = 744 giờ/tháng × 0.5% = 3.72 giờ downtime cho phép

Error budget tháng 3/2026:
  ┌──────────────────────────────────┐
  │  Allowed: 3.72 giờ              │
  │  Used:    0 giờ (chưa live)     │
  │  Remaining: 3.72 giờ            │
  │  ████████████████████░░ 100%    │
  └──────────────────────────────────┘

Khi error budget < 25%:
  → Freeze feature releases
  → Focus on reliability only
  → Post-mortem cho mỗi outage
```

---

## V. SLO theo Phase

| | Phase 0-1 (Test) | Phase 2 (Staging) | Phase 3 (Production) |
|---|---|---|---|
| **Uptime** | Không cam kết | 95% | **99.5%** |
| **TTFT p95** | <2s | <1s | **<500ms** |
| **E2E p95** | <15s | <8s | **<5s** |
| **Safety** | Test coverage | 95% catch | **>99% catch** |
| **Quality audit** | Manual review | Weekly 20 | **Weekly 50** |
| **Monitoring** | Basic logs | Grafana | **Grafana + Alerts** |
| **On-call** | None | Business hours | **24/7 alerts** |

---

## VI. Incident Severity Levels

| Level | Định nghĩa | Response time | Ví dụ |
|---|---|---|---|
| **P0 — Critical** | Service down, all users affected | <15 phút | vLLM crash, database down |
| **P1 — Major** | Degraded, >30% users affected | <1 giờ | GPU 95%, queue >200 |
| **P2 — Minor** | Degraded, <10% users affected | <4 giờ | High latency, some timeouts |
| **P3 — Low** | Cosmetic, no user impact | <24 giờ | Log errors, metric gaps |

---

## VII. SLO Review Schedule

```
Daily (automated):
  ☐ Dashboard green check
  ☐ Error rate < 1%
  ☐ No P0/P1 incidents

Weekly:
  ☐ TTFT p95 trend
  ☐ Quality audit: 50 random responses
  ☐ Safety log review
  ☐ Cost per 1K messages

Monthly:
  ☐ Uptime report vs SLO
  ☐ Error budget status
  ☐ User satisfaction score
  ☐ Capacity planning (approaching scale threshold?)
  ☐ SLO adjustment if needed
```

---

*Service Level Objectives — DokiChat — 13/03/2026*
