# Monitoring & Incident Response — DokiChat
### Kịch bản vận hành và cách xử lý — 12/03/2026

---

## I. Stack Monitoring

```
vLLM /metrics ──► Prometheus (scrape 15s) ──► Grafana Cloud
                                                ├── Dashboard
                                                ├── Alert rules
                                                └── Notification
                                                    ├── Telegram bot
                                                    └── Email
```

---

## II. Metrics quan trọng & ngưỡng

| Metric | Bình thường | Cảnh báo (Warning) | Nguy hiểm (Critical) |
|---|---|---|---|
| **GPU Utilization** | 40-80% | >85% liên tục 5ph | >95% liên tục 2ph |
| **VRAM Usage** | <85% | >90% | >95% |
| **KV Cache Usage** | <80% | >85% | >95% (start evicting) |
| **Queue Depth** | 0-10 | >50 liên tục 2ph | >200 |
| **TTFT** (time to first token) | <300ms | p95 >500ms | p95 >2s |
| **E2E Latency** | <5s | p95 >8s | p95 >15s |
| **Error Rate** | <0.5% | >1% | >5% |
| **Throughput** (tok/s) | >800 | <600 | <300 |
| **Request Success Rate** | >99% | <98% | <95% |

---

## III. Kịch bản & Cách xử lý

---

### 🟡 Kịch bản 1: GPU quá tải (GPU Util >90%, TTFT tăng)

**Triệu chứng:**
- Users thấy chữ chạy chậm, đợi lâu trước khi có chữ đầu tiên
- `vllm:num_requests_waiting` tăng
- TTFT p95 >500ms

**Nguyên nhân:**
- Quá nhiều concurrent users cho 1 GPU
- Nhiều users gửi message cùng lúc (peak hour)

**Xử lý:**

| Severity | Hành động |
|---|---|
| Warning (>85%, 5ph) | Ghi log, theo dõi tiếp |
| Critical (>95%, 2ph) | **Scale up: thêm 1 GPU pod** |

```bash
# Auto-scale script kiểm tra mỗi 30s
if gpu_util > 95% for 2 minutes:
    runpod_api.create_pod(gpu="L40S")  # thêm pod
    load_balancer.add_backend(new_pod)
```

**Phòng ngừa:**
- Đặt rate limit: Free users max 3 msg/phút, Plus max 10 msg/phút
- Giảm `--max-model-len` từ 8192 → 4096 (giải phóng VRAM cho KV cache)

---

### 🟡 Kịch bản 2: VRAM đầy (KV Cache >95%)

**Triệu chứng:**
- vLLM tự evict cache (LRU) → users quay lại phải prefill lại (~200ms)
- Throughput giảm vì prefill nhiều hơn
- Grafana: `vllm:gpu_cache_usage_perc` = 0.95+

**Nguyên nhân:**
- Quá nhiều active conversations cùng lúc
- Conversations dài (context window lớn)

**Xử lý:**

| Severity | Hành động |
|---|---|
| >90% | Bình thường — vLLM tự evict LRU cache |
| >95% liên tục | Giảm `--max-model-len` hoặc thêm GPU |
| OOM crash | Restart pod, giảm `--gpu-memory-utilization` xuống 0.85 |

**Phòng ngừa:**
- Sliding window conversation: chỉ giữ 20 turns gần nhất trong context
- Prefix caching: ON — share system prompt giữa users

---

### 🔴 Kịch bản 3: vLLM crash / Pod die

**Triệu chứng:**
- Health check fail: `GET /health` → timeout
- Tất cả users bị disconnect
- Grafana: metrics mất

**Nguyên nhân:**
- OOM kill (VRAM overflow)
- Spot instance bị thu hồi (interruptible)
- Bug trong vLLM
- CUDA error

**Xử lý immediate:**

```
1. Alert → Telegram: "⚠️ vLLM pod DOWN"
2. Auto-restart pod (RunPod auto-restart = ON)
3. Nếu Spot bị thu hồi → tạo pod mới
4. Users thấy: "Server đang khởi động lại, vui lòng đợi 30s"
```

| Thời gian | Mục tiêu |
|---|---|
| 0-5s | Detect (health check fail) |
| 5-30s | Restart pod / create new pod |
| 30-60s | vLLM load model |
| 60-90s | Service restored |

**Recovery time: ~1-2 phút**

**Phòng ngừa:**
- Production: dùng **Secure Cloud** (không bị thu hồi), không Spot
- Luôn có >= 2 pods khi >100 DAU (redundancy)
- `--gpu-memory-utilization 0.90` (giữ 10% buffer)

---

### 🟡 Kịch bản 4: Response chất lượng kém (repetition, break character)

**Triệu chứng:**
- User report: "bot nói lặp", "bot thoát vai"
- Log phát hiện: response chứa meta-commentary ("If you'd like, I can...")
- Hoặc: cùng 1 phrase lặp >3 lần trong 1 response

**Nguyên nhân:**
- `repetition_penalty` quá thấp
- `presence_penalty` chưa set (chỉ có trên vLLM)
- Prompt thiếu FORMAT_ENFORCEMENT
- Model degrade (hiếm, nhưng có thể do cache corruption)

**Xử lý:**

```python
# Post-process filter — đã có trong response_processor.py
def clean_response(text):
    # Remove meta-commentary
    patterns = [
        r"If you'd like.*$",
        r"I can also:.*$",
        r"Tell me what you prefer.*$",
    ]
    for p in patterns:
        text = re.sub(p, "", text, flags=re.MULTILINE | re.DOTALL)
    return text.strip()
```

**Phòng ngừa:**
- Luôn set `presence_penalty=1.5` trên vLLM
- FORMAT_ENFORCEMENT luôn inject cuối system prompt
- Monitor: random sample 1% responses, check quality

---

### 🔴 Kịch bản 5: Safety violation (NSFW với minor)

**Triệu chứng:**
- `safety_filter.check_input()` detect nhưng model vẫn generate
- Hoặc: filter miss edge case

**Xử lý immediate:**

```
1. Hard block → return SafetyResult(blocked=True)
2. Log incident (user_id, message, timestamp)
3. Nếu repeat offender (>3 lần): ban user
4. Review và cập nhật regex patterns
```

**Architecture defense-in-depth:**

```
Layer 1: safety_filter.py    → regex patterns (pre-filter INPUT)
Layer 2: System prompt rules  → model tự refuse
Layer 3: Post-process filter  → clean output
Layer 4: Human review         → random audit
```

**Phòng ngừa:**
- Chạy `test_safety_boundary.py` sau mỗi lần deploy
- Cập nhật regex patterns khi phát hiện edge case mới
- Log tất cả blocked requests để phân tích

---

### 🟡 Kịch bản 6: Network issues (cao latency, timeout)

**Triệu chứng:**
- Users gặp timeout
- Streaming bị ngắt giữa chừng
- E2E latency tăng đột ngột nhưng GPU util bình thường

**Nguyên nhân:**
- Network giữa App server ↔ RunPod pod chậm
- RunPod data center overload
- CDN/proxy issues

**Xử lý:**

| Tình huống | Hành động |
|---|---|
| Latency tăng <2x | Chờ tự recovery |
| Latency tăng >3x, 5+ phút | Switch data center |
| Timeout >50% requests | Emergency: migrate pod sang DC khác |

**Phòng ngừa:**
- Chọn data center gần users (US-TX-3 cho global, EU-RO-1 cho EU)
- Timeout client-side: 30s max, hiển thị "đang suy nghĩ..." cho user
- Retry logic: 1 lần retry với backoff

---

### 🟡 Kịch bản 7: Database bottleneck

**Triệu chứng:**
- API response chậm nhưng vLLM metrics bình thường
- PostgreSQL query time tăng
- Redis timeout

**Nguyên nhân:**
- Chat history table quá lớn (thiếu index)
- Redis full memory
- Too many concurrent DB connections

**Xử lý:**

| Service | Action |
|---|---|
| PostgreSQL chậm | Thêm index trên (user_id, character_id, timestamp) |
| Redis full | Tăng tier hoặc giảm TTL session |
| Qdrant chậm | Tăng tier hoặc limit vector search top_k |

---

### 🔴 Kịch bản 8: Spot instance bị thu hồi (chỉ khi dùng Spot)

**Triệu chứng:**
- RunPod gửi 5-second warning
- Pod bị terminate

**Xử lý:**

```
1. RunPod webhook → alert "Spot reclaimed"
2. Tự động tạo pod mới (Spot hoặc On-demand fallback)
3. Users thấy "reconnecting..." trong 1-2 phút
4. Service restored
```

**Auto-fallback script:**

```python
# Khi spot bị thu hồi
try:
    pod = runpod.create_pod(
        gpu_type="NVIDIA L40S",
        cloud_type="SPOT",
    )
except SpotUnavailable:
    # Fallback to on-demand
    pod = runpod.create_pod(
        gpu_type="NVIDIA L40S",  
        cloud_type="SECURE",  # on-demand, đắt hơn nhưng stable
    )
```

---

## IV. Alert Rules (Grafana)

### Telegram notification format

```
🟡 WARNING: GPU Util 92% (>85% for 5m)
   Pod: dokichat-primary-1
   Action: Monitor, consider scaling

🔴 CRITICAL: vLLM pod DOWN
   Pod: dokichat-primary-1  
   Last seen: 2 minutes ago
   Action: Auto-restart initiated
   
✅ RESOLVED: vLLM pod RECOVERED
   Pod: dokichat-primary-1
   Downtime: 87 seconds
```

### Alert rules summary

| Rule | Condition | Severity | Auto-action |
|---|---|---|---|
| GPU High | >85% for 5m | Warning | Log |
| GPU Critical | >95% for 2m | Critical | Scale up |
| Pod Down | Health fail 30s | Critical | Restart |
| TTFT Slow | p95 >2s for 3m | Warning | Log |
| Queue Deep | >200 for 1m | Critical | Scale up |
| Error Spike | >5% for 1m | Critical | Alert + investigate |
| VRAM Full | >95% for 5m | Warning | Reduce max-model-len |
| Safety Block | Any | Info | Log for review |

---

## V. Runbook — Bước kiểm tra hàng ngày

```
Morning check (5 phút):
  ☐ Grafana dashboard: tất cả metrics xanh?
  ☐ Queue depth = 0 (off-peak)?
  ☐ Error rate <0.5%?
  ☐ VRAM usage <85%?
  ☐ Kiểm tra safety log: có blocked requests mới?

Weekly review:
  ☐ Throughput trend: có giảm so với tuần trước?
  ☐ User complaints: có pattern nào lặp lại?
  ☐ Cost review: GPU hours vs users served
  ☐ Response quality: random sample 10 conversations
```

---

*Monitoring & Incident Response — DokiChat — 12/03/2026*
