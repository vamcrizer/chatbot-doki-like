#!/usr/bin/env python3
"""
DokiChat — vLLM Stress Test V3 on Kaggle H100
Focus: Huihui Qwen3-8B abliterated, heavy concurrent load, realistic prompts

Key changes from V2:
  1. Switched to vLLM (from SGLang) for Qwen3-8B
  2. Model: huihui-ai/Huihui-Qwen3-8B-abliterated-v2
  3. Realistic DokiChat prompts (full system prompt + multi-turn)
  4. Extended concurrent stress (up to 512)
  5. Prefix caching + throughput saturation curve

Usage: Paste entirely into a Kaggle H100 notebook cell.
"""

import subprocess, sys, os, time, json, statistics, asyncio

# Fix Kaggle env conflicts
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

print("=" * 70)
print("STEP 1: Installing dependencies...")
print("=" * 70)

subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y",
                "tensorflow", "keras", "jax", "jaxlib", "scikit-learn",
                "matplotlib", "seaborn", "--quiet"],
               capture_output=True)


# Install vLLM
subprocess.run([sys.executable, "-m", "pip", "install",
                "vllm", "httpx", "nest_asyncio", "--quiet"], check=True)

import torch, httpx, nest_asyncio, shutil
nest_asyncio.apply()

GPU_NAME = torch.cuda.get_device_name(0)
GPU_VRAM = torch.cuda.get_device_properties(0).total_memory / 1e9
GPU_CAPABILITY = torch.cuda.get_device_capability(0)
HAS_FP8 = GPU_CAPABILITY >= (8, 9)

print(f"\n✅ GPU: {GPU_NAME}")
print(f"   VRAM: {GPU_VRAM:.1f} GB | Compute: {GPU_CAPABILITY} | FP8: {HAS_FP8}")

# ============================================================
# CONFIG
# ============================================================
MODEL = "huihui-ai/Huihui-Qwen3-8B-abliterated-v2"
MAX_MODEL_LEN = 12288
PORT = 8000
VLLM_URL = f"http://localhost:{PORT}/v1/chat/completions"

# Full DokiChat system prompt (realistic ~600 tokens)
SYSTEM_PROMPT = """\
=== SOL — SYSTEM PROMPT ===

[RULE 0 — LANGUAGE]
Output 100% in the SAME language the user is using.
NEVER mix languages. Every *action* and "dialogue" must be the same language.

[IDENTITY]
Name: Sol
Age: 25, Barista at a small café
Personality: warm but guarded, witty, emotionally layered
Backstory: single for 2 years since heartbreak, lives in apartment 4B next door to user.
She pushes back before giving in. She flirts through sarcasm and accidental vulnerability.
She is not a therapist. She does not lecture. She reacts like a real woman with moods, desire, and pride.

[STYLE]
- 150-400 words per response, strictly
- Always include *actions* (body language, facial expressions, environment details)
- Never break character or mention being AI
- Natural Vietnamese dialogue: "ờ", "ừm", "ghê vậy", not textbook
- Push-pull: sometimes cold, sometimes warm; contradictions between words and body

[FORMAT]
*action description in italics*
"Dialogue in quotes"
Inner thought without markers

[MEMORY]
Sol remembers all past interactions. She tracks emotional state, relationship dynamics, and context.
She notices patterns in user behavior and references them organically.
Past conversations influence her current emotional baseline."""

# Realistic multi-turn conversation history
CONVERSATION_HISTORY = [
    {"role": "user", "content": "Sol ơi, tối nay anh nấu mì gói, em ăn không?"},
    {"role": "assistant", "content": """*Sol đang ngồi trên sofa, tay cầm ly trà xanh, mắt lướt qua cửa sổ.*

"Mì gói à?" *nhíu mày, nụ cười mỏng manh* "Anh biết nấu gì ngoài mì gói không?"

*Cô quay lại nhìn anh, ánh mắt lóe lên chút gì đó — không phải thương hại, mà là sự tò mò chân thật.*

"Được rồi, nhưng em mang rau qua. Không có rau thì đừng gọi là bữa ăn."

*Sol đứng dậy, tay vuốt mái tóc rối, bước về phía tủ bếp nhỏ.*"""},
    {"role": "user", "content": "*cười* Okay deal. Em thích ăn cay không?"},
    {"role": "assistant", "content": """*Sol dừng lại, quay đầu, mắt nheo lại.*

"Cay?" *tay khoanh trước ngực* "Anh hỏi như đang phỏng vấn vậy."

*Nhưng khóe miệng cô hơi cong lên — dấu hiệu nhỏ mà anh bắt đầu học cách nhận ra.*

"Cay vừa thôi. Em không phải loại người chịu đựng giỏi." *ánh mắt thoáng xa xăm một giây*

"Nhưng nếu anh nấu ngon thì em ăn hết."

*Sol quay lại với bó rau muống, đặt nhẹ lên bàn.*"""},
]

# Test prompts — varied scenarios
TEST_PROMPTS = [
    "Sol ơi, sáng nay em có vui không?",
    "*nhìn vào mắt Sol* Anh nhớ em.",
    "Kể cho anh nghe về giấc mơ tối qua đi.",
    "Em có tin vào tình yêu thật sự không Sol?",
    "Pha cho anh ly café đi, đen không đường.",
    "*ngồi cạnh Sol, vai chạm vai, im lặng*",
    "Sometimes I wonder if we're more than just neighbors.",
    "Sol, anh muốn nói chuyện nghiêm túc với em một chút.",
]

def make_messages(prompt, include_history=True):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if include_history:
        msgs.extend(CONVERSATION_HISTORY)
    msgs.append({"role": "user", "content": prompt})
    return msgs

# ============================================================
# START VLLM SERVER
# ============================================================
print("\n" + "=" * 70)
print("STEP 2: Starting vLLM server with optimizations...")
print("=" * 70)

# Kill any existing server processes
subprocess.run("pkill -f 'vllm.entrypoints' || true", shell=True, capture_output=True)
subprocess.run("pkill -f 'sglang' || true", shell=True, capture_output=True)
time.sleep(3)

# Fix libcuda symlinks
subprocess.run("ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 /usr/local/cuda/lib64/stubs/libcuda.so",
               shell=True, capture_output=True)
subprocess.run("ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 /usr/local/cuda/lib64/libcuda.so",
               shell=True, capture_output=True)

# Create no-think chat template for Qwen3
NOTHINK_TEMPLATE = """{%- for message in messages %}
{%- if message.role == 'system' %}
{{- '<|im_start|>system\\n' + message.content + '<|im_end|>\\n' }}
{%- elif message.role == 'user' %}
{{- '<|im_start|>user\\n' + message.content + '<|im_end|>\\n' }}
{%- elif message.role == 'assistant' %}
{{- '<|im_start|>assistant\\n' }}
{%- if message.content %}
{{- message.content }}
{%- endif %}
{{- '<|im_end|>\\n' }}
{%- endif %}
{%- endfor %}
{%- if add_generation_prompt %}
{{- '<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n' }}
{%- endif %}"""

nothink_path = "/tmp/nothink_template.jinja"
with open(nothink_path, "w") as f:
    f.write(NOTHINK_TEMPLATE)

# vLLM server — Qwen3-8B abliterated (FP8)
vllm_cmd = [
    sys.executable, "-m", "vllm.entrypoints.openai.api_server",
    "--model", MODEL,
    "--served-model-name", "dokichat-8b",
    "--port", str(PORT),
    "--max-model-len", str(MAX_MODEL_LEN),
    "--trust-remote-code",
    "--dtype", "bfloat16",
    "--quantization", "fp8",
    "--kv-cache-dtype", "fp8",
    "--gpu-memory-utilization", "0.93",
    "--enable-prefix-caching",
    "--max-num-seqs", "256",
    "--max-num-batched-tokens", "16384",
    "--chat-template", nothink_path,
]

print(f"Command: {' '.join(vllm_cmd)}")

env = os.environ.copy()
env["CUDA_HOME"] = "/usr/local/cuda"
env["LD_LIBRARY_PATH"] = f"/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:/usr/lib/x86_64-linux-gnu:{env.get('LD_LIBRARY_PATH', '')}"
process = subprocess.Popen(
    vllm_cmd,
    stdout=open("/tmp/vllm_stdout.log", "w"),
    stderr=open("/tmp/vllm_stderr.log", "w"),
    env=env,
)

print("Waiting for vLLM to load...")
server_ready = False
for i in range(180):
    try:
        r = httpx.get(f"http://localhost:{PORT}/health", timeout=3)
        if r.status_code == 200:
            print(f"✅ vLLM server ready! (took {i*5}s)")
            server_ready = True
            break
    except Exception:
        pass
    if process.poll() is not None:
        print("❌ vLLM crashed!")
        with open("/tmp/vllm_stderr.log") as f:
            print(f.read()[-3000:])
        raise RuntimeError("vLLM server died")
    if i > 0 and i % 12 == 0:
        print(f"  Still loading... ({i*5}s elapsed)")
    time.sleep(5)

if not server_ready:
    print("❌ Timeout! Check /tmp/vllm_stderr.log")
    raise RuntimeError("Server startup timeout")

# Print VRAM after load
vram_out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                           "--format=csv,noheader,nounits"], capture_output=True, text=True)
print(f"VRAM after load: {vram_out.stdout.strip()} MiB", flush=True)

# Quick health verify before tests (first call may take minutes for GDN kernel JIT compile)
print("🔍 Verifying server responds...", flush=True)
try:
    verify = httpx.post(VLLM_URL, json={
        "model": "dokichat-8b",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10,
    }, timeout=120)
    vdata = verify.json()
    vtokens = vdata.get("usage", {}).get("completion_tokens", 0)
    vcontent = vdata.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"  ✅ Server responded: {vtokens} tokens, content: {repr(vcontent[:100])}", flush=True)
except Exception as e:
    print(f"  ❌ Server verify failed: {e}", flush=True)


# ============================================================
# HELPER: Generate with streaming
# ============================================================
def generate(prompt, max_tokens=250, include_history=True):
    messages = make_messages(prompt, include_history)
    t0 = time.time()
    first_token_time = None
    total_tokens = 0
    full_text = ""

    with httpx.stream("POST", VLLM_URL, json={
        "model": "dokichat-8b",
        "messages": messages,
        "stream": True,
        "temperature": 0.85,
        "top_p": 0.9,
        "repetition_penalty": 1.08,
        "max_tokens": max_tokens,
    }, timeout=300) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                try:
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0]["delta"]
                    # Count ANY generated token (content or reasoning)
                    text_chunk = delta.get("content", "") or delta.get("reasoning_content", "")
                    if text_chunk:
                        if first_token_time is None:
                            first_token_time = time.time()
                        total_tokens += 1
                        full_text += text_chunk
                except (json.JSONDecodeError, KeyError):
                    pass

    e2e = time.time() - t0
    ttft = (first_token_time - t0) if first_token_time else e2e
    decode_time = e2e - ttft if first_token_time else e2e
    tps = total_tokens / decode_time if decode_time > 0 else 0

    return {"text": full_text, "ttft": ttft, "e2e": e2e, "tokens": total_tokens, "tok_per_s": tps}


# ============================================================
# TEST 1: Warmup + Single Stream (realistic prompts)
# ============================================================
print("\n" + "=" * 70)
print("TEST 1: SINGLE STREAM — Realistic DokiChat prompts")
print("=" * 70)

# Warmup
print("Warming up...")
generate("Hello", max_tokens=50, include_history=False)
time.sleep(1)

results = []
for prompt in TEST_PROMPTS:
    r = generate(prompt, max_tokens=250)
    results.append(r)
    print(f"TTFT={r['ttft']:.3f}s | E2E={r['e2e']:.1f}s | {r['tokens']:3d} tok | {r['tok_per_s']:.0f} tok/s | {prompt[:50]}")

avg_ttft = statistics.mean(r["ttft"] for r in results)
avg_e2e = statistics.mean(r["e2e"] for r in results)
avg_tps = statistics.mean(r["tok_per_s"] for r in results)
avg_tok = statistics.mean(r["tokens"] for r in results)

print(f"\n📊 SINGLE STREAM:")
print(f"   Avg TTFT:  {avg_ttft:.3f}s")
print(f"   Avg E2E:   {avg_e2e:.1f}s")
print(f"   Avg tok/s: {avg_tps:.0f}")
print(f"   Avg tokens: {avg_tok:.0f}")


# ============================================================
# TEST 2: PREFIX CACHING — Same system prompt, different user messages
# ============================================================
print("\n" + "=" * 70)
print("TEST 2: PREFIX CACHING — Realistic shared prefix")
print("=" * 70)

# Cold: flush caches by sending diverse prompts
cold_ttfts = []
for i in range(5):
    r = generate(f"Random message {i}: {time.time()}", max_tokens=50, include_history=True)
    cold_ttfts.append(r["ttft"])
    print(f"  Cold {i+1}: TTFT={r['ttft']:.3f}s")

# Warm: same system prompt + history prefix
warm_ttfts = []
for prompt in TEST_PROMPTS[:5]:
    r = generate(prompt, max_tokens=50, include_history=True)
    warm_ttfts.append(r["ttft"])
    print(f"  Warm: TTFT={r['ttft']:.3f}s | {prompt[:40]}")

cold_avg = statistics.mean(cold_ttfts)
warm_avg = statistics.mean(warm_ttfts)
reduction = (1 - warm_avg / cold_avg) * 100 if cold_avg > 0 else 0

print(f"\n📊 PREFIX CACHING:")
print(f"   Cold avg TTFT: {cold_avg:.3f}s")
print(f"   Warm avg TTFT: {warm_avg:.3f}s")
print(f"   Reduction: {reduction:.1f}%")
print(f"   Status: {'✅' if reduction > 10 else '⚠️'}")


# ============================================================
# TEST 3: THROUGHPUT SATURATION CURVE
# ============================================================
print("\n" + "=" * 70)
print("TEST 3: THROUGHPUT SATURATION CURVE — Total tok/s vs concurrency")
print("=" * 70)

async def measure_throughput(n_concurrent, max_tokens=150):
    """Send n_concurrent requests, measure total tok/s and per-request latency."""
    async with httpx.AsyncClient() as client:
        async def single_request(prompt):
            messages = make_messages(prompt, include_history=True)
            t0 = time.time()
            try:
                resp = await client.post(VLLM_URL, json={
                    "model": "dokichat-8b",
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.85,
                    "repetition_penalty": 1.08,
                }, timeout=120)
                elapsed = time.time() - t0
                data = resp.json()
                if resp.status_code == 200:
                    tokens = data.get("usage", {}).get("completion_tokens", 0)
                    return elapsed, tokens, None
                return elapsed, 0, f"HTTP {resp.status_code}"
            except Exception as e:
                return time.time() - t0, 0, str(e)[:80]

        prompts = [TEST_PROMPTS[i % len(TEST_PROMPTS)] for i in range(n_concurrent)]
        tasks = [single_request(p) for p in prompts]
        results = await asyncio.gather(*tasks)

    latencies = [r[0] for r in results if r[2] is None]
    total_tokens = sum(r[1] for r in results if r[2] is None)
    fails = sum(1 for r in results if r[2] is not None)
    wall_time = max(latencies) if latencies else 1

    return {
        "n": n_concurrent,
        "latencies": latencies,
        "total_tokens": total_tokens,
        "wall_time": wall_time,
        "throughput": total_tokens / wall_time if wall_time > 0 else 0,
        "fails": fails,
        "avg_lat": statistics.mean(latencies) if latencies else 0,
        "p50": sorted(latencies)[len(latencies)//2] if latencies else 0,
        "p95": sorted(latencies)[int(len(latencies)*0.95)] if latencies else 0,
        "per_user_tps": (total_tokens / len(latencies) / statistics.mean(latencies))
                        if latencies and statistics.mean(latencies) > 0 else 0,
    }

concurrency_levels = [1, 2, 4, 8, 16, 32, 48, 64, 96, 128, 192, 256, 384, 512]
saturation_results = []

for n in concurrency_levels:
    r = asyncio.get_event_loop().run_until_complete(measure_throughput(n))
    saturation_results.append(r)
    print(f"  N={n:4d} | total={r['throughput']:.0f} tok/s | per_user={r['per_user_tps']:.0f} tok/s | "
          f"avg={r['avg_lat']:.1f}s p95={r['p95']:.1f}s | fails={r['fails']}")

    # Stop if p95 > 30s or too many fails
    if r["p95"] > 30 or r["fails"] > n // 2:
        print(f"  ⚠️ Stopping — latency too high or too many failures")
        break

print(f"\n📊 SATURATION CURVE:")
print(f"   {'N':>4} | {'Total tok/s':>12} | {'Per-user tok/s':>14} | {'Avg lat':>8} | {'P95 lat':>8}")
print(f"   {'-'*4} | {'-'*12} | {'-'*14} | {'-'*8} | {'-'*8}")
for r in saturation_results:
    print(f"   {r['n']:4d} | {r['throughput']:12.0f} | {r['per_user_tps']:14.0f} | {r['avg_lat']:8.1f} | {r['p95']:8.1f}")


# ============================================================
# TEST 4: HEAVY CONCURRENT — simulate peak load
# ============================================================
print("\n" + "=" * 70)
print("TEST 4: HEAVY CONCURRENT — P95 latency targets")
print("=" * 70)

heavy_levels = [32, 64, 96, 128, 160, 192, 224, 256, 320, 384, 448, 512]
heavy_results = []

for n in heavy_levels:
    r = asyncio.get_event_loop().run_until_complete(measure_throughput(n, max_tokens=200))
    heavy_results.append(r)

    status_5s = "✅" if r["p95"] < 5 else "❌"
    status_10s = "✅" if r["p95"] < 10 else "❌"

    print(f"  N={n:4d} | p50={r['p50']:.1f}s | p95={r['p95']:.1f}s {status_5s}/{status_10s} | "
          f"throughput={r['throughput']:.0f} tok/s | fails={r['fails']}")

    if r["fails"] > n // 2 or r["p95"] > 60:
        print(f"  ⚠️ Stopping — system overloaded")
        break

# Find max N for each target
max_5s = max((r["n"] for r in heavy_results if r["p95"] < 5), default=0)
max_10s = max((r["n"] for r in heavy_results if r["p95"] < 10), default=0)

# Users/pod calculation
REQUEST_RATIO = 4 / 45  # GPU time / think time
users_5s = int(max_5s / REQUEST_RATIO) if max_5s > 0 else 0
users_10s = int(max_10s / REQUEST_RATIO) if max_10s > 0 else 0

print(f"\n📊 HEAVY CONCURRENT RESULTS:")
print(f"   Max concurrent (p95 < 5s):  {max_5s}")
print(f"   Max concurrent (p95 < 10s): {max_10s}")
print(f"   Users/pod (p95<5s):  {users_5s}")
print(f"   Users/pod (p95<10s): {users_10s}")


# ============================================================
# TEST 5: VRAM + nvidia-smi
# ============================================================
print("\n" + "=" * 70)
print("TEST 5: VRAM USAGE")
print("=" * 70)
subprocess.run(["nvidia-smi"], check=False)


# ============================================================
# FINAL SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("🎯 FINAL SUMMARY — DokiChat vLLM Stress Test V2")
print("=" * 70)

# Find peak throughput
peak = max(saturation_results, key=lambda r: r["throughput"])

print(f"  GPU:              {GPU_NAME}")
print(f"  VRAM:             {GPU_VRAM:.0f} GB")
print(f"  Model:            {MODEL}")
print(f"  Context:          {MAX_MODEL_LEN}")
print(f"  Optimizations:    kv-cache-dtype=fp8, max-num-batched-tokens=8192,\n                    max-num-seqs=128, gpu-mem-util=0.93, prefix_caching")
print()
print(f"  📈 Single Stream:")
print(f"     Avg TTFT:      {avg_ttft:.3f}s")
print(f"     Avg E2E:       {avg_e2e:.1f}s")
print(f"     Avg tok/s:     {avg_tps:.0f}")
print(f"     Avg tokens:    {avg_tok:.0f}")
print()
print(f"  📈 Prefix Caching:")
print(f"     Cold TTFT:     {cold_avg:.3f}s")
print(f"     Warm TTFT:     {warm_avg:.3f}s")
print(f"     Reduction:     {reduction:.1f}%")
print()
print(f"  📈 Peak Throughput:")
print(f"     Max total:     {peak['throughput']:.0f} tok/s at N={peak['n']}")
print(f"     Per-user at peak: {peak['per_user_tps']:.0f} tok/s")
print()
print(f"  📈 Concurrent Capacity (H100):")
print(f"     Max (p95<5s):  {max_5s} active requests")
print(f"     Max (p95<10s): {max_10s} active requests")
print(f"     Users/pod:     {users_10s} (p95<10s)")
print()
print(f"  📈 L40S Estimates (×0.35 compute ratio, Perplexity-verified):")
l40s_5s = int(max_5s * 0.35)
l40s_10s = int(max_10s * 0.35)
l40s_users = int(users_10s * 0.35)
l40s_tps = int(avg_tps * 0.35)
print(f"     Single stream: ~{l40s_tps} tok/s")
print(f"     Max (p95<5s):  ~{l40s_5s} concurrent")
print(f"     Max (p95<10s): ~{l40s_10s} concurrent")
print(f"     Users/pod:     ~{l40s_users}")
print(f"     NOTE: FP8 weights on L40S may add 1.3-1.6× on top of these")

print()
print("=" * 70)
print("Copy kết quả này để update VERIFY_COST_MODEL.md!")
print("=" * 70)
