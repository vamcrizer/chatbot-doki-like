# Toàn Bộ Kịch Bản Production — AI Chat App
> Tổng hợp 49 kịch bản có thể xảy ra trong production và hướng giải quyết (Bao phủ 95% thực tế)
> Cập nhật: 2026-03-30

---

## Nhóm 1: Infrastructure Sự Cố

### 1.1 GPU Pod Chết Giữa Chừng
**Triệu chứng:** User đang chat bị mất kết nối, token stream dừng đột ngột  
**Nguyên nhân:** OOM (model quá lớn so với VRAM), RunPod node lỗi, timeout  
**Giải pháp:**
- API Pod nhận lỗi và timeout tự động trả `503 Service Unavailable` có header `Retry-After: 5`
- Trong lúc chờ, scheduler retry backend connection theo cấp số nhân (exponential backoff)
- Nếu do crash cứng, cảnh báo lên logging server và cần restart/failover trên node

- Bật lại GPU pod thủ công trên RunPod dashboard

**Phòng ngừa:** Set `--gpu-memory-utilization 0.85` thay vì 0.9, buffer 15% tránh OOM

---

### 1.2 CPU Pod / API Server Chết
**Triệu chứng:** Toàn bộ user không vào được app  
**Nguyên nhân:** OOM do quá nhiều SSE connections, deploy lại lỗi, RunPod node lỗi  
**Giải pháp:**
- 2 pod: Cloudflare tự động failover sang pod thứ 2
- MVP 1 pod: restart thủ công, downtime ~1–2 phút

**Phòng ngừa:** Set memory limit `GOMEMLIMIT`, monitor RSS memory

---

### 1.3 Upstash Redis Không Phản Hồi
**Triệu chứng:** Mọi request timeout vì không lấy được history  
**Nguyên nhân:** Upstash outage, network issue, rate limit exceeded  
**Giải pháp:**
```python
try:
    history = await asyncio.wait_for(
        redis.lrange(f"history:{conv_id}", 0, 49),
        timeout=0.5  # chỉ chờ 500ms
    )
except (asyncio.TimeoutError, RedisError):
    history = []  # fallback gửi request không có history, vẫn chạy được
```
App vẫn hoạt động, chỉ mất context ngắn hơn, không sập hoàn toàn

---

### 1.4 Neon PostgreSQL Không Phản Hồi / Cold Start
**Triệu chứng:** Request đầu tiên mất 300–500ms, user thấy lag; hoặc không load được profile/bio  
**Nguyên nhân:** Neon scale-to-zero sau idle, connection pool exhausted  
**Giải pháp:**
```python
try:
    bio = await asyncio.wait_for(pg.fetchval(...), timeout=2.0)
except asyncio.TimeoutError:
    bio = ""  # fallback prompt không có bio, vẫn inference được
```
- **Cold start:** set `min_cu = 0.25` trên Neon hoặc ping mỗi 4 phút khi có user online
- **Pool exhausted:** dùng pooled connection string `-pooler`

---

### 1.5 Cloudflare Outage
**Triệu chứng:** Toàn bộ user không truy cập được  
**Nguyên nhân:** Cloudflare incident (hiếm, SLA 99.99%)  
**Giải pháp:**
- Tạm thời trỏ DNS thẳng về RunPod IP để bypass Cloudflare
- Chấp nhận mất DDoS protection tạm thời
- Theo dõi `cloudflarestatus.com`

---

### 1.6 Network Volume Không Mount Được
**Triệu chứng:** GPU Pod không start được, model không load  
**Nguyên nhân:** RunPod storage issue, volume full  
**Giải pháp:**
- GPU Pod fallback download model từ HuggingFace (chậm hơn, ~3–5 phút)
- Kiểm tra disk usage thường xuyên, dọn cache cũ

---

## Nhóm 2: Performance Degradation

### 2.1 TTFT Tăng Đột Ngột > 3s
**Nguyên nhân có thể:**
- A. GPU bị throttle nhiệt (thermal throttling)
- B. Prompt quá dài, prefill lâu
- C. vLLM queue đầy, request phải chờ
- D. Network Volume latency tăng

**Phân biệt & giải quyết:**
```bash
# A. GPU thermal throttling
gpu_temperature > 85°C → Không làm được nhiều, RunPod lo phần cứng
# Restart pod → sang node khác

# B. Prompt quá dài
prompt_tokens tăng → Trim history xuống 30 tin thay vì 50

# C. vLLM queue đầy
vllm_num_requests_waiting tăng → Bật thêm GPU pod

# D. Network Volume latency
→ Restart GPU pod để re-mount volume
```

---

### 2.2 Throughput Giảm (tok/s Thấp)
**Nguyên nhân:** Batch size nhỏ, nhiều request ngắn không được batch cùng nhau  
**Giải pháp:**
```bash
vllm serve model --max-num-seqs 256 --max-paddings 256
```

---

### 2.3 Memory Leak Trên API Pod
**Triệu chứng:** RAM tăng dần theo thời gian, pod chậm dần rồi chết  
**Nguyên nhân:** SSE connection không được close đúng cách, async generator leak  
**Giải pháp:**
```python
async def stream_response(job_id):
    try:
        async for token in llm_stream:
            yield token
    finally:
        await cleanup_connection(job_id)  # bắt buộc có finally
```
- Schedule restart pod mỗi 24h nếu không tìm được root cause

---

### 2.4 Redis Memory Đầy
**Triệu chứng:** Upstash trả lỗi OOM, không ghi được  
**Nguyên nhân:** TTL không set đúng, quá nhiều user active  
**Giải pháp:**
- Kiểm tra `EXPIRE` set trên tất cả key chưa
- Giảm history window từ 50 xuống 30 tin
- Nâng plan Upstash lên Fixed 1GB

---

### 2.5 PostgreSQL Query Chậm
**Triệu chứng:** API response time tăng, PG query > 100ms  
**Nguyên nhân:** Table messages phình to, thiếu index  
**Giải pháp:**
```sql
-- Index có nhưng cần VACUUM thường xuyên
VACUUM ANALYZE messages;

-- Partition table theo tháng khi > 100M rows
CREATE TABLE messages_202603
    PARTITION OF messages
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

---

## Nhóm 3: Security & Abuse

### 3.1 Spam / Flood Requests
**Triệu chứng:** 1 user gửi hàng trăm tin/phút, GPU bị chiếm hết  
**Giải pháp:**
```python
# Rate limit Redis: 30 tin/phút cho giai đoạn đầu
# Global rate limit theo IP
ZADD ratelimit:ip:{ip} now {req_id}
# > 100 req/phút từ 1 IP → block 1 giờ
```

---

### 3.2 GPU API Key Bị Lộ
**Triệu chứng:** RunPod bill tăng bất thường, model bị gọi từ IP lạ  
**Nguyên nhân:** API key hardcode trong code, push lên GitHub  
**Giải pháp:**
- Rotate key ngay lập tức trên RunPod dashboard
- Dùng environment variable, không bao giờ hardcode
- Bật GitHub secret scanning

---

### 3.3 Prompt Injection
**Triệu chứng:** User cố tình inject instruction vào message thay đổi behavior model  
**Giải pháp:**
```python
def sanitize(text: str) -> str:
    text = text[:2000]  # giới hạn độ dài
    text = re.sub(r"(?i)(ignore previous|system prompt|you are now)", "", text)
    return text
```

---

### 3.4 JWT Token Bị Đánh Cắp
**Triệu chứng:** Account bị truy cập từ IP khác  
**Giải pháp:**
- Access token TTL ngắn: 15 phút
- Refresh token lưu trong PostgreSQL, có thể revoke
- Bind refresh token với device fingerprint

---

### 3.5 DDoS Attack
**Triệu chứng:** Traffic tăng đột biến bất thường, Cloudflare alert  
**Giải pháp:**
- Bật Cloudflare **Under Attack Mode** 1 click
- Rate limit Cloudflare layer trước khi vào API Pod
- API Pod vẫn chạy bình thường vì Cloudflare filter

---

## Nhóm 4: Data & Consistency

### 4.1 Redis Mất Data Trước Khi Flush Vào PG
**Triệu chứng:** Tin nhắn gần nhất không lưu vào lịch sử  
**Nguyên nhân:** API Pod chết trong khoảng 30s flush interval  
**Giải pháp:**
- Upstash bật AOF persistence mặc định → data không mất khi restart
- Giảm flush interval xuống 10s nếu cần độ bền cao hơn
- Hoặc flush ngay sau mỗi tin của assistant

---

### 4.2 Duplicate Messages Trong DB
**Triệu chứng:** Lịch sử chat hiển thị tin nhắn bị lặp  
**Nguyên nhân:** Flush worker retry khi PG timeout, insert 2 lần  
**Giải pháp:**
```sql
-- Dùng INSERT ON CONFLICT DO NOTHING
INSERT INTO messages (id, conv_id, user_id, role, content, created_at)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (id) DO NOTHING;
-- id là UUID do client gen → idempotent
```

---

### 4.3 Race Condition 2 Device Cùng Gửi Tin
**Triệu chứng:** Thứ tự tin nhắn bị sai khi user dùng 2 thiết bị  
**Giải pháp:**
- Dùng `created_at` timestamp từ server, không từ client
- Sort messages theo `created_at` khi render

---

### 4.4 Neon Database Corruption (Hiếm)
**Giải pháp:**
- Neon backup daily tự động
- Export weekly ra Cloudflare R2 thủ công:
```bash
pg_dump $DATABASE_URL | gzip | \
aws s3 cp - s3://bucket/backup-$(date +%Y%m%d).sql.gz \
--endpoint-url https://your-r2-endpoint
```

---

## Nhóm 5: Billing & Costs

### 5.1 GPU Chạy Không Tắt Khi Không Có Users
**Triệu chứng:** RunPod bill tăng dù ban đêm không có user  
**Giải pháp:**
- Tắt GPU pod thủ công lúc 2–6am nếu traffic thực sự = 0
- Hoặc autoscaler script đơn giản như đã cấp trước

---

### 5.2 Upstash Bill Tăng Bất Ngờ
**Nguyên nhân:** Quên set TTL, key tồn tại mãi mãi và tích lũy  
**Giải pháp:**
```python
# Audit tìm key không có TTL
redis.object("ENCODING", key)
# Set TTL cho tất cả key dạng history và ratelimit
```

---

### 5.3 Neon Bill Tăng Do Compute Hours
**Nguyên nhân:** Query chậm giữ compute active lâu hơn cần thiết  
**Giải pháp:**
- `pg_stat_statements` tìm slow query
- Add index đúng chỗ
- Set `statement_timeout = 5000` (5s) tránh query treo vô hạn

---

## Nhóm 6: Operational

### 6.1 Deploy Model Mới Không Downtime
**Giải pháp — Blue-green deployment thủ công:**
1. Start GPU Pod 2 với model mới
2. Chờ Pod 2 warm up (~20s với Network Volume)
3. Cập nhật vLLM Router backends chỉ gửi Pod 2
4. Chờ Pod 1 xử lý hết request đang chạy (drain)
5. Stop GPU Pod 1

---

### 6.2 Neon Schema Migration Không Downtime
**Giải pháp:**
```sql
-- ĐÚNG: thêm column nullable, không lock table
ALTER TABLE messages ADD COLUMN metadata JSONB;

-- SAI: thêm NOT NULL không có DEFAULT → lock toàn bộ table
ALTER TABLE messages ADD COLUMN metadata JSONB NOT NULL;
```

---

### 6.3 Upstash Key Naming Conflict
**Phòng ngừa từ đầu — đặt prefix rõ ràng:**
```
history:{conv_id}
ratelimit:user:{user_id}
ratelimit:ip:{ip}
session:{session_id}
lock:{conv_id}
```

---

### 6.4 vLLM Router Mất Danh Sách GPU Pods
**Triệu chứng:** Router trả 502 vì không còn backend nào  
**Nguyên nhân:** Tất cả GPU pod restart cùng lúc  
**Giải pháp:**
- Không restart tất cả GPU cùng lúc → rolling restart từng pod
- Health check endpoint `/health` trên mỗi GPU pod, Router tự remove backend lỗi

---

## Nhóm 7: vLLM & GPU Đặc Thù

### 7.1 KV Cache Đầy VRAM
**Triệu chứng:** TTFT tăng dần theo thời gian, không phải đột ngột  
**Nguyên nhân:** User có lịch sử chat dài → prompt dài → KV cache chiếm dần VRAM  
(LLaMA 13B tốn ~1MB KV cache/token, context 4K = 4GB chỉ riêng cache)  
**Giải pháp:**
```bash
# Bật chunked prefill — xử lý prompt dài theo chunk, không block GPU
vllm serve model --enable-chunked-prefill

# Monitor KV cache usage
# Nếu vllm_gpu_cache_usage_perc > 90% liên tục → thêm GPU hoặc giảm max_model_len
vllm serve model --max-model-len 4096
```

---

### 7.2 Prefix Cache Miss Hoàn Toàn
**Triệu chứng:** TTFT cao bất thường dù model warm, session affinity đang hoạt động  
**Nguyên nhân:** GPU pod restart → KV cache xóa hết, mọi request phải prefill lại từ đầu  
**Giải pháp:**
- Chấp nhận sau restart 10–20 request đầu sẽ chậm hơn bình thường, sau đó cache warm lại tự nhiên
- Không restart GPU pod giờ cao điểm

---

### 7.3 vLLM Treo Không Sinh Token
**Triệu chứng:** Request không trả về gì, không có token, cứ treo mãi  
**Nguyên nhân:** Deadlock trong vLLM scheduler, thường gặp với batch size lớn  
**Giải pháp:**
```python
# API Pod set timeout cứng cho inference call
async with asyncio.timeout(60):  # tối đa 60s
    async for token in llm_stream:
        yield token
# Timeout trả về lỗi rõ ràng thay vì treo vô hạn
```

---

### 7.4 GPU Chạy Nhưng Throughput = 0
**Triệu chứng:** Pod đang running, không có lỗi, nhưng không sinh token nào  
**Nguyên nhân:** vLLM process chết nhưng container vẫn sống, health check pass vì port vẫn mở  
**Giải pháp:**
```bash
# Health check PHẢI check health của vLLM, không chỉ check port
curl http://gpu-pod:8000/health
# Nếu trả về 200 → vLLM đang chạy thật
# Nếu timeout hoặc 503 → restart pod
```

---

## Nhóm 8: SSE & Streaming Đặc Thù

### 8.1 Proxy Timeout Cắt SSE Giữa Chừng
**Triệu chứng:** Response bị cắt đúng sau ~30s hoặc 60s, không phụ thuộc độ dài response  
**Nguyên nhân:** Cloudflare, Nginx, hay bất kỳ proxy nào đều có idle timeout mặc định  
**Giải pháp:**
```python
# Gửi SSE heartbeat mỗi 15s giữ connection sống
async def stream_with_heartbeat(llm_stream):
    last_token_time = time.time()
    async for token in llm_stream:
        yield f" {token}\n\n"
        last_token_time = time.time()
        # Nếu model đang nghĩ lâu hơn 10s, gửi comment giữ connection
        if time.time() - last_token_time > 10:
            yield ": heartbeat\n\n"  # SSE comment, không hiện ra UI
```
> FastAPI mới nhất tự động gửi ping mỗi 15s khi dùng `EventSourceResponse`

---



### 8.4 Memory Leak Do SSE Connection Không Close
**Triệu chứng:** RAM API Pod tăng ~50MB/giờ, không bao giờ giảm  
**Nguyên nhân:** User đóng tab nhưng server không biết → async generator tiếp tục chạy trong background  
**Giải pháp:**
```python
async def stream_response(request: Request, job_id: str):
    try:
        async for token in llm_stream(job_id):
            if await request.is_disconnected():  # check mỗi token
                break
            yield f" {token}\n\n"
    finally:
        await cancel_llm_job(job_id)  # hủy job trên vLLM nếu user disconnect
```

---

## Nhóm 9: Cache Stampede & Thundering Herd

### 9.1 Cache Stampede Sau Redis Restart
> **Đây là kịch bản nguy hiểm nhất, ít người nghĩ đến**

```
Redis restart → toàn bộ cache miss
        ↓
10,000 user load app cùng lúc
        ↓
10,000 request đồng thời hit PostgreSQL
        ↓
PG connection pool exhausted → PG chết → app chết hoàn toàn
```

**Giải pháp — Mutex Lock (chỉ 1 request query PG):**
```python
async def get_history_safe(conv_id):
    data = await redis.get(f"history:{conv_id}")
    if data:
        return json.loads(data)

    # Cache miss → dùng lock, chỉ 1 request query PG
    async with redis.lock(f"lock:{conv_id}", timeout=5):
        data = await redis.get(f"history:{conv_id}")  # double check
        if data:
            return json.loads(data)

        # Chỉ 1 request này query PG, các request khác chờ lock
        history = await pg.fetch("SELECT * FROM messages WHERE conv_id=$1 LIMIT 50", conv_id)
        await redis.setex(f"history:{conv_id}", 3600, json.dumps(history))
        return history
```

---

### 9.2 Thundering Herd Khi Deploy
**Triệu chứng:** Mỗi lần deploy spike CPU 100% trong 30–60s đầu  
**Nguyên nhân:** Pod restart → cache lạnh → mọi request đều hit PG cùng lúc  
**Giải pháp — Warm cache trước khi nhận traffic:**
```python
@app.on_event("startup")
async def warmup():
    # Pre-warm cache cho N conversation active nhất
    active_convs = await pg.fetch(
        "SELECT conv_id FROM messages GROUP BY conv_id "
        "ORDER BY MAX(created_at) DESC LIMIT 100"
    )
    for conv in active_convs:
        await get_history_safe(conv["conv_id"])
```

---

## Nhóm 10: UX & Edge Cases

### 10.1 User Gửi Tin Khi Model Đang Sinh Token
**Triệu chứng:** User bấm gửi tin mới trong khi response cũ chưa xong → 2 stream chạy song song → UI lộn xộn  
**Giải pháp:**
```python
# Backend: 1 conv_id chỉ cho phép 1 active stream tại 1 thời điểm
active_streams = set()

async def chat(conv_id):
    if conv_id in active_streams:
        raise HTTPException(409, "Another response is being generated")
    active_streams.add(conv_id)
    try:
        async for token in llm_stream:
            yield token
    finally:
```

---

### 10.2 Prompt Quá Dài Vượt Context Window
**Triệu chứng:** vLLM trả lỗi `maximum context length exceeded`  
**Nguyên nhân:** bio dài + 50 tin lịch sử + tin mới > `max_model_len`  
**Giải pháp:**
```python
def trim_history(bio, history, new_msg, max_tokens=3500):
    bio_tokens = len(bio) // 2
    new_msg_tokens = len(new_msg) // 2
    budget = max_tokens - bio_tokens - new_msg_tokens - 200  # buffer

    # Trim history từ tin cũ nhất cho đến khi vừa budget
    trimmed, used = [], 0
    for msg in reversed(history):  # từ mới nhất đến cũ nhất
        tokens = len(msg["content"]) // 2
        if used + tokens > budget:
            break
        trimmed.insert(0, msg)
        used += tokens
    return trimmed
```

---

## Nhóm 11: RunPod Đặc Thù

### 11.1 GPU Pod Bị Preempt (Community Cloud)
**Triệu chứng:** Pod tự dưng terminate giữa chừng, không báo trước  
**Nguyên nhân:** Community Cloud GPU là spot instance, có thể bị lấy lại bất cứ lúc nào  
**Giải pháp:**
- Dùng **Secure Cloud** thay vì Community Cloud để ít bị preempt hơn
- Hoặc dùng **Reserved pod** nếu cần stability cao

---

### 11.2 Network Volume Chậm Bất Ngờ
**Triệu chứng:** Model load chậm hơn bình thường, TTFT tăng do IO wait  
**Nguyên nhân:** Network Volume là NFS, latency phụ thuộc load của storage cluster  
**Giải pháp:**
```bash
# Startup script GPU pod: copy model về local disk trước
cp -r /runpod-volume/model /tmp/model  # copy về local SSD
vllm serve /tmp/model ...              # serve từ local, không qua NFS
```

---

## Nhóm 12: Đặc thù AI Roleplay / Model Behavior

### 12.1 Model Bị Hallucinate Nặng Cùng Một Lỗi
**Triệu chứng:** Hàng loạt user report nhân vật nói lảm nhảm, lặp lại một từ vô nghĩa (ví dụ: "I... I... I... I..."), hoặc phá vỡ persona (break in character).  
**Nguyên nhân:** Lỗi do context window chứa các token lặp lại bị vLLM tính toán attention sai, hoặc setting `repetition_penalty` / `temperature` chưa phù hợp với base model mới update.  
**Giải pháp:**
- **Khẩn cấp:** Override config `temperature` (thường giảm xuống) hoặc tăng `repetition_penalty` thông qua Redis config (không cần restart pod).
- **Lâu dài:** Tích hợp một hàm filter (Logit Processor) để phát hiện chuỗi lặp lại và tự động force stop stream.

---

### 12.2 Model Xả Output Quá Dài (Over-generation)
**Triệu chứng:** Token generation kéo dài bất thường, vượt qua giới hạn trả lời mong muốn (ví dụ model roleplay tự diễn luôn phần của user).  
**Nguyên nhân:** Thiếu các Stop Tokens đúng chuẩn (ví dụ: `<|im_end|>` hoặc `User:` bị model lờ đi).  
**Giải pháp:**
- Đảm bảo cấu hình vLLM có đầy đủ danh sách `stop_token_ids` và `stop` strings.
- API Server tự động `break` stream và gửi lệnh cancel job nếu phát hiện model bắt đầu gen ra text đại diện cho User.

---

### 12.3 Immersion Cache Trả Về Câu Cũ Dù Context Mới
**Triệu chứng:** Dù user đã chuyển qua bối cảnh mới, nhưng do prompt neo (anchor prompt) vẫn giống hệt, Immersion Cache vẫn trả về câu trả lời cũ đã được cache.  
**Nguyên nhân:** Khóa cache chỉ dựa trên `immersion:{char}:{lang}` mà không tính đến các biến số ngữ cảnh (scene, mood).  
**Giải pháp:**
- Cần thêm ít nhất một tham số động vào cache key (ví dụ: hash của 3 tin nhắn gần nhất) hoặc vô hiệu hóa Immersion Cache (bypass) khi scene state thay đổi mạnh.

---

## Nhóm 13: Distributed System & Rate Limit (Scale Lớn)

### 13.1 Race Condition ở Rate Limiter
**Triệu chứng:** User thỉnh thoảng vượt qua được giới hạn (ví dụ cho 30 tin/phút nhưng spam được 35 tin).  
**Nguyên nhân:** Code kiểm tra rate limit chia làm 2 bước `GET` rồi `INCR`, giữa 2 bước đó user gửi nhiều request đồng thời.  
**Giải pháp:**
- Sử dụng Lua Script trong Redis (đảm bảo tính atomic) hoặc các hàm built-in của Upstash Rate Limiter (đã implement sẵn Sliding Window/Token Bucket bằng Lua).

---

### 13.2 Clock Drift (Lệch Giờ Server)
**Triệu chứng:** JWT token thỉnh thoảng bị báo "Expired" ngay khi vừa tạo, hoặc thứ tự tin nhắn bị sai lệch nghiêm trọng.  
**Nguyên nhân:** Các pod FastAPI chạy trên các node RunPod khác nhau có hệ thống thời gian không đồng bộ (lệch vài giây).  
**Giải pháp:**
- Luôn sử dụng thư viện xử lý JWT có cho phép `clock_skew_leeway` (ví dụ cho phép lệch 10-30s).
- Khi lưu DB, để PostgreSQL tự gen `created_at` (dùng `DEFAULT NOW()`) thay vì truyền timestamp từ Python pod vào, vì DB luôn là nguồn thời gian duy nhất (Single Source Truth).

---

## Nhóm 14: Storage & DB Limits

### 14.1 Neon DB Bị Khóa Ghi (Read-Only Mode)
**Triệu chứng:** Mọi lệnh insert lịch sử chat đều ném ra lỗi.  
**Nguyên nhân:** Ổ cứng/Compute time của Neon đạt giới hạn (ví dụ hết dung lượng free tier hoặc gói hiện tại).  
**Giải pháp:**
- Setup alert trước khi đạt 80% dung lượng.
- Nếu xảy ra, API Server cần tự động chuyển sang chế độ "Cache-only mode" (chỉ lưu session trên Redis, chấp nhận rủi ro mất data nếu Redis sập) để user không bị gián đoạn, trong lúc dev nâng cấp gói DB.

---

### 14.2 Postgres ID Overflow
**Triệu chứng:** Ứng dụng sập hoàn toàn khi tạo tin nhắn mới.  
**Nguyên nhân:** Nếu bạn dùng `SERIAL` (Integers 32-bit) cho ID bảng `messages`, với volume chat của AI app, giới hạn ~2 tỷ records sẽ bị chạm tới nhanh hơn bạn nghĩ (10k user x 100 tin/ngày = 1 triệu tin/ngày, 5 năm là tràn).  
**Giải pháp:**
- Bắt buộc dùng `BIGSERIAL` (64-bit) cho các khóa chính tăng tự động, hoặc tốt nhất là dùng UUID (v4 hoặc v7).

---



## Ma Trận Ưu Tiên Xử Lý (Triagiang)

Chỉ tập trung làm các kịch bản đánh dấu 🔴 P0 và 🟡 P1 trước khi launch production. Các kịch bản P2 và P3 có thể xử lý dần trong giai đoạn Growth/Scale.

| Nhóm kịch bản | Tần suất | Mức độ nghiêm trọng | Ưu tiên fix |
|---|---|---|---|
| GPU Pod chết giữa chừng | Cao | Cao | 🔴 P0 |
| Redis không phản hồi | Trung | Cao | 🔴 P0 |
| Cache Stampede | Thấp | Rất cao | 🔴 P0 |
| Memory Leak SSE | Cao | Cao | 🔴 P0 |
| Proxy cắt SSE 30s | Cao | Cao | 🔴 P0 |
| Prompt vượt context | Trung | Trung | 🟡 P1 |
| Duplicate messages | Trung | Trung | 🟡 P1 |
| Thundering herd deploy | Thấp | Cao | 🟡 P1 |
| JWT bị đánh cắp | Thấp | Cao | 🟡 P1 |
| Spam flood | Trung | Trung | 🟡 P1 |
| API key bị lộ | Rất thấp | Rất cao | 🟡 P1 |
| GPU throughput = 0 | Thấp | Cao | 🟡 P1 |
| Model Xả Output Quá Dài | Trung | Trung | 🟡 P1 |
| KV Cache đầy VRAM | Trung | Trung | 🟠 P2 |
| Neon cold start | Cao | Thấp | 🟠 P2 |
| PostgreSQL query chậm | Trung | Thấp | 🟠 P2 |
| Redis bill tăng | Thấp | Thấp | 🟠 P2 |
| GPU chạy ban đêm | Thấp | Thấp | 🟠 P2 |
| Neon DB Bị Khóa Ghi | Rất thấp | Rất cao | 🟠 P2 |
| Model Bị Hallucinate Nặng | Thỉnh thoảng | Cao | 🟠 P2 |
| Race Condition ở Rate Limiter | Trung | Thấp | 🟠 P2 |
| Schema migration | Rất thấp | Trung | 🟢 P3 |
| Network Volume chậm | Thấp | Thấp | 🟢 P3 |
| Postgres ID Overflow | Không đáng kể | Rất cực đoan | 🟢 P3 |

---

## Nguyên Tắc Xử Lý Chung

| Nguyên tắc | Áp dụng |
|---|---|
| **Fail gracefully** | Mọi external call đều có timeout + fallback |
| **Idempotent writes** | `INSERT ON CONFLICT DO NOTHING` |
| **Never block users** | Redis/PG timeout → tiếp tục với data rỗng |
| **Drain trước khi tắt** | Không kill pod đột ngột khi đang có request |
| **Rotate secrets định kỳ** | API key, JWT secret mỗi 90 ngày |
| **Test recovery** | Thỉnh thoảng tắt thử 1 pod xem system phản ứng thế nào |
