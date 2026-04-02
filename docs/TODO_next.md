# TODO Next: 3 Điểm Chốt Hạ Cho Scale Ngang (Horizontal Scaling)

Kiến trúc hiện tại **gần đúng rồi, nhưng có 3 điểm cần code cẩn thận ngay từ đầu** để scale ngang không bị vỡ.

***

## ✅ Những gì đã scale-ready

| Thành phần | Lý do |
|---|---|
| Session state | Nằm trong Redis, không trong RAM pod → thêm pod mới đọc được ngay |
| Rate limit | Redis ZSET → distributed tự nhiên |
| Write-behind messages | Redis Streams + Consumer Group → nhiều pod flush không duplicate |
| SSE sticky | Cloudflare cookie-based → user gắn cứng vào 1 pod |

***

## 🔴 Vấn đề 1: Summary trigger bị duplicate

```python
# Code hiện tại (nguy hiểm với nhiều pod):
if turn_count % 50 == 0:
    asyncio.create_task(generate_summary(...))
```

Pod #1 và Pod #2 cùng nhận turn 50 của 2 user khác nhau — không vấn đề. **Nhưng nếu cùng 1 user** gửi 2 request gần nhau đúng lúc `turn_count = 50` và cả 2 pod đều check → **2 summary được tạo ra** cho cùng 1 đoạn hội thoại.

**Fix bằng Redis distributed lock:**
```python
lock_key = f"summary_lock:{conv_id}:{turn_count}"
acquired = await redis.set(lock_key, 1, nx=True, ex=60)
if acquired:
    asyncio.create_task(generate_summary(...))
# nx=True: chỉ 1 pod set được, pod kia bị skip
```

***

## 🔴 Vấn đề 2: Consumer Group flush worker chạy trên mỗi pod

Mỗi API pod đang chạy 1 background worker `XREADGROUP`. Với Redis Streams + Consumer Group thì **đây là đúng** — mỗi pod là 1 consumer, Streams tự phân chia message. Nhưng cần đảm bảo Consumer Group **được tạo 1 lần duy nhất** khi khởi động:

```python
# startup event trong FastAPI
@app.on_event("startup")
async def startup():
    try:
        await redis.xgroup_create("db_write:stream:messages", "pg_workers", "$", mkstream=True)
        await redis.xgroup_create("db_write:stream:affections", "pg_workers", "$", mkstream=True)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise  # Group đã tồn tại → bỏ qua, không phải lỗi
```

***

## 🟡 Vấn đề 3: Phase 1 chỉ có 1 GPU — vLLM Router chưa có

Khi bắt đầu 1 GPU, bạn gọi thẳng GPU không qua Router. Nhưng **code cần viết sao cho URL GPU là config**, không hardcode:

```python
# ❌ Hardcode
GPU_URL = "http://gpu-pod-1.internal:8000"

# ✅ Config-driven — thêm GPU chỉ cần sửa env
GPU_ENDPOINTS = os.getenv("GPU_ENDPOINTS", "http://gpu-1.internal:8000").split(",")
# Phase 2: "http://gpu-1.internal:8000,http://gpu-2.internal:8000"
# → Router đọc list này, round-robin hoặc least-waiting
```

***

## Tóm lại: Dev từ 1 pod nhưng viết như nhiều pod

```
1 CPU Pod + 1 GPU Pod (hiện tại)
    │
    ├── Redis là nguồn state duy nhất ✅ (đã đúng)
    ├── Summary lock: redis.set(nx=True) ← cần thêm
    ├── Consumer Group startup: BUSYGROUP safe ← cần thêm  
    └── GPU URL: đọc từ env, comma-separated ← cần thêm

Scale lên 2 CPU + 2 GPU:
    → Thêm pod mới, đổi env GPU_ENDPOINTS
    → Không sửa 1 dòng code logic
```

3 dòng code nhỏ ở trên là khoản đầu tư rẻ nhất để tránh phải refactor lớn khi scale.
