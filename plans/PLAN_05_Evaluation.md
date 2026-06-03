# PLAN 05 — Evaluation (C7)
**Component:** C7 Evaluation Module  
**Tuần chính:** Tuần 5-6  
**Deliverable:** Auto metrics + Human evaluation ≥5 cases + MLflow comparison

---

## 1. Overview

Evaluation gồm 2 lớp song song:
1. **Automatic metrics** — tính từ CitedClaim data (citation coverage, hallucination rate…)
2. **Human evaluation** — rubric 8 tiêu chí, do author/mentor chấm thủ công

Kết quả được log vào MLflow để so sánh giữa các prompt versions.

---

## 2. Automatic Metrics (`src/c7_eval/metrics.py`)

### 2.1 Metric Definitions

```python
METRICS_SPEC = {
    "citation_coverage": {
        "formula": "claims_with_citation / total_claims",
        "description": "% claims có ít nhất 1 source_id SUPPORTED",
        "target_mvp": 0.90,
        "op": ">="
    },
    "citation_accuracy": {
        "formula": "verified_citations / total_citations",
        "description": "% citations thật sự support claim (SUPPORTED vs PARTIAL)",
        "target_mvp": 0.85,
        "op": ">="
    },
    "unsupported_claim_rate": {
        "formula": "unsupported_claims / total_claims",
        "description": "% claims không có source backup",
        "target_mvp": 0.10,
        "op": "<="
    },
    "hallucination_rate": {
        "formula": "contradicted_claims / total_claims",
        "description": "% claims mâu thuẫn với source (CONTRADICTED)",
        "target_mvp": 0.05,
        "op": "<="
    },
    "missing_section_rate": {
        "formula": "empty_sections / total_sections",
        "description": "% sections bị bỏ trống không lý do",
        "target_mvp": 0.05,
        "op": "<="
    },
}

def compute_auto_metrics(summary: FinalSummary) -> dict:
    """
    Compute tất cả metrics từ FinalSummary.
    Gọi sau khi C6 finalize.
    """
    all_claims = []
    empty_sections = 0
    
    for section in summary.sections:
        all_claims.extend(section.cited_claims)
        if section.noi_dung.startswith("Chưa thấy ghi nhận"):
            empty_sections += 1

    total = len(all_claims)
    if total == 0:
        return {"error": "No claims found"}

    supported   = sum(1 for c in all_claims if c.status == "SUPPORTED")
    partial     = sum(1 for c in all_claims if c.status == "PARTIAL")
    unsupported = sum(1 for c in all_claims if c.status in ("UNSUPPORTED", "NO_CITATION"))
    contradicted = sum(1 for c in all_claims if c.status == "CONTRADICTED")

    total_citations = sum(len(c.citations) for c in all_claims)
    verified_citations = sum(
        len(c.citations) for c in all_claims if c.status == "SUPPORTED"
    )

    return {
        "citation_coverage":      round(supported / total, 3),
        "citation_accuracy":      round(verified_citations / max(total_citations, 1), 3),
        "unsupported_claim_rate": round(unsupported / total, 3),
        "hallucination_rate":     round(contradicted / total, 3),
        "missing_section_rate":   round(empty_sections / len(summary.sections), 3),
        "total_claims":           total,
        "supported_claims":       supported,
        "total_citations":        total_citations,
        "latency_seconds":        summary.metrics.get("latency_seconds"),
    }
```

### 2.2 Target Check

```python
def check_all_targets(metrics: dict) -> tuple[bool, dict]:
    """
    Return (all_passed, {metric: passed/failed})
    """
    results = {}
    for metric, spec in METRICS_SPEC.items():
        val = metrics.get(metric)
        if val is None:
            results[metric] = None
            continue
        if spec["op"] == ">=":
            results[metric] = val >= spec["target_mvp"]
        else:
            results[metric] = val <= spec["target_mvp"]
    
    all_passed = all(v for v in results.values() if v is not None)
    return (all_passed, results)
```

---

## 3. Human Evaluation

### 3.1 Evaluation Cases

| Case | Lý do chọn |
|------|-----------|
| BN001 | Golden case — expect điểm cao |
| BN002 | Multi-visit — test longitudinal summary |
| BN005 | ICD-10 mâu thuẫn — test verifier behavior |
| BN010 | XN nguy hiểm — test luu_y section |
| BN014 | 5 visits — test coherence xuyên suốt |

### 3.2 Evaluation Package per Case

```
eval/cases/BN001/
  ├── ehr_source.json          # EHR gốc (để evaluator đối chiếu)
  ├── summary_output.json      # FinalSummary output
  └── summary_rendered.txt     # Bản render dễ đọc
```

### 3.3 Summary Renderer (`src/c7_eval/render_summary.py`)

```python
SECTION_DISPLAY_NAMES = {
    "tong_quan":      "Tổng quan",
    "ly_do_kham":     "Lý do khám",
    "tien_su":        "Tiền sử bệnh",
    "thuoc_hien_tai": "Thuốc đang dùng",
    "di_ung":         "Dị ứng",
    "xn_bat_thuong":  "Xét nghiệm bất thường",
    "chan_doan":      "Chẩn đoán",
    "luu_y":          "⚠️ Điểm cần lưu ý",
}

def render_summary(summary: FinalSummary) -> str:
    lines = [
        "═" * 55,
        f"  TÓM TẮT BỆNH ÁN — {summary.patient_id}",
        f"  Ngày tạo: {summary.ngay_tao[:10]}",
        f"  Model: {summary.model_version} | Prompt: {summary.prompt_version}",
        "═" * 55,
        "",
    ]

    for section in summary.sections:
        name = SECTION_DISPLAY_NAMES.get(section.section_id, section.section_id)
        lines.append(f"▸ {name}")
        lines.append(f"  {section.noi_dung}")
        
        # Citations
        all_ids = []
        for claim in section.cited_claims:
            all_ids.extend(claim.citations)
        if all_ids:
            # Deduplicate, format as [ID]
            unique_ids = list(dict.fromkeys(all_ids))
            lines.append("  " + " ".join(f"[{sid}]" for sid in unique_ids))
        lines.append("")

    # Metrics
    if summary.metrics:
        m = summary.metrics
        lines.append("─" * 55)
        lines.append(f"METRICS: citation_coverage={m.get('citation_coverage', 'N/A'):.0%} | "
                     f"hallucination={m.get('hallucination_rate', 'N/A'):.0%} | "
                     f"latency={m.get('latency_seconds', 'N/A')}s")
        lines.append("═" * 55)

    return "\n".join(lines)
```

### 3.4 Human Evaluation Form (`eval/form_template.json`)

```json
{
  "evaluation_id": "EVAL_BN001_v1",
  "patient_id": "BN001",
  "evaluator": "self | mentor_A",
  "model_version": "claude-sonnet-4-5",
  "prompt_version": "v1",
  "date": "2024-05-15",
  "scores": {
    "correctness": null,
    "completeness": null,
    "conciseness": null,
    "clinical_usefulness": null,
    "citation_accuracy": null,
    "hallucination": null,
    "icd10_correct": null,
    "abbreviation_correct": null,
    "overall": null
  },
  "errors": [],
  "notes": ""
}
```

### 3.5 Rubric Scoring Guide

| Tiêu chí | 5 | 4 | 3 | 2 | 1 |
|----------|---|---|---|---|---|
| **Tính chính xác** | Tất cả thông tin đúng 100% | 1 lỗi nhỏ, không nguy hiểm | 1-2 lỗi minor | Có lỗi significant | Nhiều lỗi hoặc có lỗi nguy hiểm |
| **Tính đầy đủ** | Đủ tất cả thông tin quan trọng | Thiếu 1 item minor | Thiếu vài item | Thiếu thông tin quan trọng | Bỏ sót nhiều |
| **Tính ngắn gọn** | Rất ngắn gọn, không thừa | Ngắn gọn | Tạm được | Hơi dài | Quá dài, lặp lại |
| **Hữu dụng lâm sàng** | Bác sĩ có thể dùng ngay không cần đọc lại | Hữu ích | Oke | Cần bổ sung nhiều | Không hữu ích |
| **Citation chính xác** | Tất cả citations đúng source | 1 citation sai | Vài citation sai | Nhiều citation sai | Không reliable |

**Hallucination:** `true` nếu có BẤT KỲ thông tin nào không có trong EHR source  
**ICD-10 đúng:** `true` nếu tất cả mã ICD-10 trong summary khớp với EHR  
**Viết tắt đúng:** `true` nếu không có viết tắt bị expand sai  

### 3.6 Error Categories

```python
ERROR_TYPES = {
    "wrong_drug_dose":    {"severity": "Critical", "example": "Metformin 500mg → 5000mg"},
    "wrong_lab_value":    {"severity": "Critical", "example": "HbA1c 8.2% → 5.2%"},
    "wrong_icd10":        {"severity": "Critical", "example": "I10 → I50"},
    "hallucination":      {"severity": "Critical", "example": "Ghi BN dị ứng Aspirin khi source không có"},
    "missing_allergy":    {"severity": "Critical", "example": "Có dị ứng Penicillin nhưng summary không ghi"},
    "wrong_abbrev":       {"severity": "Major",    "example": "THA → 'thoát vị ổ bụng'"},
    "wrong_citation":     {"severity": "Major",    "example": "Citation trỏ về XN nhưng nội dung là ghi chú BS"},
    "unsupported_claim":  {"severity": "Major",    "example": "Suy diễn không có nguồn"},
    "missing_citation":   {"severity": "Minor",    "example": "Claim đúng nhưng không gắn citation"},
    "summary_too_long":   {"severity": "Minor",    "example": "Lặp lại thông tin"},
}
```

---

## 4. Evaluation Data Schema

```python
# src/c7_eval/schemas.py

class ErrorEntry(BaseModel):
    type: str           # Từ ERROR_TYPES keys
    claim: str          # Câu bị lỗi
    severity: str       # "Critical" | "Major" | "Minor"
    note: str = ""

class HumanEvaluation(BaseModel):
    evaluation_id: str
    patient_id: str
    evaluator: str
    model_version: str
    prompt_version: str
    date: str
    scores: dict = {
        "correctness": None,
        "completeness": None,
        "conciseness": None,
        "clinical_usefulness": None,
        "citation_accuracy": None,
        "hallucination": None,      # bool
        "icd10_correct": None,      # bool
        "abbreviation_correct": None,  # bool
        "overall": None
    }
    errors: list[ErrorEntry] = []
    notes: str = ""

    @property
    def avg_numeric_score(self) -> float:
        numeric = [v for k, v in self.scores.items()
                   if isinstance(v, (int, float)) and v is not None
                   and k not in ("hallucination", "icd10_correct", "abbreviation_correct")]
        return sum(numeric) / len(numeric) if numeric else 0.0
```

---

## 5. Evaluation Analysis Notebook

`notebooks/05_evaluation_analysis.ipynb`:

```python
# 1. Load tất cả human eval results
import json, glob
results = [json.load(open(f)) for f in glob.glob("eval/results/EVAL_*.json")]

# 2. Tổng hợp scores
import pandas as pd
df = pd.DataFrame([{
    "patient_id": r["patient_id"],
    "prompt_version": r["prompt_version"],
    "correctness": r["scores"]["correctness"],
    "completeness": r["scores"]["completeness"],
    "clinical_usefulness": r["scores"]["clinical_usefulness"],
    "citation_accuracy": r["scores"]["citation_accuracy"],
    "overall": r["scores"]["overall"],
    "hallucination": r["scores"]["hallucination"],
    "error_count": len(r["errors"])
} for r in results])

print(df.describe())
print("\nError distribution:")
all_errors = [e for r in results for e in r["errors"]]
error_df = pd.DataFrame(all_errors)
print(error_df["severity"].value_counts())

# 3. So sánh prompt versions trên MLflow
import mlflow
client = mlflow.tracking.MlflowClient()
runs = client.search_runs(
    experiment_ids=["1"],
    order_by=["metrics.citation_coverage DESC"]
)
for run in runs[:10]:
    print(run.data.params, run.data.metrics)

# 4. Identify top issues
critical_errors = [e for e in all_errors if e["severity"] == "Critical"]
print(f"\nCritical errors: {len(critical_errors)}")
```

---

## 6. Tests

```python
# tests/test_c7_eval.py

class TestAutoMetrics:
    def test_citation_coverage_calculation(self, sample_summary):
        metrics = compute_auto_metrics(sample_summary)
        assert 0 <= metrics["citation_coverage"] <= 1

    def test_hallucination_rate_is_zero_for_clean_summary(self, clean_summary):
        metrics = compute_auto_metrics(clean_summary)
        assert metrics["hallucination_rate"] == 0.0

    def test_missing_section_rate(self, summary_with_empty_sections):
        metrics = compute_auto_metrics(summary_with_empty_sections)
        assert metrics["missing_section_rate"] > 0

    def test_targets_passed_for_golden_case(self, bn001_final_summary):
        metrics = compute_auto_metrics(bn001_final_summary)
        all_passed, results = check_all_targets(metrics)
        # Log failures for debugging
        failed = {k: v for k, v in results.items() if not v}
        assert all_passed, f"Failed targets: {failed}"

class TestRenderer:
    def test_render_includes_all_sections(self, sample_summary):
        rendered = render_summary(sample_summary)
        for section_id in SECTION_DISPLAY_NAMES:
            assert SECTION_DISPLAY_NAMES[section_id] in rendered

    def test_render_includes_metrics(self, sample_summary):
        rendered = render_summary(sample_summary)
        assert "METRICS:" in rendered
        assert "citation_coverage" in rendered
```
