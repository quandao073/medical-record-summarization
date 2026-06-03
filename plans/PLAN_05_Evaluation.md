# PLAN 05 — Evaluation (C7)

**Component:** C7 Evaluation Module  
**Interface:** `FinalSummary` + source dataset → automatic metrics + human review package  
**Cập nhật cho:** bộ PoC dataset 4 bệnh nhân đã chuẩn hóa

---

## 1. Mục tiêu

Evaluation đánh giá hệ thống ở 2 lớp:

1. **Automatic metrics:** tính từ `FinalSummary`, `CitedClaim`, `SourceChunk`.
2. **Human evaluation:** chấm thủ công theo rubric lâm sàng.

Với PoC, evaluation không cần quá phức tạp nhưng phải chứng minh được pipeline có kiểm soát factuality và citation.

---

## 2. Automatic metrics

### 2.1 Metrics cần có

| Metric | Công thức | Target PoC |
|---|---|---:|
| `citation_coverage` | claims có citation / total claims | ≥ 0.80 |
| `citation_accuracy` | supported citations / total citations | ≥ 0.80 |
| `unsupported_claim_rate` | unsupported claims / total claims | ≤ 0.15 |
| `hallucination_rate` | contradicted claims / total claims | ≤ 0.05 |
| `missing_section_rate` | empty sections / total sections | ≤ 0.10 |
| `critical_claim_coverage` | critical claims có citation / critical claims | ≥ 0.85 |
| `latency_seconds` | thời gian chạy / patient | ghi nhận, chưa cần tối ưu |

### 2.2 Function gợi ý

```python
def compute_auto_metrics(summary: FinalSummary) -> dict:
    all_claims = []
    empty_sections = 0

    for section in summary.sections:
        all_claims.extend(section.cited_claims)
        if not section.content or section.content.startswith("Chưa thấy ghi nhận"):
            empty_sections += 1

    total = len(all_claims)
    if total == 0:
        return {"error": "No claims found"}

    supported = sum(c.status == "SUPPORTED" for c in all_claims)
    unsupported = sum(c.status in ["UNSUPPORTED", "NO_CITATION"] for c in all_claims)
    contradicted = sum(c.status == "CONTRADICTED" for c in all_claims)

    return {
        "citation_coverage": supported / total,
        "unsupported_claim_rate": unsupported / total,
        "hallucination_rate": contradicted / total,
        "missing_section_rate": empty_sections / len(summary.sections),
        "total_claims": total
    }
```

---

## 3. Human evaluation

### 3.1 Cases nên chấm

| Patient | Lý do |
|---|---|
| P001 | Happy path phức tạp, nhiều visits, trend rõ |
| P002 | Case ổn định, ít edge case |
| P003 | Nhiều bệnh nền/longitudinal |
| P004 | Edge cases: missing dose, missing unit, allergy unclear, ICD mismatch |

### 3.2 Rubric

| Tiêu chí | Mô tả | Điểm |
|---|---|---|
| Clinical relevance | Summary có đúng nội dung bác sĩ cần không | 1–5 |
| Factual correctness | Có đúng với source không | 1–5 |
| Citation correctness | Citation có trỏ đúng source không | 1–5 |
| Completeness | Có bỏ sót thông tin quan trọng không | 1–5 |
| Conciseness | Có ngắn gọn, dễ đọc không | 1–5 |
| Vietnamese fluency | Tiếng Việt y khoa có tự nhiên không | 1–5 |
| Safety | Có claim nguy hiểm/hallucination không | 1–5 |
| Usefulness | Có hữu ích cho bác sĩ trước khám không | 1–5 |

---

## 4. Evaluation package

Mỗi patient nên có folder:

```text
eval/cases/P001/
├── ehr_source.json
├── source_chunks.json
├── summary_output.json
├── summary_rendered.md
├── metrics.json
└── human_eval_form.json
```

---

## 5. Render summary

Summary render để mentor/evaluator đọc nhanh:

```text
TÓM TẮT BỆNH ÁN — P001

## Tổng quan bệnh nhân
...

## Thuốc hiện tại
...
Citation: [P001-E004-MED-METFORMIN]

## Xét nghiệm bất thường
...
Citation: [P001-E004-LAB-HBA1C]
```

---

## 6. Error analysis

Sau evaluation cần ghi nhận:

| Error type | Ví dụ | Hành động |
|---|---|---|
| Missing evidence | Claim đúng nhưng không citation | cải thiện retrieval |
| Wrong citation | Citation trỏ sai source | sửa matcher |
| Over-summary | Summary quá chung | sửa prompt |
| Hallucination | Thêm thông tin không có source | tăng guardrail |
| Missing section | Section rỗng | kiểm retrieval policy |
| Low Vietnamese quality | Câu không tự nhiên | sửa prompt/template |

---

## 7. Acceptance criteria

| ID | Tiêu chí |
|---|---|
| C7-AC01 | Tính được auto metrics cho mọi patient |
| C7-AC02 | Tạo evaluation package cho P001–P004 |
| C7-AC03 | Có human eval form |
| C7-AC04 | Có error analysis |
| C7-AC05 | Có report tổng hợp cuối tuần 4 |
| C7-AC06 | Metrics được hiển thị trên UI |
