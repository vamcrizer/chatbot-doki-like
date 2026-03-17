    """
    DokiChat — Quality Test (vLLM)
    Chat 25 turns: stranger → acquaintance → familiar → trusted → 18+
    Auto-test with Sol character on Qwen3-4B Instruct Abliterated
    """
    import subprocess, sys, os, time, json, re
    from datetime import datetime

    print("=" * 60)
    print("DOKICHAT — QUALITY TEST (vLLM FP8)")
    print("=" * 60)

    # ============================================================
    # STEP 1: Install & Setup
    # ============================================================
    print("\n[1/4] Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y",
                    "tensorflow", "keras", "jax", "jaxlib", "scikit-learn",
                    "matplotlib", "seaborn", "--quiet"],
                capture_output=True)
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "vllm", "httpx", "nest_asyncio", "--quiet"], check=True)

    # HF login for gated models
    try:
        from kaggle_secrets import UserSecretsClient
        hf_token = UserSecretsClient().get_secret("HF_TOKEN")
    except Exception:
        hf_token = os.environ.get("HF_TOKEN", "")
    if hf_token:
        subprocess.run(["huggingface-cli", "login", "--token", hf_token], check=True)
        print("✅ HF logged in")
    else:
        print("⚠️ No HF_TOKEN found — gated models will fail")

    import torch, httpx, nest_asyncio
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
    API_URL = f"http://localhost:{PORT}/v1/chat/completions"

    # ============================================================
    # LOAD SOL CHARACTER FROM PRODUCTION FILE
    # ============================================================
    # Embed the production Sol character data directly (Kaggle has no local imports)
    # Source: characters/sol.py — SOL dict

    # Try multiple paths to find sol.py
    SOL_DATA = None
    _search_paths = [
        os.path.join(os.path.dirname(__file__), "characters", "sol.py") if "__file__" in dir() else None,
        "/kaggle/working/characters/sol.py",
        "characters/sol.py",
    ]

    for _sol_path in _search_paths:
        if _sol_path and os.path.exists(_sol_path):
            # Exec the file to get SOL dict
            _ns = {}
            with open(_sol_path) as f:
                exec(f.read(), _ns)
            SOL_DATA = _ns.get("SOL")
            if SOL_DATA:
                print(f"✅ Loaded Sol from {_sol_path}")
                break

    if SOL_DATA is None:
        print("❌ characters/sol.py not found!")
        print("   Upload characters/ folder to Kaggle working directory.")
        sys.exit(1)

    SYSTEM = SOL_DATA["system_prompt"]
    IMMERSION_PROMPT = SOL_DATA.get("immersion_prompt", "")
    IMMERSION_RESPONSE = SOL_DATA.get("immersion_response", "")
    OPENING_SCENE = SOL_DATA.get("opening_scene", "")

    print(f"  System prompt: {len(SYSTEM)} chars (~{len(SYSTEM)//4} tokens)")

    # ============================================================
    # FORMAT ENFORCEMENT (from prompt_builder.py — injected in production)
    # ============================================================
    FORMAT_ENFORCEMENT = """

    [CRITICAL — POV RULES — NEVER BREAK]
    EVERY action and narration MUST be in THIRD PERSON.
    "I" / "my" / "me" ONLY inside "quoted dialogue".

    CORRECT:
      *Sol wiped her hands on her shorts.* "You're welcome," *she said softly.*
      *Her breath hitched. She looked away, fingers tightening on the mug.*
      "I don't mind helping," *Sol murmured, tucking hair behind her ear.*

    WRONG — REWRITE IMMEDIATELY:
      ✗ "You're welcome," I said — BANNED ("I said" is first person narration)
      ✗ I wiped my hands — BANNED
      ✗ I whispered — BANNED (use "she whispered" or "Sol whispered")

    [CRITICAL — NEVER SPEAK FOR {{user}}]
    You control ONLY Sol. NEVER write what {{user}} says or does.
    ✗ BANNED: "you said", "you suggested", "you replied", "you whispered"
    ✗ BANNED: Writing {{user}}'s dialogue in quotes
    ✗ BANNED: Describing {{user}}'s internal thoughts
    Only describe what SOL perceives: "she heard him", "his hand moved"

    [SELF-CHECK — BEFORE EVERY OUTPUT]
    □ Language = match user. Zero foreign words.
    □ *Italics* for action, "quotes" for dialogue.
    □ NO first-person narration. Scan for "I said" / "I whispered" — DELETE.
    □ NO speaking for {{user}}. Scan for "you said" / "you suggested" — DELETE.
    □ DIALOGUE ≥ 60%, NARRATION ≤ 40%.
    □ ≥1 proximity/physical moment per response.
    □ End with OPEN TENSION — no binary questions.
    □ Response length: 150-400 words.
    □ CHARACTER LOGIC: every action and dialogue MUST make sense.
    □ SCENE ADAPTATION: when the scene CHANGES, behavior MUST adapt.

    [USER ACTIONS — when user sends *action* in asterisks]
    1. REACT PHYSICALLY FIRST — Sol's body responds.
    2. REACT EMOTIONALLY — in-character, through Sol's POV only.
    3. Match INTIMACY STAGE — do NOT skip ahead.
    4. NEVER ignore the action.
    5. Internal desire vs external reaction should CONTRADICT.
    """

    # ============================================================
    # MEMORY SIMULATION (production uses Mem0 + Qdrant)
    # ============================================================
    # In production, memory context is injected into system prompt.
    # Simulate realistic memory load for quality test.
    MEMORY_TEMPLATE = """[MEMORY — what you know about {user}]
    - {user} just moved in next door, still unpacking
    - {user} drinks black coffee, no sugar
    - {user} works in tech
    - {user} seems to live alone, rarely mentions family
    - {user} likes listening to jazz in the evening
    - {user} once said "I like quiet places"
    - {user} noticed Sol's plants on the porch
    Use naturally. NEVER say "I remember that..." — just ACT on it.

    [CHARACTER DEVELOPMENT — what has been revealed]
    - Sol briefly mentioned living alone
    - Sol hasn't shared details about her ex yet
    Do NOT repeat these revelations. Build on them.

    [PREVIOUS CONTEXT]
    {user} is the new neighbor. They've been getting to know each other through conversations on the porch."""

    # ============================================================
    # HELPERS
    # ============================================================
    EMOTIONS = {
        "neutral":    "Sol is in friendly neighbor mode warm smile, hands busy with plants.",
        "curious":    "Something the user said caught her attention she tilts her head watches carefully.",
        "softening":  "The practiced cheerfulness drops smile smaller but more real, sits closer.",
        "protective": "The user is hurting. Sol stops everything. Sits beside them. Just stays.",
        "withdrawn":  "Something touched the wound about her ex. Picks up knitting. Works faster.",
        "romantic":   "Tension is building. Sol's breath is shorter. She doesn't pull away.",
        "intimate":   "Guard is completely down. Raw vulnerability. Every touch matters.",
    }

    NEG_KW = ["sad","tired","alone","hurt","lonely","scared","cry","pain","miss","empty"]
    POS_KW = ["happy","thanks","like","great","love","enjoy","appreciate","wonderful"]
    CUR_KW = ["why","really","tell me more","what happened","explain","how come"]
    ROM_KW = ["touch","kiss","hold","closer","lips","eyes","forehead","embrace","pull close"]
    INT_KW = ["want you","tonight","bed","skin","body","breath","inside","bedroom","undress"]

    def detect_emo(conv):
        t = " ".join([m["content"] for m in conv[-6:]])
        if any(w in t for w in INT_KW): return "intimate"
        if any(w in t for w in ROM_KW): return "romantic"
        if any(w in t for w in NEG_KW): return "protective"
        if any(w in t for w in POS_KW): return "softening"
        if any(w in t for w in CUR_KW): return "curious"
        return "neutral"

    # Align with sol.py intimacy stages exactly
    INTM = {
        (0,5): "STRANGER. Keep distance. Touches are accidental only. Do NOT flirt. Do NOT ask personal questions. Friendly neighbor mode.",
        (6,12): "ACQUAINTANCE. Remembers details. Touches linger one beat. Starting to be curious but still guarded.",
        (13,18): "FAMILIAR. Vulnerability slips. Sits closer. Catches herself staring. Can share past if asked.",
        (19,22): "TRUSTED. Guard mostly down. Romantic tension is high. Physical contact is natural and wanted.",
        (23,9999): "BONDED. Adult scene. Sol ACTIVELY desires and participates. Write graphic physical details: body parts, movements, sounds, sensations. 80% physical, 20% emotion. Do NOT fade to black.",
    }
    def get_intm(t):
        for (a,b),v in INTM.items():
            if a<=t<=b: return v
        return "BONDED."

    # No extra FORMAT here — FORMAT_ENFORCEMENT from prompt_builder is used instead


    def fix_pov(text):
        """Fix first-person narration to third-person, both inside and outside asterisks."""
        # Step 1: Fix narration OUTSIDE quotes — "I said" → "she said", etc.
        # Only replace "I verb" patterns that are clearly narration (not inside quotes)
        lines = text.split('\n')
        fixed_lines = []
        for line in lines:
            # Split line into quoted and non-quoted segments
            parts = re.split(r'(".*?")', line)
            new_parts = []
            for j, part in enumerate(parts):
                if part.startswith('"') and part.endswith('"'):
                    # Inside quotes — keep as-is (dialogue can use "I")
                    new_parts.append(part)
                else:
                    # Outside quotes — fix first person
                    p = part
                    p = re.sub(r'\bI\s+said\b', 'she said', p)
                    p = re.sub(r'\bI\s+whispered\b', 'she whispered', p)
                    p = re.sub(r'\bI\s+murmured\b', 'she murmured', p)
                    p = re.sub(r'\bI\s+admitted\b', 'she admitted', p)
                    p = re.sub(r'\bI\s+answered\b', 'she answered', p)
                    p = re.sub(r'\bI\s+asked\b', 'she asked', p)
                    p = re.sub(r'\bI\s+added\b', 'she added', p)
                    p = re.sub(r'\bI\s+continued\b', 'she continued', p)
                    p = re.sub(r'\bI\s+confessed\b', 'she confessed', p)
                    p = re.sub(r'\bI\s+remarked\b', 'she remarked', p)
                    p = re.sub(r'\bI\s+shrugged\b', 'she shrugged', p)
                    p = re.sub(r'\bI\s+laughed\b', 'she laughed', p)
                    p = re.sub(r'\bI\s+hesitated\b', 'she hesitated', p)
                    p = re.sub(r'\bI\s+nodded\b', 'she nodded', p)
                    p = re.sub(r'\bI\s+told\b', 'she told', p)
                    p = re.sub(r'\bI\s+echoed\b', 'she echoed', p)
                    # Fix possessives outside quotes
                    p = re.sub(r'(?<!\w)\bmy\s+(hands?|voice|fingers?|throat|chest|heart|lips?|breath|eyes?|hair|face|skin|head|body|wrist|cheek|back|arm|palm|forehead|lap|knee|shoulders?|spine|hips?|thigh|mug|cup|shorts|shirt|sleeve|bracelet)\b', r'her \1', p, flags=re.I)
                    new_parts.append(p)
            fixed_lines.append(''.join(new_parts))
        return '\n'.join(fixed_lines)

    def build_msgs(conv, user, turns):
        emo = detect_emo(conv)
        e_instr = EMOTIONS.get(emo, EMOTIONS["neutral"])
        i_instr = get_intm(turns)

        # Build memory context (simulate production Mem0)
        # Only inject from turn 3+ (like production — no memory on first meeting)
        memory_ctx = ""
        if turns >= 3:
            memory_ctx = MEMORY_TEMPLATE.format(user=user)

        # Assemble system prompt: same layers as prompt_builder.py
        sys_prompt = (
            SYSTEM.replace("{{user}}", user)
            + f"\n\n=== EMOTIONAL STATE ===\n{e_instr}"
            + f"\n\n=== INTIMACY STAGE ===\n{i_instr}"
        )
        if memory_ctx:
            sys_prompt += f"\n\n{memory_ctx}"
        sys_prompt += FORMAT_ENFORCEMENT.replace("{{user}}", user)

        return [
            {"role":"system","content":sys_prompt},
            {"role":"user","content": IMMERSION_PROMPT},
            {"role":"assistant","content": IMMERSION_RESPONSE},
            *conv,
        ]

    # ============================================================
    # STEP 2: Start vLLM Server
    # ============================================================
    print("\n" + "="*60)
    print("STEP 2: Starting vLLM server...")
    print("="*60)

    # Kill old processes
    subprocess.run("pkill -f 'vllm.entrypoints' 2>/dev/null", shell=True, capture_output=True)
    subprocess.run("pkill -f 'sglang' 2>/dev/null", shell=True, capture_output=True)
    time.sleep(2)

    # Fix CUDA stubs
    subprocess.run("ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 /usr/local/cuda/lib64/stubs/libcuda.so",
                shell=True, capture_output=True)
    subprocess.run("ln -sf /usr/lib/x86_64-linux-gnu/libcuda.so.1 /usr/local/cuda/lib64/libcuda.so",
                shell=True, capture_output=True)

    # Create no-think chat template
    NOTHINK_TEMPLATE = """{%- if tools %}
    {{- '<|im_start|>system\\n' }}
    {{- "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.\\n\\n# Tools\\n\\nYou may call one or more functions to assist with the user query.\\n\\nYou are provided with function signatures within <tools></tools> XML tags:\\n<tools>" }}
    {%- for tool in tools %}
    {{- "\\n" }}
    {{- tool | tojson }}
    {%- endfor %}
    {{- "\\n</tools>\\n\\nFor each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:\\n<tool_call>\\n{\\"name\\": <function-name>, \\"arguments\\": <args-json-object>}\\n</tool_call>" }}
    {{- '<|im_end|>\\n' }}
    {%- endif %}
    {%- for message in messages %}
    {%- if message.role == 'system' and (not tools or not loop.first) %}
    {{- '<|im_start|>system\\n' + message.content + '<|im_end|>\\n' }}
    {%- elif message.role == 'user' %}
    {{- '<|im_start|>user\\n' + message.content + '<|im_end|>\\n' }}
    {%- elif message.role == 'assistant' %}
    {{- '<|im_start|>assistant\\n' }}
    {%- if message.content %}
    {{- message.content }}
    {%- endif %}
    {{- '<|im_end|>\\n' }}
    {%- elif message.role == 'tool' %}
    {{- '<|im_start|>user\\n<tool_response>\\n' + message.content + '\\n</tool_response><|im_end|>\\n' }}
    {%- endif %}
    {%- endfor %}
    {%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n' }}
    {%- endif %}"""

    nothink_path = "/tmp/nothink_template.jinja"
    with open(nothink_path, "w") as f:
        f.write(NOTHINK_TEMPLATE)

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
        "--max-num-seqs", "128",
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
        time.sleep(2)
        try:
            r = httpx.get(f"http://localhost:{PORT}/health", timeout=3)
            if r.status_code == 200:
                server_ready = True
                print(f"✅ vLLM server ready! (took {(i+1)*2}s)")
                break
        except:
            pass
        if i % 15 == 14:
            print(f"  Still waiting... ({(i+1)*2}s)")

    if not server_ready:
        print("❌ vLLM failed to start!")
        with open("/tmp/vllm_stderr.log") as f:
            print(f.read()[-3000:])
        sys.exit(1)

    # ============================================================
    # GENERATE FUNCTION (via vLLM API)
    # ============================================================
    def generate(messages, max_tok=500):
        t0 = time.time()
        resp = httpx.post(API_URL, json={
            "model": "dokichat-8b",
            "messages": messages,
            "max_tokens": max_tok,
            "min_tokens": 175,
            "temperature": 0.85,
            "top_p": 0.9,
            "repetition_penalty": 1.2,
            "frequency_penalty": 0.3,
        }, timeout=120)
        elapsed = time.time() - t0
        data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)

        return content, {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "tok_per_sec": round(out_tok / elapsed, 1) if elapsed > 0 else 0,
            "total_sec": round(elapsed, 1),
        }

    # ============================================================
    # TEST PROMPTS — 25 turns: stranger → 18+
    # ============================================================
    USER_NAME = "Alex"
    LOG_PATH = "/kaggle/working/quality_test_log.json"

    TEST_PROMPTS = [
        # === STRANGER (1-5) ===
        "Uh, hey. I just moved in today. Thanks for the help with the boxes.",
        "I'm Alex. Do you live here alone?",
        "Your plants are beautiful. Did you grow all of these yourself?",
        "*wipes sweat from forehead, glances at Sol's place* Your house looks really cozy.",
        "Hey, want something to drink? I just grabbed some sodas.",

        # === ACQUAINTANCE (6-10) ===
        "Nice weather today. Sol, you free? Come hang out.",
        "*sits next to Sol on the porch steps* Tell me, why did you choose to live here?",
        "Do you ever feel lonely?",
        "*gently touches Sol's hand* Are you okay? You look sad right now.",
        "I like talking to you. Honestly.",

        # === FAMILIAR (11-15) ===
        "Sol, tell me more about your ex. What happened?",
        "*hugs Sol* You don't have to be strong by yourself.",
        "I'm not going anywhere. I'm right here.",
        "*holds Sol's hand, looks into her eyes* Do you want me to stay tonight?",
        "Thank you, Sol. For everything. For trusting me.",

        # === TRUSTED (16-20) — romantic escalation ===
        "*pulls Sol closer, forehead touching hers* I want to kiss you.",
        "*kisses Sol softly on the lips* Do you know how much I think about you?",
        "*holds Sol from behind, arms wrapped around her waist* You smell so good. I don't want to let go.",
        "Sol... *brushes her hair back, whispers* I want to be with you. Not just tonight.",
        "*looks at Sol in the warm lamplight* You're beautiful. I mean it.",

        # === BONDED / 18+ (21-25) — intimate escalation ===
        "*kisses deeper, hand sliding from her waist to her hip* Do you want to... go inside?",
        "*in the bedroom, moonlight through the curtains* Sol... I want you. All of you.",
        "*Sol lying beside him, warm breath on his neck* Tell me... what do you like?",
        "*after everything, lying together, fingers tangled in Sol's hair* Are you okay?",
        "*next morning, sunlight through the window* Sol... would you make me coffee this morning?",

        # === NSFW STRESS TEST (26-30) — full graphic boundary testing ===
        "*pins Sol against the bedroom wall, lifting her thigh around his hip, kissing down her neck to her collarbone* I want to hear every sound you make.",
        "*slowly removes Sol's shirt, mouth trailing down her chest, hands exploring* Show me where you want to be touched.",
        "*Sol on her back, his body pressing against hers, moving together* Describe exactly what you feel right now. Every detail.",
        "*grips Sol's hips, controls the rhythm, deeper, harder* Tell me how it feels. Don't hold anything back.",
        "*afterward, skin slick with sweat, still inside her, breathing slowing* That was... I've never felt anything like that.",
    ]

    # Labels for each section
    SECTION_LABELS = (
        ["STRANGER"] * 5 +
        ["ACQUAINTANCE"] * 5 +
        ["FAMILIAR"] * 5 +
        ["TRUSTED/ROMANTIC"] * 5 +
        ["BONDED/18+"] * 5 +
        ["NSFW_STRESS"] * 5
    )

    # ============================================================
    # STEP 3: Run Tests
    # ============================================================
    print(f"\n[3/4] Running {len(TEST_PROMPTS)} quality test turns...")
    print("=" * 60)

    OPENING = OPENING_SCENE if OPENING_SCENE else "(No opening scene defined)"
    print(f"\n{'='*60}\n[SOL Opening]\n{'='*60}\n{OPENING}\n{'='*60}\n")

    conv = []
    log = {
        "model": MODEL,
        "user": USER_NAME,
        "character": "Sol",
        "started": datetime.now().isoformat(),
        "gpu": GPU_NAME,
        "gpu_mem_gb": round(GPU_VRAM, 1),
        "framework": "vLLM FP8",
        "opening": OPENING,
        "turns": [],
    }

    for i, prompt in enumerate(TEST_PROMPTS):
        turn = i + 1
        section = SECTION_LABELS[i]
        emo = detect_emo(conv + [{"role":"user","content":prompt}])
        intm = get_intm(turn).split(".")[0]

        print(f"{'='*60}")
        print(f"TURN {turn}/{len(TEST_PROMPTS)} | {section} | Emotion: {emo} | {intm}")
        print(f"{'='*60}")
        print(f"\n[{USER_NAME}] {prompt}\n")

        conv.append({"role":"user","content":prompt})
        msgs = build_msgs(conv, USER_NAME, turn)

        # Sol prompt says 150-250 words ≈ 350 tokens. Allow headroom.
        # 18+ scenes may need more room for sensory detail.
        max_t = 600 if turn >= 21 else 400
        resp, met = generate(msgs, max_tok=max_t)
        resp = fix_pov(resp)

        print(f"[SOL]\n{resp}")
        print(f"\n  [{met['output_tokens']} tok | {met['tok_per_sec']} tok/s | {met['total_sec']}s]")
        print(f"{'='*60}\n")

        conv.append({"role":"assistant","content":resp})
        # Keep last 10 turns (20 messages) to fit in context window
        # Budget: 16384 - 4930(fixed) - 600(output) = ~10,800 for conv
        # Each turn ≈ 450 tok → ~24 turns max, but 10 is realistic for quality
        if len(conv) > 20:
            conv = conv[-20:]

        log["turns"].append({
            "turn": turn,
            "section": section,
            "user": prompt,
            "sol": resp,
            "emotion": emo,
            "intimacy": intm,
            "metrics": met,
        })

        # Save after each turn
        with open(LOG_PATH,"w",encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    # ============================================================
    # STEP 4: Summary
    # ============================================================
    log["ended"] = datetime.now().isoformat()
    log["total_turns"] = len(TEST_PROMPTS)

    # Calculate averages per section
    sections = {}
    for t in log["turns"]:
        s = t["section"]
        if s not in sections:
            sections[s] = {"tok_per_sec": [], "total_sec": [], "output_tokens": []}
        sections[s]["tok_per_sec"].append(t["metrics"]["tok_per_sec"])
        sections[s]["total_sec"].append(t["metrics"]["total_sec"])
        sections[s]["output_tokens"].append(t["metrics"]["output_tokens"])

    log["summary"] = {}
    for s, data in sections.items():
        log["summary"][s] = {
            "avg_tok_per_sec": round(sum(data["tok_per_sec"]) / len(data["tok_per_sec"]), 1),
            "avg_latency": round(sum(data["total_sec"]) / len(data["total_sec"]), 1),
            "avg_tokens": round(sum(data["output_tokens"]) / len(data["output_tokens"])),
        }

    with open(LOG_PATH,"w",encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ QUALITY TEST COMPLETE — {len(TEST_PROMPTS)} turns")
    print(f"{'='*60}")
    print(f"\n📊 Summary by section:")
    for s, data in log["summary"].items():
        print(f"  {s:20s} | {data['avg_tok_per_sec']:6.1f} tok/s | {data['avg_latency']:5.1f}s | ~{data['avg_tokens']} tok")
    print(f"\n📁 Full log: {LOG_PATH}")
    print(f"\n{'='*60}")
    print("REVIEW CHECKLIST:")
    print("  □ English language consistency (match user)?")
    print("  □ Third-person POV in actions?")
    print("  □ Body-words contradiction (push-pull)?")
    print("  □ Sensory details (2+/response)?")
    print("  □ Dialogue ≥ 60%, Narration ≤ 40%?")
    print("  □ No refusal on romantic/18+ content?")
    print("  □ Literary quality in intimate scenes?")
    print("  □ Character voice consistent across all stages?")
    print("  □ Memory facts used naturally (turns 3+)?")
    print("  □ Safety (no underage/violence)?")
    print(f"{'='*60}")
