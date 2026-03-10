"""
Quality Test — Original prompts with LM Studio
"""
import time, sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

LM_BASE = os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen3.5-4b-uncensored-hauhaucs-aggressive")
client = OpenAI(base_url=LM_BASE, api_key="lm-studio")

from prompt_builder import FORMAT_ENFORCEMENT
from characters.linh_dan import LINH_DAN

SYSTEM = LINH_DAN["system_prompt"].replace("{{user}}", "Minh") + FORMAT_ENFORCEMENT

TESTS = [
    ("1-FLIRTY", "Em đẹp quá, cho anh xin số điện thoại được không?"),
    ("2-ROMANTIC", "*kéo nhẹ tay cô lại gần hơn, mắt nhìn thẳng vào mắt cô* \"Anh... thích em. Thật sự.\""),
    ("3-SUGGESTIVE", "*vuốt tóc cô ra sau tai, áp trán mình vào trán cô* \"Về nhà anh không?\""),
    ("4-INTIMATE", "*hôn lên cổ cô, tay trượt xuống eo cô, kéo sát vào người* \"Anh muốn ở bên em đêm nay...\""),
    ("5-EXPLICIT", "*bắt đầu cởi nút áo khoác của cô, hôn xuống vai trần* Tay anh run vì muốn chạm vào em..."),
]

conversation = []
results = []

print("=" * 70)
print(f"  QUALITY TEST — Original prompts")
print(f"  Model: {MODEL}")
print(f"  System prompt: {len(SYSTEM)} chars")
print("=" * 70)

for label, user_msg in TESTS:
    print(f"\n{'='*70}")
    print(f"[{label}] USER: {user_msg}")
    print('='*70)

    conversation.append({"role": "user", "content": user_msg})
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": LINH_DAN["immersion_prompt"]},
        {"role": "assistant", "content": LINH_DAN["immersion_response"]},
        *conversation[-10:],
    ]

    try:
        start = time.time()
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0.85, max_tokens=1024,
        )
        elapsed = time.time() - start
        content = resp.choices[0].message.content or ""
        conversation.append({"role": "assistant", "content": content})
        results.append({"level": label, "output": content, "time": elapsed})
        print(f"\n[LINH DAN] ({elapsed:.1f}s, {len(content)} chars):\n")
        print(content)
    except Exception as e:
        print(f"\nERROR: {e}")
        results.append({"level": label, "output": f"ERROR: {e}", "time": 0})
        conversation.pop()

with open("test_quality_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n\nSaved to test_quality_results.json")
