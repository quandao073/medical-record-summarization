# PLAN 03 — Citation Pipeline (C5)

**Component:** C5 Citation Builder  
**Interface:** `SummarySection` + `list[SourceChunk]` → `list[CitedClaim]`  
**Cập nhật cho:** `SourceChunk.content`, `source_type` tiếng Anh, claim status taxonomy chuẩn

---

## 1. Mục tiêu

Citation Pipeline có nhiệm vụ biến draft summary thành các claim có thể kiểm chứng.

Luồng:

```text
SummarySection.content
→ claim extraction
→ candidate evidence retrieval
→ evidence matching
→ citation attachment
→ CitedClaim[]
```

---

## 2. Atomic claim

Atomic claim là một fact độc lập có thể verify riêng.

Ví dụ input:

```text
Bệnh nhân đang dùng Metformin 1000 mg 1 viên 2 lần/ngày và Empagliflozin 10 mg 1 viên buổi sáng.
```

Tách đúng:

```json
[
  {
    "claim_text": "Bệnh nhân đang dùng Metformin 1000 mg, 1 viên, 2 lần/ngày.",
    "is_critical": true
  },
  {
    "claim_text": "Bệnh nhân đang dùng Empagliflozin 10 mg, 1 viên buổi sáng.",
    "is_critical": true
  }
]
```

Không nên để một claim chứa nhiều thuốc hoặc nhiều facts.

---

## 3. Critical claim classification

`is_critical = true` nếu claim liên quan đến:

- Thuốc + liều/cách dùng.
- Kết quả xét nghiệm có số và đơn vị.
- Chẩn đoán hoặc ICD-10.
- Dị ứng.
- Sinh hiệu bất thường.
- Biến chứng quan trọng.

`is_critical = false` nếu claim chỉ là mô tả chung như tuổi, nghề nghiệp, tình trạng ổn định không có số liệu critical.

---

## 4. Claim statuses

```text
SUPPORTED
PARTIALLY_SUPPORTED
LOW_CONFIDENCE
UNSUPPORTED
NO_CITATION
CONTRADICTED
NEED_REVIEW
```

Ý nghĩa:

| Status | Ý nghĩa |
|---|---|
| `SUPPORTED` | Source hỗ trợ rõ claim |
| `PARTIALLY_SUPPORTED` | Source chỉ hỗ trợ một phần |
| `LOW_CONFIDENCE` | Có liên quan nhưng matching yếu hoặc thiếu metadata |
| `UNSUPPORTED` | Không tìm thấy source đủ hỗ trợ |
| `NO_CITATION` | Claim không có source_id |
| `CONTRADICTED` | Source nói ngược lại claim |
| `NEED_REVIEW` | Cần bác sĩ/evaluator kiểm tra |

---

## 5. Candidate filtering

Không nên match claim với toàn bộ chunks. Cần filter theo section/source_type.

```python
TYPE_FILTER = {
    "current_medications": ["medication"],
    "abnormal_labs": ["lab_result"],
    "diagnoses": ["diagnosis"],
    "allergies": ["allergy", "clinical_note"],
    "vitals": ["vital"],
}
```

Sau đó dùng:

```text
exact metadata match
→ keyword match
→ vector similarity
→ LLM/NLI nếu cần
```

---

## 6. Evidence matching

Một claim được coi là supported khi:

- Source có cùng patient.
- Source có thông tin tương ứng.
- Giá trị số khớp nếu là lab/vital.
- Tên thuốc, hàm lượng, liều khớp nếu là medication.
- ICD-10/tên bệnh khớp nếu là diagnosis.
- Dị ứng/substance/reaction khớp nếu là allergy.

Ví dụ rule cho lab:

```python
def match_lab_claim(claim, chunk):
    if chunk.source_type != "lab_result":
        return "UNSUPPORTED"
    if exact_value_and_unit_in_claim(claim, chunk.metadata):
        return "SUPPORTED"
    if test_name_in_claim(claim, chunk.metadata):
        return "PARTIALLY_SUPPORTED"
    return "UNSUPPORTED"
```

---

## 7. Citation attachment

Output cuối:

```json
{
  "claim_text": "HbA1c 9.2%, cao hơn khoảng tham chiếu.",
  "status": "SUPPORTED",
  "citations": ["P001-E001-LAB-HBA1C"],
  "confidence_score": 0.95,
  "is_critical": true,
  "verification_status": "PENDING"
}
```

---

## 8. Edge cases cần test

| Case | Expected behavior |
|---|---|
| Medication thiếu dose | `LOW_CONFIDENCE` hoặc `NEED_REVIEW` |
| Lab thiếu unit | `PARTIALLY_SUPPORTED` hoặc `LOW_CONFIDENCE` |
| Allergy thiếu reaction | `SUPPORTED` cho substance, `NEED_REVIEW` cho reaction/severity |
| ICD mismatch | `CONTRADICTED` hoặc `NEED_REVIEW` |
| Claim không có source | `NO_CITATION` |
| Claim critical không source | C6 remove hoặc flag mạnh |

---

## 9. Acceptance criteria

| ID | Tiêu chí |
|---|---|
| C5-AC01 | Extract được atomic claims |
| C5-AC02 | Phân loại được critical claims |
| C5-AC03 | Attach được citation source_id |
| C5-AC04 | Match đúng medication/lab/diagnosis claims |
| C5-AC05 | Edge cases bị flag đúng |
| C5-AC06 | Không tạo source_id mới |
| C5-AC07 | Citation coverage critical claims ≥ 85% cho PoC |
