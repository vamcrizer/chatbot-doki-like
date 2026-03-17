# MÔI TRƯỜNG DEPLOY — DokiChat Production
### Nghiên cứu 11/03/2026

***

## I. CORE STACK — Verified

| Component | Version | Nguồn |
|---|---|---|
| **vLLM** | **v0.17.0** (released 6-7/03/2026) | PyPI, GitHub releases |
| **Python** | **3.12** (vLLM hỗ trợ 3.9-3.12, khuyến nghị 3.12) | vLLM docs |
| **PyTorch** | **2.10** (đi kèm vLLM v0.17.0) | vLLM release notes |
| **CUDA** | **12.8** (vLLM pre-compiled binaries) | vLLM GPU install page |
| **FlashAttention** | **4** (mới trong v0.17.0) | vLLM release notes |
| **FastAPI** | **0.135.1** | PyPI |
| **Uvicorn** | **0.41.0** (requires Python ≥3.10) | PyPI |
| NVIDIA Driver | Chưa xác nhận exact patch — cần kiểm tra CUDA 12.8 release notes | — |

### vLLM v0.17.0 highlights

- Upgrade PyTorch 2.10
- FlashAttention 4
- **Full support Qwen3.5 family** ← quan trọng cho DokiChat
- Model Runner V2 matured (Pipeline Parallel, Decode Context Parallel)
- `--performance-mode` flag mới
- Anthropic API compatibility

***

## II. DOCKER IMAGES

| Image | Dùng cho | Ghi chú |
|---|---|---|
| **`vllm/vllm-openai:latest`** | GPU pods (primary + worker) | ✅ Khuyến nghị — official vLLM |
| **`vllm/vllm-openai:v0.17.0`** | Pin version cụ thể | ✅ Production nên pin |
| `nvcr.io/nvidia/vllm:25.09-py3` | NVIDIA NGC image | ⚠️ Có thể không hỗ trợ GGUF |
| `python:3.12-slim` | API server (FastAPI) | ✅ |
| `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` | RunPod base image | ⚠️ PyTorch 2.8, cũ hơn vLLM cần |

**Kết luận:** Dùng `vllm/vllm-openai:v0.17.0` cho GPU pods, `python:3.12-slim` cho API server.

***

## III. MODEL FORMAT — ĐÃ GIẢI QUYẾT ✅

### Vấn đề ban đầu

GGUF trên vLLM là "highly experimental" — throughput chỉ ~60-200 tok/s, trong khi BF16 Safetensors đạt ~1,200 tok/s. Dùng GGUF Q8 trên vLLM sẽ cần 5-10× GPU hơn, chi phí không khả thi.

### Giải pháp: Convert BF16 GGUF → BF16 Safetensors (lossless)

Model uncensored của hauhaucs **có bản BF16 GGUF**. Convert BF16 GGUF → BF16 Safetensors là **lossless** — cùng precision, chỉ khác format đóng gói.

```bash
pip install gguf transformers torch safetensors

python -c "
from transformers import AutoModelForCausalLM, AutoTokenizer

# Convert 4B
model = AutoModelForCausalLM.from_pretrained('path/to/qwen3.5-4b-uncensored-bf16.gguf', device_map='cpu')
tokenizer = AutoTokenizer.from_pretrained('Qwen/Qwen3.5-4B')
model.save_pretrained('./qwen3.5-4b-uncensored-safetensors', safe_serialization=True)
tokenizer.save_pretrained('./qwen3.5-4b-uncensored-safetensors')

# Convert 9B — tương tự
model = AutoModelForCausalLM.from_pretrained('path/to/qwen3.5-9b-uncensored-bf16.gguf', device_map='cpu')
tokenizer = AutoTokenizer.from_pretrained('Qwen/Qwen3.5-9B')
model.save_pretrained('./qwen3.5-9b-uncensored-safetensors', safe_serialization=True)
tokenizer.save_pretrained('./qwen3.5-9b-uncensored-safetensors')
"
```

### Kết quả

| | GGUF Q8 trên vLLM | BF16 GGUF → Safetensors trên vLLM |
|---|---|---|
| Chất lượng | Uncensored ✅ | Uncensored ✅ (giữ nguyên) |
| Precision | Q8 (quantized) | **BF16 (full precision)** |
| Throughput | ~60-200 tok/s | **~1,200 tok/s** |
| Prefix caching | ⚠️ Hạn chế | ✅ Full support |
| Tensor parallel | ⚠️ Không đầy đủ | ✅ Full support |
| **Báo cáo chi phí** | ❌ Cần sửa lại | ✅ **Giữ nguyên** |

> **Kết luận:** Convert BF16 GGUF → Safetensors giải quyết hoàn toàn vấn đề. Throughput ~1,200 tok/s đúng như báo cáo. Chi phí giữ nguyên. Chất lượng uncensored giữ nguyên.

### Model files sau convert (upload lên Network Volume)

```
/workspace/models/
├── qwen3.5-4b-uncensored-safetensors/    (~8 GB BF16)
│   ├── config.json
│   ├── model.safetensors
│   └── tokenizer files
├── qwen3.5-9b-uncensored-safetensors/    (~18 GB BF16)
│   ├── config.json
│   ├── model.safetensors
│   └── tokenizer files
└── qwen3-embedding-0.6b/                (~1 GB)
    Tổng: ~27 GB → Network Volume 30 GB
```

> ⚠️ Lưu ý: BF16 Safetensors lớn hơn GGUF Q8 (~2× kích thước file). 4B BF16 ~8GB vs Q8 ~4.5GB. Network Volume cần 30GB thay vì 20GB.

***

## IV. REQUIREMENTS.TXT

### API Server (`requirements-api.txt`)

```txt
fastapi==0.135.1
uvicorn[standard]==0.41.0
sqlalchemy
asyncpg
redis[hiredis]
pydantic
PyJWT
alembic
qdrant-client
sentence-transformers
prometheus-client
python-dotenv
httpx
openai
```

### vLLM Worker (thêm vào vLLM image) (`requirements-worker.txt`)

```txt
redis[hiredis]
prometheus-client
```

> vLLM image đã có sẵn torch, cuda, transformers. Không install thêm torch vì gây conflict binary.

***

## V. POSTGRESQL

| Version | Status | Ghi chú |
|---|---|---|
| PostgreSQL 17.6 | Latest stable (confirmed Azure) | ✅ Dùng |
| PostgreSQL 18.1 | Có thể mới hơn nhưng chưa confirmed | ⚠️ Chờ verify |

→ Dùng **PostgreSQL 17** cho ổn định.

***

## VI. RUNPOD TEMPLATE CONFIG

### Template tạo qua MCP hoặc REST API:

```json
{
  "name": "dokichat-primary",
  "imageName": "yourname/dokichat-primary:latest",
  "category": "NVIDIA",
  "containerDiskInGb": 20,
  "volumeInGb": 30,
  "volumeMountPath": "/workspace",
  "ports": ["8000/http", "8001/http", "8002/http", "22/tcp"],
  "env": {
    "MODEL_4B": "/workspace/models/qwen3.5-4b-uncensored-safetensors",
    "MODEL_9B": "/workspace/models/qwen3.5-9b-uncensored-safetensors",
    "MODEL_EMBED": "/workspace/models/qwen3-embedding-0.6b",
    "REDIS_URL": "redis://your-redis:6379",
    "PYTHONUNBUFFERED": "1"
  },
  "isPublic": false,
  "isServerless": false
}
```

### Startup command options:

```bash
# Option 1: Docker CMD trong Dockerfile
CMD ["/start.sh"]

# Option 2: Set trong template
"dockerStartCmd": ["bash", "-c", "/start.sh"]

# Option 3: JSON format
{"cmd": ["/start.sh"], "entrypoint": ["bash", "-c"]}
```

### Network Volume cho model weights:

```bash
# Tạo qua MCP
mcp_runpod_create-network-volume(
    name="dokichat-models",
    size=30,            # 30 GB cho 3 models BF16 (~27 GB)
    dataCenterId="US-TX-3"  # hoặc data center phù hợp
)
```

Pods mount Network Volume → models có sẵn tại `/workspace/models/`, không cần download.

***

## VII. TODO — TRƯỚC KHI DEPLOY

- [x] ~~Giải quyết vấn đề GGUF~~ → Convert BF16 GGUF → Safetensors (lossless)
- [ ] Download BF16 GGUF từ HuggingFace (4B + 9B)
- [ ] Chạy convert script → Safetensors output
- [ ] Verify output: load Safetensors vào vLLM local, test vài prompt
- [ ] Xác nhận NVIDIA driver minimum cho CUDA 12.8
- [ ] Tạo Docker Hub account
- [ ] Build + push Docker images
- [ ] Tạo RunPod Network Volume (30 GB)
- [ ] Upload Safetensors models lên Network Volume
- [ ] Tạo RunPod templates
- [ ] Raise GPU quota với RunPod support

***

*Nghiên cứu môi trường deploy — DokiChat — Cập nhật 12/03/2026*
