# Xin cấp vốn 550K để test máy chủ GPU — AI Companion Chat
## 19/03/2026

---

## Đã làm được gì

Đã chọn xong AI cho AI Companion chat: **Qwen3-30B-A3B**.

Đã test miễn phí trên máy cao cấp nhất của Google (H100) và kết quả rất tốt:

- **Tốc độ trả lời**: 1.2 giây cho mỗi tin nhắn — người dùng gần như không phải chờ
- **Chịu tải**: 128 người chat cùng lúc trên 1 máy, ai cũng được trả lời trong 5 giây
- **Đa ngôn ngữ**: đã giải quyết được ~95% vấn đề language mixing (AI trộn lẫn ngôn ngữ — lỗi phổ biến nhất của chatbot đa ngôn ngữ). Test trên 7 ngôn ngữ có thị trường chatbot lớn nhất: Anh, Tây Ban Nha, Bồ Đào Nha, Indonesia, Đức, Hindi, Filipino — AI trả lời đúng ngôn ngữ 100%, không lẫn tiếng Anh
- **Chất lượng hội thoại**: 8.5-9/10 cho 5 ngôn ngữ chính — đủ chuẩn production

Vài đoạn chat thật từ AI (không chỉnh sửa), cùng câu hỏi **"Sống một mình... không bao giờ cô đơn sao?"** — 5 ngôn ngữ:

**English:**
> *Sol's hand froze mid-motion as she adjusted the vase of daisies on the table. The flowers wobbled, their white petals trembling like startled birds. She steadied them with a gentle touch, her pulse fluttering in her throat.*
>
> *"I don't know," she said, staring at the wall instead of meeting his eyes. "Sometimes I think loneliness is just a word people use when they're too scared to ask for something."*
>
> *Instead, she stood up abruptly, knocking over a stack of magazines. "I should probably go check on my plants," she said. Ethan reached out, his hand hovering near hers. "Sol—" She didn't wait for him to finish. The screen door slammed behind her, echoing like a heartbeat.*

**Spanish:**
> *"No siempre," dijo, aunque su voz sonó más débil de lo que quería. Su dedo índice se movió sin control, rozando el borde de una taza que nunca usaba.*
>
> *"A veces es mejor estar sola," añadió, mientras giraba la botella de agua entre sus dedos. "Al menos así sabes qué esperar."*
>
> *"¿Y si no quieres saber qué esperar?" preguntó él, con una voz baja, casi un susurro. Sol bajó la mirada, sintiendo cómo su corazón se aceleraba.*

**Portuguese:**
> *"Às vezes," admitiu, com a voz baixa, quase um murmúrio. "Mas a solidão não é o mesmo que estar sozinha."*
>
> *"Eu tenho minhas coisas," respondeu, olhando para as folhas das plantas que crescem junto à janela. "Minhas plantas, meu trabalho, minha rotina. E... às vezes, as pessoas aparecem."*
>
> *Lucas a encarou por um momento, e Sol sentiu o mundo parar por um segundo.*

**Indonesian:**
> *"Tidak juga," katanya, suaranya terdengar ringan tapi ada sesuatu yang tersembunyi di balik kata-katanya.*
>
> *"Kadang-kadang," lanjutnya, "aku merasa seperti bunga yang tumbuh di sudut ruangan. Banyak orang lewat, tapi tidak pernah benar-benar melihatku."*
>
> *"Tapi aku baik-baik saja," katanya lagi, "aku punya buku, taman, dan..." Dia berhenti sejenak, kemudian tersenyum. "Dan orang-orang seperti kamu."*

**German:**
> *„Einsam?" wiederholte sie, während sie den Kaffee in zwei Tassen goss. Ihre Stimme klang leiser, als sie es gewollt hatte.*
>
> *„Manchmal… aber ich habe genug zu tun." Sie lachte leise, aber es klang eher wie ein Versuch, die Stille zu füllen.*
>
> *„Du bist nicht allein, wenn du es nicht willst," sagte er, und seine Stimme klang warm, wie ein Hauch von Frühling in der Hitze des Sommers.*

Tất cả output thật, **không chỉnh sửa**. 0 từ tiếng Anh lẫn vào ES/PT/ID/DE. Đã test 56 lượt trên 7 ngôn ngữ, xác nhận qua 3 lần chạy.

---

## Vấn đề

Máy test (H100) giá **$2.69/giờ** — quá đắt để vận hành lâu dài.

Máy dự kiến dùng thật: **RTX PRO 6000** — giá chỉ **$1.69/giờ** (rẻ hơn 37%), bộ nhớ lớn hơn (96GB vs 80GB).

Nhưng tất cả con số hiệu năng của RTX PRO 6000 hiện tại là **tính toán trên giấy**, chưa chạy thật. Cần chạy thử để biết:

- Tốc độ trả lời thực tế bao nhiêu?
- Phục vụ được bao nhiêu người cùng lúc?
- Có vấn đề tương thích gì không?

---

## Đề xuất

Thuê máy RTX PRO 6000 khoảng **10 giờ** để chạy test, dùng loại giá rẻ nhất (spot — $1.19/giờ).

**Chi phí: ~550.000 VND (~$21)**

| Hạng mục | Chi phí |
|----------|--------|
| Máy GPU spot ~10 giờ x $1.19/hr | ~$12 (~310K) |
| Ổ cứng mạng 100GB ($0.07/GB/tháng) | $7.00 (~180K) |
| Lưu trữ tạm | ~$0.50 (~13K) |
| **Tổng** | **~$19-21 (~500-550K VND)** |

Ổ cứng mạng 100GB để chứa model AI (~60GB bản đầy đủ) + dữ liệu test. Giữ lại dùng cho production sau này.

---

## Nếu kết quả tốt

- Xác nhận 1 máy RTX PRO 6000 ($1,217/tháng ~ 30 triệu VND) phục vụ được khoảng 1 triệu người dùng

## Nếu kết quả không như kỳ vọng

- Biết sớm, chuyển sang máy rẻ hơn (L40S — $619/tháng ~ 15 triệu VND)
- Mất 550K nhưng tránh chọn sai máy cho production

---

**Tóm lại**: 550K để chạy thử trước khi quyết định thuê máy dài hạn cho sản phẩm.
