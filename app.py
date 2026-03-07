import streamlit as st
import time
from characters import CHARACTERS
from conversation import ConversationManager
from prompt_builder import build_messages_full
from cerebras_client import chat_stream

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="AI Companion Demo",
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

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Cài đặt")

    user_name = st.text_input("Tên của bạn", value="Minh")

    character_key = st.selectbox(
        "Chọn nhân vật",
        options=list(CHARACTERS.keys()),
        format_func=lambda k: CHARACTERS[k]["name"],
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
    st.caption("Model: **gpt-oss-120b**")
    st.caption("Provider: **Cerebras Inference**")
    st.divider()

    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.conv.clear()
        st.session_state.messages_display = []
        st.rerun()

    # Reset khi đổi nhân vật hoặc tên user
    if (
        character_key != st.session_state.character_key
        or user_name != st.session_state.user_name
    ):
        st.session_state.conv.clear()
        st.session_state.messages_display = []
        st.session_state.character_key = character_key
        st.session_state.user_name = user_name

# ── Header ────────────────────────────────────────────────────
char = CHARACTERS[st.session_state.character_key]
st.title(f"✨ {char['name']}")
st.caption("AI Companion Demo · Powered by Cerebras")
st.divider()

# ── Render lịch sử chat ───────────────────────────────────────
# Hiển thị opening scene nếu chưa có tin nhắn nào
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

    messages = build_messages_full(
        character_key=st.session_state.character_key,
        conversation_window=st.session_state.conv.get_window(),
        user_name=st.session_state.user_name,
        total_turns=st.session_state.conv.total_turns,
    )

    with st.chat_message("assistant"):
        start = time.time()
        response = st.write_stream(
            chat_stream(messages, temperature=temperature)
        )
        elapsed = time.time() - start
        st.caption(f"⚡ {elapsed:.2f}s · gpt-oss-120b · Cerebras")

    st.session_state.conv.add_assistant(response)
    st.session_state.messages_display.append(
        {"role": "assistant", "content": response}
    )
