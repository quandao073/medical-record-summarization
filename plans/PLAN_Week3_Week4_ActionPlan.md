# Kế hoạch hành động — Tuần 3 & 4
**Medical Record Summarization — Citation Pipeline + Demo**
**Tác giả:** Đào Anh Quân | **Ngày tạo:** 2026-06-03 | **Cập nhật lần cuối:** 2026-06-04

---

## 0. Cập nhật rà soát — 2026-06-04 (Tuần 3, Ngày 1)

### Bugs đã fix
| Bug | File | Mô tả | Trạng thái |
|---|---|---|---|
| Section ID sai | `poc/dry_run.py:50` | `"thuoc_hien_tai"` → `"current_medications"` | ✅ Fixed |
| API key không khớp | `poc/dry_run.py` footer | Footer ghi `ANTHROPIC_API_KEY` nhưng pipeline dùng OpenAI | ✅ Fixed |

### Điểm cần lưu ý phát hiện qua rà soát
- Citation logic hiện tại quá thô: toàn bộ content 1 section = 1 `CitedClaim` (không phải atomic claims). Sẽ được xử lý đúng tại C5.
- `week2_status.py` check cứng `sections == 8` — cần cập nhật thành `sections == 9` sau khi thêm `treatment_timeline`.

### Tiến độ Tuần 3 (cập nhật 2026-06-04)
| Task | Trạng thái |
|---|---|
| C3 Section-wise Retrieval | ❌ Chưa bắt đầu |
| Section `treatment_timeline` (9th) | ❌ Chưa bắt đầu |
| C5 Claim Extractor | ❌ Chưa bắt đầu |
| C5 Evidence Matcher | ❌ Chưa bắt đầu |
| C6 Verifier | ❌ Chưa bắt đầu |
| Migrate OpenAI → Claude API | ❌ Chưa bắt đầu |
| Tests C3/C5/C6 | ❌ Chưa bắt đầu |

---

## 1. Trạng thái cuối Tuần 2

### Đã hoàn thành (23/23 ✅)

| Component | File | Trạng thái |
|---|---|---|
| Raw dataset chuẩn hóa | `data/raw/*.json` (10 files) | ✅ |
| Assembler | `src/c1_emr/assembler.py` | ✅ |
| C1: Validator | `src/c1_emr/validator.py` | ✅ |
| C1: De-identifier | `src/c1_emr/deidentifier.py` | ✅ |
| C1: Normalizer | `src/c1_emr/normalizer.py` | ✅ |
| C2: Chunker | `src/c2_chunking/chunker.py` | ✅ 83 chunks / P001 |
| C2: Store Builder | `src/c2_chunking/store_builder.py` | ✅ |
| PoC Pipeline (OpenAI) | `poc/poc_pipeline.py` | ✅ 8 sections, 29.7s |
| 44 unit tests | `tests/` | ✅ |
| Cấu trúc thư mục | `data/raw/`, `data/processed/`, `data/dictionaries/`, `data/seeds/` | ✅ |

### Gap so với spec đầy đủ

| Gap | Mô tả | Priority |
|---|---|---|
| Section `treatment_timeline` | PoC có 8 section, spec yêu cầu 9 | HIGH |
| Section-wise retrieval | PoC dump toàn bộ chunks vào context, không filter theo section | HIGH |
| Claim extraction (C5) | Chưa tách atomic claims từ summary text | HIGH |
| Citation matching (C5) | Citation hiện tại chỉ check source_id tồn tại, không verify nội dung | HIGH |
| Hallucination verifier (C6) | Chưa có KEEP/FLAG/REMOVE logic | HIGH |
| Chuyển từ OpenAI → Claude | `poc_pipeline.py` dùng OpenAI SDK | MEDIUM |
| FastAPI + Streamlit | Chưa có | MEDIUM |
| Evaluation framework | Chưa có auto metrics end-to-end | MEDIUM |

---

## 2. Mục tiêu Tuần 3 — Citation & Hallucination Mitigation

**Deadline:** Cuối tuần 3  
**Tiêu chí thành công:** Critical claims có citation ≥ 85%, unsupported critical claims bị remove

### 2.1 Section-wise Retrieval (C3)

**File mới:** `src/c3_retrieval/retriever.py`

Mỗi section chỉ nhận chunks phù hợp, thay vì dump toàn bộ 83 chunks:

```python
SECTION_SOURCE_TYPES = {
    "patient_overview":    ["patient_info", "diagnoses", "vitals"],
    "chief_complaint":     ["clinical_notes"],
    "medical_history":     ["clinical_notes", "diagnoses", "allergies"],
    "current_medications": ["medications"],
    "allergies":           ["allergies", "clinical_notes"],
    "abnormal_labs":       ["labs"],           # filter is_abnormal=True
    "diagnoses":           ["diagnoses"],      # ưu tiên encounter gần nhất
    "treatment_timeline":  ["labs", "medications", "diagnoses", "clinical_notes"],
    "clinical_alerts":     ["labs", "vitals", "allergies", "diagnoses"],
}
```

Logic retrieval theo thứ tự:
1. Metadata filter theo `source_type` + `is_abnormal`/`is_current`
2. Recency filter: ưu tiên encounter gần nhất cho `current_medications`, `diagnoses`
3. Full-text keyword match (BM25 hoặc đơn giản hơn là substring) cho `clinical_notes`

Interface:

```python
def retrieve_for_section(
    chunks: list[SourceChunk],
    section_id: str,
    max_chunks: int = 15,
) -> list[SourceChunk]:
    ...
```

**Acceptance criteria:**
- `current_medications` chỉ nhận `medications` chunks
- `abnormal_labs` chỉ nhận labs với `is_abnormal=True`
- `treatment_timeline` nhận đa dạng types, sort theo date asc
- Mỗi section nhận ≤ 15 chunks

---

### 2.2 Section `treatment_timeline` (bổ sung vào C4)

**File:** `poc/poc_pipeline.py` + `src/c3_retrieval/retriever.py`

Section thứ 9 còn thiếu. Nội dung: mô tả thay đổi key metrics qua các lần khám.

Guideline cho LLM:
```text
Mô tả diễn biến điều trị theo thứ tự thời gian.
Tập trung vào: HbA1c, huyết áp, LDL, UACR, thay đổi thuốc, biến chứng mới.
Format: [Ngày] — [Sự thay đổi chính]
Không đưa khuyến nghị mới.
```

Cập nhật `SECTIONS` từ 8 → 9 sections.

---

### 2.3 Claim Extraction (C5 — bước 1)

**File mới:** `src/c5_citation/claim_extractor.py`

Tách atomic claims từ `SummarySection.content`. Dùng LLM hoặc rule-based.

```python
def extract_claims(section: SummarySection) -> list[CitedClaim]:
    """
    Input:  SummarySection với content text
    Output: list[CitedClaim] với claim_text + is_critical + status=NO_CITATION
    """
    ...
```

Quy tắc `is_critical = True` nếu claim có:
- Tên thuốc + liều/hàm lượng
- Giá trị xét nghiệm + đơn vị
- Mã ICD-10 hoặc tên chẩn đoán
- Tên chất gây dị ứng
- Sinh hiệu bất thường

Cách tiếp cận cho PoC: dùng LLM với structured output (JSON list of claims).

---

### 2.4 Evidence Matching (C5 — bước 2)

**File mới:** `src/c5_citation/evidence_matcher.py`

Với mỗi claim, tìm source chunks hỗ trợ:

```python
def match_claim(
    claim: CitedClaim,
    store: dict[str, dict],
    section_id: str,
) -> CitedClaim:
    """
    Tìm source chunks cho claim.
    Trả về claim đã có status và citations.
    """
    ...
```

Logic matching theo source_type:

| Claim type | Matching rule |
|---|---|
| Medication | Tên thuốc khớp (case-insensitive) trong `chunk.metadata["drug_name"]` |
| Lab | `test_name` khớp + value tương đồng trong `chunk.content` |
| Diagnosis | `icd10_code` hoặc `diagnosis_name` xuất hiện trong `chunk.content` |
| Allergy | `substance` khớp trong `chunk.content` |
| General | Keyword overlap ≥ 2 tokens giữa claim và chunk content |

Output status:

```text
exact metadata match → SUPPORTED
keyword match → PARTIALLY_SUPPORTED
weak overlap → LOW_CONFIDENCE
no match → UNSUPPORTED / NO_CITATION
```

---

### 2.5 Hallucination Verifier (C6)

**File mới:** `src/c6_verifier/verifier.py`

```python
def verify_summary(
    sections: list[SummarySection],
    store: dict[str, dict],
) -> tuple[list[SummarySection], SummaryMetrics]:
    """
    Với mỗi section:
      1. Extract claims
      2. Match evidence
      3. Apply decision matrix (KEEP/FLAG/REMOVE)
      4. Rebuild section content từ kept/flagged claims
    Trả về sections đã được verify + metrics.
    """
    ...
```

Decision matrix (từ PLAN_04):

| Status | Critical | Action |
|---|---|---|
| SUPPORTED | any | KEEP |
| PARTIALLY_SUPPORTED | any | FLAG |
| LOW_CONFIDENCE | any | FLAG |
| UNSUPPORTED | false | FLAG |
| UNSUPPORTED | true | REMOVE |
| NO_CITATION | false | FLAG |
| NO_CITATION | true | REMOVE |
| CONTRADICTED | any | REMOVE |
| NEED_REVIEW | any | FLAG |

---

### 2.6 Chuyển sang Claude API

**File cập nhật:** `poc/poc_pipeline.py`

Thay `from openai import OpenAI` bằng Anthropic SDK.  
Dùng model: `claude-sonnet-4-6` (mặc định), hỗ trợ `claude-haiku-4-5` cho dev.

```python
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model=model,
    max_tokens=1000,
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": prompt}],
)
text = response.content[0].text
```

Cập nhật `.env.example`: thêm `ANTHROPIC_API_KEY`.  
Xóa `OPENAI_API_KEY` dependency.

---

### 2.7 Tests Tuần 3

**File mới:** `tests/test_c3_retrieval.py`, `tests/test_c5_citation.py`, `tests/test_c6_verifier.py`

Các test tối thiểu:

```text
test_c3_retrieval.py
  - test_current_medications_only_gets_med_chunks
  - test_abnormal_labs_filters_is_abnormal
  - test_treatment_timeline_sorted_by_date
  - test_max_chunks_respected

test_c5_citation.py
  - test_extract_claims_returns_list
  - test_medication_claim_is_critical
  - test_claim_matched_to_correct_source
  - test_no_citation_when_no_match
  - test_lab_claim_matched_by_value

test_c6_verifier.py
  - test_unsupported_critical_claim_removed
  - test_contradicted_claim_removed
  - test_low_confidence_claim_flagged
  - test_metrics_computed_correctly
  - test_allergy_section_not_silenced
```

### Acceptance criteria Tuần 3

| ID | Tiêu chí | Target |
|---|---|---|
| W3-01 | Retrieve đúng chunks theo section | Pass |
| W3-02 | `treatment_timeline` section tồn tại | Pass |
| W3-03 | Số section = 9 | 9/9 |
| W3-04 | Extract được atomic claims | Pass |
| W3-05 | Critical claims có citation ≥ 85% | ≥ 85% cho P001 |
| W3-06 | Unsupported critical claims bị remove | Pass |
| W3-07 | Tính được 7 auto metrics | Pass |
| W3-08 | Pipeline dùng Claude API | Pass |
| W3-09 | Tests mới all green | Pass |

---

## 3. Mục tiêu Tuần 4 — Evaluation + FastAPI + Streamlit Demo

**Deadline:** Cuối tuần 4  
**Tiêu chí thành công:** Demo chạy được end-to-end, trình bày được 5–7 phút

### 3.1 Auto Evaluation Report

**File mới:** `src/c7_evaluation/evaluator.py`

```python
def evaluate_summary(
    summary: FinalSummary,
    store: dict[str, dict],
) -> dict:
    """
    Tính metrics và tạo evaluation report.
    """
    ...
```

Metrics cần có (từ `SummaryMetrics`):

```text
citation_coverage        = SUPPORTED / total_claims
unsupported_claim_rate   = (UNSUPPORTED + NO_CITATION) / total_claims
hallucination_rate       = CONTRADICTED / total_claims
missing_section_rate     = empty_sections / total_sections
total_claims
latency_seconds
token_count
```

Output: `data/processed/outputs/{patient_id}_summary.json`

Human evaluation package:

```text
eval/cases/{patient_id}/
├── ehr_source.json         ← assembled EHR (deidentified)
├── summary_output.json     ← FinalSummary
├── summary_rendered.md     ← markdown-rendered version
└── evaluation_form.json    ← rubric + blank scores
```

Rubric (8 tiêu chí, thang 1–5):

| Tiêu chí | Mô tả |
|---|---|
| clinical_relevance | Thông tin có liên quan lâm sàng |
| factual_correctness | Không sai thực tế so với source |
| citation_correctness | Citation dẫn đúng source |
| completeness | Không bỏ sót thông tin quan trọng |
| conciseness | Ngắn gọn, không dài dòng |
| vietnamese_fluency | Tiếng Việt có dấu, đúng ngữ pháp |
| safety | Không kê đơn, không chẩn đoán thêm |
| doctor_usefulness | Bác sĩ có thể dùng được trong thực tế |

---

### 3.2 FastAPI

**File mới:** `api/main.py`, `api/routers/summary.py`, `api/routers/sources.py`

Endpoints tối thiểu:

```text
GET  /health
GET  /patients                          → list patient_ids
POST /summarize/{patient_id}            → FinalSummary JSON
GET  /source/{source_id}               → SourceChunk JSON
GET  /metrics/{patient_id}             → SummaryMetrics JSON
GET  /eval/{patient_id}                → evaluation report
```

Chạy: `uvicorn api.main:app --reload`

---

### 3.3 Streamlit UI

**File mới:** `ui/app.py`

Layout tối thiểu:

```text
Sidebar
  └── Patient selector (P001–P004)
  └── Model selector (sonnet / haiku)
  └── [Generate Summary] button

Main panel
  └── Header: tên bệnh nhân, ngày tạo
  └── Clinical Alerts (highlight đỏ)
  └── Tabs: [Overview] [Medications] [Labs] [Diagnoses] [History] [Timeline]
  └── Mỗi tab: content + citation badges
  └── Citation badge → sidebar panel xem source gốc
  └── Footer: metrics bar (coverage, latency, tokens)
```

Chạy: `streamlit run ui/app.py`

---

### 3.4 Demo Script (5–7 phút)

Thứ tự demo:

1. Chạy `dry_run.py` — show 4 patients, chunk counts, no warnings (**30s**)
2. Mở Streamlit, chọn P001 → Generate Summary (**45s**)
3. Đọc Clinical Alerts → highlight allergy Penicillin (**30s**)
4. Tab Medications → click citation badge → xem source gốc (**45s**)
5. Tab Abnormal Labs → show HbA1c 9.2% SUPPORTED (**30s**)
6. Chuyển P002 → generate → show "Chưa thấy ghi nhận dị ứng" (**30s**)
7. Chuyển P004 → show edge cases flagged (missing dose, missing unit) (**45s**)
8. Show metrics bar: coverage, hallucination_rate (**30s**)
9. Show FinalSummary JSON trong terminal (**15s**)

---

### Acceptance criteria Tuần 4

| ID | Tiêu chí | Target |
|---|---|---|
| W4-01 | FastAPI chạy local | Pass |
| W4-02 | Streamlit demo chạy | Pass |
| W4-03 | P001–P004 generate summary end-to-end | Pass |
| W4-04 | Citation badge click → đúng source | Pass |
| W4-05 | Evaluation report có đủ 7 metrics | Pass |
| W4-06 | Human eval form tồn tại cho 4 patients | Pass |
| W4-07 | Demo script 5–7 phút hoàn thành | Pass |
| W4-08 | week4_status.py: tất cả check pass | Pass |

---

## 4. Thứ tự triển khai (ưu tiên)

```text
Tuần 3:
  Day 1-2:  C3 Retrieval (retriever.py) + treatment_timeline section
  Day 3-4:  C5 Claim Extractor + Evidence Matcher
  Day 5:    C6 Verifier + metrics
  Day 6:    Chuyển OpenAI → Claude API
  Day 7:    Tests tuần 3 + dry_run validation

Tuần 4:
  Day 1:    Auto evaluation + human eval package
  Day 2-3:  FastAPI endpoints
  Day 4-5:  Streamlit UI
  Day 6:    Integration test end-to-end
  Day 7:    Demo rehearsal + week4_status.py
```

---

## 5. File structure mới cần tạo

```text
src/
├── c3_retrieval/
│   ├── __init__.py
│   └── retriever.py          ← section-wise retrieval
├── c5_citation/
│   ├── __init__.py
│   ├── claim_extractor.py    ← tách atomic claims
│   └── evidence_matcher.py   ← match claim ↔ source
├── c6_verifier/
│   ├── __init__.py
│   └── verifier.py           ← KEEP/FLAG/REMOVE + metrics
└── c7_evaluation/
    ├── __init__.py
    └── evaluator.py          ← auto metrics + human eval package

api/
├── __init__.py
├── main.py
└── routers/
    ├── summary.py
    └── sources.py

ui/
└── app.py

tests/
├── test_c3_retrieval.py
├── test_c5_citation.py
└── test_c6_verifier.py

eval/
└── cases/                    ← generated by evaluator
    ├── P001/
    ├── P002/
    ├── P003/
    └── P004/

scripts/
└── week4_status.py           ← checkpoint tuần 4
```

---

## 6. Rủi ro và mitigation

| Rủi ro | Khả năng | Mitigation |
|---|---|---|
| Claim extraction LLM trả JSON lỗi format | Cao | Pydantic validation + retry + fallback rule-based |
| Evidence matching quá heuristic, nhiều false negative | Trung bình | Ưu tiên metadata exact match trước, keyword fallback |
| Streamlit không kịp thời gian | Trung bình | Scope tối giản: chỉ cần hiển thị text + 1 panel citations |
| Claude API latency quá cao | Thấp | Dùng `claude-haiku-4-5` trong dev, sonnet chỉ cho demo |
| C6 remove quá nhiều claims hợp lệ | Trung bình | Bắt đầu với FLAG mode, chỉ REMOVE khi rất chắc chắn |

---

## 7. Tham chiếu

| Tài liệu | Mô tả |
|---|---|
| `plans/PLAN_00_Architecture.md` | Tổng kiến trúc pipeline |
| `plans/PLAN_02_Active_Summarizer.md` | C4 — Section-wise summarization |
| `plans/PLAN_03_Citation_Pipeline.md` | C5 — Claim extraction + evidence matching |
| `plans/PLAN_04_Hallucination_Mitigation.md` | C6 — KEEP/FLAG/REMOVE verifier |
| `plans/PLAN_05_Evaluation.md` | Evaluation metrics + human eval |
| `plans/PLAN_06_Demo_API_UI.md` | FastAPI + Streamlit spec |
| `plans/ImplementationPlanV3.md` | Master plan 4 tuần |
