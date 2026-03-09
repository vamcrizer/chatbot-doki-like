import streamlit as st
import time
import threading
from datetime import datetime
from characters import get_all_characters
from conversation import ConversationManager
from prompt_builder import build_messages_full
from cerebras_client import chat_stream
from character_generator import (
    generate_character_from_bio,
    generate_emotional_states,
    save_character,
    delete_character,
    load_custom_characters,
)
from memory.scene_tracker import SceneTracker
from memory.mem0_store import create_memory_store
from memory.fact_extractor import extract_facts, extract_facts_lightweight
from memory.summarizer import summarize_conversation

# ── Export helper ───────────────────────────────────────────
def build_export_txt(
    char_name: str,
    user_name: str,
    opening: str,
    messages: list[dict],
    total_turns: int,
) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append(f"AI Companion Demo — Chat Export")
    lines.append(f"Nhân vật : {char_name}")
    lines.append(f"Người dùng: {user_name}")
    lines.append(f"Thời gian : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Turns     : {total_turns}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("[OPENING SCENE]")
    lines.append(opening)
    lines.append("")
    lines.append("-" * 60)
    lines.append("")
    for msg in messages:
        if msg["role"] == "user":
            lines.append(f"[{user_name.upper()}]")
        else:
            lines.append(f"[{char_name.upper()}]")
        lines.append(msg["content"])
        lines.append("")
    lines.append("=" * 60)
    lines.append("END OF SESSION")
    return "\n".join(lines)


# ── Memory helpers ────────────────────────────────────────────
def build_memory_context(mem_store, user_name: str) -> str:
    """Build the [MEMORY] context block from stored facts + summary."""
    facts = mem_store.get_all()
    summary = mem_store.get_summary()

    if not facts and not summary:
        return ""

    parts = []

    # User facts
    user_facts = [f for f in facts if f.get("type") in ("user_fact", "emotional_state")]
    if user_facts:
        parts.append(f"[MEMORY — what you know about {user_name}]")
        for f in user_facts[-10:]:  # top 10 most recent
            parts.append(f"- {f['text']}")
        parts.append("Use naturally. NEVER say \"I remember that...\" — just ACT on it.")

    # Character development notes
    char_notes = [f for f in facts if f.get("type") == "character_note"]
    if char_notes:
        parts.append("\n[CHARACTER DEVELOPMENT — what has been revealed]")
        for f in char_notes[-5:]:
            parts.append(f"- {f['text']}")
        parts.append("Do NOT repeat these revelations. Build on them.")

    # Session summary
    if summary:
        parts.append(f"\n[PREVIOUS CONTEXT]\n{summary}")

    return "\n".join(parts) if parts else ""


def async_memory_update(mem_store, user_msg, assistant_msg, character_name,
                        conversation_history, total_turns, summarize_every=10):
    """Background memory update — runs after response is sent."""
    try:
        # 1. Extract facts from this turn
        existing = [m["text"] for m in mem_store.get_all()]
        facts = extract_facts(user_msg, assistant_msg, existing)

        # Also grab lightweight facts (instant, no LLM)
        light_facts = extract_facts_lightweight(user_msg)

        # Merge, dedupe
        all_facts = facts + [f for f in light_facts
                             if not any(f["text"] == ef["text"] for ef in facts)]

        if all_facts:
            mem_store.add(all_facts)
            print(f"[Mem0] Stored {len(all_facts)} facts: "
                  f"{[f['text'][:50] for f in all_facts]}")

        # 2. Summarize every N turns
        if total_turns > 0 and total_turns % summarize_every == 0:
            old_summary = mem_store.get_summary()
            new_summary = summarize_conversation(
                conversation_history,
                existing_summary=old_summary,
                character_name=character_name,
            )
            if new_summary:
                mem_store.update_summary(new_summary)
                print(f"[Mem0] Updated summary ({len(new_summary)} chars)")

    except Exception as e:
        print(f"[Mem0] Async update error: {e}")


# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="DokiChat — AI Companion",
    page_icon="✨",
    layout="centered",
)

# ── Session State init ────────────────────────────────────────
if "conv" not in st.session_state:
    st.session_state.conv = ConversationManager(max_turns=10)
if "character_key" not in st.session_state:
    st.session_state.character_key = "kael"
if "user_name" not in st.session_state:
    st.session_state.user_name = "bạn"
if "messages_display" not in st.session_state:
    st.session_state.messages_display = []
if "show_creator" not in st.session_state:
    st.session_state.show_creator = False
if "creating" not in st.session_state:
    st.session_state.creating = False

# Memory system init
if "scene_tracker" not in st.session_state:
    st.session_state.scene_tracker = SceneTracker()
if "mem_store" not in st.session_state:
    st.session_state.mem_store = None  # initialized when character selected

# ── Load characters dynamically ──────────────────────────────
ALL_CHARACTERS = get_all_characters()

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Cài đặt")

    user_name = st.text_input("Tên của bạn", value="Hung")

    character_key = st.selectbox(
        "Chọn nhân vật",
        options=list(ALL_CHARACTERS.keys()),
        format_func=lambda k: ALL_CHARACTERS[k]["name"],
    )

    temperature = st.slider(
        "Temperature",
        min_value=0.1,
        max_value=1.0,
        value=0.85,
        step=0.05,
        help="Cao = sáng tạo hơn | Thấp = nhất quán hơn",
    )

    st.divider()

    # ── Character Creator Button ──
    if st.button("✨ Tạo nhân vật mới", use_container_width=True, type="primary"):
        st.session_state.show_creator = not st.session_state.show_creator
        st.rerun()

    # ── Delete custom character ──
    custom_chars = load_custom_characters()
    if character_key in custom_chars:
        if st.button(f"🗑️ Xóa {ALL_CHARACTERS[character_key]['name']}", use_container_width=True):
            delete_character(character_key)
            st.session_state.character_key = "kael"
            st.session_state.conv.clear()
            st.session_state.messages_display = []
            st.session_state.mem_store = None
            st.session_state.scene_tracker = SceneTracker()
            st.rerun()

    st.divider()
    st.caption("Model: **gpt-oss-120b**")
    st.caption("Provider: **Cerebras Inference**")

    # Memory status
    if st.session_state.mem_store:
        mem_count = len(st.session_state.mem_store.get_all())
        has_summary = bool(st.session_state.mem_store.get_summary())
        scene = st.session_state.scene_tracker.current_scene
        st.caption(f"🧠 Memories: **{mem_count}** | Summary: **{'✅' if has_summary else '—'}**")
        st.caption(f"📍 Scene: **{scene}**")

    st.divider()

    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.conv.clear()
        st.session_state.messages_display = []
        st.session_state.scene_tracker = SceneTracker()
        # Don't clear mem_store — memories persist across sessions!
        st.rerun()

    # Xuất chat
    if st.session_state.messages_display:
        _export_char = ALL_CHARACTERS[st.session_state.character_key]
        _export_opening = _export_char["opening_scene"].replace(
            "{{user}}", st.session_state.user_name
        )
        _export_txt = build_export_txt(
            char_name=_export_char["name"],
            user_name=st.session_state.user_name,
            opening=_export_opening,
            messages=st.session_state.messages_display,
            total_turns=st.session_state.conv.total_turns,
        )
        _filename = (
            f"chat_{_export_char['name'].replace(' ', '_')}"
            f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        st.download_button(
            label="📄 Xuất chat (.txt)",
            data=_export_txt.encode("utf-8"),
            file_name=_filename,
            mime="text/plain",
            use_container_width=True,
        )

    # Reset khi đổi nhân vật hoặc tên user
    if (
        character_key != st.session_state.character_key
        or user_name != st.session_state.user_name
    ):
        st.session_state.conv.clear()
        st.session_state.messages_display = []
        st.session_state.character_key = character_key
        st.session_state.user_name = user_name
        st.session_state.scene_tracker = SceneTracker()
        st.session_state.mem_store = None  # re-init for new char

# ── Initialize memory store for current character ─────────────
if st.session_state.mem_store is None:
    st.session_state.mem_store = create_memory_store(
        user_id=st.session_state.user_name,
        character_id=st.session_state.character_key,
    )

# ── Character Creator Dialog ─────────────────────────────────
if st.session_state.show_creator:
    st.markdown("---")
    st.subheader("✨ Tạo nhân vật mới")
    st.markdown(
        "Nhập tiểu sử nhân vật. AI sẽ tự động tạo prompt, "
        "tính cách, và cảnh mở đầu."
    )

    with st.form("character_creator_form"):
        char_name_input = st.text_input(
            "Tên nhân vật",
            placeholder="Ví dụ: Ân Thư, Minh Khôi, Yuki...",
        )

        bio_input = st.text_area(
            "Tiểu sử nhân vật",
            height=250,
            placeholder="""Ví dụ:
Tên: Ân Thư
Tuổi: 18
Giới tính: Nữ
Nghề nghiệp: Học sinh cấp 3

Tính cách: Bề ngoài tự tin, sắc sảo, luôn giữ nụ cười thách thức.
Thực chất sâu trong lòng là sự tổn thương, cô đơn.

Gia thế: Xuất thân gia đình giàu có nhưng tình cảm lạnh nhạt.

Hoàn cảnh: Từng bị bạn bè xa lánh, bị gài bẫy và đuổi học.
Hiện tại đứng trước ngã rẽ cuộc đời.

Setting: Con hẻm sau trung tâm, đêm muộn.
Giọng nói: Dùng "ta/ngươi", mỉa mai, chua chát nhưng thỉnh thoảng lộ ra sự mong manh."""
        )

        submitted = st.form_submit_button(
            "🚀 Tạo nhân vật", use_container_width=True, type="primary"
        )

    if submitted and char_name_input and bio_input:
        # Prepend name to bio if not already there
        full_bio = bio_input
        if char_name_input.lower() not in bio_input.lower():
            full_bio = f"Tên: {char_name_input}\n{bio_input}"

        with st.status("🧠 Đang tạo nhân vật...", expanded=True) as status:
            st.write("📝 Đang phân tích tiểu sử...")

            try:
                # Step 1: Generate character prompt
                st.write("🎭 Đang tạo system prompt và cảnh mở đầu...")
                char_data = generate_character_from_bio(full_bio)

                # Ensure name is set
                if "name" not in char_data or not char_data["name"]:
                    char_data["name"] = char_name_input

                # Store bio for reference
                char_data["_bio"] = full_bio

                # Step 2: Generate emotional states
                st.write("💭 Đang tạo trạng thái cảm xúc...")
                emo_states = generate_emotional_states(
                    full_bio, char_data["name"]
                )

                # Step 3: Save to JSON
                st.write("💾 Đang lưu nhân vật...")
                key = save_character(char_data, emo_states)

                status.update(
                    label=f"✅ Đã tạo {char_data['name']}!",
                    state="complete",
                )

                # Show preview
                st.success(f"Nhân vật **{char_data['name']}** đã được tạo!")

                with st.expander("👀 Xem cảnh mở đầu", expanded=True):
                    st.markdown(
                        char_data["opening_scene"].replace(
                            "{{user}}", user_name
                        )
                    )

                with st.expander("🔧 Xem system prompt"):
                    st.code(char_data["system_prompt"], language=None)

                st.info(
                    f"Chọn **{char_data['name']}** trong danh sách "
                    f"nhân vật bên trái để bắt đầu chat!"
                )

                # Switch to new character
                st.session_state.character_key = key
                st.session_state.conv.clear()
                st.session_state.messages_display = []
                st.session_state.show_creator = False
                st.session_state.mem_store = None
                st.session_state.scene_tracker = SceneTracker()

                # Reload
                st.rerun()

            except Exception as e:
                status.update(label="❌ Lỗi khi tạo nhân vật", state="error")
                st.error(f"Có lỗi xảy ra: {str(e)}")
                st.exception(e)

    st.markdown("---")

# ── Header ────────────────────────────────────────────────────
char = ALL_CHARACTERS[st.session_state.character_key]
st.title(f"✨ {char['name']}")
st.caption("DokiChat · AI Companion Demo · Powered by Cerebras")
st.divider()

# ── Render lịch sử chat ───────────────────────────────────────
if not st.session_state.messages_display:
    opening = char["opening_scene"].replace("{{user}}", st.session_state.user_name)
    with st.chat_message("assistant"):
        st.markdown(opening)

for msg in st.session_state.messages_display:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Chat input ────────────────────────────────────────────────
if user_input := st.chat_input(f"Nhắn tin với {char['name']}..."):

    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages_display.append(
        {"role": "user", "content": user_input}
    )

    st.session_state.conv.add_user(user_input)

    # Update scene tracker
    st.session_state.scene_tracker.update(user_input)
    scene_context = st.session_state.scene_tracker.get_context_block()

    # Build memory context
    memory_context = build_memory_context(
        st.session_state.mem_store,
        st.session_state.user_name,
    )

    # Adaptive window: shrink when memory fills the gap
    has_memory = bool(memory_context)

    messages = build_messages_full(
        character_key=st.session_state.character_key,
        conversation_window=st.session_state.conv.get_window(has_memory=has_memory),
        user_name=st.session_state.user_name,
        total_turns=st.session_state.conv.total_turns,
        memory_context=memory_context,
        scene_context=scene_context,
    )

    with st.chat_message("assistant"):
        start = time.time()
        response = st.write_stream(
            chat_stream(messages, temperature=temperature)
        )
        elapsed = time.time() - start

        # Show scene + memory info
        scene_label = st.session_state.scene_tracker.current_scene
        mem_count = len(st.session_state.mem_store.get_all())
        st.caption(f"⚡ {elapsed:.2f}s · gpt-oss-120b · 📍{scene_label} · 🧠{mem_count}")

    st.session_state.conv.add_assistant(response)
    st.session_state.messages_display.append(
        {"role": "assistant", "content": response}
    )

    # Async memory update (non-blocking)
    threading.Thread(
        target=async_memory_update,
        args=(
            st.session_state.mem_store,
            user_input,
            response,
            char["name"],
            st.session_state.conv.history,
            st.session_state.conv.total_turns,
        ),
        daemon=True,
    ).start()
