"""
Quick test script — verify LM Studio connection + model quality for DokiChat.
Run: conda activate companion-demo && python test_lmstudio.py
"""
import sys
import time
import httpx

# ── 1. Check LM Studio server is running ──────────────────────
print("=" * 60)
print("🔍 TEST 1: LM Studio Server Connection")
print("=" * 60)

LM_BASE = "http://localhost:1234"

try:
    resp = httpx.get(f"{LM_BASE}/v1/models", timeout=5.0)
    resp.raise_for_status()
    data = resp.json()
    models = data.get("data", [])
    if models:
        print(f"✅ LM Studio server is running!")
        print(f"   Loaded models:")
        for m in models:
            print(f"   - {m['id']}")
        model_id = models[0]["id"]
    else:
        print("⚠️  Server running but no models loaded!")
        print("   → Load a model in LM Studio first.")
        sys.exit(1)
except httpx.ConnectError:
    print("❌ Cannot connect to LM Studio at localhost:1234")
    print("   → Make sure LM Studio is running with server enabled.")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# ── 2. Test OpenAI SDK compatibility ──────────────────────────
print()
print("=" * 60)
print("🔍 TEST 2: OpenAI SDK Compatibility (non-streaming)")
print("=" * 60)

from openai import OpenAI
client = OpenAI(base_url=f"{LM_BASE}/v1", api_key="lm-studio")

try:
    start = time.time()
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Reply in Vietnamese."},
            {"role": "user", "content": "Xin chào! Bạn là ai?"},
        ],
        temperature=0.7,
        max_tokens=200,
    )
    elapsed = time.time() - start
    content = response.choices[0].message.content
    print(f"✅ Non-streaming OK ({elapsed:.2f}s)")
    print(f"   Model: {model_id}")
    print(f"   Response: {content[:200]}")
except Exception as e:
    print(f"❌ Non-streaming failed: {e}")

# ── 3. Test streaming ─────────────────────────────────────────
print()
print("=" * 60)
print("🔍 TEST 3: Streaming")
print("=" * 60)

try:
    start = time.time()
    stream = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Reply in Vietnamese."},
            {"role": "user", "content": "Kể tôi nghe một câu chuyện ngắn 3 dòng."},
        ],
        temperature=0.85,
        max_tokens=300,
        stream=True,
    )
    
    full_text = ""
    chunk_count = 0
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            full_text += delta.content
            chunk_count += 1
    
    elapsed = time.time() - start
    print(f"✅ Streaming OK ({elapsed:.2f}s, {chunk_count} chunks)")
    print(f"   Response: {full_text[:300]}")
except Exception as e:
    print(f"❌ Streaming failed: {e}")

# ── 4. Test Vietnamese roleplay quality ───────────────────────
print()
print("=" * 60)
print("🔍 TEST 4: Vietnamese Roleplay Quality (DokiChat format)")
print("=" * 60)

ROLEPLAY_SYSTEM = """You are Linh Đan, a 24-year-old bartender at a hidden jazz bar.
You speak Vietnamese. You are sarcastic, guarded, with a hidden artistic side.
Use *italics* for actions, "quotes" for dialogue.
Keep response 150-300 words. Mix dialogue (60%) with narration (40%)."""

try:
    start = time.time()
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": ROLEPLAY_SYSTEM},
            {"role": "user", "content": "Xin chào, quán này có gì đặc biệt không?"},
        ],
        temperature=0.85,
        max_tokens=1024,
    )
    elapsed = time.time() - start
    content = response.choices[0].message.content
    
    print(f"✅ Roleplay response ({elapsed:.2f}s)")
    print(f"   Length: {len(content)} chars, ~{len(content.split())} words")
    print("-" * 40)
    print(content)
    print("-" * 40)
    
    # Quick quality checks
    has_italics = "*" in content
    has_quotes = '"' in content or '"' in content or '"' in content
    has_vietnamese = any(c in content for c in "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệ")
    
    print(f"   Has *action* italics: {'✅' if has_italics else '❌'}")
    print(f"   Has \"dialogue\" quotes: {'✅' if has_quotes else '❌'}")
    print(f"   Has Vietnamese diacritics: {'✅' if has_vietnamese else '❌'}")

except Exception as e:
    print(f"❌ Roleplay test failed: {e}")

print()
print("=" * 60)
print("✨ All tests complete!")
print(f"   Model: {model_id}")
print(f"   Update .env LM_STUDIO_MODEL={model_id} if needed.")
print("=" * 60)
