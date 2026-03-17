# 💰 Chi phí Test & Dev — DokiChat
### 12/03/2026

---

## Chiến lược: Deploy từng phần, kiểm soát chi phí

Đưa từng thành phần lên online theo thứ tự, kiểm tra kỹ trước khi sang bước sau.
Chi phí production → xem **TOM_TAT_BAO_CAO_2.md**.

---

## Phase 0: Test GPU trên RunPod (Spot)

**Mục tiêu:** Xác nhận vLLM + model chạy ổn trên cloud GPU.

| Thành phần | Vị trí | Chi phí |
|---|---|---|
| vLLM + 4B model | **RunPod Spot L40S** | $0.26/hr |
| FastAPI app | Local (máy dev) | $0 |
| PostgreSQL | Local | $0 |
| Redis | Local | $0 |
| Qdrant | Local | $0 |

```
Ngân sách Phase 0:
  Test 8 giờ/ngày × 3 ngày = 24 giờ × $0.26 = $6.24
  Dự phòng: $15
  
  💵 Tổng: ~$15-20
```

> ⚠️ Spot có thể bị ngắt bất kỳ lúc nào — OK cho test.

---

## Phase 1: GPU ổn định + Database online (Demo)

**Mục tiêu:** Hệ thống đủ để demo cho team/sếp.

| Thành phần | Vị trí | Chi phí |
|---|---|---|
| vLLM + 4B + 9B | **RunPod On-Demand L40S** | $0.86/hr |
| FastAPI app | Local hoặc VPS rẻ | $0-5 |
| PostgreSQL | **Supabase Free** (500MB, 50K users) | $0 |
| Redis | Local | $0 |
| Qdrant | **Qdrant Free Cloud** (~1M vectors) | $0 |

```
Ngân sách Phase 1 (demo 1-2 tuần):
  GPU: 8 giờ/ngày × 10 ngày = 80 giờ × $0.86 = $68.80
  Supabase + Qdrant Free: $0
  
  💵 Tổng: ~$70-80
  
  * Chỉ bật GPU khi cần test/demo, tắt khi không dùng
```

---

## Tổng ngân sách Test & Dev

| Phase | Thời gian | Chi phí |
|---|---|---|
| **Phase 0** — Test GPU (Spot) | 3 ngày | **~$20** |
| **Phase 1** — Demo (On-Demand) | 1-2 tuần | **~$70-80** |
| **Tổng** | | **~$90-100** |

> Chi phí production (staging 24/7, scale) → xem **TOM_TAT_BAO_CAO_2.md**

---

*Chi phí Test & Dev — DokiChat — 12/03/2026*
