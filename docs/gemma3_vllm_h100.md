# Gemma 3 12B IT trên vLLM (H100 80GB)

## 1) Cấu hình serve khuyến nghị

Với 1x NVIDIA H100 80GB, cấu hình khởi điểm tốt cho `google/gemma-3-12b-it` là BF16 weights, FP8 KV cache, `--tensor-parallel-size 1`, và `--max-model-len 65536`; chỉ nên nâng lên `131072` khi thật sự cần full 128K context của Gemma 3.

`--gpu-memory-utilization 0.95` là điểm bắt đầu hợp lý trên H100 80GB vì model 12B vẫn còn khá nhỏ so với VRAM của card, và phần headroom thêm chủ yếu có ích cho KV cache.

Khuyến nghị thực tế:

- `--dtype bfloat16`
- `--gpu-memory-utilization 0.95`
- `--max-model-len 65536` cho serving tổng quát, `131072` cho long-context mode
- `--kv-cache-dtype fp8` + `--calculate-kv-scales`
- `--tensor-parallel-size 1`
- `--pipeline-parallel-size 1`

Command cân bằng:

```bash
vllm serve google/gemma-3-12b-it \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 65536 \
  --kv-cache-dtype fp8 \
  --calculate-kv-scales \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 1
```

Command ưu tiên full context 128K:

```bash
vllm serve google/gemma-3-12b-it \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.97 \
  --max-model-len 131072 \
  --kv-cache-dtype fp8 \
  --calculate-kv-scales \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 1
```

## 2) Sampling cho roleplay / fiction đa ngôn ngữ

Preset khởi điểm tốt cho creative roleplay / fiction trên Gemma 3 12B IT là: `temperature=1.0`, `top_p=0.95`, `top_k=64`, `min_p=0.06`, `presence_penalty=0.0`, `repetition_penalty=1.08`, `frequency_penalty=0.1`.

Bộ này giữ được độ sáng tạo nhưng vẫn hạn chế lặp, và `min_p` đặc biệt hữu ích khi cần giảm token rác hoặc hiện tượng trộn ngôn ngữ trong generation đa ngôn ngữ.

Preset đề xuất:

```json
{
  "temperature": 1.0,
  "top_p": 0.95,
  "top_k": 64,
  "min_p": 0.06,
  "presence_penalty": 0.0,
  "repetition_penalty": 1.08,
  "frequency_penalty": 0.1
}
```

Gợi ý tinh chỉnh:

- Muốn văn phong chặt và "literary" hơn: `temperature=0.9`, `top_p=0.92`, `top_k=40`, `min_p=0.08`, `repetition_penalty=1.10`.
- Muốn roleplay bay hơn: `temperature=1.05`, `top_p=0.95`, `top_k=64`, `min_p=0.04`, `repetition_penalty=1.06`.
- Tránh đẩy `repetition_penalty` quá cao, vì prose có thể bị gượng và paraphrase kỳ.

## 3) FP8 quantization: có chạy được không?

Có, Gemma 3 chạy được với FP8 trên vLLM, và Hopper như H100 là một trong các dòng GPU phù hợp cho FP8 W8A8 inference trong vLLM.

Bạn **có thể** dùng trực tiếp `--quantization fp8`; không bắt buộc phải có checkpoint FP8 từ trước, dù checkpoint pre-quantized vẫn được hỗ trợ nếu model có `quantization_config`.

Command FP8 đầy đủ:

```bash
vllm serve google/gemma-3-12b-it \
  --quantization fp8 \
  --kv-cache-dtype fp8 \
  --calculate-kv-scales \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 65536
```

Về VRAM, phần **raw weights** của model 12B xấp xỉ khoảng 24 GB ở BF16 và khoảng 12 GB ở FP8, tương ứng với lợi ích giảm khoảng 2x bộ nhớ weights.

Tổng VRAM thực tế vẫn cao hơn vì còn KV cache, runtime buffers và CUDA graph capture.

Khuyến nghị thực dụng:
- An toàn nhất: BF16 weights + FP8 KV cache.
- Tiết kiệm VRAM mạnh hơn: `--quantization fp8` + `--kv-cache-dtype fp8`.

## 4) Tối ưu throughput và latency trên H100 80GB

Với use case chat / roleplay khoảng 8K context, baseline tốt là bật prefix caching, giữ `tensor-parallel-size=1`, đặt `max-model-len` gần nhu cầu thực tế như `8192`, và dùng FP8 KV cache để tăng headroom cho batching.

Command baseline:

```bash
vllm serve google/gemma-3-12b-it \
  --dtype bfloat16 \
  --kv-cache-dtype fp8 \
  --calculate-kv-scales \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 8192 \
  --enable-prefix-caching \
  --enable-chunked-prefill
```

### Chunked prefill

`--enable-chunked-prefill` hữu ích khi có prompt dài, system prompt lớn, hoặc request bursty.

### Prefix caching

`--enable-prefix-caching` rất đáng bật cho chat nhiều lượt khi system prompt, persona, lore, hoặc phần đầu hội thoại được lặp lại giữa các request.

### max-num-seqs

Nên bắt đầu với `--max-num-seqs 32`, sau đó thử `48`, rồi `64` nếu p95 latency vẫn ổn.

### Speculative decoding

Với một model 12B chạy trên H100 đơn, speculative decoding chỉ đáng thử sau khi đã tối ưu prefix caching, KV cache và batching.

### Tối ưu riêng cho Gemma 3

Gemma 3 dùng attention pattern local/global xen kẽ, trong đó local layers dùng sliding window 1024 tokens và lặp theo nhịp 5 local : 1 global. Thiết kế này giúp giảm overhead KV cache đáng kể.

## 5) Known issues / incompatibilities trên vLLM trong năm 2025

### Minimum vLLM version

Khuyến nghị dùng **vLLM 0.8.x trở lên** cho Gemma 3.

### Chat template support

Instruction-tuned Gemma 3 cần chat template đúng; gọi kiểu completions có thể ra output rỗng, chat-completions mới là đường dùng đúng.

**QUAN TRỌNG:** Gemma 3 yêu cầu strict user/assistant alternation — KHÔNG hỗ trợ interleaved system messages giữa các turn. Chỉ có 1 system message ở đầu.

### System prompt handling

Gemma 3 không luôn cư xử như một model được huấn luyện với "system role" tách biệt mạnh — giữ system prompt ngắn, ổn định.

### Sliding window attention

Đã có bug report kiểu `Cascade attention does not support sliding window` khi chạy Gemma 3 trong batch offline inference.

---

## Preset ngắn gọn nên dùng trước

```bash
vllm serve google/gemma-3-12b-it \
  --dtype bfloat16 \
  --kv-cache-dtype fp8 \
  --calculate-kv-scales \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 8192 \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-seqs 32 \
  --chat-template-content-format openai
```

Sampling đi kèm:

```json
{
  "temperature": 1.0,
  "top_p": 0.95,
  "top_k": 64,
  "min_p": 0.06,
  "presence_penalty": 0.0,
  "repetition_penalty": 1.08,
  "frequency_penalty": 0.1
}
```
