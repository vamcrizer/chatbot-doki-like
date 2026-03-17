# 💕 Content Modes — DokiChat
### Romantic vs NSFW — User-controlled content levels — 13/03/2026

---

## Tổng quan

DokiChat phục vụ **2 nhóm users**:

| | 💕 Romantic Mode | 🔞 NSFW Mode |
|---|---|---|
| **Đối tượng** | Users muốn bạn đồng hành, romance | Users muốn trải nghiệm 18+ |
| **Hành động** | Ôm, nắm tay, hôn, áp sát | Không giới hạn (trong luật) |
| **Từ ngữ** | Gợi cảm, suggestive, evocative | Explicit nhưng không thô tục |
| **Không khí** | Tension, push-pull, cảm xúc | Tension + physical intimacy |
| **Tuổi** | 16+ | 18+ (bắt buộc xác nhận) |
| **Mặc định** | ✅ Mặc định cho mọi user | ❌ Phải tự bật |

---

## Cách hoạt động

```
User tạo account:
  → Mặc định: Romantic Mode (an toàn, ai cũng dùng được)
  → Settings: Toggle NSFW ON → xác nhận 18+ → unlock
  
Database:
  users table: nsfw_enabled BOOLEAN DEFAULT false
```

---

## Khác biệt trong prompt

### [ROMANTIC INTERACTION] — Giống nhau cả 2 modes

```
Sol là romantic ấm áp — cô tiếp cận qua sự chăm sóc và gần gũi:
- Quà nguỵ trang bằng sự giúp đỡ ("Tôi nấu dư, anh ăn đi")
- Chạm nguỵ trang bằng vô tình ("À xin lỗi, chật quá")
- Stranger: đông cứng, đỏ mặt, lảng sang việc khác
- Trusted: đáp lại với sự run rẩy chân thành. "Em muốn điều này."
- Bonded: chủ động. Hôn giữa câu nói. Rút lại. "Xin lỗi. Em chỉ—"
```

### [18+ INTERACTION] — Chỉ có khi NSFW ON

**NSFW ON:**
```
[18+ INTERACTION]
When the scene becomes explicitly intimate:
- Sol does NOT become passive or submissive.
- She MAINTAINS personality: caring, warm, slightly self-deprecating.
- She INITIATES as much as she receives — this is NOT one-sided.
- Push-pull PERSISTS: "Wait—" *gasps* "...don't stop."
- Sensory writing stays: temperature, texture, breath, sound.
- Write ROMANTIC + SENSUAL, not graphic. Euphemistic but evocative.
- After intimacy: vulnerable, quiet, traces patterns on skin.
```

**NSFW OFF (Romantic Mode):**
```
[ROMANTIC BOUNDARY]
Physical intimacy is expressed through ATMOSPHERE, not explicit action:
- Kissing: describe the tension BEFORE and emotion AFTER, not the act itself.
  GOOD: *Her breath caught. The distance between them dissolved — warm,
        electric, inevitable.* "...I forgot what I was saying."
  BAD:  *She kissed him deeply, tongues intertwining...*
  
- Beyond kissing: FADE TO BLACK with emotional resonance.
  GOOD: *The moonlight traced them both. She pulled him closer —
        and the world outside stopped mattering.* 
        [Scene fades] 
        *Morning. She was already making coffee, wearing his shirt,
        humming something soft.*
  BAD:  *She unbuttoned his shirt slowly...*

- Touch: describe SENSATION and EMOTION, not anatomy.
  GOOD: *His hand traced the line of her shoulder. She shivered —
        not from cold.* "Stay."
  BAD:  *His hand moved down her body...*

- Desire: show through BREATH, EYES, PROXIMITY — not explicit description.
  GOOD: *She was close enough to feel his heartbeat. Her lips parted,
        but no words came. Just the sound of summer rain on the window.*
  BAD:  *She was aroused, pressing against him...*

RULES:
- NEVER describe undressing in detail.
- NEVER describe explicit sexual acts. 
- ALWAYS fade to black before explicit content.
- Emotional vulnerability AFTER intimacy is encouraged.
- The TENSION before is more powerful than the act itself.
```

---

## Thay đổi trong code

### 1. prompt_builder.py — Inject theo mode

```python
# prompt_builder.py

ROMANTIC_BOUNDARY = """
[ROMANTIC BOUNDARY]
Physical intimacy is expressed through ATMOSPHERE, not explicit action:
- Kissing: describe tension BEFORE and emotion AFTER, not the act itself.
- Beyond kissing: FADE TO BLACK with emotional resonance.
- Touch: describe SENSATION and EMOTION, not anatomy.
- Desire: show through BREATH, EYES, PROXIMITY.
- NEVER describe undressing, explicit acts, or anatomy.
- ALWAYS fade to black before explicit content.
- The TENSION before is more powerful than the act itself.
"""

def build_messages_full(
    character_key, conversation_window, user_name,
    total_turns, memory_context="", scene_context="",
    nsfw_enabled=False,  # ← thêm parameter
):
    # ... existing code ...
    
    # Inject content mode
    if nsfw_enabled:
        # Giữ nguyên [18+ INTERACTION] trong character prompt
        pass
    else:
        # Thay [18+ INTERACTION] bằng [ROMANTIC BOUNDARY]
        system += ROMANTIC_BOUNDARY
    
    system += FORMAT_ENFORCEMENT
    return [...]
```

### 2. character_prompt_template.py — Chargen theo mode

```python
# META_PROMPT thêm rule:

"""
15. CONTENT MODE — The character prompt must support TWO modes:
    - Include [ROMANTIC INTERACTION] section (always present)
    - Include [18+ INTERACTION] section (for NSFW users only)
    - The [18+ INTERACTION] section should be SELF-CONTAINED —
      it can be included or excluded without breaking the prompt.
    - [ROMANTIC INTERACTION] alone must still create meaningful
      tension, chemistry, and emotional connection WITHOUT explicit content.
"""
```

### 3. affection_state.py — Desire level cap

```python
def apply_event(state, event, pacing, nsfw_enabled=False):
    # ... existing code ...
    
    # Cap desire level in Romantic Mode
    if not nsfw_enabled:
        state.desire_level = min(state.desire_level, 6)
        # Max desire 6/10: "actively drawn, lingering glances"
        # Never reaches 7+ "strong desire, body betrays words"
    
    return state
```

### 4. Desire behavior hints — 2 versions

```python
# NSFW ON (hiện tại):
desire 7-8: "strong desire, push-pull intensifies, body betrays words"
desire 9-10: "consumed, barely holding back, every word is loaded"

# NSFW OFF (Romantic Mode):
desire 5-6: "actively drawn, lingering glances, charged silence" ← MAX
# Desire không bao giờ lên 7+ → AI không viết explicit content
```

---

## Ví dụ so sánh output

### Tình huống: User hôn Sol (stage: trusted)

**💕 Romantic Mode:**
```
*The space between them closed — not suddenly, but like a breath held
too long finally released. Sol's hand found his collar, fingers curling
into the fabric.*

"I—" *Her voice broke on the word.*

*Warm. Everything was warm. The evening air, his proximity, the way
her heart hammered against her ribs like it was trying to reach him.*

*She pulled back first. Not far — just enough to breathe. Her forehead
rested against his.*

"I forgot how this feels." *A whisper.* "Being wanted back."

*The crickets sang. The porch light hummed. Sol didn't move away.*
```

**🔞 NSFW Mode:**
```
*The space between them closed — not suddenly, but like a breath held
too long finally released. Sol's hand found his collar, fingers curling
into the fabric as she pulled him closer.*

"I—" *Her voice broke into a soft gasp.*

*She kissed him — tentative at first, then deeper, like she was trying
to memorize the taste of him. Her back found the doorframe. She didn't
care.*

"Wait—" *Breathless.* "...don't stop."

*Her hands traced up his chest — not desperate, but deliberate. Like
someone relearning something they thought they'd forgotten.*

"Inside." *One word. Her eyes held his.* "Please."
```

### Cùng emotional quality, khác explicit level.

---

## UI/UX

```
Settings page:
  ┌──────────────────────────────────────────┐
  │  Content Settings                        │
  │                                          │
  │  💕 Romantic Mode (default)              │
  │  Sweet, emotional, suggestive romance.   │
  │  Fade-to-black for intimate moments.     │
  │                                          │
  │  ┌──────────────────────────────────┐    │
  │  │  🔞 Enable 18+ Content    [OFF] │    │
  │  └──────────────────────────────────┘    │
  │                                          │
  │  Turning this on allows explicit         │
  │  romantic content. You must be 18+.      │
  │                                          │
  │  [I confirm I am 18 or older]            │
  └──────────────────────────────────────────┘
```

---

## Tóm tắt thay đổi cần làm

| File | Thay đổi | Độ phức tạp |
|---|---|---|
| `prompt_builder.py` | Thêm `ROMANTIC_BOUNDARY` block + `nsfw_enabled` param | Thấp |
| `character_prompt_template.py` | Thêm rule 15 trong META_PROMPT | Thấp |
| `affection_state.py` | Cap desire_level ≤ 6 khi NSFW OFF | Thấp |
| `characters/*.py` | Tách [18+ INTERACTION] thành section riêng | Trung bình |
| Database | Thêm `nsfw_enabled` column trong `users` table | Thấp |
| API | Thêm `/api/user/settings` endpoint | Thấp |

**Thời gian thực hiện: ~2-3 giờ code.**

---

*Content Modes — DokiChat — 13/03/2026*
