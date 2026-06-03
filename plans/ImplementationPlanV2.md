# Implementation Plan V2 — Clinical Summarization & Citation Pipeline
**Author:** Đào Anh Quân | **Solo** | **Strategy:** PARTNER (MVP)
**Cập nhật từ V1 sau nhận xét mentor Tuần 1**

---

## Tóm tắt nhận xét mentor & điều chỉnh

**Điểm mạnh đã được xác nhận:**
- PRD thiết kế production workflow, phân biệt AI-generated draft vs clinician-approved summary
- Citation grounding, HITL, audit logging, safety review đã được thiết kế đúng hướng
- Evaluation framework đa tầng đã có trong thiết kế

**Điều chỉnh chính cho giai đoạn tiếp theo:**

| Nhận xét mentor | Hành động cụ thể |
|----------------|-----------------|
| "Phần lớn vẫn ở mức thiết kế sản phẩm" | Đưa PoC kỹ thuật lên ưu tiên #1 từ đầu Tuần 2 |
| "Benchmark các mô hình summarization" | Thêm Model Benchmark Sprint vào Tuần 3 |
| "Xây dựng citation verification pipeline" | Tách citation pipeline thành deliverable riêng với test harness |
| "Đánh giá trên bộ dữ liệu mục tiêu" | Chạy evaluation sớm từ Tuần 4, không chờ Tuần 5 |
| "Chứng minh tính khả thi của giải pháp" | Mỗi tuần có số liệu cụ thể chứng minh tiến độ |

---

## Lịch tổng quan

| Tuần | Milestone | Focus chính | Deliverable chứng minh khả thi |
|------|-----------|-------------|-------------------------------|
| 1 | PRD & Workflow ✅ | Design | PRD 8.5/10 (đã hoàn thành) |
| 2 | Dataset + PoC kỹ thuật | **Pipeline PoC chạy được** | End-to-end trên BN001, metrics đầu tiên |
| 3 | Baseline + Model Benchmark | **So sánh models** | Bảng benchmark ≥2 models/prompts |
| 4 | Citation Verification Pipeline | **Citation pipeline** | Citation accuracy ≥85% trên test set |
| 5 | Evaluation trên target dataset | **Đánh giá toàn diện** | Metrics trên ≥10 cases, error analysis |
| 6 | Final Demo + Report | Polish + demo | Demo live + final evaluation report |

---

## Tuần 2 — Dataset + PoC Kỹ Thuật

### Mục tiêu chính
Tuần này có 2 mục tiêu song song:
1. **Chuẩn bị dataset** (như V1, nhưng compact hơn — đủ để chạy PoC ngay)
2. **PoC kỹ thuật chạy được vào cuối tuần** — pipeline tối giản nhưng end-to-end

> **Thay đổi so với V1:** V1 thiết kế dataset 15-20 cases trước rồi mới code. V2 làm 5 golden cases trước, chạy PoC ngay trên đó, rồi mở rộng thêm 10 cases. Tiếp cận "narrow but deep" thay vì "broad then implement".

### Task 2.0 — Setup môi trường (ngày 1)

```bash
python -m venv .venv && source .venv/bin/activate
pip install pydantic fastapi uvicorn faiss-cpu chromadb \
            sentence-transformers rank-bm25 anthropic openai \
            mlflow pytest python-dotenv pyyaml pandas
```

**File setup cần xong trong ngày 1:**
- `src/schemas.py` — contract của toàn pipeline (giữ nguyên từ V1)
- `configs/config.yaml` — config LLM, embedding, retrieval
- `.env.example` — LLM API keys

### Task 2.1 — 5 Golden Cases (ngày 1-2)

Thay vì tạo đủ 15-20 cases ngay, tạo **5 golden cases** trước để unblock PoC:

| Case | Bệnh chính | Số visits | Mục đích trong PoC |
|------|-----------|-----------|---------------------|
| BN001 | ĐTĐ type 2 + THA + RLLPM | 1 visit | Happy path, benchmark baseline |
| BN002 | ĐTĐ type 2 | 3 visits | Test longitudinal summary |
| BN003 | THA đơn thuần | 2 visits | Test khi thiếu XN lipid |
| BN004 | ĐTĐ + RLLPM | 1 visit | Test không có dị ứng |
| BN005 | ĐTĐ type 2 | 2 visits | Edge case: thuốc thiếu liều, ICD mâu thuẫn |

Source: Dùng `data/vietnamese-clinic-data-seeds/` đã có làm template, bổ sung thêm multi-visit và edge cases.

Script tạo data: `notebooks/01_data_generation.ipynb`
- Dùng Claude API sinh variation từ BN001 template
- Kiểm tra thủ công tính nhất quán lâm sàng của 5 cases

### Task 2.2 — C1: EMR Integration (ngày 2-3)

Giữ nguyên thiết kế từ V1, ưu tiên chạy được trước khi tối ưu:

```
src/c1_emr/
├── validator.py      # Validate schema EHR JSON
├── deidentifier.py   # Mask PII fields
└── normalizer.py     # Chuẩn hóa viết tắt y khoa VN
```

**Acceptance criteria:**
```bash
python -c "
from src.c1_emr.validator import validate_ehr
from src.c1_emr.deidentifier import deidentify
from src.c1_emr.normalizer import normalize_text
import json
ehr = json.load(open('data/raw/BN001.json'))
valid, errors = validate_ehr(ehr)
assert valid, errors
safe = deidentify(ehr)
assert '[REDACTED]' in str(safe)
print('C1 OK')
"
```

### Task 2.3 — C2: Chunking + Stores (ngày 3-4)

```
src/c2_chunking/
├── chunker.py        # EHR → List[SourceChunk]
└── store_builder.py  # Build structured store + vector store
```

**Kiểm tra nhanh:**
- BN001 phải ra ≥20 chunks với source_id đúng format
- Structured store lookup bất kỳ source_id trong < 1ms

### Task 2.4 — PoC End-to-End (ngày 4-5)

**Đây là deliverable quan trọng nhất của Tuần 2.**

PoC tối giản: dùng LLM trực tiếp với toàn bộ chunks làm context, KHÔNG cần RAG hay citation phức tạp — mục tiêu là chứng minh pipeline chạy được.

```python
# poc/poc_pipeline.py
def run_poc(patient_id: str) -> dict:
    """
    1. Load + validate EHR
    2. De-identify + normalize
    3. Chunk → source chunks
    4. Format ALL chunks thành 1 context string
    5. Gọi LLM với system prompt + section prompts
    6. Parse output thành sections
    7. Gắn citation đơn giản: keyword matching với source_id
    8. Trả về dict {section: {text, citations}}
    """
```

**Chạy PoC trên BN001, ghi lại:**
- Latency (giây/case)
- Số sections sinh ra đủ không
- Có hallucination rõ ràng nào không (kiểm tra thủ công)
- Token count (estimate cost)

`notebooks/02_poc_analysis.ipynb`: So sánh output PoC với gold standard BN001

### Task 2.5 — Mở rộng dataset (song song, ngày 5-7)

Sau khi PoC chạy được, mở rộng thêm 10 cases:

| Cases | Edge case cần test |
|-------|--------------------|
| BN006–007 | Missing fields (không có XN, không có đơn thuốc) |
| BN008–009 | Nhiều chẩn đoán mâu thuẫn nhau |
| BN010–011 | Giá trị XN nguy hiểm (HbA1c > 12%, Kali 2.1 mmol/L) |
| BN012–013 | Tiếng Anh lẫn tiếng Việt trong clinical notes |
| BN014–015 | 5+ visits — test summary có tổng hợp xuyên suốt không |

### Checkpoint Tuần 2

| Checkpoint | Cách kiểm tra | Target |
|-----------|--------------|--------|
| PoC chạy end-to-end | `python poc/poc_pipeline.py --patient BN001` không crash | Pass |
| BN001 ra đủ 8 sections | Kiểm tra trong output JSON | 8/8 |
| Latency PoC | Đo bằng `time` | ≤ 60s (chấp nhận cho PoC) |
| Không hallucination rõ ràng | Manual review BN001-BN005 | 0 critical errors |
| 15 EHR JSONs tồn tại | `ls data/raw/BN*.json | wc -l` | ≥ 15 |
| Tests C1+C2 pass | `pytest tests/test_c1_emr.py tests/test_c2_chunking.py` | All green |

---

## Tuần 3 — Baseline RAG + Model Benchmark

### Mục tiêu chính
1. Nâng PoC lên RAG pipeline có retrieval thật sự
2. **Benchmark ≥2 models/prompt strategies** để chọn approach tốt nhất cho citation pipeline

> **Thêm mới so với V1:** Model Benchmark Sprint là deliverable bắt buộc. Không chỉ dùng 1 model mà phải so sánh và có số liệu cụ thể.

### Task 3.1 — C3: Retrieval Service (ngày 1-3)

Giữ nguyên thiết kế Hybrid RRF từ V1:

```
src/c3_retrieval/
├── keyword_retriever.py   # BM25
├── vector_retriever.py    # FAISS + multilingual-e5
└── hybrid_retriever.py    # RRF fusion
```

Optimization quan trọng: **Section-aware retrieval** — mỗi section dùng query khác nhau, filter theo source_type:

| Section | Preferred source_type | Query template |
|---------|----------------------|----------------|
| thuoc_hien_tai | thuoc | "thuốc đang dùng liều lượng cách dùng" |
| xn_bat_thuong | xet_nghiem | "xét nghiệm bất thường tăng cao giảm thấp" |
| chan_doan | chan_doan | "chẩn đoán bệnh chính bệnh kèm mã ICD" |
| di_ung | di_ung, tien_su | "dị ứng thuốc thức ăn phản ứng" |

### Task 3.2 — C4: Active Summarizer — RAG (ngày 2-4)

Giữ nguyên thiết kế từ V1 nhưng thêm **structured prompt output** để dễ parse citation sau:

```python
SECTION_PROMPTS_V1 = {
    "thuoc_hien_tai": """
[CONTEXT]
{evidence_text}

Liệt kê thuốc theo format (chỉ dùng thông tin trong [CONTEXT]):
• [source_id] | [Tên thuốc] [Hàm lượng] — [Liều], [Cách dùng]
Nếu thiếu liều → ghi "(thiếu thông tin liều)".
"""
}
# Bao gồm source_id inline để C5 extract citation dễ hơn
```

### Task 3.3 — Model Benchmark Sprint (ngày 3-6)

**Đây là deliverable bắt buộc theo yêu cầu mentor.**

#### 3.3.1 Benchmark dimensions

| Dimension | Cách đo | Metric |
|-----------|---------|--------|
| Factual accuracy | Manual spot-check 5 cases | % claims khớp source |
| Citation-ability | C5 extract được source_id không | % claims có citation |
| Hallucination rate | Claim không có trong source | % hallucinated claims |
| Vietnamese quality | Fluency + medical terminology | 1-5 rubric |
| Latency | Đo bằng `time` | giây/section |
| Token efficiency | Tokens/section | avg tokens |

#### 3.3.2 Các configuration cần benchmark

**Tier 1 — Prompt strategies (bắt buộc benchmark):**

| Config | Mô tả |
|--------|-------|
| `prompt_v1_zero_shot` | System prompt + section prompt, không có example |
| `prompt_v2_few_shot_1` | Thêm 1 gold example (BN001) |
| `prompt_v2_few_shot_3` | Thêm 3 gold examples (BN001, BN002, BN003) |
| `prompt_v3_structured_output` | Yêu cầu output JSON với source_id inline |
| `prompt_v4_chain_of_thought` | Thêm "hãy suy luận từng bước" trước khi output |

**Tier 2 — Models (benchmark nếu còn thời gian/budget):**

| Model | API | Ghi chú |
|-------|-----|---------|
| `claude-sonnet-4-6` | Anthropic | Model chính, dùng làm baseline |
| `gpt-4o-mini` | OpenAI | Cost comparison, tốc độ |
| `gpt-4o` | OpenAI | Quality comparison |

> Nếu hạn chế budget, benchmark ít nhất 2 prompt strategies trên cùng 1 model.

#### 3.3.3 Benchmark pipeline

```python
# notebooks/03_model_benchmark.ipynb

BENCHMARK_CASES = ["BN001", "BN002", "BN005"]  # Golden + multi-visit + edge
BENCHMARK_CONFIGS = ["prompt_v1_zero_shot", "prompt_v2_few_shot_1",
                     "prompt_v3_structured_output"]

results = {}
for case in BENCHMARK_CASES:
    for config in BENCHMARK_CONFIGS:
        summary = run_pipeline(case, config=config)
        results[(case, config)] = {
            "sections_complete": count_complete_sections(summary),
            "citation_parseable": count_parseable_citations(summary),
            "latency": summary.metrics["latency_seconds"],
            "token_count": summary.metrics["token_count"],
        }

# Export bảng benchmark ra CSV
# Chọn config tốt nhất → dùng làm default từ Tuần 4 trở đi
```

#### 3.3.4 Output benchmark

`reports/benchmark/benchmark_week3.md`:

```markdown
## Model Benchmark Results — Week 3

### Summary Table
| Config | Citation Rate | Hallucination | Latency | Cost/case |
|--------|--------------|---------------|---------|-----------|
| prompt_v1_zero_shot | X% | Y% | Zs | $A |
| prompt_v2_few_shot_1 | X% | Y% | Zs | $A |
| ...

### Winner: {config}
### Reason: ...
### Next steps: ...
```

### Task 3.4 — MLflow Tracking Setup (ngày 1)

```python
# src/mlflow_logger.py
import mlflow

def log_summary_run(patient_id: str, config: str, final_summary: FinalSummary):
    with mlflow.start_run(run_name=f"{patient_id}_{config}"):
        mlflow.log_param("patient_id", patient_id)
        mlflow.log_param("config", config)
        mlflow.log_param("model_version", final_summary.model_version)
        mlflow.log_param("prompt_version", final_summary.prompt_version)
        mlflow.log_metric("citation_coverage", final_summary.metrics["citation_coverage"])
        mlflow.log_metric("hallucination_rate", final_summary.metrics.get("hallucination_rate", 0))
        mlflow.log_metric("latency_seconds", final_summary.metrics["latency_seconds"])
        mlflow.log_artifact(f"data/outputs/{patient_id}_{config}.json")
```

### Checkpoint Tuần 3

| Checkpoint | Target |
|-----------|--------|
| RAG pipeline chạy BN001–BN005 | Đủ 8 sections, không crash |
| Benchmark table hoàn chỉnh | ≥2 configs so sánh trên ≥3 cases |
| Config winner được chọn | Có số liệu cụ thể justify lựa chọn |
| Latency ≤ 30s/case với config winner | Đo và log vào MLflow |
| MLflow có ≥10 runs | `mlflow ui` hiện được |

---

## Tuần 4 — Citation Verification Pipeline

### Mục tiêu chính
Build và validate citation verification pipeline. Đây là core differentiator của hệ thống.

> **Tăng cường so với V1:** V1 mô tả citation pipeline về mặt kỹ thuật. V2 thêm **test harness với labeled dataset** để có số liệu citation accuracy cụ thể.

### Task 4.0 — Chuẩn bị Citation Test Dataset (ngày 1)

Trước khi build C5/C6, cần dataset để đo accuracy của citation pipeline.

**Tạo `data/citation_test_set.jsonl`:**

```json
{"claim": "Bệnh nhân dùng Metformin 1000mg 2 viên/ngày", 
 "expected_source_ids": ["BN001_LK001_THUOC_T001"],
 "expected_status": "SUPPORTED",
 "is_critical": true}

{"claim": "HbA1c 9.2% vượt mức mục tiêu < 7.0%",
 "expected_source_ids": ["BN001_LK001_XN_HBA1C"],
 "expected_status": "SUPPORTED", 
 "is_critical": true}

{"claim": "Bệnh nhân dị ứng Penicillin",
 "expected_source_ids": ["BN001_LK001_DIUNG"],
 "expected_status": "SUPPORTED",
 "is_critical": true}

{"claim": "Bệnh nhân đã từng phẫu thuật tim",
 "expected_source_ids": [],
 "expected_status": "UNSUPPORTED",
 "is_critical": false}
# ... ≥30 labeled claims từ BN001-BN005
```

Target: ≥30 labeled claims, phân đều SUPPORTED / UNSUPPORTED / CONTRADICTED.

### Task 4.1 — C5: Citation Builder (ngày 1-4)

Giữ nguyên thiết kế từ V1:

```
src/c5_citation/
├── claim_extractor.py    # LLM → atomic claims
├── evidence_matcher.py   # NLI via LLM: claim + source → SUPPORTED/UNSUPPORTED/...
└── citation_builder.py   # Orchestrate + build CitedClaim objects
```

**Thêm mới: Confidence scoring**

```python
class EvidenceMatcher:
    def match(self, claim: str, candidates: list[SourceChunk]
              ) -> tuple[str, list[str], float]:
        """
        Returns: (status, source_ids, confidence_score)
        
        confidence_score:
        - SUPPORTED + high cosine similarity → 0.85-1.0
        - SUPPORTED + low cosine similarity → 0.60-0.84 → LOW_CONFIDENCE
        - PARTIAL → 0.50-0.75
        - UNSUPPORTED → 0.0-0.40
        
        Threshold từ PRD OQ-11: 0.85 → LOW_CONFIDENCE vs SUPPORTED
        """
```

### Task 4.2 — C6: Hallucination Verifier (ngày 3-5)

Giữ nguyên business rules từ V1. Thêm chi tiết về HITL flow:

```python
class HallucinationVerifier:
    def verify_and_finalize(self, ...):
        # Như V1, nhưng thêm:
        # - Track tất cả removed claims để log
        # - HITL: LOW_CONFIDENCE claims → cần doctor verification
        ...
    
    def get_hitl_queue(self, final_summary: FinalSummary) -> list[dict]:
        """
        Trả về danh sách claims cần bác sĩ xác nhận.
        Dùng cho demo: hiển thị prompt xác nhận trong UI.
        """
        return [
            {
                "claim_id": f"{section.section_id}_{i}",
                "claim_text": claim.claim_text,
                "source_ids": claim.citations,
                "confidence": claim.confidence_score,
                "status": claim.status,
            }
            for section in final_summary.sections
            for i, claim in enumerate(section.cited_claims)
            if claim.status in ("LOW_CONFIDENCE", "NEED_REVIEW")
        ]
```

### Task 4.3 — Citation Pipeline Test Harness (ngày 4-5)

**Đây là điểm mới quan trọng so với V1 — cần có số liệu citation accuracy.**

```python
# tests/test_citation_accuracy.py

def test_citation_pipeline_accuracy():
    """
    Chạy citation pipeline trên labeled test set.
    So sánh predicted vs expected.
    """
    test_cases = load_json("data/citation_test_set.jsonl")
    results = []
    
    for tc in test_cases:
        pred_status, pred_sources, _ = matcher.match(
            tc["claim"],
            load_chunks_for_patient(tc["patient_id"])
        )
        results.append({
            "correct_status": pred_status == tc["expected_status"],
            "correct_source": any(s in pred_sources 
                                  for s in tc["expected_source_ids"])
        })
    
    citation_accuracy = sum(r["correct_status"] for r in results) / len(results)
    source_precision = sum(r["correct_source"] for r in results) / len(results)
    
    print(f"Citation Status Accuracy: {citation_accuracy:.1%}")
    print(f"Source ID Precision: {source_precision:.1%}")
    
    # Target từ PRD: Citation Accuracy ≥ 85%
    assert citation_accuracy >= 0.80, f"Citation accuracy {citation_accuracy:.1%} < 80% threshold"
```

### Task 4.4 — Pipeline Orchestrator (ngày 5)

Như V1 — wire tất cả components lại với nhau trong `src/pipeline.py`.

### Checkpoint Tuần 4

| Checkpoint | Target | Cách đo |
|-----------|--------|---------|
| Citation accuracy trên test set | ≥ 80% | `pytest tests/test_citation_accuracy.py -v` |
| BN001 citation coverage | ≥ 85% | `summary.metrics["citation_coverage"]` |
| BN005 edge case: ICD mâu thuẫn bị detect | Pass | Manual review + test |
| HITL queue hoạt động | LOW_CONFIDENCE claims được list ra | Unit test |
| All tests pass | Green | `pytest tests/` |
| MLflow có ≥5 runs so sánh | Có thể xem comparison | `mlflow ui` |

---

## Tuần 5 — Evaluation Trên Target Dataset

### Mục tiêu chính
Chạy evaluation toàn diện trên ≥10 cases, có số liệu cụ thể chứng minh tính khả thi.

> **Thay đổi so với V1:** V1 để evaluation chủ yếu trong Tuần 5. V2 đẩy evaluation sớm hơn với test harness từ Tuần 4, và Tuần 5 tập trung vào **tổng hợp insights + iterate**.

### Task 5.1 — Full Evaluation Run (ngày 1-2)

Chạy pipeline trên toàn bộ 15 cases, ghi lại metrics:

```python
# notebooks/05_full_evaluation.ipynb

EVAL_CASES = [f"BN{i:03d}" for i in range(1, 16)]

all_metrics = []
for case in EVAL_CASES:
    try:
        summary = pipeline.run(case)
        all_metrics.append({
            "patient_id": case,
            "citation_coverage": summary.metrics["citation_coverage"],
            "hallucination_rate": summary.metrics.get("hallucination_rate", 0),
            "unsupported_claim_rate": summary.metrics["unsupported_claim_rate"],
            "latency": summary.metrics["latency_seconds"],
            "sections_complete": len([s for s in summary.sections 
                                     if s.noi_dung and "Chưa thấy" not in s.noi_dung])
        })
    except Exception as e:
        all_metrics.append({"patient_id": case, "error": str(e)})

df = pd.DataFrame(all_metrics)
print(df.describe())
print(f"\nAvg Citation Coverage: {df['citation_coverage'].mean():.1%}")
print(f"Avg Hallucination Rate: {df['hallucination_rate'].mean():.1%}")
print(f"Avg Latency: {df['latency'].mean():.1f}s")
```

### Task 5.2 — Human Evaluation (ngày 2-4)

Chọn **10 cases** đại diện (mở rộng từ 5 của V1):

| Case | Lý do chọn | Điều cần kiểm tra |
|------|-----------|-------------------|
| BN001 | Golden case | Tổng thể chất lượng |
| BN002 | Multi-visit | Longitudinal coherence |
| BN003 | Thiếu XN lipid | Handling missing data |
| BN005 | ICD mâu thuẫn | Edge case detection |
| BN008 | Chẩn đoán mâu thuẫn | CONTRADICTED claim handling |
| BN010 | XN nguy hiểm | luu_y section quality |
| BN011 | Kali thấp | Critical lab flagging |
| BN012 | Mixed language | Normalization quality |
| BN014 | 5+ visits | Summary coherence dài |
| BN015 | 5+ visits khác | Consistency check |

**Human evaluation form:** Giữ nguyên từ PRD Section 9.1.2.

Với mỗi case, file đánh giá trong `eval/results/EVAL_{case}_v1.json`.

### Task 5.3 — Error Analysis (ngày 4-5)

```python
# notebooks/05_error_analysis.ipynb

# Load tất cả evaluation results
evals = [load_json(f"eval/results/EVAL_{c}_v1.json") for c in EVAL_CASES_HUMAN]

# Phân loại lỗi
error_types = Counter([e["type"] for ev in evals for e in ev["errors"]])
severity_dist = Counter([e["severity"] for ev in evals for e in ev["errors"]])

# Top 3 lỗi phổ biến nhất → prioritize fix trong Tuần 6
print("Top errors:")
for err_type, count in error_types.most_common(5):
    print(f"  {err_type}: {count} occurrences")

# So sánh prompt versions nếu đã thử ≥2 versions
if BENCHMARK_CONFIGS:
    compare_prompt_versions(BENCHMARK_CONFIGS, EVAL_CASES_HUMAN)
```

### Task 5.4 — Iterate dựa trên Error Analysis (ngày 5-7)

Dựa trên top lỗi, thực hiện **1-2 targeted fix**:

| Nếu top lỗi là | Fix được đề xuất |
|----------------|-----------------|
| Citation sai nguồn | Tinh chỉnh candidate filter trong C5 |
| Hallucination trong "luu_y" section | Thêm stricter guardrail trong system prompt |
| Viết tắt xử lý sai | Mở rộng abbreviation dictionary |
| Section "thuoc_hien_tai" thiếu liều | Cải thiện chunking cho medication |
| Latency cao | Cache embedding, reduce max_chunks_per_claim |

### Task 5.5 — FastAPI + Demo UI (song song, ngày 3-7)

**FastAPI (`api/main.py`):**

```python
@app.post("/summarize/{patient_id}")
async def summarize(patient_id: str, config: str = "default") -> dict:
    summary = pipeline.run(patient_id)
    return summary.dict()

@app.get("/source/{source_id}")
async def get_source(source_id: str) -> dict:
    return structured_store.get(source_id)

@app.get("/patients")
async def list_patients() -> list[str]:
    return list_available_patients()

@app.patch("/citation/{source_id}/verify")
async def verify_citation(source_id: str, body: VerificationRequest) -> dict:
    # HITL: bác sĩ xác nhận/từ chối citation
    return update_verification_status(source_id, body)
```

**Streamlit UI (`ui/app.py`)** — ưu tiên Streamlit cho MVP, nhanh hơn Next.js:

```python
# Trang chính
patient = st.selectbox("Chọn bệnh nhân", available_patients)
if st.button("Tạo tóm tắt"):
    with st.spinner("Đang xử lý..."):
        summary = call_api(f"/summarize/{patient}")
    
    # Hiển thị từng section
    for section in summary["sections"]:
        with st.expander(section["section_id"], expanded=True):
            st.write(section["noi_dung"])
            # Citation badges
            for claim in section["cited_claims"]:
                if claim["citations"]:
                    for src_id in claim["citations"]:
                        if st.button(f"[{src_id}]", key=src_id):
                            show_source_panel(src_id)
    
    # Metrics
    st.sidebar.metric("Citation Coverage", 
                      f"{summary['metrics']['citation_coverage']:.0%}")
    st.sidebar.metric("Latency", 
                      f"{summary['metrics']['latency_seconds']:.1f}s")
```

### Checkpoint Tuần 5

| Checkpoint | Target | Cách đo |
|-----------|--------|---------|
| Full evaluation 10 cases xong | Có file JSON | `ls eval/results/ | wc -l` ≥ 10 |
| Avg citation coverage | ≥ 85% | `df["citation_coverage"].mean()` |
| Avg hallucination rate | ≤ 10% (target ≤ 5% ở T6) | `df["hallucination_rate"].mean()` |
| Human Accuracy Score avg | ≥ 3.5/5 | `df["scores.correctness"].mean()` |
| Error analysis xong | Top 3 lỗi được identify | Notebook output |
| ≥1 targeted fix được implement | Pipeline cải thiện | Before/after comparison |
| FastAPI + Streamlit chạy | `uvicorn api.main:app --reload` không crash | Manual test |

---

## Tuần 6 — Final Demo + Report

### Mục tiêu chính
Polish, chạy final evaluation, chuẩn bị demo và report thể hiện tính khả thi đã được chứng minh.

### Task 6.1 — Fix các lỗi còn lại từ Tuần 5 (ngày 1-2)

- Xử lý tất cả edge cases từ error analysis
- Latency ≤ 30s/case (cache embedding nếu cần)
- Proper error handling ở mọi bước

### Task 6.2 — Hoàn thiện Demo UI (ngày 2-4)

**Features bắt buộc cho demo:**

```
✓ Dropdown chọn patient (5 demo cases)
✓ Loading indicator khi pipeline chạy
✓ Summary render với 8 sections rõ ràng
✓ Citation badges [source_id] clickable
✓ Citation panel hiện nội dung gốc khi click
✓ Allergy section highlight ⚠️ màu đỏ
✓ Metrics panel: citation coverage %, hallucination rate, latency
✓ Flag ⚠️ cho LOW_CONFIDENCE claims
✓ HITL: button "Xác nhận" / "Không khớp" cho low-confidence claims
```

**Nice-to-have:**
```
○ Side-by-side so sánh 2 prompt versions
○ Export summary JSON/Markdown
○ MLflow link trực tiếp từ UI
```

### Task 6.3 — Final Evaluation Run (ngày 3-4)

Chạy lại full evaluation 10 cases với pipeline đã cải thiện:
- So sánh metrics Tuần 5 vs Tuần 6
- Verify tất cả acceptance criteria trong PRD Section 10.1

**Final metrics checklist từ PRD Success Metrics:**

| Metric | Target PRD | Kết quả thực tế (ghi vào) |
|--------|-----------|--------------------------|
| Citation Coverage | ≥ 90% | ___ |
| Citation Accuracy | ≥ 85% | ___ |
| Unsupported Claim Rate | ≤ 10% | ___ |
| Hallucination Rate | ≤ 5% | ___ |
| Missing Section Rate | ≤ 5% | ___ |
| Human Accuracy Score | ≥ 4/5 | ___ |
| Human Usefulness Score | ≥ 4/5 | ___ |
| Demo Coverage | ≥ 5 cases | ___ |
| MVP Latency | ≤ 30s/case | ___ |

### Task 6.4 — Demo Script (ngày 5)

**Kịch bản demo 10 phút:**

```
1. (1 phút)  Giới thiệu bài toán + pipeline overview (dùng diagram)
2. (2 phút)  Demo BN001 — golden case, show citation click
3. (2 phút)  Demo BN005 — edge case, show verifier loại claim mâu thuẫn
4. (1 phút)  Demo BN010 — XN nguy hiểm, show luu_y section + flag
5. (2 phút)  Metrics dashboard: trước/sau iterate
6. (2 phút)  MLflow comparison: prompt_v1 vs best config
```

### Task 6.5 — Final Report (ngày 5-7)

`reports/submit/Report_Week_6-Dao_Anh_Quan-Final_Evaluation.md`:

**Cấu trúc report:**
1. Executive Summary — kết quả chứng minh tính khả thi
2. Technical Implementation — component diagram + code architecture
3. Model Benchmark Results — bảng so sánh từ Tuần 3
4. Citation Pipeline Accuracy — số liệu từ test harness
5. Full Evaluation Results — metrics trên 10 cases
6. Error Analysis — top lỗi, root cause, fix
7. Limitations & Next Steps — post-MVP roadmap

### Checkpoint Tuần 6 (Final)

| Checkpoint | Target |
|-----------|--------|
| Pipeline chạy ≥5 patients không crash | Pass |
| Latency ≤ 30s/case | Pass |
| Citation Coverage ≥ 90% trên golden case | Pass |
| Hallucination Rate ≤ 5% | Pass |
| Human Accuracy Score ≥ 4/5 | Pass |
| UI demo không lỗi trong 10 phút | Pass |
| Final report có số liệu đầy đủ | Submit |

---

## Cấu trúc thư mục dự án

```
MedicalRecordSummarization/
├── data/
│   ├── raw/                    # EHR JSONs (BN001-BN015)
│   ├── processed/              # Validated + de-identified
│   ├── chunks/                 # Source chunks per patient
│   ├── stores/                 # Structured store + FAISS index
│   ├── citation_test_set.jsonl # Labeled dataset cho citation test
│   └── dictionaries/
│       └── medical_abbreviations_vi.json
├── src/
│   ├── schemas.py              # Pydantic models — contract toàn pipeline
│   ├── c1_emr/                 # EMR Integration
│   ├── c2_chunking/            # Chunking Service
│   ├── c3_retrieval/           # Retrieval (BM25 + Vector + Hybrid)
│   ├── c4_summarizer/          # Active Summarizer + Prompts
│   ├── c5_citation/            # Citation Builder
│   ├── c6_verifier/            # Hallucination Verifier + HITL
│   ├── c7_eval/                # Evaluation + Metrics
│   └── pipeline.py             # Orchestrator
├── poc/
│   └── poc_pipeline.py         # PoC tối giản (Tuần 2)
├── api/
│   └── main.py                 # FastAPI endpoints
├── ui/
│   └── app.py                  # Streamlit demo UI
├── eval/
│   ├── cases/                  # Eval packages (ehr + output)
│   └── results/                # Human evaluation JSONs
├── notebooks/
│   ├── 01_data_generation.ipynb
│   ├── 02_poc_analysis.ipynb
│   ├── 03_model_benchmark.ipynb
│   ├── 04_citation_pipeline.ipynb
│   └── 05_full_evaluation.ipynb
├── tests/
│   ├── test_c1_emr.py
│   ├── test_c2_chunking.py
│   ├── test_c3_retrieval.py
│   ├── test_c4_summarizer.py
│   ├── test_c5_citation.py
│   ├── test_c6_verifier.py
│   ├── test_citation_accuracy.py  # Test harness với labeled data (MỚI)
│   └── test_pipeline.py
├── reports/
│   ├── benchmark/
│   │   └── benchmark_week3.md     # Model benchmark results (MỚI)
│   └── submit/
│       ├── Report_Week_1-...PRD.md
│       └── Report_Week_6-...Final.md
├── plans/
│   ├── ImplementationPlanV1.md
│   └── ImplementationPlanV2.md    # File này
├── configs/
│   └── config.yaml
└── mlruns/                        # MLflow tracking
```

---

## Cost Estimate (LLM API) — cập nhật

| Phase | Calls/patient | Tokens/call | Total/patient |
|-------|--------------|-------------|---------------|
| C4 Summarizer (8 sections) | 8 | ~2K in + 300 out | ~18K tokens |
| C5 Claim extraction (8 sections) | 8 | ~500 + 200 | ~5.5K tokens |
| C5 Evidence matching (~40 claims × 3 chunks) | 120 | ~300 + 10 | ~37K tokens |
| C3 Benchmark (5 configs × 5 cases × 8 sections) | 200 extra | ~2K in + 300 out | ~460K tokens (one-time) |
| **Total / patient (production pipeline)** | | | **~60K tokens** |

20 patients × 3 iterations + benchmark = ~**4M tokens total**

Claude Sonnet: ~$3/1M input + $15/1M output (ratio 80/20) ≈ **~$15–20 total**

*Có thể giảm 50%+ bằng cách cache embedding và batch evidence matching.*

---

## Decision Log (V1 → V2)

| Ngày | Quyết định | Lý do |
|------|-----------|-------|
| Tuần 1 | PARTNER strategy, RAG + LLM API | Timeline 6 tuần, dataset nhỏ |
| Tuần 1 | Citation chunk-level cho MVP | Cân bằng khả thi vs truy vết |
| V2 Update | Thêm PoC tối giản vào Tuần 2 | Mentor: cần chứng minh kỹ thuật ngay |
| V2 Update | Model Benchmark Sprint thành deliverable bắt buộc | Mentor: benchmark các mô hình summarization |
| V2 Update | Citation test harness với labeled dataset | Mentor: cần số liệu citation accuracy cụ thể |
| V2 Update | Streamlit thay Next.js cho demo UI | Next.js tốn thời gian setup, Streamlit đủ cho MVP |
| V2 Update | Đẩy evaluation từ T5 sang T4 (test harness) | Phát hiện lỗi sớm hơn để có thời gian iterate |

---

*V2 — Cập nhật sau nhận xét mentor Tuần 1. Focus shift: Design → Technical Proof of Concept + Benchmark + Evaluation.*
