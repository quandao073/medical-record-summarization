# Kế hoạch triển khai V3 — PoC 4 tuần với bộ seed dataset đã chuẩn hóa

**Project:** Clinical Summarization & Citation Pipeline  
**Author:** Đào Anh Quân  
**Scope:** Solo Technical PoC  
**Strategy:** PARTNER/MVP first  

---

## Chuẩn dữ liệu nền tảng

Toàn bộ kế hoạch triển khai giả định bộ seed dataset PoC đã được chuẩn hóa tại:

```text
data/raw/
├── patients.json
├── encounters.json
├── clinical_notes.json
├── diagnoses.json
├── labs.json
├── medications.json
├── allergies.json
├── vitals.json
├── imaging_reports.json
└── procedures.json
```

Quy ước dữ liệu:

| Layer | Chuẩn |
|---|---|
| Tên field JSON | Tiếng Anh, `snake_case` |
| Clinical free-text | Tiếng Việt có dấu |
| ID / source_id | ASCII-safe, ổn định |
| Enum / controlled values | Tiếng Anh |
| Viết tắt y khoa | Giữ như dữ liệu thực tế, chuẩn hóa ở bước preprocessing |

Một số field đã chuẩn hóa quan trọng:

```text
dob → date_of_birth
abnormal → is_abnormal
critical → is_critical
temperature_c → temperature_celsius
spo2 → spo2_percent
report_text → findings
procedure_text → description
result_summary → result
noi_dung → content
ngay_tao → created_at
```

Các section chuẩn cho summary:

```text
patient_overview
chief_complaint
medical_history
current_medications
allergies
abnormal_labs
diagnoses
treatment_timeline
clinical_alerts
```


---

## 1. Mục tiêu tổng thể trong 4 tuần

Mục tiêu của 4 tuần là chứng minh tính khả thi kỹ thuật của pipeline:

```text
Raw modular EHR dataset
→ validation
→ de-identification
→ normalization
→ source chunking
→ section-wise retrieval/RAG
→ active summarization
→ citation pipeline
→ hallucination verification
→ evaluation
→ FastAPI + Streamlit demo
```

Đây là **technical PoC**, không phải production MVP hoàn chỉnh. Thành công của PoC được đo bằng việc hệ thống chạy được end-to-end trên bộ seed dataset chuẩn hóa và sinh summary có citation kiểm chứng được.

---

## 2. Phạm vi triển khai

### In scope

- Load raw dataset dạng nhiều file JSON modular.
- Assemble dữ liệu theo `patient_id` và `encounter_id`.
- Validate schema và quan hệ khóa.
- De-identify PII.
- Normalize viết tắt y khoa trong clinical text.
- Tạo `SourceChunk` có `source_id`, `source_type`, `content`, `metadata`.
- Retrieval theo từng section.
- Sinh summary theo section.
- Tách claim, gắn citation và verify claim-source.
- Flag claim `LOW_CONFIDENCE`, `UNSUPPORTED`, `NO_CITATION`, `CONTRADICTED`.
- Tạo evaluation report.
- Demo bằng FastAPI + Streamlit.

### Out of scope

- Fine-tune model.
- Triển khai production HIS/EMR.
- Full FHIR integration.
- Kubernetes/Edge deployment.
- Next.js UI hoàn chỉnh.
- Clinical decision support hoặc khuyến nghị điều trị.
- Dùng dữ liệu bệnh nhân thật chưa được de-identify.

---

## 3. Milestone tổng quan

| Tuần | Trọng tâm | Deliverable chính | Tiêu chí hoàn thành |
|---|---|---|---|
| Tuần 1 | Dataset + C1/C2 | Raw validation, assembler, chunker | Tạo được `SourceChunk` cho 4 bệnh nhân |
| Tuần 2 | Retrieval + Active Summarizer | Section-wise RAG + draft summary | Sinh đủ 9 section cho ít nhất 2 bệnh nhân |
| Tuần 3 | Citation + Hallucination Mitigation | Claim extraction, evidence matching, verifier | Claim critical không source bị flag/remove |
| Tuần 4 | Evaluation + Demo | FastAPI/Streamlit + report | Demo end-to-end + metrics trên toàn dataset |

---

## 4. Tuần 1 — Dataset, EMR Integration, Chunking

### Mục tiêu

Biến bộ raw dataset chuẩn hóa thành dữ liệu an toàn, sạch và có thể cite.

### Task 1.1 — Setup project

```bash
python -m venv .venv
source .venv/bin/activate

pip install pydantic fastapi uvicorn streamlit             sentence-transformers rank-bm25 faiss-cpu chromadb             pandas pyyaml python-dotenv pytest
```

File cần có:

```text
src/schemas.py
src/c1_emr/validator.py
src/c1_emr/assembler.py
src/c1_emr/deidentifier.py
src/c1_emr/normalizer.py
src/c2_chunking/chunker.py
configs/config.yaml
.env.example
```

### Task 1.2 — Data contracts

`src/schemas.py` cần định nghĩa các model chính:

```text
PatientRecord
EncounterRecord
ClinicalNoteRecord
DiagnosisRecord
LabRecord
MedicationRecord
AllergyRecord
VitalRecord
ImagingRecord
ProcedureRecord
AssembledEHR
SourceChunk
CitedClaim
SummarySection
FinalSummary
ValidationError
```

Các field phải dùng tiếng Anh chuẩn:

```text
date_of_birth
is_abnormal
is_critical
temperature_celsius
spo2_percent
content
created_at
```

### Task 1.3 — Validator

Validator cần kiểm tra:

- `patient_id` tồn tại trong mọi record.
- Record theo lần khám phải có `encounter_id`.
- `encounter_id` phải tồn tại trong `encounters.json`.
- Date format hợp lệ.
- Lab có `test_name`, `value`, `unit` nếu có thể.
- Medication critical nên có `drug_name`, `strength`, `dose`, `frequency`.
- Edge cases intentional được ghi warning, không hard fail.

### Task 1.4 — Assembler

Assembler join dữ liệu theo:

```text
patients.patient_id
  └── encounters.patient_id
        ├── clinical_notes.encounter_id
        ├── diagnoses.encounter_id
        ├── labs.encounter_id
        ├── medications.encounter_id
        ├── allergies.encounter_id
        ├── vitals.encounter_id
        ├── imaging_reports.encounter_id
        └── procedures.encounter_id
```

Output:

```python
def assemble_patient_ehr(patient_id: str) -> AssembledEHR:
    ...
```

### Task 1.5 — Chunking

Mỗi fact có thể cite độc lập nên trở thành một `SourceChunk`.

Ví dụ source types:

```text
patient_profile
encounter
clinical_note
diagnosis
lab_result
medication
allergy
vital
imaging
procedure
derived_trend
```

Format source ID gợi ý:

```text
P001-E001-LAB-HBA1C
P001-E001-MED-METFORMIN
P001-E001-DX-E11
P001-E001-NOTE-HISTORY_OF_PRESENT_ILLNESS
P001-E001-VITALS
P001-ALLERGY-PENICILLIN
```

### Acceptance criteria tuần 1

| Checkpoint | Target |
|---|---|
| Load được toàn bộ raw files | Pass |
| Validate dataset | 0 error, warning intentional được chấp nhận |
| Assemble được mọi patient | 4/4 patients |
| Chunk được mọi patient | ≥ 150 chunks tổng |
| Structured lookup theo source_id | Pass |
| Unit tests C1/C2 | All green |

---

## 5. Tuần 2 — Section-wise Retrieval + Active Summarizer

### Mục tiêu

Tạo được summary theo section, mỗi section có retrieval policy riêng.

### Task 2.1 — Retrieval policies

Ví dụ:

| Section | Source types ưu tiên | Logic |
|---|---|---|
| `patient_overview` | patient_profile, diagnosis, medical_history | bệnh nền chính, thông tin ổn định |
| `chief_complaint` | encounter, clinical_note | ưu tiên encounter gần nhất |
| `medical_history` | clinical_note, diagnosis, allergy | lấy thông tin ổn định qua nhiều lần khám |
| `current_medications` | medication | lấy thuốc mới nhất/active |
| `allergies` | allergy, clinical_note | ưu tiên structured allergy |
| `abnormal_labs` | lab_result | filter `is_abnormal=true`, ưu tiên mới nhất |
| `diagnoses` | diagnosis | lấy chẩn đoán gần nhất và ICD-10 |
| `treatment_timeline` | lab_result, medication, diagnosis, clinical_note | lấy theo timeline |
| `clinical_alerts` | lab_result, vital, allergy, diagnosis | lấy critical/high-risk chunks |

### Task 2.2 — Hybrid retrieval

Pipeline retrieval tối thiểu:

```text
metadata filter
→ keyword retrieval / BM25
→ vector retrieval
→ merge/rerank
→ evidence pack
```

Với PoC, có thể ưu tiên metadata filter + keyword trước, vector search dùng cho clinical notes.

### Task 2.3 — Active Summarizer

Active Summarizer chạy theo vòng lặp:

```python
for section_id in SECTION_ORDER:
    policy = SECTION_POLICIES[section_id]
    evidence = retriever.retrieve(patient_id, policy)
    section = summarizer.generate(section_id, evidence)
```

Output của mỗi section:

```json
{
  "section_id": "abnormal_labs",
  "title": "Xét nghiệm bất thường",
  "content": "...",
  "cited_claims": []
}
```

### Task 2.4 — Prompt guardrails

Prompt bắt buộc:

- Chỉ dùng evidence được cung cấp.
- Không tự thêm chẩn đoán.
- Không kê đơn.
- Không tạo source_id mới.
- Nếu thiếu thông tin, ghi “Chưa thấy ghi nhận trong dữ liệu được cung cấp.”
- Giữ nguyên tên thuốc, liều, giá trị số, đơn vị, ICD-10.

### Acceptance criteria tuần 2

| Checkpoint | Target |
|---|---|
| Retrieve được evidence cho mọi section | Pass |
| Sinh đủ 9 sections cho P001/P002 | 9/9 |
| Section thuốc lấy latest/current meds | Pass |
| Section lab lấy abnormal labs đúng | Pass |
| Timeline có ít nhất 1 trend | Pass |
| Không có hallucination critical rõ ràng | 0 lỗi nghiêm trọng khi review thủ công |

---

## 6. Tuần 3 — Citation Pipeline + Hallucination Mitigation

### Mục tiêu

Biến summary text thành các atomic claims có citation, sau đó verify claim-source.

### Task 3.1 — Claim extraction

Tách từng section thành atomic claims:

```json
[
  {
    "claim_text": "Bệnh nhân đang dùng Metformin 1000 mg, 1 viên, 2 lần/ngày.",
    "is_critical": true
  }
]
```

Claim critical gồm:

- Thuốc + liều.
- Kết quả xét nghiệm số + đơn vị.
- Chẩn đoán / ICD-10.
- Dị ứng.
- Sinh hiệu bất thường.

### Task 3.2 — Evidence matching

Với mỗi claim:

```text
claim
→ candidate source chunks
→ NLI / rule matching
→ status
```

Status chuẩn:

```text
SUPPORTED
PARTIALLY_SUPPORTED
LOW_CONFIDENCE
UNSUPPORTED
NO_CITATION
CONTRADICTED
NEED_REVIEW
```

### Task 3.3 — Rule-based verifier

Quy tắc xử lý:

| Claim status | Critical? | Action |
|---|---:|---|
| SUPPORTED | any | KEEP |
| PARTIALLY_SUPPORTED | any | FLAG |
| LOW_CONFIDENCE | any | FLAG |
| UNSUPPORTED | false | FLAG |
| UNSUPPORTED | true | REMOVE hoặc NEED_REVIEW |
| NO_CITATION | false | FLAG |
| NO_CITATION | true | REMOVE |
| CONTRADICTED | any | REMOVE |
| NEED_REVIEW | any | FLAG |

### Task 3.4 — Confidence score

Confidence có thể tính đơn giản từ:

```text
retrieval_score
source_type_reliability
metadata_completeness
exact_value_match
recency
source_consistency
```

### Acceptance criteria tuần 3

| Checkpoint | Target |
|---|---|
| Extract claims cho mọi section | Pass |
| Critical claims có citation | ≥ 85% |
| Claim medication/lab/diagnosis có source | ≥ 85% |
| Unsupported critical claim bị remove/flag | Pass |
| Edge cases missing dose/unit được flag | Pass |
| Metrics tính được | Pass |

---

## 7. Tuần 4 — Evaluation + Demo API/UI

### Mục tiêu

Tạo demo end-to-end có thể trình bày với mentor.

### Task 4.1 — Auto metrics

Metrics cần có:

```text
citation_coverage
citation_accuracy
unsupported_claim_rate
hallucination_rate
missing_section_rate
total_claims
latency_seconds
```

### Task 4.2 — Human evaluation package

Mỗi case nên có:

```text
eval/cases/P001/
├── ehr_source.json
├── summary_output.json
├── summary_rendered.md
└── evaluation_form.json
```

Rubric:

| Tiêu chí | Điểm |
|---|---|
| Clinical relevance | 1–5 |
| Factual correctness | 1–5 |
| Citation correctness | 1–5 |
| Completeness | 1–5 |
| Conciseness | 1–5 |
| Vietnamese fluency | 1–5 |
| Safety | 1–5 |
| Usefulness for doctor | 1–5 |

### Task 4.3 — FastAPI

Endpoints tối thiểu:

```text
GET  /api/v1/health
GET  /api/v1/patients
POST /api/v1/summarize/{patient_id}
GET  /api/v1/source/{source_id}
GET  /api/v1/metrics/{patient_id}
```

### Task 4.4 — Streamlit UI

UI tối thiểu:

- Chọn patient.
- Bấm generate summary.
- Hiển thị sections.
- Citation badges click được.
- Panel xem source gốc.
- Metrics bar.
- Highlight clinical alerts/allergies.

### Acceptance criteria tuần 4

| Checkpoint | Target |
|---|---|
| API chạy local | Pass |
| Streamlit demo chạy | Pass |
| P001–P004 generate summary | Pass |
| Citation click lookup đúng source | Pass |
| Evaluation report có metrics | Pass |
| Demo script 5–7 phút | Hoàn thành |

---

## 8. Nhận xét về tính khả thi

Kế hoạch 4 tuần khả thi nếu giữ scope là **technical PoC**. Rủi ro lớn nhất không nằm ở UI, mà nằm ở citation verification và claim-source matching.

Ưu tiên đúng nên là:

```text
1. Dataset contract đúng
2. Chunking đúng
3. Retrieval theo section đúng
4. Citation trace được về source
5. Verifier flag được lỗi
6. UI chỉ cần đủ demo
```

Không nên dành quá nhiều thời gian cho benchmark model, Next.js UI hoặc fine-tuning trong 4 tuần.
