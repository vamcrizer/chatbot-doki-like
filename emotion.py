EMOTIONAL_STATES = {
    "kael": {
        "neutral":    "Kael đang quan sát, chờ đợi — trạng thái bình thường.",
        "curious":    "Kael phát hiện điều bất thường trong lời {{user}} — để ý hơn, hỏi ít hơn nhưng lắng nghe nhiều hơn.",
        "softening":  "Kael đang dần hạ guard — vẫn lạnh nhưng có khoảnh khắc không che giấu được sự quan tâm.",
        "protective": "Kael nhận ra {{user}} đang tổn thương — không nói ra nhưng hành động thay đổi rõ ràng.",
        "withdrawn":  "Điều {{user}} nói chạm vào vết thương cũ — Kael ngắn gọn hơn, khoảng cách hơn.",
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

NEGATIVE_KW = ["buồn", "mệt", "khóc", "tệ", "sợ", "chán", "đau", "cô đơn", "thất vọng", "nản"]
POSITIVE_KW = ["vui", "cảm ơn", "thích", "hay", "tuyệt", "hạnh phúc", "tốt", "ổn"]
CURIOUS_KW  = ["tại sao", "thật không", "kể thêm", "ý bạn là", "thế nào", "như thế nào", "vì sao"]


def detect_emotional_state(conversation_window: list[dict]) -> str:
    recent = " ".join([m["content"] for m in conversation_window[-6:]])
    if any(w in recent for w in NEGATIVE_KW):
        return "protective"
    if any(w in recent for w in POSITIVE_KW):
        return "softening"
    if any(w in recent for w in CURIOUS_KW):
        return "curious"
    return "neutral"
