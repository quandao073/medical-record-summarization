# Medical Record Summarization

Pipeline tóm tắt bệnh án điện tử (EHR) tiếng Việt có citation grounding — mỗi thông tin trong summary đều được truy vết về nguồn dữ liệu gốc và xác minh tự động.

**Dự án thực tập tại VSF - Khối y tế**

**Chương trình Đào tạo Nhân tài AI thực chiến - VinUni - VinGroup**

---

## Tổng quan

Hệ thống tự động tóm tắt hồ sơ bệnh án thành 9 sections có cấu trúc. Mỗi claim trong summary được liên kết với source chunk (kết quả xét nghiệm, đơn thuốc, chẩn đoán, ghi chú lâm sàng) và gán trạng thái xác minh. Bác sĩ có thể click citation để xem nội dung gốc, review từng claim, và xác nhận summary.

```
EHR JSON → C1 (Xử lý) → C2 (Chunk) → C3 (Retrieve) → C4 (LLM) → C5 (Citation) → C6 (Verify) → FinalSummary
```

**Stack:** Python 3.11+ · FastAPI · Next.js 14 · PostgreSQL · Redis · Docker Compose · Nginx · Prometheus · Grafana · OpenAI / LM Studio / Ollama · Alembic · Pydantic · Pytest

---

## Kết quả

### Benchmark (gpt-4o-mini, 8 bệnh nhân)

| Chỉ số | Giá trị |
|---|---|
| Citation precision | **90.2%** |
| Citation recall | 84.7% |
| Critical precision | **92.5%** |
| Human eval (6 tiêu chí, 1 evaluator) | 4.23 / 5.0 |
| Latency | 5.3–8.1s / case |
| Tests | 435 pass |

### Multi-Run Benchmark (3 runs, gpt-4o-mini)

| Patient | Citation Precision | Critical Precision | Latency |
|---|---|---|---|
| P001 | 97.6% ± 0.1% | 100% | 8.1 ± 0.4s |
| P006 | 91.7% ± 1.2% | 91.9% | 6.8 ± 0.3s |
| P007 | 85.2% ± 2.0% | 100% | 5.7 ± 0.8s |
| P008 | 94.1% ± 0.0% | 100% | 5.3 ± 1.6s |

### Human Evaluation (8 bệnh nhân)

| Tiêu chí | Trọng số |
|---|---|
| Clinical Correctness | 25% |
| Completeness | 20% |
| Citation Faithfulness | 20% |
| Safety | 20% |
| Temporal Correctness | 10% |
| Readability | 5% |

Trung bình: **4.23 / 5.0** (1 evaluator, 8 patients × 6 criteria = 48 đánh giá)

---

## Chạy nhanh

### Docker (recommended)

```bash
# Set API key
echo "OPENAI_API_KEY=sk-..." > .env

# Start full stack
docker compose up --build -d

# Verify
curl http://localhost/health              # {"status":"alive"}
curl http://localhost/api/v1/patients     # 8 patients
open http://localhost                     # Frontend

# Teardown
docker compose down
```

### Local Model (LM Studio / Ollama on host)

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build -d
```

### Local Development

```bash
# Python backend
pip install -r requirements.txt
uvicorn api.main:app --reload                    # Terminal 1, port 8000

# Frontend
cd frontend && npm install && npm run dev        # Terminal 2, port 3000

# Pipeline CLI
python -m poc.poc_pipeline --patient P001 --model gpt-4o-mini
python -m poc.poc_pipeline --all-patients --model gpt-4o-mini

# Tests
pytest tests/ -q                                 # 435 tests

# Evaluation
python -m src.c7_evaluation.run_eval --all

# Multi-run benchmark
python -m scripts.run_multirun_benchmark --patients P001 P006 --models openai:gpt-4o-mini --n-runs 3
```

---

## Cấu trúc dự án

```
.
├── api/                           # FastAPI application
│   ├── main.py                    #   App, middleware, lifespan
│   ├── dependencies.py            #   LLM client dependency injection
│   ├── errors.py                  #   Error handlers (LLM→502, Circuit→503)
│   ├── middleware/                 #   Timeout, Rate Limiter, Request Tracing
│   └── routers/                   #   summary, sources, review, human_eval, health, metrics, tasks
├── src/
│   ├── schemas.py                 # Pydantic models (15+ schemas)
│   ├── c1_emr/                    # C1: EHR ingestion — validate, de-identify, normalize, assemble
│   ├── c2_chunking/               # C2: Chunking — 9 source types, 1 chunk = 1 citable unit
│   ├── c3_retrieval/              # C3: Section-wise retrieval (rule-based + optional vector re-rank)
│   ├── c4_llm_draft/              # C4: LLM summarizer + prompts (9 sections, tiếng Việt)
│   ├── c5_citation/               # C5: Claim extraction + evidence matching
│   ├── c6_verifier/               # C6: Verification — SUPPORTED / PARTIAL / CONTRADICTED
│   ├── c7_evaluation/             # C7: Gold label evaluation (precision, recall, critical)
│   ├── cache/                     # Two-tier cache: Redis (L1) + file JSON (L2)
│   ├── monitoring/                # Prometheus metrics (counters, histograms, gauges)
│   ├── tasks/                     # Background task store (in-memory, dedup, eviction)
│   ├── db/                        # Database engine, models, repositories, seed, timing
│   ├── llm/                       # LLM abstraction layer
│   │   ├── factory.py             #   create_llm_client() — auto-infer provider from model name
│   │   ├── providers/             #   OpenAI, Anthropic (Claude), LM Studio, Ollama
│   │   ├── circuit_breaker.py     #   CLOSED / OPEN / HALF_OPEN states
│   │   └── retry.py              #   Exponential backoff
│   └── logging_config.py          # Structured JSON logging
├── frontend/                      # Next.js 14 + TailwindCSS
│   ├── app/page.tsx               #   Main page — patient selector, model selector, summary viewer
│   ├── components/                #   14 components (SectionCard, SourcePanel, MetricsBar, ...)
│   └── lib/                       #   API client, types, models
├── configs/
│   └── config.yaml                # LLM provider, retrieval top_k, citation, verifier settings
├── data/
│   ├── raw/                       # EHR synthetic data (10 JSON files, 401 records)
│   ├── processed/                 # Assembled, stores, outputs
│   ├── human_eval/                # Human evaluation scores (8 patients)
│   └── benchmark/                 # Benchmark results + multi-run
├── eval/
│   ├── gold/                      # Gold labels (257 claims, 144 critical)
│   └── results/                   # C7 evaluation results per patient
├── scripts/                       # Benchmark, audit, multi-run scripts
├── poc/
│   └── poc_pipeline.py            # End-to-end pipeline runner (C1→C6)
├── monitoring/                    # Prometheus + Grafana configs & dashboards
├── migrations/                    # Alembic database migrations
├── tests/                         # 435 tests (32 test files)
├── docker-compose.yml             # Full stack: 7 services (DB, Redis, API, Frontend, Nginx, Prometheus, Grafana)
├── docker-compose.local.yml       # Override for local model access
├── Dockerfile                     # API image (Python 3.11-slim)
├── frontend/Dockerfile            # Frontend image (multi-stage, node:20-alpine)
└── nginx/nginx.conf               # Reverse proxy
```

---

## Bộ dữ liệu

8 bệnh nhân synthetic, 5 nhóm bệnh lý, 25 encounters, 401 bản ghi:

| Patient | Nhóm bệnh | Enc | Records | Edge Case |
|---|---|---|---|---|
| P001 | ĐTĐ type 2 + THA + RLLPM | 4 | 81 | Microalbuminuria, biến chứng thần kinh |
| P002 | ĐTĐ + THA ổn định | 3 | 40 | Negative case — không nên có cảnh báo |
| P003 | THA kháng trị + ĐTĐ | 5 | 91 | Nhập viện cấp cứu, thay đổi thuốc phức tạp |
| P004 | ĐTĐ + THA + hạ đường huyết | 3 | 38 | Glucose 2.5 critical, dị ứng thuốc |
| P005 | COPD + Suy tim | 3 | 54 | BNP trend 680→380, SpO2 84%, spirometry |
| P006 | CKD G3b + ĐTĐ | 2 | 44 | 3 dị ứng (1 unconfirmed→NEED_REVIEW) |
| P007 | Cường giáp Basedow | 3 | 31 | TSH trend 3 encounters, Methimazole titration |
| P008 | Loét dạ dày + GERD | 2 | 22 | H. pylori eradication workflow |

Dữ liệu hoàn toàn synthetic (`is_synthetic: true`). Không có dữ liệu bệnh nhân thật.

---

## Chi tiết các module

### C1 — Xử lý EHR
- **Assembler:** ghép 10 file JSON thô thành `AssembledEHR` per bệnh nhân
- **Validator:** kiểm tra required fields, kiểu dữ liệu, tham chiếu encounter
- **De-identifier:** mask PII (tên, CCCD, SĐT, địa chỉ, BHYT)
- **Normalizer:** mở rộng viết tắt y khoa tiếng Việt (ĐTĐ, THA, BN, RLLPM, ...)

### C2 — Chunking
Một chunk = một đơn vị có thể cite độc lập. 9 loại source type:
`patient_info` · `allergies` · `vitals` · `labs` · `medications` · `diagnoses` · `clinical_notes` · `imaging` · `procedures`

Mỗi chunk có `source_id` duy nhất và `metadata` structured để evidence matching.

### C3 — Retrieval
Lọc rule-based per section, config-driven `top_k` (`configs/config.yaml`). Hỗ trợ optional vector re-ranking:
- Section hiện tại (medications, reason_for_visit): chỉ lần khám mới nhất
- Section tích lũy (diagnoses, overview): tất cả encounters, dedup by ICD
- Section lịch sử (treatment_timeline, medical_history): tất cả encounters, chronological
- Section xu hướng (abnormal_labs): 2 encounters gần nhất + unique abnormal labs cũ

### C4 — LLM Summarization
- **Providers:** OpenAI (gpt-4o-mini, gpt-4o), Anthropic (Claude), LM Studio, Ollama
- **Temperature:** 0
- **9 sections** với hướng dẫn riêng bằng tiếng Việt
- **System prompt:** 15+ quy tắc — không hallucinate, không kê đơn, giữ nguyên đơn vị đo, atomic claims
- **Concurrent:** 9 sections song song qua `ThreadPoolExecutor`
- **Config:** provider/model qua `configs/config.yaml`, CLI args, hoặc API query params

### C5 — Citation & Evidence Matching
Trích xuất atomic claims từ mỗi section, khớp từng claim với source chunks:
- **Exact match:** tên thuốc + hàm lượng, tên XN + giá trị, mã ICD
- **High overlap:** ≥70% từ khóa của claim xuất hiện trong chunk → SUPPORTED
- **Keyword match:** ≥2 token chung → LOW_CONFIDENCE

### C6 — Verification
Gán trạng thái cho từng claim:

| Trạng thái | Ý nghĩa |
|---|---|
| `SUPPORTED` | Khớp chính xác hoặc high-overlap |
| `PARTIALLY_SUPPORTED` | Chỉ khớp keyword |
| `LOW_CONFIDENCE` | Evidence yếu |
| `NEED_REVIEW` | Có source nhưng cần bác sĩ xác nhận (vd: dị ứng chưa confirm) |
| `NO_CITATION` | Không tìm được evidence |
| `CONTRADICTED` | Evidence mâu thuẫn với claim |

Conservative mode (default): FLAG thay vì REMOVE — để bác sĩ quyết định.

### C7 — Gold Label Evaluation
- 254 gold claims (143 critical) across 8 patients
- Regex pattern matching: `claim_pattern` → `expected_source_ids`
- Metrics: `citation_precision`, `citation_recall`, `critical_precision`
- Audit script phân tách precision gaps vs recall gaps

---

## Giao diện (Frontend)

Next.js 14 app với 14 components, mô hình T-C-R (Transparency · Control · Recovery):

### Transparency
- **MetricsBar** — citation coverage, critical coverage, unsupported rate, latency
- **CitationBadge** — color-coded inline (xanh=SUPPORTED, vàng=PARTIAL, đỏ=UNSUPPORTED)
- **SourcePanel** — slide-over hiển thị nội dung gốc chunk + metadata structured
- **Raw Encounter View** — click "Xem bản ghi gốc" để xem full encounter data

### Control
- **Patient Selector** — chọn bệnh nhân (P001–P008)
- **Model Selector** — chọn LLM provider/model (OpenAI, LM Studio, Ollama)
- **Tech Mode** — toggle hiển thị thông tin kỹ thuật (source_id, model version, cache status)
- **Quick/Detail Mode** — toggle chế độ đọc tóm tắt / chi tiết

### Recovery
- **ClaimReviewButtons** — Approve / Edit / Flag từng claim
- **NeedsReviewSection** — hiển thị claims cần bác sĩ kiểm tra
- **SummaryActionBar** — Xác nhận / Lưu nháp / Gửi phản hồi
- **HumanEvalPanel** — đánh giá 6 tiêu chí (1–5) với error categorization

### Specialized Renderers
- **LabsTable** — xét nghiệm bất thường, reference range, trend
- **MedsTable** — thuốc hiện tại, liều, tần suất
- **DiagnosesTable** — ICD-10, loại chẩn đoán, active/inactive

---

## Deployment

### Docker Compose (production-like)

| Service | Image | Port | Mô tả |
|---|---|---|---|
| `db` | postgres:16-alpine | 5432 | PostgreSQL database |
| `redis` | redis:7-alpine | 6379 | Summary cache (L1), LRU 256MB |
| `api` | Python 3.11-slim + uvicorn (2 workers) | 8000 | FastAPI backend |
| `frontend` | Node.js 20 Alpine (standalone Next.js) | 3000 | Next.js 14 frontend |
| `nginx` | nginx:alpine | 80 | Reverse proxy |
| `prometheus` | prom/prometheus | 9090 | Metrics collection (scrape 15s) |
| `grafana` | grafana/grafana | 3001 | Dashboard (auto-provisioned, 7 panels) |

### Reliability

| Component | Mô tả |
|---|---|
| Request Tracing | `X-Request-ID` header, structured JSON logging |
| Timeout | 504 sau 120s (`asyncio.wait_for`) |
| Rate Limiter | Sliding window, 30 rpm, health endpoints excluded |
| Retry | Exponential backoff (configurable max_retries) |
| Circuit Breaker | CLOSED → OPEN → HALF_OPEN states |
| Error Handling | LLM→502, CircuitOpen→503, Validation→422 |
| Health Checks | `/health`, `/health/ready`, `/health/circuit-breakers` |

### API Endpoints

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/v1/patients` | Danh sách bệnh nhân |
| POST | `/api/v1/summarize/{patient_id}` | Chạy pipeline, trả summary |
| GET | `/api/v1/cache/{patient_id}` | Lấy summary từ cache |
| GET | `/api/v1/source/{source_id}` | Tra cứu source chunk |
| GET | `/api/v1/raw-encounter/{patient_id}/{encounter_id}` | Dữ liệu encounter gốc |
| GET/POST | `/api/v1/review/{patient_id}` | Doctor review workflow |
| GET/POST | `/api/v1/human-eval/{patient_id}` | Human evaluation scores |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/cache/stats` | Cache hit/miss statistics |
| POST | `/api/v1/cache/invalidate-all` | Xóa toàn bộ cache |
| DELETE | `/api/v1/cache/{patient_id}` | Xóa cache bệnh nhân |
| GET | `/api/v1/metrics` | Prometheus metrics |
| GET | `/api/v1/tasks/{task_id}` | Trạng thái background task |

---

## Chi phí API

| Model | Chi phí/case | 8 bệnh nhân |
|---|---|---|
| gpt-4o-mini | ~$0.003 | ~$0.024 |
| gpt-4o | ~$0.03 | ~$0.24 |
| LM Studio / Ollama | $0 (local) | $0 |

---

## Hạn chế

- Dữ liệu synthetic — chưa test với EMR thật (cần IRB approval)
- 1 evaluator cho human evaluation — không có inter-rater reliability
- Single-node Docker Compose — không horizontally scalable
- In-memory rate limiter và task store — reset khi restart API
- Summary là bản nháp — cần bác sĩ review trước khi sử dụng lâm sàng
- Citation partial/no-source claims được flag, không bị loại bỏ
