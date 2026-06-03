# PLAN 04 — Hallucination Mitigation (C6)

**Component:** C6 Hallucination Verifier  
**Interface:** `dict[section_id, list[CitedClaim]]` → `FinalSummary`  
**Cập nhật cho:** taxonomy claim status chuẩn và `SummarySection.content`

---

## 1. Mục tiêu

C6 là lớp kiểm soát cuối cùng trước khi trả summary cho UI. Nhiệm vụ là quyết định mỗi claim sẽ được:

```text
KEEP
FLAG
REMOVE
```

Mục tiêu chính không phải “làm summary hay hơn”, mà là giảm rủi ro clinical hallucination.

---

## 2. Decision matrix

| Claim status | Critical? | Action | Lý do |
|---|---:|---|---|
| `SUPPORTED` | any | KEEP | Có evidence rõ |
| `PARTIALLY_SUPPORTED` | false | FLAG | Có source nhưng thiếu một phần |
| `PARTIALLY_SUPPORTED` | true | FLAG | Critical claim cần bác sĩ review |
| `LOW_CONFIDENCE` | any | FLAG | Matching yếu hoặc thiếu metadata |
| `UNSUPPORTED` | false | FLAG | Không nguy hiểm nhưng cần cảnh báo |
| `UNSUPPORTED` | true | REMOVE | Critical claim không source |
| `NO_CITATION` | false | FLAG | Không trace được source |
| `NO_CITATION` | true | REMOVE | Critical + không citation |
| `CONTRADICTED` | any | REMOVE | Source mâu thuẫn claim |
| `NEED_REVIEW` | any | FLAG | Cần bác sĩ kiểm tra |

---

## 3. Business rules

### BR-01: Không giữ critical claim không có evidence

```text
Nếu is_critical = true và status ∈ [UNSUPPORTED, NO_CITATION]
→ REMOVE
```

### BR-02: Claim bị mâu thuẫn luôn bị loại

```text
Nếu status = CONTRADICTED
→ REMOVE
```

### BR-03: Low-confidence phải hiển thị cảnh báo

```text
Nếu status = LOW_CONFIDENCE hoặc NEED_REVIEW
→ FLAG + hiển thị "Cần xác minh"
```

### BR-04: Allergy section không được mất dấu

Nếu không có dị ứng:

```text
Chưa thấy ghi nhận dị ứng trong dữ liệu được cung cấp.
```

Nếu có dị ứng thiếu reaction/severity:

```text
Dị ứng [substance] đã được ghi nhận, nhưng chưa rõ phản ứng hoặc mức độ. Cần xác nhận thêm.
```

### BR-05: Không tự sửa ICD-10

Nếu diagnosis text và ICD-10 không khớp:

```text
Không tự sửa.
Flag NEED_REVIEW hoặc CONTRADICTED.
```

### BR-06: Không khuyến nghị điều trị mới

Nếu LLM sinh ra khuyến nghị không có trong source:

```text
REMOVE hoặc FLAG tùy criticality.
```

---

## 4. FinalSummary reconstruction

Verifier tái dựng lại final summary từ kept/flagged claims.

```json
{
  "patient_id": "P001",
  "created_at": "2026-06-03T10:00:00+07:00",
  "prompt_version": "poc_v1",
  "model_version": "selected_model",
  "sections": [
    {
      "section_id": "abnormal_labs",
      "title": "Xét nghiệm bất thường",
      "content": "HbA1c 9.2%, cao hơn khoảng tham chiếu.",
      "cited_claims": []
    }
  ],
  "metrics": {}
}
```

---

## 5. Metrics

C6 tính các metrics cơ bản:

```text
citation_coverage
unsupported_claim_rate
hallucination_rate
missing_section_rate
total_claims
supported_claims
flagged_claims
removed_claims
```

Công thức gợi ý:

```text
citation_coverage = supported_claims / total_claims
unsupported_claim_rate = unsupported_or_no_citation_claims / total_claims
hallucination_rate = contradicted_claims / total_claims
missing_section_rate = empty_sections / total_sections
```

---

## 6. UI behavior

| Claim action | UI |
|---|---|
| KEEP | Hiển thị bình thường |
| FLAG | Hiển thị warning badge |
| REMOVE | Không hiển thị trong summary chính, có thể ghi trong debug panel |
| NEED_REVIEW | Hiển thị “Cần bác sĩ xác minh” |
| LOW_CONFIDENCE | Hiển thị “Độ tin cậy thấp” |

---

## 7. Acceptance criteria

| ID | Tiêu chí |
|---|---|
| C6-AC01 | Critical unsupported claim bị remove |
| C6-AC02 | Contradicted claim bị remove |
| C6-AC03 | Low-confidence claim bị flag |
| C6-AC04 | Allergy missing info được flag đúng |
| C6-AC05 | Tính được auto metrics |
| C6-AC06 | FinalSummary dùng field tiếng Anh chuẩn |
| C6-AC07 | UI có thể phân biệt KEEP/FLAG/REMOVE |
