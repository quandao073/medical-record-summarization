# PLAN 00 — Tổng quan kiến trúc

**Project:** Medical Record Summarization  
**Strategy:** PARTNER/MVP PoC  
**Cập nhật cho:** bộ raw dataset modular đã chuẩn hóa

---

## 1. Cấu trúc thư mục đề xuất

```text
MedicalRecordSummarization/
├── src/
│   ├── schemas.py
│   ├── pipeline.py
│   ├── c1_emr/
│   │   ├── validator.py
│   │   ├── assembler.py
│   │   ├── deidentifier.py
│   │   └── normalizer.py
│   ├── c2_chunking/
│   │   ├── chunker.py
│   │   └── store_builder.py
│   ├── c3_retrieval/
│   │   ├── keyword_retriever.py
│   │   ├── vector_retriever.py
│   │   ├── hybrid_retriever.py
│   │   └── policies.py
│   ├── c4_summarizer/
│   │   ├── prompt_templates.py
│   │   └── summarizer.py
│   ├── c5_citation/
│   │   ├── claim_extractor.py
│   │   ├── evidence_matcher.py
│   │   └── citation_builder.py
│   ├── c6_verifier/
│   │   ├── business_rules.py
│   │   └── verifier.py
│   └── c7_eval/
│       ├── metrics.py
│       ├── render_summary.py
│       └── report_builder.py
├── api/
│   └── main.py
├── ui/
│   └── streamlit_app.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── stores/
│   ├── cache/
│   └── abbrev_dict.json
├── eval/
│   ├── cases/
│   └── results/
├── tests/
├── configs/
│   └── config.yaml
└── plans/
```

---

## 2. Kiến trúc component

```text
Raw modular JSON files
        ↓
C1 EMR Integration
validator → assembler → deidentifier → normalizer
        ↓
C2 Chunking
AssembledEHR → SourceChunk[] → structured store/vector store
        ↓
C3 Retrieval
section policies → metadata filter → BM25/vector/hybrid retrieval
        ↓
C4 Active Summarizer
section-wise prompt → SummarySection draft
        ↓
C5 Citation Pipeline
claim extraction → evidence matching → citation attachment
        ↓
C6 Hallucination Verifier
business rules → KEEP/FLAG/REMOVE → FinalSummary
        ↓
C7 Evaluation
auto metrics + human review package
        ↓
FastAPI + Streamlit UI
```

---

## 3. Data contracts lõi

Các model trong `src/schemas.py` là nguồn sự thật duy nhất cho toàn pipeline.

```python
class SourceChunk(BaseModel):
    source_id: str
    source_type: str
    patient_id: str
    encounter_id: str | None = None
    date: str | None = None
    content: str
    metadata: dict = Field(default_factory=dict)

class CitedClaim(BaseModel):
    claim_text: str
    status: ClaimStatus = "NO_CITATION"
    citations: list[str] = Field(default_factory=list)
    confidence_score: float | None = None
    is_critical: bool = False
    verification_status: VerificationStatus = "PENDING"

class SummarySection(BaseModel):
    section_id: str
    title: str | None = None
    content: str = ""
    cited_claims: list[CitedClaim] = Field(default_factory=list)

class FinalSummary(BaseModel):
    patient_id: str
    created_at: str
    prompt_version: str
    model_version: str
    sections: list[SummarySection]
    metrics: SummaryMetrics
```

---

## 4. Source types chuẩn

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

Không dùng source types tiếng Việt như `xet_nghiem`, `thuoc`, `chan_doan` trong code chính. Nội dung lâm sàng bên trong `content` vẫn là tiếng Việt có dấu.

---

## 5. Section-wise pipeline

Final summary không sinh một lần từ toàn bộ bệnh án. Hệ thống sinh theo từng section:

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

Mỗi section có retrieval policy riêng, ví dụ:

- `current_medications`: ưu tiên thuốc mới nhất/active.
- `abnormal_labs`: filter `is_abnormal=true`.
- `treatment_timeline`: lấy nhiều visits theo thứ tự thời gian.
- `clinical_alerts`: lấy dị ứng, lab/vital bất thường, diagnosis nguy cơ cao.

---

## 6. Nguyên tắc thiết kế

1. Không để LLM truy cập raw EHR dài trực tiếp.
2. Mọi claim quan trọng phải trace được về `source_id`.
3. Source chunk là đơn vị citation nhỏ nhất.
4. Critical claims không có citation phải bị remove hoặc flag.
5. Pipeline phải dễ debug theo từng component.
6. PoC ưu tiên tính đúng và traceability hơn UI đẹp.

---

## 7. API/UI trong PoC

Với scope 4 tuần, dùng:

```text
Backend: FastAPI
UI: Streamlit
Storage: JSON files + in-memory structured store
Vector: FAISS/Chroma tùy thời gian
```

Không ưu tiên Next.js trong PoC 4 tuần.
