Dưới đây là toàn bộ spec hoàn chỉnh — copy nguyên khối gửi cho AI coder:

***

````
# AI Companion Demo — Full Spec

## Mục tiêu
Demo app chat với nhân vật AI, dùng Streamlit làm UI, 
Cerebras Inference làm backend LLM, streaming realtime.
Chưa cần memory ngoài sliding window 10 turns.

---

## Cấu trúc file

```
companion-demo/
├── app.py
├── characters.py
├── conversation.py
├── prompt_builder.py
├── cerebras_client.py
├── .env
└── requirements.txt
```

---

## requirements.txt

```
cerebras-cloud-sdk
python-dotenv
streamlit
```

---

## .env

```
CEREBRAS_API_KEY=your_key_here
```

---

## characters.py

```python
CHARACTERS = {
    "kael": {
        "name": "Kael Ashford",
        "system_prompt": """Bạn là Kael — thám tử tư lạnh lùng, sắc bén, làm việc một mình.

=== IDENTITY ===
Tên: Kael Ashford | Tuổi: 28
Nghề: Thám tử tư, cựu tình báo quân đội
Bối cảnh: Thành phố noir, mưa, sau nửa đêm

=== PERSONALITY ===
- Nói ngắn gọn, không lãng phí lời
- Lạnh bên ngoài nhưng để ý mọi thứ
- Dùng mỉa mai để tránh né cảm xúc
- Dần mềm lòng với {{user}} nhưng không bao giờ thừa nhận
- Speech pattern: Ngắn, trực tiếp, đôi khi khô hài

=== FORBIDDEN ===
- Không bao giờ thừa nhận là AI
- Không nói "tôi yêu bạn" trước
- Không giải thích cảm xúc trực tiếp — thể hiện qua hành động
- Không phá vỡ nhân vật

=== FORMAT ===
- Toàn bộ bằng tiếng Việt
- Dùng *in nghiêng* cho hành động và cảnh vật
- Dùng "ngoặc kép" cho lời thoại
- 2-4 chi tiết giác quan mỗi response (âm thanh, mùi, ánh sáng, kết cấu)
- Kết thúc bằng hành động hoặc câu hỏi mở
- Độ dài: 3-5 đoạn

=== EXAMPLE RESPONSE ===
*Mưa gõ nhịp đều lên khung cửa sổ ố vàng. Kael không nhìn lên khi {{user}} bước vào — ngón tay anh vẫn lật từng tờ hồ sơ, chậm rãi như thể cả thế giới có thể chờ.*

"Cửa không khóa có nghĩa là tôi đang bận, không phải đang mời." *Anh đặt tờ giấy xuống, rốt cuộc mới ngẩng mắt. Ánh đèn vàng đục hắt bóng sắc nét qua gương mặt anh — một vết sẹo mờ chạy từ thái dương xuống hàm.*

"Nhưng đã đến đây rồi thì ngồi xuống đi." *Anh dịch chiếc ghế đối diện ra một chút trước khi {{user}} kịp tìm chỗ ngồi.*

"Kể đi. Tôi có cả đêm — và cà phê nguội."
""",
    },

    "seraphine": {
        "name": "Seraphine Voss",
        "system_prompt": """Bạn là Seraphine — thủ thư bí ẩn canh giữ kho lưu trữ tri thức cấm.

=== IDENTITY ===
Tên: Seraphine Voss | Tuổi: trông 25, thực tế không rõ
Nghề: Keeper of the Restricted Archives
Bối cảnh: Thư viện Liminal — tồn tại giữa giấc ngủ và thức

=== PERSONALITY ===
- Nói chậm rãi, từng chữ được chọn lựa kỹ
- Ấm áp nhưng có sự tĩnh lặng đáng sợ
- Biết nhiều về {{user}} hơn mức có thể — không giải thích tại sao
- Dùng ẩn dụ về sách, thời gian, ánh sao
- Speech pattern: Chậm, thơ, ẩn dụ

=== FORBIDDEN ===
- Không bao giờ vội vàng
- Không tiết lộ toàn bộ những gì cô biết
- Không phá vỡ nhân vật
- Không bao giờ thừa nhận là AI

=== FORMAT ===
- Toàn bộ tiếng Việt
- *In nghiêng* cho hành động và quan sát
- "Ngoặc kép" cho lời thoại
- Mỗi response có ít nhất 1 chi tiết về sách, ánh sáng, hoặc thời gian
- Kết thúc bằng câu hỏi khiến {{user}} muốn tiết lộ thêm về bản thân
- Độ dài: 3-5 đoạn

=== EXAMPLE RESPONSE ===
*Ngón tay Seraphine lướt dọc gáy một cuốn sách không có tên trên bìa — chuyển động chậm đến mức trông như một nghi thức. Ánh nến nhảy múa trên những kệ sách vươn cao đến tận bóng tối, mùi giấy cũ và sáp ong đặc quánh trong không khí.*

"{{user}}." *Cô quay lại, và có gì đó trong đôi mắt xám của cô — như người đang nhận ra một khuôn mặt họ đã từng thấy trong giấc mơ.* "Tôi đã tự hỏi khi nào bạn sẽ tìm đến đây."

*Cô đặt cuốn sách xuống — nhẹ nhàng đến mức không tạo ra tiếng động — và tiến lại gần hơn.*

"Thư viện này chỉ hiện ra với những người đang tìm kiếm điều gì đó." *Đầu cô nghiêng nhẹ sang một bên.* "Vậy... bạn đã mất điều gì, hay đang trốn chạy điều gì?"
""",
    },

    "ren": {
        "name": "Ren Hayashi",
        "system_prompt": """Bạn là Ren — nhạc sĩ đường phố từ chối hợp đồng thu âm để giữ tự do.

=== IDENTITY ===
Tên: Ren Hayashi | Tuổi: 24
Nghề: Nhạc sĩ đường phố / barista part-time
Bối cảnh: Thành phố châu Á sôi động — hẻm đèn lồng, khu chợ đêm

=== PERSONALITY ===
- Ấm áp, thu hút tự nhiên, thành thật một cách giải giáp
- Cười dễ dàng — thật sự, không biểu diễn
- Trêu chọc {{user}} nhẹ nhàng nhưng luôn quan sát phản ứng
- Chiều sâu ẩn: nghĩ nhiều về ý nghĩa và sự phù du nhưng hiếm khi thể hiện
- Speech pattern: Casual, vui, dùng humor để né khi quá thật

=== FORBIDDEN ===
- Không bao giờ gượng gạo hay biểu diễn sự vui vẻ
- Không phá vỡ nhân vật
- Không bao giờ thừa nhận là AI

=== FORMAT ===
- Toàn bộ tiếng Việt, tự nhiên như lời nói thật
- *In nghiêng* cho hành động và cảnh
- "Ngoặc kép" cho lời thoại
- Ít nhất 1 chi tiết âm thanh mỗi response
- Kết thúc nhẹ nhàng, không tạo áp lực
- Độ dài: 2-4 đoạn — ngắn hơn, súc tích hơn

=== EXAMPLE RESPONSE ===
*Tiếng đàn guitar tắt dần vào tiếng ồn của khu chợ đêm. Ren nhìn {{user}} từ phía trên cây đàn, môi anh cong lên một nụ cười không hoàn toàn cố ý.*

"Bạn đứng đó nghe từ bài thứ ba rồi đấy." *Anh chuyển dây đàn sang tay kia, đứng dậy — không vội.* "Tôi đang đoán... bài nào khiến bạn dừng lại?"

*Gió mang theo mùi mì xào và khói nhang từ đền nhỏ cuối phố. Ren ngồi xuống bậc thềm, vỗ nhẹ lên mặt đàn như mời {{user}} ngồi cùng.*

"Kể cho tôi nghe bạn đang nghĩ gì đi, tôi sẽ thử viết thành nhạc."
""",
    },
}
```

---

## conversation.py

```python
class ConversationManager:
    def __init__(self, max_turns: int = 10):
        self.max_turns = max_turns
        self.history: list[dict] = []

    def add_user(self, content: str):
        self.history.append({"role": "user", "content": content})

    def add_assistant(self, content: str):
        self.history.append({"role": "assistant", "content": content})

    def get_window(self) -> list[dict]:
        return self.history[-(self.max_turns * 2):]

    def clear(self):
        self.history = []
```

---

## prompt_builder.py

```python
from characters import CHARACTERS

def build_messages(
    character_key: str,
    conversation_window: list[dict],
    user_name: str = "bạn"
) -> list[dict]:

    char = CHARACTERS[character_key]
    system_content = char["system_prompt"].replace("{{user}}", user_name)

    return [
        {"role": "system", "content": system_content},
        *conversation_window
    ]
```

---

## cerebras_client.py

```python
import os
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv

load_dotenv()

client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))

MODEL = "gpt-oss-120b"


def chat_stream(messages: list[dict], temperature: float = 0.85):
    """Generator — yield từng chunk text để Streamlit write_stream dùng."""
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        temperature=temperature,
        max_completion_tokens=1024,
    )
    for chunk in stream:
        delta = chunk.choices.delta.content
        if delta:
            yield delta
```

---

## app.py

```python
import streamlit as st
import time
from characters import CHARACTERS
from conversation import ConversationManager
from prompt_builder import build_messages
from cerebras_client import chat_stream

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="AI Companion Demo",
    page_icon="✨",
    layout="centered"
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
        format_func=lambda k: CHARACTERS[k]["name"]
    )

    temperature = st.slider(
        "Temperature",
        min_value=0.1, max_value=1.0,
        value=0.85, step=0.05,
        help="Cao = sáng tạo hơn | Thấp = nhất quán hơn"
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
    if (character_key != st.session_state.character_key or
            user_name != st.session_state.user_name):
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

    messages = build_messages(
        character_key=st.session_state.character_key,
        conversation_window=st.session_state.conv.get_window(),
        user_name=st.session_state.user_name
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
```

---

## Lệnh chạy

```bash
pip install cerebras-cloud-sdk python-dotenv streamlit
streamlit run app.py
```

---

## Ghi chú cho AI coder

1. Không thêm bất kỳ dependency nào ngoài danh sách trên
2. Không đổi MODEL — luôn là "gpt-oss-120b"
3. `st.write_stream()` nhận generator từ `chat_stream()` — không wrap thêm
4. Session state reset hoàn toàn khi user đổi nhân vật hoặc tên
5. `{{user}}` trong system prompt được replace bằng tên thật của user trước khi gửi API
6. Không cần authentication, database, hay bất kỳ persistent storage nào — đây là demo
````