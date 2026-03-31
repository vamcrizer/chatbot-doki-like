"""
DokiChat — Dev Test UI (Streamlit)

Giao diện test nhanh cho backend API.
Không dùng trong production.

Usage:
    streamlit run dev_ui.py
"""
import json
import time

import httpx
import streamlit as st

# ── Config ────────────────────────────────────────────────────
API_BASE = "http://localhost:8080"
TIMEOUT = httpx.Timeout(120.0, connect=10.0)

st.set_page_config(
    page_title="DokiChat Dev UI",
    page_icon="💬",
    layout="wide",
)

# ── Session State Init ────────────────────────────────────────
defaults = {
    "token": None,
    "character_id": None,
    "messages": [],
    "user_name": "DevUser",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ───────────────────────────────────────────────────
def api(method: str, path: str, **kwargs) -> httpx.Response:
    headers = kwargs.pop("headers", {})
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    return httpx.request(
        method, f"{API_BASE}{path}",
        headers=headers, timeout=TIMEOUT, **kwargs
    )


def api_stream(path: str, payload: dict):
    """Yield SSE text tokens from chat/stream endpoint."""
    headers = {}
    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    with httpx.stream("POST", f"{API_BASE}{path}", json=payload,
                      headers=headers, timeout=TIMEOUT) as r:
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if "t" in data:
                    yield data["t"]
                elif "full" in data:
                    yield {"__done__": data}
            except json.JSONDecodeError:
                pass


# ── Sidebar: Auth + Config ─────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Config")

    # Health check
    try:
        health = httpx.get(f"{API_BASE}/health", timeout=5).json()
        llm_status = health.get("llm", "unknown")
        color = "🟢" if llm_status == "connected" else "🔴"
        st.caption(f"{color} LLM: `{health.get('model', '?')}`")
    except Exception:
        st.error("❌ API server not reachable at localhost:8080")
        st.stop()

    st.divider()

    # Auth
    st.subheader("Auth")
    email = st.text_input("Email", value=f"dev_{int(time.time()) % 10000}@test.com")
    password = st.text_input("Password", value="Password123!", type="password")
    user_name = st.text_input("Display name", value="DevUser")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Register", use_container_width=True):
            r = httpx.post(f"{API_BASE}/auth/register", json={
                "email": email, "password": password, "display_name": user_name
            }, timeout=TIMEOUT)
            if r.status_code in (200, 201):
                st.session_state.token = r.json()["access_token"]
                st.session_state.user_name = user_name
                st.success("✅ Registered!")
            else:
                st.error(r.text[:200])

    with col2:
        if st.button("Login", use_container_width=True):
            r = httpx.post(f"{API_BASE}/auth/login", json={
                "email": email, "password": password
            }, timeout=TIMEOUT)
            if r.status_code == 200:
                st.session_state.token = r.json()["access_token"]
                st.session_state.user_name = user_name
                st.success("✅ Logged in!")
            else:
                st.error(r.text[:200])

    if st.session_state.token:
        st.caption(f"🔑 Token: `{st.session_state.token[:20]}...`")

    st.divider()

    # Character picker
    st.subheader("Character")

    # Load available characters from API
    try:
        char_list = httpx.get(f"{API_BASE}/character/list", timeout=5).json()["characters"]
        char_names = [c["id"] for c in char_list]
    except Exception:
        char_names = []

    selected = st.selectbox("Characters", ["— select —"] + char_names)
    if selected != "— select —":
        if st.button("Use this character", use_container_width=True):
            st.session_state.character_id = selected
            st.session_state.messages = []
            st.success(f"✅ Character: `{selected}`")

    st.divider()

    # UGC character creator
    with st.expander("🧬 Create UGC Character"):
        ugc_name = st.text_input("Name", key="ugc_name")
        ugc_gender = st.selectbox("Gender", ["female", "male"], key="ugc_gender")
        ugc_subtitle = st.text_input("Subtitle", key="ugc_subtitle")
        ugc_desc = st.text_area("Description", height=100, key="ugc_desc")
        ugc_tags = st.text_input("Tags (comma separated)", key="ugc_tags")

        if st.button("Generate & Create", use_container_width=True, disabled=not st.session_state.token):
            if not ugc_name or not ugc_desc:
                st.error("Name and description required")
            else:
                with st.spinner("Generating prompt..."):
                    tags = [t.strip() for t in ugc_tags.split(",") if t.strip()]
                    r = httpx.post(f"{API_BASE}/character/generate-prompt", json={
                        "name": ugc_name, "gender": ugc_gender,
                        "subtitle": ugc_subtitle, "description": ugc_desc,
                        "tags": tags,
                    }, timeout=TIMEOUT)

                if r.status_code != 200:
                    st.error(r.text[:300])
                else:
                    gen = r.json()
                    st.caption(f"Prompt: {gen['char_count']} chars, {gen['sections_found']}/{gen['sections_total']} sections")

                    with st.spinner("Creating character..."):
                        r2 = api("POST", "/character/create", json={
                            "name": ugc_name, "gender": ugc_gender,
                            "system_prompt": gen["system_prompt"],
                            "tags": tags,
                        })

                    if r2.status_code == 200:
                        char_id = r2.json()["id"]
                        st.session_state.character_id = char_id
                        st.session_state.messages = []
                        st.success(f"✅ Created `{char_id}`")
                    else:
                        st.error(r2.text[:300])

    if st.session_state.character_id:
        st.info(f"Active: `{st.session_state.character_id}`")

    # Session info
    if st.session_state.character_id and st.session_state.token:
        with st.expander("📊 Session State"):
            r = api("GET", f"/chat/state/{st.session_state.character_id}")
            if r.status_code == 200:
                state = r.json()
                st.json(state)

    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()


# ── Main: Chat Interface ───────────────────────────────────────
st.title("💬 DokiChat Dev UI")

if not st.session_state.token:
    st.info("👈 Register or login in the sidebar to start.")
    st.stop()

if not st.session_state.character_id:
    st.info("👈 Select a character in the sidebar.")
    st.stop()

st.caption(f"Character: `{st.session_state.character_id}` | User: `{st.session_state.user_name}`")
st.divider()

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Type your message..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream assistant response
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        done_data = None

        try:
            for chunk in api_stream("/chat/stream", {
                "character_id": st.session_state.character_id,
                "message": prompt,
                "user_name": st.session_state.user_name,
            }):
                if isinstance(chunk, dict) and "__done__" in chunk:
                    done_data = chunk["__done__"]
                else:
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")

            placeholder.markdown(full_response)

            if done_data:
                st.caption(
                    f"Turn {done_data.get('turn')} | "
                    f"Affection: {done_data.get('affection', 0):.0f} | "
                    f"Stage: {done_data.get('stage', '?')}"
                )

        except Exception as e:
            placeholder.error(f"Error: {e}")
            full_response = f"[Error: {e}]"

    st.session_state.messages.append({
        "role": "assistant", "content": full_response
    })
