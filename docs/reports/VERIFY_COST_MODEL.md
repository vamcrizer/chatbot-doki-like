# DokiChat — Cost Model & GPU Selection (Verify with Perplexity)
### 16/03/2026

---

## 1. Product Overview

DokiChat is a self-hosted AI companion chat app (like Character.AI / Replika).
Users chat 1-on-1 with fictional AI characters in Vietnamese + English.
Revenue model: freemium, $9.99/month subscription.

---

## 2. Model — CONFIRMED via Benchmark

### Chat Model

| Spec | Value |
|---|---|
| **Model** | `DavidAU/Qwen3-4B-Instruct-2507-Polaris-Alpha-Distill-Heretic-Abliterated` |
| **Base** | Qwen3-4B-Instruct-2507 (official Alibaba) |
| **Architecture** | Pure dense transformer (NOT hybrid GDN) |
| **Abliteration** | Heretic v1.0.1 — refusal rate 8/100, KL divergence 0.06 |
| **Thinking** | ❌ Disabled via custom Jinja template (empty `<think></think>` block) |
| **Precision** | FP8 weights + FP8 KV cache (vLLM `--quantization fp8 --kv-cache-dtype fp8`) |
| **Context** | 4,096 tokens (production setting) |
| **Avg output** | ~128 tokens (natural EOS), max 200 tokens |
| **Avg input** | ~800 tokens (system + history + format) |

### Other Models

| Role | Model | VRAM | Usage |
|---|---|---|---|
| Chargen | Qwen3.5-9B-DavidAU FP8 | ~9 GB | 1% of MAU, separate pod |
| Embedding | Qwen3-Embedding-0.6B | ~1 GB | Co-located with chat |

---

## 3. H100 Benchmark — ACTUAL DATA (16/03/2026, Kaggle)

All numbers measured, not estimated.

### 3.1 Single Stream

| Metric | Value |
|---|---|
| tok/s | **282** |
| TTFT | 0.061s |
| E2E latency | **0.5s** |
| Avg tokens | 128 (natural stop) |
| VRAM used | 78,431 / 81,559 MiB (96%) |

### 3.2 Throughput Saturation Curve

```
      N |  Total tok/s | Per-user tok/s |  Avg lat |  P95 lat
   ---- | ------------ | -------------- | -------- | --------
      1 |          280 |            280 |    0.5s  |    0.5s
      8 |        1,875 |            259 |    0.5s  |    0.6s   ← linear scaling
     16 |        2,854 |            212 |    0.6s  |    0.7s
     32 |        3,271 |            112 |    1.2s  |    1.3s   ← batch kicks in
     64 |        5,816 |            102 |    1.3s  |    1.5s
     96 |        7,690 |             92 |    1.4s  |    1.6s
    192 |        8,011 |             59 |    2.2s  |    3.1s   ← plateau
    256 |        7,891 |             47 |    2.7s  |    4.1s
    384 |        7,707 |             29 |    4.3s  |    6.1s   ← degrading
    512 |        7,530 |             20 |    6.3s  |    8.5s   ← overloaded
```

### 3.3 Heavy Concurrent (max_tokens=200, production-like)

```
   N=  96 | p50=1.5s | p95=1.9s ✅ | throughput= 7,090 tok/s
   N= 192 | p50=2.3s | p95=3.5s ✅ | throughput= 7,527 tok/s
   N= 256 | p50=2.9s | p95=4.4s ✅ | throughput= 7,789 tok/s  ← MAX p95<5s
   N= 320 | p50=3.8s | p95=5.4s ❌ | throughput= 8,205 tok/s
   N= 384 | p50=4.4s | p95=6.3s ❌ | throughput= 7,934 tok/s
   N= 512 | p50=6.9s | p95=8.9s ❌ | throughput= 7,794 tok/s  ← MAX p95<10s
```

**Key numbers:**
- Max concurrent (p95 < 5s): **256**
- Max concurrent (p95 < 10s): **512**
- Peak throughput plateau: **~7,500-8,200 tok/s** sustained from N=96 to N=512

### 3.4 vLLM Config (tested)

```bash
vllm serve DavidAU/Qwen3-4B-Instruct-2507-Polaris-Alpha-Distill-Heretic-Abliterated \
  --quantization fp8 \
  --kv-cache-dtype fp8 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.93 \
  --enable-prefix-caching \
  --max-num-seqs 256 \
  --max-num-batched-tokens 8192 \
  --chat-template /path/to/nothink_template.jinja
```

### 3.5 Response Quality Sample (no thinking)

```
System: "You are Sol, a warm and playful girl next door."
User: "Hey Sol, how are you this morning?"

Response (65 tokens, 0.23s):
"Ah, you finally found me—just in time for a quick chat. I'm great,
thanks for asking! Morning sun's cozy, and I was just spying on the
neighborhood cats doing a skipping routine outside my window. Want to
hear about them, or are you looking for something more low-key to do today?"
```
✅ Natural, in-character, no thinking tokens, finished with EOS.

---

## 4. L40S Estimates (NOT benchmarked — need verification)

### 4.1 Estimation Methodology

L40S FP8 performance estimated from H100 using compute ratio.

| Factor | H100 80GB SXM | L40S 48GB | Ratio |
|---|---|---|---|
| FP8 TFLOPS | 3,958 | 733 | 0.185 |
| Memory BW | 3,352 GB/s | 864 GB/s | 0.258 |
| Real-world ratio (4B model, decode-bound) | — | — | **~0.35** |

Why 0.35 instead of 0.185? Small models are memory-bandwidth bound during decode,
not compute bound. L40S ratio = ~0.258 (mem BW) adjusted up for lower overhead.

### 4.2 Estimated L40S Numbers

| Metric | H100 (actual) | L40S (estimated ×0.35) |
|---|---|---|
| Single stream tok/s | 282 | **~100** |
| Max concurrent p95<5s | 256 | **~90** |
| Max concurrent p95<10s | 512 | **~180** |
| TTFT | 0.061s | **~0.17s** |
| E2E single stream | 0.5s | **~1.3s** |

### 4.3 L40S VRAM Budget

```
L40S 48 GB:
  4B FP8 weights:        ~4.5 GB
  Embed (0.6B BF16):     ~1.0 GB
  CUDA overhead:         ~2.0 GB
  Available for KV:      ~40.5 GB
  KV per seq (4K FP8):   ~64 MB → max ~630 concurrent sequences
  Actual bottleneck:     compute throughput (NOT memory)
```

⚠️ **L40S numbers require real benchmark to validate. H100→L40S ratio varies by model.**

---

## 5. Engagement Assumptions

| Metric | Value | Source |
|---|---|---|
| DAU/MAU ratio | 35% | Companion apps: 25-45% |
| Peak online (% of DAU) | 10% = **3.5% of MAU** | Evening concentrated |
| Peak duration | 6 hours/day (18-24h) | Companion usage |
| Day online (% of DAU) | 5% | 10 hours/day |
| Night online (% of DAU) | 1.5% | 8 hours/day |
| Time between messages | 45 seconds | User reads + types + sends |
| Active chatting rate | 50% of online | Rest are browsing/idle |

### Request duration under load

| Concurrency | P50 latency (H100) | P50 latency (L40S est.) |
|---|---|---|
| Low (N≤16) | 0.5-0.7s | 1.3-2.0s |
| Medium (N=96) | 1.5s | ~4.3s |
| High (N=256) | 2.9s | — (exceeds L40S capacity) |

**For cost modeling, use P50 under typical load:**
- H100: **~2s** per request (at ~100-200 concurrent)
- L40S: **~3.5s** per request (at ~50-90 concurrent)

---

## 6. Capacity Model

### 6.1 Users Per Pod

```
Duty cycle = request_time / time_between_messages

H100:
  duty = 2.0s / 45s = 4.4%
  Active chatters/pod = 256 / 0.044 = 5,818 (at max p95<5s)
  66% safety margin: 3,840 active chatters
  Online users (÷50% active rate): 7,680 online users/pod
  Conservative planning: 5,000 online users/pod

L40S:
  duty = 3.5s / 45s = 7.8%
  Active chatters/pod = 90 / 0.078 = 1,154 (at max p95<5s)
  66% safety margin: 762 active chatters
  Online users (÷50% active rate): 1,524 online users/pod
  Conservative planning: 1,000 online users/pod
```

### 6.2 Pods Needed Per Scale

**Peak online = 3.5% of MAU**

| MAU | Peak online | H100 pods (peak) | H100 pods (day) | H100 pods (night) | L40S pods (peak) | L40S pods (day) | L40S pods (night) |
|---|---|---|---|---|---|---|---|
| 100K | 3,500 | 1 | 1 | 1 | 4 | 2 | 1 |
| 500K | 17,500 | 4 | 2 | 1 | 18 | 9 | 3 |
| 1M | 35,000 | 7 | 4 | 2 | 35 | 18 | 6 |
| 5M | 175,000 | 35 | 18 | 6 | 175 | 88 | 27 |
| 10M | 350,000 | 70 | 35 | 11 | 350 | 175 | 53 |

---

## 7. GPU Pricing (RunPod)

| GPU | On-Demand | 1-Year Reserved | Notes |
|---|---|---|---|
| **L40S (Secure)** | $0.86/hr | $0.71/hr ($511/mo) | ✅ Confirmed pricing |
| **H100 80GB SXM (Community)** | $2.49/hr | ~$2.09/hr (~$1,505/mo) | ⚠️ Need to verify reserved |
| **H100 80GB SXM (Secure)** | $3.29/hr | ~$2.50/hr (~$1,800/mo) | ⚠️ Need to verify reserved |

### Services (same for both GPU options)

| Service | 1M MAU | 5M MAU | 10M MAU |
|---|---|---|---|
| Redis (GalaxyCloud) | $95 | $195 | $395 |
| Qdrant Cloud | $75 | $200 | $400 |
| Monitoring (Grafana) | $19 | $54 | $54 |
| Chargen pod (4090) | $365 | $365 | $365 |
| **Total services** | **$554** | **$814** | **$1,214** |

---

## 8. Cost Table — Option A: L40S (Lower cost, more pods)

### Auto-scaling strategy:
- **Reserved**: 1-year savings ($0.71/hr), run 24/7 = night minimum
- **On-demand**: $0.86/hr, scale by time of day
- Night (8h): reserved only
- Day (10h): reserved + on-demand
- Peak (6h): reserved + max on-demand

```
GPU cost = reserved_pods × $511/mo
         + (day_pods - reserved) × 10h × 30d × $0.86
         + (peak_pods - day_pods) × 6h × 30d × $0.86
```

| MAU | Reserved | Day extra | Peak extra | GPU cost | Services | **TOTAL/mo** | **$/user** |
|---|---|---|---|---|---|---|---|
| **500K** | 3 × $511 | 6 × $258 | 9 × $155 | **$4,323** | $179 | **$4,502** | **$0.009** |
| **1M** | 6 × $511 | 12 × $258 | 17 × $155 | **$8,801** | $554 | **$9,355** | **$0.009** |
| **5M** | 27 × $511 | 61 × $258 | 87 × $155 | **$43,020** | $814 | **$43,834** | **$0.009** |
| **10M** | 53 × $511 | 122 × $258 | 175 × $155 | **$85,338** | $1,214 | **$86,552** | **$0.009** |

### Detailed 1M MAU breakdown:
```
Night:  6 reserved      = 6 × $511                    = $3,066
Day:   18 needed - 6 rsv = 12 × 10h × 30d × $0.86    = $3,096
Peak:  35 needed - 18 day = 17 × 6h × 30d × $0.86    = $2,639
GPU total:                                             = $8,801
+ Services:                                            = $554
TOTAL 1M:                                              = $9,355/mo
```

---

## 9. Cost Table — Option B: H100 (Fewer pods, simpler ops)

Same auto-scaling strategy, H100 Community pricing ($2.49/hr OD, ~$1,505/mo reserved).

```
GPU cost = reserved_pods × $1,505/mo
         + (day_pods - reserved) × 10h × 30d × $2.49
         + (peak_pods - day_pods) × 6h × 30d × $2.49
```

| MAU | Reserved | Day extra | Peak extra | GPU cost | Services | **TOTAL/mo** | **$/user** |
|---|---|---|---|---|---|---|---|
| **500K** | 1 × $1,505 | 1 × $747 | 2 × $449 | **$3,150** | $179 | **$3,329** | **$0.007** |
| **1M** | 2 × $1,505 | 2 × $747 | 3 × $449 | **$5,851** | $554 | **$6,405** | **$0.006** |
| **5M** | 6 × $1,505 | 12 × $747 | 17 × $449 | **$25,627** | $814 | **$26,441** | **$0.005** |
| **10M** | 11 × $1,505 | 24 × $747 | 35 × $449 | **$49,998** | $1,214 | **$51,212** | **$0.005** |

### Detailed 1M MAU breakdown:
```
Night:  2 reserved       = 2 × $1,505                  = $3,010
Day:    4 needed - 2 rsv  = 2 × 10h × 30d × $2.49     = $1,494
Peak:   7 needed - 4 day  = 3 × 6h × 30d × $2.49      = $1,347
GPU total:                                              = $5,851
+ Services:                                             = $554
TOTAL 1M:                                               = $6,405/mo
```

---

## 10. Comparison: H100 vs L40S

| Metric | L40S | H100 Community | H100 advantage |
|---|---|---|---|
| **1M MAU/mo** | $9,355 | **$6,405** | **-32%** |
| **5M MAU/mo** | $43,834 | **$26,441** | **-40%** |
| **10M MAU/mo** | $86,552 | **$51,212** | **-41%** |
| Pods at 10M peak | 350 | **70** | 5× fewer |
| Operations complexity | High (many pods) | **Low** | Simpler |
| Availability (RunPod) | ✅ High | ⚠️ Limited | Risk |
| Benchmark status | ❌ Estimated | ✅ **Actual data** | Reliable |
| Cold start risk | Low (small model) | Low | Same |

**H100 is 32-41% cheaper AND simpler to operate.**
Main risk: H100 availability on RunPod at scale.

---

## 11. Revenue vs Cost

| MAU | Cost/mo (H100) | Cost/mo (L40S) | Revenue/mo (5% × $9.99) | Margin (H100) | Margin (L40S) |
|---|---|---|---|---|---|
| 100K | $2,900 | $3,000 | $49,950 | **94%** | **94%** |
| 1M | $6,405 | $9,355 | $499,500 | **99%** | **98%** |
| 5M | $26,441 | $43,834 | $2,497,500 | **99%** | **98%** |
| 10M | $51,212 | $86,552 | $4,995,000 | **99%** | **98%** |

---

## 12. Key Risks & Unknowns

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **L40S numbers are ESTIMATED** | Entire L40S cost table could be wrong | 1h benchmark on L40S ($0.86) to validate |
| 2 | **H100 reserved pricing unverified** | ±20% on H100 cost | Verify with RunPod sales |
| 3 | **H100 availability at scale** | Can't get 70 H100s on RunPod | Multi-provider or L40S fallback |
| 4 | **DAU/MAU higher than 35%** | More pods | Use 45% for worst-case |
| 5 | **Active chat rate > 50%** | More concurrent per user | Stress test showed 256 headroom |
| 6 | **FP8 quality for Vietnamese** | Must use BF16 → ~1.5× pods | Quality test needed |
| 7 | **Prefix caching ineffective** | Benchmark shows only 0.3% | Accept — still fast enough |
| 8 | **Abliterated model too uncensored** | Safety concerns | Custom safety filter in app layer |

---

## 13. Questions for Perplexity

1. **H100→L40S ratio**: We used ×0.35 for a 4B decode-bound model. Is this reasonable? What empirical data exists for Qwen3-4B FP8 on L40S?

2. **H100 pricing**: RunPod H100 80GB SXM community $2.49/hr — correct? What is 1-year reserved pricing? Are there cheaper H100 providers for sustained workloads (Lambda, CoreWeave, Crusoe)?

3. **H100 availability**: Can we realistically run 70 H100s on RunPod at 10M MAU? Or should we use a different provider?

4. **Engagement assumptions**: 3.5% of MAU peak online, 50% active chatting, 45s between messages — reasonable for companion chatbot?

5. **Cost comparison**: Our model shows H100 is 32-41% cheaper than L40S. Does this match industry data? Are there scenarios where L40S wins?

6. **Is there a better GPU option?** A100 80GB, A6000, or others for this workload? (4B FP8 model, 256 concurrent, ~8K tok/s sustained)

7. **Auto-scaling**: RunPod API cold start for H100 pods? Warm pool needed? Cost of keeping warm pods idle?

8. **At 10M MAU, $51K/mo on H100**: Is this realistic for a companion chatbot? What do Character.AI / Replika spend per user?

---

*DokiChat Cost Model v3 — 16/03/2026 — For Perplexity verification*
*Based on actual H100 benchmark of DavidAU/Qwen3-4B-Instruct-2507-Polaris-Alpha-Distill-Heretic-Abliterated*
