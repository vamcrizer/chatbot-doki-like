# vLLM Deploy Guide — DokiChat
### Cập nhật 12/03/2026

---

## I. vLLM là gì?

vLLM là inference engine cho LLM, tối ưu hóa tốc độ và bộ nhớ GPU.

**Tính năng chính:**

| Feature | Giải thích |
|---|---|
| **PagedAttention** | Quản lý KV cache theo "pages" — không lãng phí VRAM, cho phép nhiều users hơn |
| **Continuous Batching** | Request xong → slot trống → request mới vào ngay, GPU luôn chạy 90%+ |
| **Prefix Caching** | System prompt giống nhau → cache 1 lần, share cho tất cả users cùng character |
| **Streaming** | Trả token từng cái qua SSE, user thấy chữ chạy ra real-time |
| **OpenAI API** | Tương thích `/v1/chat/completions` — đổi URL là xong |
| **Tensor Parallel** | Chia model qua nhiều GPU (cần cho model lớn) |
| **Quantization** | Hỗ trợ BF16, FP16, FP8, AWQ, GPTQ |

---

## II. Cài đặt

### Docker (Khuyến nghị — dùng cho RunPod)

```bash
# Image chính thức
docker pull vllm/vllm-openai:v0.17.0

# Chạy serve model
docker run --runtime nvidia --gpus all \
  -v /workspace/models:/models \
  -p 8000:8000 \
  vllm/vllm-openai:v0.17.0 \
  --model /models/qwen3.5-4b-davidau \
  --served-model-name dokichat-4b \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching
```

### Pip (Dev/test local)

```bash
pip install vllm==0.17.0
```

---

## III. Chạy vLLM Server

### Command cơ bản cho DokiChat 4B

```bash
vllm serve /models/qwen3.5-4b-davidau \
  --served-model-name dokichat-4b \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  --chat-template /models/qwen3.5-4b-davidau/chat_template.jinja \
  --disable-log-requests
```

### Command cho 9B Chargen (co-locate cùng pod)

```bash
vllm serve /models/qwen3.5-9b-davidau \
  --served-model-name dokichat-9b \
  --host 0.0.0.0 \
  --port 8001 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.40 \
  --chat-template /models/qwen3.5-9b-davidau/chat_template.jinja \
  --disable-log-requests
```

### Giải thích params

| Param | Giá trị | Ý nghĩa |
|---|---|---|
| `--served-model-name` | `dokichat-4b` | Tên model trong API response |
| `--max-model-len` | `8192` | Context length tối đa (tokens). Tăng = tốn VRAM cho KV cache |
| `--gpu-memory-utilization` | `0.90` | % VRAM vLLM được dùng. 0.9 = dùng 90%, giữ 10% buffer |
| `--enable-prefix-caching` | — | Cache system prompt, tiết kiệm compute cho cùng character |
| `--chat-template` | path | Custom Jinja template (bắt buộc cho DavidAU) |
| `--disable-log-requests` | — | Tắt log chi tiết (production performance) |

---

## IV. Custom Chat Template — BẮT BUỘC

DavidAU models cần custom Jinja template để:
1. Disable thinking mode (`enable_thinking = false`)
2. Anti-repeat/loop fixes từ DavidAU

### Patch template trước khi serve

```python
import os

TEMPLATE_PATH = "/models/qwen3.5-4b-davidau/chat_template.jinja"

# Đọc template gốc
with open(TEMPLATE_PATH, "r") as f:
    content = f.read()

# Inject disable thinking ở đầu file
if "enable_thinking" not in content:
    patched = "{% set enable_thinking = false %}\n" + content
    with open(TEMPLATE_PATH, "w") as f:
        f.write(patched)
    print("✅ Patched: enable_thinking = false")
else:
    print("✅ Template already patched")
```

---

## V. Gọi API — OpenAI Compatible

### Endpoints

| Endpoint | Method | Chức năng |
|---|---|---|
| `/v1/models` | GET | List models đang serve |
| `/v1/chat/completions` | POST | Chat completion (streaming/non-streaming) |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

### Chat request (non-streaming)

```python
import httpx

VLLM_URL = "http://<runpod-ip>:8000"

response = httpx.post(f"{VLLM_URL}/v1/chat/completions", json={
    "model": "dokichat-4b",
    "messages": [
        {"role": "system", "content": "<system prompt>"},
        {"role": "user", "content": "Hey Sol!"},
    ],
    "temperature": 0.85,
    "top_p": 0.9,
    "top_k": 20,
    "repetition_penalty": 1.1,
    "presence_penalty": 1.5,
    "max_tokens": 500,
    "min_tokens": 150,
})

result = response.json()
print(result["choices"][0]["message"]["content"])
```

### Chat request (streaming SSE)

```python
import httpx

with httpx.stream("POST", f"{VLLM_URL}/v1/chat/completions", json={
    "model": "dokichat-4b",
    "messages": [...],
    "stream": True,
    "temperature": 0.85,
    "top_p": 0.9,
    "top_k": 20,
    "repetition_penalty": 1.1,
    "presence_penalty": 1.5,
    "max_tokens": 500,
    "min_tokens": 150,
}) as resp:
    for line in resp.iter_lines():
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            import json
            chunk = json.loads(data)
            token = chunk["choices"][0]["delta"].get("content", "")
            print(token, end="", flush=True)
```

---

## VI. Sampling Parameters cho DokiChat

### Chat (4B — non-thinking)

```json
{
    "temperature": 0.85,
    "top_p": 0.9,
    "top_k": 20,
    "repetition_penalty": 1.1,
    "presence_penalty": 1.5,
    "max_tokens": 500,
    "min_tokens": 150
}
```

### Chargen (9B — instruct)

```json
{
    "temperature": 0.7,
    "top_p": 0.8,
    "top_k": 20,
    "repetition_penalty": 1.0,
    "presence_penalty": 1.5,
    "max_tokens": 4000
}
```

> **Lưu ý:** `presence_penalty` chỉ có trên vLLM, không có trên Transformers library. Đây là lý do production phải dùng vLLM.

---

## VII. VRAM Planning

### Đo thực tế (H100, BF16 Safetensors)

| Model | VRAM |
|---|---|
| 4B DavidAU | ~9 GB |
| 9B DavidAU | ~18 GB |
| Qwen3-Embed-0.6B | ~1 GB |

### Co-locate trên L40S 48GB

```
Cách 1: Cả 3 model 24/7
  4B (9GB) + 9B (18GB) + Embed (1GB) = 28GB
  Còn 20GB cho KV cache → OK cho testing
  
Cách 2: 4B 24/7, 9B chỉ load khi cần (Khuyến nghị)
  vLLM --gpu-memory-utilization 0.90 cho 4B
  → 4B dùng ~43GB (weights + KV cache)
  → 9B chỉ gọi khi chargen (rare, <1% requests)
```

### gpu-memory-utilization guide

| Giá trị | VRAM dùng (L40S) | Use case |
|---|---|---|
| `0.50` | 24 GB | Co-locate 2 models |
| `0.70` | 33.6 GB | Co-locate + headroom |
| `0.90` | 43.2 GB | Single model, max concurrent |
| `0.95` | 45.6 GB | Aggressive, production |

---

## VIII. RunPod Deployment

### Startup script (`start.sh`)

```bash
#!/bin/bash
set -e

echo "🚀 DokiChat vLLM Starting..."

# Patch chat template
python3 /app/patch_template.py

# Start vLLM for 4B chat
vllm serve /workspace/models/qwen3.5-4b-davidau \
  --served-model-name dokichat-4b \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  --chat-template /workspace/models/qwen3.5-4b-davidau/chat_template.jinja \
  --disable-log-requests &

# Wait for vLLM to be ready
echo "Waiting for vLLM..."
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
  sleep 2
done
echo "✅ vLLM ready"

# Keep container alive
wait
```

### Test connection

```bash
# Check health
curl http://<pod-url>:8000/health

# List models
curl http://<pod-url>:8000/v1/models

# Test chat
curl http://<pod-url>:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dokichat-4b",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

---

## IX. Monitoring

### Prometheus metrics endpoint

```
GET /metrics
```

Metrics quan trọng:

| Metric | Ý nghĩa |
|---|---|
| `vllm:num_requests_running` | Số requests đang xử lý |
| `vllm:num_requests_waiting` | Số requests đang chờ trong queue |
| `vllm:gpu_cache_usage_perc` | % KV cache đang dùng |
| `vllm:avg_generation_throughput_toks_per_s` | Throughput trung bình |
| `vllm:e2e_request_latency_seconds` | Latency end-to-end |
| `vllm:time_to_first_token_seconds` | TTFT — thời gian đến token đầu tiên |

### Grafana dashboard

```
vLLM /metrics → Prometheus (15s scrape) → Grafana Cloud
```

---

## X. Troubleshooting

| Vấn đề | Nguyên nhân | Fix |
|---|---|---|
| OOM (Out of Memory) | VRAM không đủ | Giảm `--max-model-len` hoặc `--gpu-memory-utilization` |
| Slow TTFT | KV cache đầy, prefix miss | Enable `--enable-prefix-caching` |
| Token repeat | Thiếu penalty | Thêm `presence_penalty=1.5` + `repetition_penalty=1.1` |
| Model load fail | Sai path hoặc format | Verify safetensors files exist, check CUDA version |
| Thinking tags in output | Template chưa patch | Run `patch_template.py` trước khi serve |
| Wrong language | Template forced English | Ensure RULE 0 in system prompt matches user language |

---

*vLLM Deploy Guide — DokiChat — 12/03/2026*
