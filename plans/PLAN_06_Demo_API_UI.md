# PLAN 06 — Demo API & UI

**Component:** FastAPI Backend + Streamlit PoC UI  
**Cập nhật cho:** dataset chuẩn hóa và scope PoC 4 tuần

---

## 1. Mục tiêu

Demo cần chứng minh pipeline chạy end-to-end, không cần UI đẹp như sản phẩm thật.

Luồng demo:

```text
Chọn patient
→ Run summarization pipeline
→ Xem clinical summary theo section
→ Click citation
→ Xem source gốc
→ Xem metrics
→ Xem claim bị flag/need review
```

---

## 2. FastAPI backend

### 2.1 Endpoints tối thiểu

```text
GET  /api/v1/health
GET  /api/v1/patients
POST /api/v1/summarize/{patient_id}
GET  /api/v1/source/{source_id}
GET  /api/v1/metrics/{patient_id}
DELETE /api/v1/cache/{patient_id}
```

### 2.2 Response chính

`POST /api/v1/summarize/{patient_id}` trả về `FinalSummary`:

```json
{
  "patient_id": "P001",
  "created_at": "2026-06-03T10:00:00+07:00",
  "prompt_version": "poc_v1",
  "model_version": "selected_model",
  "sections": [],
  "metrics": {}
}
```

### 2.3 Source lookup

`GET /api/v1/source/{source_id}` trả về:

```json
{
  "source_id": "P001-E001-LAB-HBA1C",
  "source_type": "lab_result",
  "patient_id": "P001",
  "encounter_id": "P001-E001",
  "date": "2024-01-10",
  "content": "HbA1c: 9.2% ...",
  "metadata": {}
}
```

---

## 3. Streamlit UI

### 3.1 Component tối thiểu

```text
Patient selector
Run summary button
Summary sections
Citation badges
Source panel
Metrics bar
Debug panel
```

### 3.2 Layout gợi ý

```text
┌─────────────────────────────────────────────┐
│ Patient selector: P001                      │
│ [Generate Summary] [Clear Cache]            │
├─────────────────────────────────────────────┤
│ Metrics: citation coverage, hallucination   │
├─────────────────────────────────────────────┤
│ Tổng quan bệnh nhân                         │
│ ... [source_id]                             │
├─────────────────────────────────────────────┤
│ Thuốc hiện tại                              │
│ ... [source_id]                             │
├─────────────────────────────────────────────┤
│ Source panel                                │
│ source_id, source_type, content, metadata   │
└─────────────────────────────────────────────┘
```

---

## 4. UI behavior cho claim status

| Status | UI |
|---|---|
| `SUPPORTED` | Citation badge bình thường |
| `PARTIALLY_SUPPORTED` | Badge vàng |
| `LOW_CONFIDENCE` | Warning badge |
| `UNSUPPORTED` | Warning hoặc debug |
| `NO_CITATION` | Badge “No citation” |
| `CONTRADICTED` | Không hiển thị trong summary chính, hiện debug |
| `NEED_REVIEW` | Badge “Cần xác minh” |

---

## 5. Cache

Để demo ổn định, dùng cache:

```text
data/cache/P001_latest.json
data/cache/P002_latest.json
```

Flow:

```text
Nếu cache tồn tại → load cache
Nếu force_refresh → xóa cache và regenerate
```

---

## 6. Demo script 5–7 phút

1. Giới thiệu bài toán: bác sĩ khó đọc nhiều records.
2. Chọn P001.
3. Run summary.
4. Chỉ ra các section: thuốc, xét nghiệm, chẩn đoán, timeline.
5. Click citation HbA1c.
6. Click citation thuốc.
7. Mở clinical alerts.
8. Chọn P004 để demo edge case.
9. Chỉ ra missing dose/unit/allergy unclear bị flag.
10. Kết luận: pipeline có grounding + citation + verifier.

---

## 7. Không làm trong PoC

- Next.js UI.
- Authentication.
- Database production.
- Real HIS integration.
- Role-based access control.
- PDF export đẹp.
- Kubernetes deployment.

---

## 8. Acceptance criteria

| ID | Tiêu chí |
|---|---|
| UI-AC01 | List được patients |
| UI-AC02 | Generate summary được cho P001–P004 |
| UI-AC03 | Hiển thị đủ sections |
| UI-AC04 | Click citation xem được source |
| UI-AC05 | Hiển thị metrics |
| UI-AC06 | Hiển thị warning cho low-confidence |
| UI-AC07 | Demo chạy ổn định trong 5–7 phút |
