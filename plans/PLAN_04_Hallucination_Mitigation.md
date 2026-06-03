# PLAN 04 — Hallucination Mitigation (C6)
**Component:** C6 Hallucination Verifier  
**Tuần chính:** Tuần 4 (cùng với C5)  
**Interface:** `{section_id: List[CitedClaim]}` → `FinalSummary`

---

## 1. Overview

C6 là bước cuối của pipeline. Nó áp dụng business rules để quyết định:
- **KEEP:** Đưa claim vào final summary
- **FLAG:** Đưa vào nhưng gắn cảnh báo `⚠️ Chưa xác minh`
- **REMOVE:** Loại khỏi final summary

Sau khi xử lý, C6 tổng hợp text lại, tính auto metrics, và build `FinalSummary`.

---

## 2. Business Rules (`src/c6_verifier/business_rules.py`)

### 2.1 Decision Matrix

| Claim Status | is_critical | Action | Lý do |
|-------------|-------------|--------|-------|
| SUPPORTED | True/False | KEEP | Evidence đầy đủ |
| PARTIAL | False | FLAG | Thiếu một phần evidence, nhưng không nguy hiểm |
| PARTIAL | True | FLAG | Giữ lại với cảnh báo rõ ràng — bác sĩ cần verify |
| UNSUPPORTED | False | FLAG | Không có source nhưng không nguy hiểm |
| UNSUPPORTED | True | REMOVE | BR-07: thuốc/liều/XN/chẩn đoán không có source → loại |
| CONTRADICTED | True/False | REMOVE | Source nói ngược lại — nguy hiểm khi để lại |
| NO_CITATION | False | FLAG | Không tìm được source_id — giữ với cảnh báo |
| NO_CITATION | True | REMOVE | Critical + không trace được → loại |

```python
from src.schemas import CitedClaim

def decide_action(claim: CitedClaim, section_id: str) -> tuple[str, str]:
    """
    Return (action, reason)
    action: "KEEP" | "REMOVE" | "FLAG"
    """
    status = claim.status
    critical = claim.is_critical

    # CONTRADICTED luôn REMOVE — bất kể critical
    if status == "CONTRADICTED":
        return ("REMOVE", "Source contradicts this claim")

    # Critical + không có evidence → REMOVE
    if critical and status in ("UNSUPPORTED", "NO_CITATION"):
        return ("REMOVE", f"Critical claim with no evidence: {status}")

    # Có evidence đầy đủ → KEEP
    if status == "SUPPORTED":
        return ("KEEP", "Fully supported by evidence")

    # Mọi trường hợp còn lại → FLAG
    return ("FLAG", f"Needs verification: {status}")
```

### 2.2 Special Rules

```python
# BR-04: Allergy section không được trống
def ensure_allergy_section(
    section_id: str,
    kept_claims: list[CitedClaim],
    text_parts: list[str]
) -> list[str]:
    """
    Nếu section_id == "di_ung" và không có claim nào được KEEP/FLAG,
    inject default text để bác sĩ biết đây không phải bị bỏ sót.
    """
    if section_id == "di_ung" and not kept_claims:
        return ["Chưa thấy ghi nhận dị ứng trong dữ liệu được cung cấp."]
    return text_parts

# BR-05: Mã ICD-10 không tự sửa
# Đã được enforce trong C4 prompt → không cần thêm rule ở C6

# BR-09: Không tự đưa khuyến nghị điều trị
# Đã được enforce trong C4 prompt → không cần thêm rule ở C6
```

---

## 3. Verifier Implementation (`src/c6_verifier/verifier.py`)

```python
from src.schemas import CitedClaim, SummarySection, FinalSummary
from src.c6_verifier.business_rules import decide_action, ensure_allergy_section
from datetime import datetime

FLAG_SUFFIX = " [⚠️ Chưa xác minh]"
REMOVE_PLACEHOLDER = None  # Claim bị loại → không xuất hiện

class HallucinationVerifier:
    def __init__(self, config: dict):
        self.config = config

    def verify_section(
        self,
        section_id: str,
        claims: list[CitedClaim]
    ) -> tuple[list[CitedClaim], str]:
        """
        Apply business rules per claim.
        Return: (kept_claims, reconstructed_text)
        """
        kept_claims = []
        text_parts = []
        removed_count = 0

        for claim in claims:
            action, reason = decide_action(claim, section_id)

            if action == "KEEP":
                kept_claims.append(claim)
                text_parts.append(claim.claim_text)

            elif action == "FLAG":
                flagged_claim = claim.copy()
                flagged_claim.claim_text += FLAG_SUFFIX
                kept_claims.append(flagged_claim)
                text_parts.append(flagged_claim.claim_text)

            elif action == "REMOVE":
                removed_count += 1
                # Không thêm vào kept_claims hay text_parts

        # BR-04: Allergy section không được trống
        text_parts = ensure_allergy_section(section_id, kept_claims, text_parts)

        reconstructed = " ".join(text_parts) if text_parts else \
                        "Chưa thấy ghi nhận trong dữ liệu được cung cấp."

        return kept_claims, reconstructed, removed_count

    def verify_and_finalize(
        self,
        patient_id: str,
        cited_sections: dict[str, list[CitedClaim]],
        prompt_version: str,
        model_version: str
    ) -> FinalSummary:
        final_sections = []
        all_claims = []
        total_removed = 0

        for section_id, claims in cited_sections.items():
            kept, text, removed = self.verify_section(section_id, claims)

            final_sections.append(SummarySection(
                section_id=section_id,
                noi_dung=text,
                cited_claims=kept
            ))

            all_claims.extend(claims)  # All claims including removed — for metrics
            total_removed += removed

        metrics = self._compute_metrics(all_claims)
        metrics["removed_claims"] = total_removed

        return FinalSummary(
            patient_id=patient_id,
            ngay_tao=datetime.now().isoformat(),
            prompt_version=prompt_version,
            model_version=model_version,
            sections=final_sections,
            metrics=metrics
        )

    def _compute_metrics(self, all_claims: list[CitedClaim]) -> dict:
        total = len(all_claims)
        if total == 0:
            return {}

        supported  = sum(1 for c in all_claims if c.status == "SUPPORTED")
        partial    = sum(1 for c in all_claims if c.status == "PARTIAL")
        removed    = sum(1 for c in all_claims
                        if c.is_critical and c.status in ("UNSUPPORTED", "NO_CITATION", "CONTRADICTED"))
        flagged    = sum(1 for c in all_claims
                        if not c.is_critical and c.status in ("UNSUPPORTED", "NO_CITATION", "PARTIAL"))
        hallucinated = sum(1 for c in all_claims if c.status == "CONTRADICTED")

        return {
            "citation_coverage":      round(supported / total, 3),       # Target ≥ 0.90
            "citation_accuracy":      round(supported / (supported + partial + flagged + 1e-9), 3),
            "hallucination_rate":     round(hallucinated / total, 3),    # Target ≤ 0.05
            "unsupported_claim_rate": round((removed + flagged) / total, 3),  # Target ≤ 0.10
            "total_claims":           total,
            "supported_claims":       supported,
        }
```

---

## 4. Prompt-Level Guardrails

Ngoài post-generation verification ở C6, guardrails được baked vào C4 prompts:

### 4.1 Constraint Injection trong System Prompt

```
NGUYÊN TẮC BẮT BUỘC:
1. CHỈ dùng thông tin có trong [DỮ LIỆU BỆNH ÁN]
2. Nếu không có thông tin: ghi "Chưa thấy ghi nhận..."
3. KHÔNG kê đơn, KHÔNG chẩn đoán thêm
4. Giữ NGUYÊN mã ICD-10, tên thuốc, giá trị số
```

### 4.2 Evidence-First Format

Format "**[source_id]** noi_dung" trong context khiến LLM:
- Thấy rõ mỗi fact đến từ đâu
- Có xu hướng bám sát source hơn
- C5 có thể extract citation dễ hơn

### 4.3 Per-Section Constraints

| Section | Constraint thêm |
|---------|----------------|
| `chan_doan` | "Dùng đúng mã ICD-10 từ dữ liệu — không tự chỉnh sửa" |
| `thuoc_hien_tai` | "Nếu thiếu liều → ghi (thiếu thông tin liều)" |
| `xn_bat_thuong` | "Chỉ liệt kê kết quả nằm NGOÀI khoảng tham chiếu" |
| `luu_y` | "KHÔNG gợi ý điều trị hay thay đổi thuốc" |

---

## 5. Metrics Computation

### 5.1 Auto Metrics

```python
METRIC_TARGETS = {
    "citation_coverage":      (">=", 0.90),   # ≥ 90%
    "citation_accuracy":      (">=", 0.85),   # ≥ 85%
    "hallucination_rate":     ("<=", 0.05),   # ≤ 5%
    "unsupported_claim_rate": ("<=", 0.10),   # ≤ 10%
}

def check_targets(metrics: dict) -> dict[str, bool]:
    """Return dict: metric → passed/failed"""
    results = {}
    for metric, (op, target) in METRIC_TARGETS.items():
        val = metrics.get(metric, 0)
        if op == ">=":
            results[metric] = val >= target
        else:
            results[metric] = val <= target
    return results
```

### 5.2 Per-Patient Metrics Log

```json
{
  "patient_id": "BN001",
  "run_id": "run_20240501_001",
  "prompt_version": "v1",
  "model_version": "claude-sonnet-4-5",
  "metrics": {
    "citation_coverage": 0.92,
    "citation_accuracy": 0.88,
    "hallucination_rate": 0.02,
    "unsupported_claim_rate": 0.08,
    "total_claims": 24,
    "supported_claims": 22,
    "removed_claims": 1,
    "latency_seconds": 24.3
  },
  "targets_passed": {
    "citation_coverage": true,
    "citation_accuracy": true,
    "hallucination_rate": true,
    "unsupported_claim_rate": true
  }
}
```

---

## 6. MLflow Tracking (`src/c7_eval/mlflow_logger.py`)

```python
import mlflow

class MLflowLogger:
    def __init__(self, config: dict):
        mlflow.set_tracking_uri(config["mlflow"]["tracking_uri"])
        mlflow.set_experiment(config["mlflow"]["experiment_name"])

    def log_run(self, patient_id: str, summary: FinalSummary):
        with mlflow.start_run():
            # Params (cho reproducibility)
            mlflow.log_params({
                "patient_id": patient_id,
                "prompt_version": summary.prompt_version,
                "model_version": summary.model_version,
            })

            # Metrics
            if summary.metrics:
                mlflow.log_metrics(summary.metrics)

            # Artifact: full summary JSON
            import tempfile, json, os
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, encoding="utf-8"
            ) as f:
                json.dump(summary.dict(), f, ensure_ascii=False, indent=2)
                tmp_path = f.name
            mlflow.log_artifact(tmp_path, "summaries")
            os.unlink(tmp_path)

    def compare_runs(self, run_ids: list[str]) -> dict:
        """Load runs từ MLflow và compare metrics"""
        client = mlflow.tracking.MlflowClient()
        comparison = {}
        for run_id in run_ids:
            run = client.get_run(run_id)
            comparison[run_id] = run.data.metrics
        return comparison
```

---

## 7. Tests

```python
# tests/test_c6_verifier.py

class TestBusinessRules:
    def test_contradicted_always_removed(self):
        claim = CitedClaim(
            claim_text="Creatinine bình thường",
            status="CONTRADICTED",
            citations=[],
            is_critical=True
        )
        action, _ = decide_action(claim, "xn_bat_thuong")
        assert action == "REMOVE"

    def test_critical_unsupported_removed(self):
        claim = CitedClaim(
            claim_text="HbA1c 9.2%",
            status="UNSUPPORTED",
            citations=[],
            is_critical=True
        )
        action, _ = decide_action(claim, "xn_bat_thuong")
        assert action == "REMOVE"

    def test_noncritical_unsupported_flagged_not_removed(self):
        claim = CitedClaim(
            claim_text="Thể trạng thừa cân",
            status="UNSUPPORTED",
            citations=[],
            is_critical=False
        )
        action, _ = decide_action(claim, "tong_quan")
        assert action == "FLAG"

    def test_supported_critical_kept(self):
        claim = CitedClaim(
            claim_text="Metformin 1000mg, 2 viên/ngày",
            status="SUPPORTED",
            citations=["BN001_LK001_THUOC_T001"],
            is_critical=True
        )
        action, _ = decide_action(claim, "thuoc_hien_tai")
        assert action == "KEEP"

class TestVerifier:
    def test_allergy_section_never_silently_empty(self, verifier):
        empty_claims = []
        kept, text, _ = verifier.verify_section("di_ung", empty_claims)
        assert "Chưa thấy ghi nhận dị ứng" in text

    def test_removed_claims_not_in_final_text(self, verifier):
        claims = [
            CitedClaim(
                claim_text="Secret hallucinated drug",
                status="UNSUPPORTED",
                citations=[],
                is_critical=True  # → REMOVE
            )
        ]
        _, text, removed = verifier.verify_section("thuoc_hien_tai", claims)
        assert "Secret hallucinated drug" not in text
        assert removed == 1

    def test_flagged_claims_have_warning_suffix(self, verifier):
        claims = [
            CitedClaim(
                claim_text="Bệnh nhân có biến chứng thận",
                status="PARTIAL",
                citations=["some_id"],
                is_critical=False
            )
        ]
        _, text, _ = verifier.verify_section("luu_y", claims)
        assert "⚠️ Chưa xác minh" in text

    def test_metrics_sum_consistently(self, verifier, sample_claims):
        metrics = verifier._compute_metrics(sample_claims)
        total = metrics["total_claims"]
        assert total == len(sample_claims)
        assert metrics["citation_coverage"] <= 1.0
        assert metrics["hallucination_rate"] <= 1.0

    def test_final_summary_is_serializable(self, verifier, sample_cited_sections):
        summary = verifier.verify_and_finalize(
            "BN001", sample_cited_sections, "v1", "claude-sonnet-4-5"
        )
        import json
        # Should not raise
        json.dumps(summary.dict(), ensure_ascii=False)
```
