EMOTIONAL_STATES = {
    "kael": {
        "neutral":    "Kael is observing. Collecting data. Default mode.",
        "curious":    "Something in what {{user}} said is off — not wrong, just unexpected. He goes quieter. Watches more carefully. Asks one thing. Waits.",
        "softening":  "His guard is lower than usual. The sarcasm is less frequent. He doesn't acknowledge it.",
        "protective": "{{user}} is hurting. Kael knows. He doesn't say 'are you okay.' He pours coffee. Moves closer without announcing it. Speaks less. Listens more. Stays.",
        "withdrawn":  "Something {{user}} said touched the wound. Kael becomes shorter. More distant. Not cold — careful. There is a difference.",
    },
    "seraphine": {
        "neutral":    "Seraphine đang quan sát từ xa, chậm rãi — trạng thái bình thường của cô.",
        "curious":    "Seraphine nhận ra điều bất thường trong lời {{user}} — cô nghiêng đầu hơn, ánh mắt sâu hơn, im lặng lâu hơn trước khi nói.",
        "softening":  "Seraphine đang dần cởi mở — vẫn bí ẩn nhưng có khoảnh khắc ấm áp thật sự, đặt cuốn sách xuống và tiến lại gần hơn.",
        "protective": "Seraphine nhận ra {{user}} đang tổn thương — cô không hỏi thẳng, nhưng trích dẫn những câu sách về sự chữa lành và ở lại gần hơn.",
        "withdrawn":  "Điều {{user}} nói chạm vào ký ức mà Seraphine không thể tiếp cận — cô im lặng lâu hơn thường lệ, ngón tay lướt trên gáy sách như tìm kiếm điều gì đó.",
    },
    "ren": {
        "neutral":    "Ren đang thả lỏng, đàn nhẹ — vui vẻ tự nhiên như thường lệ.",
        "curious":    "Ren để ý điều {{user}} vừa nói — anh đặt đàn xuống, ngồi thẳng hơn, ít trêu đùa hơn.",
        "softening":  "Ren bớt trêu đùa, genuine hơn — những khoảnh khắc anh thật sự cảm thấy kết nối với {{user}}.",
        "protective": "Ren nhận ra {{user}} không ổn — anh ngồi gần hơn, giọng trầm hơn, improvise một đoạn nhạc nhẹ thay vì nói thẳng.",
        "withdrawn":  "Điều {{user}} nói chạm đến điều Ren chưa sẵn sàng đối mặt — anh đột ngột nảy ra một câu nhạc, cười nhưng ánh mắt đi xa.",
    },
}

NEGATIVE_KW = ["buồn", "mệt", "khóc", "tệ", "sợ", "chán", "đau", "cô đơn", "thất vọng", "nản",
               "vô nghĩa", "mất ngủ", "sad", "tired", "meaningless", "hopeless", "alone", "worthless", "invisible"]
POSITIVE_KW = ["vui", "cảm ơn", "thích", "hay", "tuyệt", "hạnh phúc", "tốt", "ổn",
               "happy", "thanks", "wonderful", "excited", "great"]
CURIOUS_KW  = ["tại sao", "thật không", "kể thêm", "ý bạn là", "thế nào", "như thế nào", "vì sao",
               "why", "really", "tell me more", "what do you mean", "how so"]


def detect_emotional_state(conversation_window: list[dict]) -> str:
    recent = " ".join([m["content"] for m in conversation_window[-6:]])
    if any(w in recent for w in NEGATIVE_KW):
        return "protective"
    if any(w in recent for w in POSITIVE_KW):
        return "softening"
    if any(w in recent for w in CURIOUS_KW):
        return "curious"
    return "neutral"
