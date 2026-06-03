# PLAN 00 — Architecture Overview
**Project:** Medical Record Summarization | **Strategy:** PARTNER (MVP)

---

## 1. Project Directory Structure

```
MedicalRecordSummarization/
├── src/
│   ├── schemas.py                  # Contract types — toàn bộ pipeline import từ đây
│   ├── pipeline.py                 # Orchestrator: chạy C1→C2→C3→C4→C5→C6
│   ├── c1_emr/
│   │   ├── validator.py            # Pydantic schema validation
│   │   ├── deidentifier.py         # PII masking (CCCD, BHYT, phone, address)
│   │   └── normalizer.py           # Viết tắt y khoa VN → full text
│   ├── c2_chunking/
│   │   ├── chunker.py              # EHR → List[SourceChunk]
│   │   └── store_builder.py        # Build structured store + FAISS vector store
│   ├── c3_retrieval/
│   │   ├── keyword_retriever.py    # BM25Okapi
│   │   ├── vector_retriever.py     # multilingual-e5-large + FAISS
│   │   └── hybrid_retriever.py     # RRF fusion + section-specific queries
│   ├── c4_summarizer/
│   │   ├── prompt_templates.py     # System prompt + per-section user prompts
│   │   └── summarizer.py           # LLM calls per section, retry logic
│   ├── c5_citation/
│   │   ├── claim_extractor.py      # LLM: summary text → atomic claims JSON
│   │   ├── evidence_matcher.py     # LLM-as-NLI: claim × source → SUPPORTED/…
│   │   └── citation_builder.py     # Orchestrate extraction + matching per section
│   ├── c6_verifier/
│   │   ├── business_rules.py       # KEEP / REMOVE / FLAG decision logic
│   │   └── verifier.py             # Apply rules, compute metrics, build FinalSummary
│   └── c7_eval/
│       ├── metrics.py              # Auto metrics: citation_coverage, hallucination_rate
│       ├── render_summary.py       # FinalSummary → human-readable text
│       └── mlflow_logger.py        # Log runs, params, metrics to MLflow
├── api/
│   └── main.py                     # FastAPI: /summarize, /source, /health
├── ui/                             # Next.js app
│   ├── app/
│   │   ├── page.tsx                # Patient selector
│   │   └── summary/[id]/page.tsx   # Summary viewer + citation panel
│   └── components/
│       ├── SummarySection.tsx
│       ├── CitationBadge.tsx
│       └── CitationPanel.tsx
├── data/
│   ├── raw/                        # EHR JSONs (synthetic / de-identified)
│   ├── stores/
│   │   ├── structured.json         # {source_id: SourceChunk}
│   │   └── vector_index/           # FAISS index + idx→source_id map
│   ├── abbrev_dict.json            # Từ điển viết tắt y khoa VN
│   └── icd10_vn.json               # ICD-10 lookup (QĐ 4469)
├── notebooks/
│   ├── 01_data_generation.ipynb
│   ├── 02_dataset_validation.ipynb
│   ├── 03_baseline_eval.ipynb
│   ├── 04_citation_debug.ipynb
│   └── 05_evaluation_analysis.ipynb
├── eval/
│   ├── cases/                      # Per-patient: ehr_source + summary_output + rendered
│   └── results/                    # EVAL_BN00X_v1.json human evaluation outputs
├── tests/
│   ├── test_c1_emr.py
│   ├── test_c2_chunking.py
│   ├── test_c3_retrieval.py
│   ├── test_c4_summarizer.py
│   ├── test_c5_citation.py
│   ├── test_c6_verifier.py
│   └── test_pipeline.py
├── configs/
│   └── config.yaml
├── .env                            # API keys — không commit
├── requirements.txt
└── plans/                          # Các PLAN files này
```

---

## 2. Component Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Input: EHR JSON                       │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────┐
│  C1: EMR Integration                                    │
│  validator → deidentifier → normalizer                  │
│  Output: safe_normalized_ehr (dict)                     │
└────────────────────────┬───────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────┐
│  C2: Chunking Service                                   │
│  chunker → store_builder                                │
│  Output: List[SourceChunk] + structured_store + FAISS  │
└────────────────────────┬───────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────┐
│  C3: Retrieval (per section)                            │
│  BM25 + vector → RRF hybrid → top-k chunks             │
│  Output: {section_id: List[SourceChunk]}               │
└────────────────────────┬───────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────┐
│  C4: Active Summarizer                                  │
│  per-section LLM prompt → draft text                   │
│  Output: {section_id: draft_text}                      │
└────────────────────────┬───────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────┐
│  C5: Citation Builder                                   │
│  claim_extractor → evidence_matcher → citations        │
│  Output: {section_id: List[CitedClaim]}                │
└────────────────────────┬───────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────┐
│  C6: Hallucination Verifier                             │
│  business_rules → KEEP/REMOVE/FLAG → FinalSummary      │
│  Output: FinalSummary (with metrics)                   │
└────────────────────────┬───────────────────────────────┘
                         ↓
┌────────────────────────────────────────────────────────┐
│  FastAPI → Next.js UI                                   │
│  /summarize + /source endpoints                         │
│  Citation viewer, metrics dashboard                     │
└────────────────────────────────────────────────────────┘
```

---

## 3. Core Data Contracts (`src/schemas.py`)

```python
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import date, datetime

class SourceChunk(BaseModel):
    source_id: str           # "BN001_LK001_XN_HBA1C"
    source_type: str         # "xet_nghiem" | "thuoc" | "chan_doan" | "tien_su"
                             # | "sinh_hieu" | "cdha" | "ghi_chu" | "hanh_chinh" | "di_ung"
    patient_id: str
    visit_id: str
    ngay: Optional[date]
    noi_dung: str            # Text đã normalize, sẵn sàng embed
    metadata: dict           # bat_thuong, ten_thuoc, ma_icd10, ...

class CitedClaim(BaseModel):
    claim_text: str
    status: Literal["SUPPORTED", "PARTIAL", "UNSUPPORTED", "CONTRADICTED", "NO_CITATION"]
    citations: list[str]     # List[source_id]
    is_critical: bool        # Thuốc/liều/dị ứng/chẩn đoán/XN → True

class SummarySection(BaseModel):
    section_id: str          # "thuoc_hien_tai", "xn_bat_thuong", ...
    noi_dung: str            # Reconstructed text sau verify
    cited_claims: list[CitedClaim]

class FinalSummary(BaseModel):
    patient_id: str
    ngay_tao: str            # ISO 8601
    prompt_version: str
    model_version: str
    sections: list[SummarySection]
    metrics: Optional[dict]  # citation_coverage, hallucination_rate, latency_seconds

class EHRValidationError(BaseModel):
    field: str
    message: str
```

---

## 4. Tech Stack — Quyết định và Lý do

| Layer | Công nghệ | Phiên bản MVP | Lý do chọn |
|-------|-----------|--------------|------------|
| **LLM (chính)** | Claude Sonnet | claude-sonnet-4-5 | Tiếng Việt tốt, instruction-following mạnh, đủ fast |
| **LLM (fallback)** | GPT-4o | gpt-4o | Backup khi Anthropic API down |
| **Embedding** | multilingual-e5-large | intfloat/multilingual-e5-large | Hỗ trợ tiếng Việt tốt, chạy local free |
| **Vector Store** | FAISS (IndexFlatIP) | faiss-cpu | Nhẹ, không cần server, phù hợp MVP |
| **Keyword Search** | BM25 (rank-bm25) | — | Tốt cho tên thuốc, số XN, exact match |
| **Schema validation** | Pydantic v2 | — | Type safety, tự động validate |
| **Backend** | FastAPI | — | Async, OpenAPI docs tự động |
| **Frontend** | Next.js 14 (App Router) | — | React server components, TypeScript |
| **Experiment tracking** | MLflow | — | Log params/metrics/artifacts |
| **Data format** | JSON + SQLite | — | Đủ cho MVP, không cần Postgres |
| **Testing** | pytest | — | Standard Python |

### Lý do KHÔNG dùng trong MVP

| Không dùng | Lý do |
|-----------|-------|
| Self-hosted LLM | Cần ≥24GB VRAM cho 7B+ quality — vượt resource hiện có |
| Qdrant / Milvus | Overkill cho ≤20 patients demo |
| Redis (cache) | Thêm dependency phức tạp, cache file JSON là đủ |
| Kubernetes | Production concern — không trong 6 tuần |
| LangChain | Abstracts quá nhiều, khó debug citation pipeline |
| FHIR API | Post-MVP — cần bệnh viện hợp tác |

---

## 5. Configuration (`configs/config.yaml`)

```yaml
llm:
  provider: "anthropic"          # "anthropic" | "openai"
  model: "claude-sonnet-4-5"
  max_tokens: 500                # Per section — summary ngắn gọn
  temperature: 0.1               # Gần deterministic cho medical

embedding:
  model: "intfloat/multilingual-e5-large"
  batch_size: 32
  normalize: true                # Bắt buộc cho IndexFlatIP = cosine

retrieval:
  top_k_default: 5
  top_k_per_section:
    tong_quan: 5
    ly_do_kham: 4
    tien_su: 8                   # Nhiều visits → cần nhiều hơn
    thuoc_hien_tai: 6
    di_ung: 3
    xn_bat_thuong: 10            # XN nhiều nhất
    chan_doan: 5
    luu_y: 12                    # Cần tổng hợp nhiều nguồn
  rrf_k: 60                      # RRF constant

citation:
  min_similarity_threshold: 0.70
  judge_model: "claude-sonnet-4-5"
  max_chunks_per_claim: 3        # Giới hạn LLM NLI calls để tiết kiệm cost
  judge_temperature: 0.0         # Deterministic hoàn toàn cho NLI

stores:
  structured_path: "data/stores/structured.json"
  vector_index_path: "data/stores/vector_index"

mlflow:
  tracking_uri: "mlruns"
  experiment_name: "clinical-summarization-mvp"

api:
  host: "0.0.0.0"
  port: 8000
  cors_origins: ["http://localhost:3000"]
```

---

## 6. Environment Variables (`.env`)

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # Fallback
MLFLOW_TRACKING_URI=mlruns
DATA_DIR=data
LOG_LEVEL=INFO
```

---

## 7. Data Flow Summary

```
EHR JSON
  → [C1] Validate schema (pydantic) | de-identify PII | normalize viết tắt
  → [C2] Chunk thành SourceChunks theo semantic unit
          + Build structured store (dict: source_id → chunk)
          + Build FAISS vector index (embed noi_dung với prefix "passage: ")
  → [C3] Per section: Hybrid retrieval (BM25 + vector → RRF)
  → [C4] Per section: LLM call với evidence chunks embedded in context
          (source_id inline để C5 có thể extract)
  → [C5] Per section: extract claims → NLI match → attach citations
  → [C6] Apply business rules (KEEP/REMOVE/FLAG) → FinalSummary + metrics
  → [FastAPI] Serve JSON + source lookup
  → [Next.js] Render + citation click → source panel
  → [MLflow] Log run (model, prompt_version, metrics)
```

---

## 8. Component Interface Summary

| From → To | Interface |
|-----------|-----------|
| C1 → C2 | `safe_ehr: dict` (validated, de-id, normalized) |
| C2 → C3+C5 | `List[SourceChunk]` + 2 stores |
| C3 → C4 | `{section_id: List[SourceChunk]}` |
| C4 → C5 | `{section_id: draft_text}` |
| C5 → C6 | `{section_id: List[CitedClaim]}` |
| C6 → API | `FinalSummary` |
| API → UI | JSON (`/summarize/{id}` + `/source/{id}`) |

---

## 9. Môi trường setup

```bash
# Python env
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install pydantic fastapi uvicorn faiss-cpu chromadb \
            sentence-transformers rank-bm25 anthropic openai \
            mlflow pytest python-dotenv pyyaml

# Verify embedding model (download ~1.2GB)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-large')"

# Next.js UI
cd ui && npx create-next-app@latest . --typescript --tailwind --app --no-git

# MLflow server (local)
mlflow ui --host 0.0.0.0 --port 5000
```
