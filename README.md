# Medical Record Summarization

Pipeline tóm tắt bệnh án điện tử (EHR) tiếng Việt có citation grounding — mỗi thông tin trong summary đều được truy vết về nguồn dữ liệu gốc và xác minh tự động.

**Dự án thực tập — VSF Healthcare AI, Phase 3**

---

## Tổng quan

Hệ thống tự động tóm tắt hồ sơ bệnh án thành 9 sections có cấu trúc. Mỗi claim trong summary được liên kết với một source chunk (kết quả xét nghiệm, đơn thuốc, chẩn đoán, ghi chú lâm sàng) và gán trạng thái xác minh.

```
EHR JSON → C1 (Xử lý) → C2 (Chunk) → C3 (Retrieve) → LLM → C5 (Match) → C6 (Verify) → FinalSummary JSON
```

**Stack:** Python · OpenAI GPT-4o-mini · Next.js · FastAPI · Pydantic · Pytest

---

## Kết quả benchmark (Tuần 2, GPT-4o-mini)

| Chỉ số | Trước khi fix | Sau khi fix |
|---|---|---|
| Citation coverage | 67% | **90%** |
| Critical coverage | 89% | **93%** |
| Tin cậy thấp | 29% | **6%** |
| Hallucination | 0% | 0% |
| Tests | 158 pass | 158 pass |

---

## Cấu trúc dự án

```
.
├── data/
│   ├── raw/                  # Dữ liệu EHR synthetic (10 file JSON, 272 bản ghi)
│   └── dictionaries/         # Từ điển viết tắt y khoa tiếng Việt (42 từ)
├── src/
│   ├── schemas.py            # Pydantic models (15 schemas)
│   ├── c1_emr/               # Xử lý EHR: validate, de-identify, normalize, assemble
│   ├── c2_chunking/          # Chunker: 9 loại source type, 1 chunk = 1 đơn vị cite
│   ├── c3_retrieval/         # Rule-based retrieval per section
│   ├── c5_citation/          # Trích xuất claim + khớp evidence
│   ├── c6_verifier/          # Xác minh: KEEP / FLAG / REMOVE
│   └── c7_evaluation/        # (Tuần 3) Đánh giá tự động
├── poc/
│   └── poc_pipeline.py       # Runner end-to-end (C1→C6)
├── frontend/                 # Next.js UI (summary viewer, citation panel, metrics)
└── tests/                    # 158 unit tests (5 file)
```

---

## Bộ dữ liệu

4 bệnh nhân synthetic (P001–P004), mỗi người đại diện một kịch bản lâm sàng khác nhau:

| Bệnh nhân | Hồ sơ | Edge case |
|---|---|---|
| P001 | ĐTĐ type 2 + THA + RLLPM + microalbuminuria | Biến chứng thần kinh ngoại biên sớm |
| P002 | ĐTĐ + THA ổn định, không biến chứng | Negative case — không nên có cảnh báo |
| P003 | THA kháng trị + ĐTĐ mới chẩn đoán | Nhập viện cấp cứu ICD I16.1 (phân biệt với I10) |
| P004 | ĐTĐ + THA + hạ đường huyết nặng | Glucose 2.5 mmol/L critical, dị ứng thuốc không rõ loại |

Dữ liệu hoàn toàn synthetic (`is_synthetic: true`). Các trường PII là placeholder để test de-identification. Không có dữ liệu bệnh nhân thật.

---

## Chạy nhanh

**Yêu cầu:** Python 3.10+, Node.js 18+, `OPENAI_API_KEY`

```bash
# Cài đặt thư viện Python
pip install -r requirements.txt

# Chạy toàn bộ test suite
pytest tests/ -q

# Chạy pipeline cho 1 bệnh nhân
python -m poc.poc_pipeline --patient P001 --model gpt-4o-mini

# Chạy pipeline cho tất cả bệnh nhân
python -m poc.poc_pipeline --all-patients --model gpt-4o-mini

# Khởi động frontend (cần backend chạy tại :8000)
cd frontend && npm install && npm run dev
```

---

## Chi tiết các module

### C1 — Xử lý EHR
- **Assembler:** ghép 10 file JSON thô thành một `AssembledEHR` per bệnh nhân
- **Validator:** kiểm tra required fields, kiểu dữ liệu, tham chiếu encounter
- **De-identifier:** mask PII (tên → `[TÊN BỆNH NHÂN]`, CCCD → `[REDACTED]`, SĐT, địa chỉ, BHYT)
- **Normalizer:** mở rộng viết tắt y khoa tiếng Việt (ĐTĐ, THA, BN, RLLPM, ...)

### C2 — Chunking
Một chunk = một đơn vị có thể cite độc lập. 9 loại source type:
`patient_info` · `allergies` · `vitals` · `labs` · `medications` · `diagnoses` · `clinical_notes` · `imaging` · `procedures`

Mỗi chunk có `source_id` duy nhất và `metadata` structured để evidence matching.

### C3 — Retrieval
Lọc rule-based per section — không cần vector search cho EHR structured:
- Section hiện tại (medications, diagnoses): chỉ lần khám mới nhất
- Section lịch sử (medical_history, treatment_timeline): tất cả encounters, sắp theo thời gian
- Dị ứng & thông tin hành chính: luôn giữ (patient-level chunks, không bị encounter filter)

### C4 — LLM Summarization
- Model: `gpt-4o-mini` (mặc định) / `gpt-4o` (benchmark)
- Temperature: 0 (kết quả ổn định)
- 9 sections với hướng dẫn riêng bằng tiếng Việt
- System prompt: 15 quy tắc — không hallucinate, không kê đơn, giữ nguyên đơn vị đo lường

### C5 — Citation & Evidence Matching
Trích xuất atomic claims từ mỗi section, sau đó khớp từng claim với source chunks:
- **Exact match:** tên thuốc + hàm lượng, tên XN + giá trị, mã ICD
- **High overlap:** ≥70% từ khóa của claim xuất hiện trong chunk → SUPPORTED
- **Keyword match:** ≥2 token chung (tokenization nhận biết dấu câu)

### C6 — Verification
Gán trạng thái cho từng claim:

| Trạng thái | Ý nghĩa |
|---|---|
| `SUPPORTED` | Khớp chính xác hoặc high-overlap |
| `PARTIALLY_SUPPORTED` | Chỉ khớp keyword |
| `LOW_CONFIDENCE` | Evidence yếu |
| `NEED_REVIEW` | Có source nhưng cần bác sĩ xác nhận (vd: dị ứng chưa confirm) |
| `NO_CITATION` | Không tìm được evidence cho critical claim |
| `CONTRADICTED` | Evidence mâu thuẫn với claim |

---

## Giao diện (Frontend)

Next.js app theo mô hình T-C-R (Transparency · Control · Recovery):

- **MetricsBar** — coverage, critical coverage, tỷ lệ tin cậy thấp, latency, token count
- **SectionCard** — nội dung per section với citation badge inline (xanh=SUPPORTED, vàng=PARTIAL, đỏ=NO\_CITATION)
- **SourcePanel** — slide-over hiển thị nội dung gốc chunk + metadata structured
- **LabsTable / MedsTable / DiagnosesTable** — renderer chuyên biệt theo loại section

---

## Chi phí API

| Model | Chi phí/bệnh nhân | Chi phí/tháng (3.000 bệnh nhân) |
|---|---|---|
| GPT-4o-mini | ~$0.005 (~118 VND) | ~$14 (~355.000 VND) |
| GPT-4o | ~$0.079 (~1.974 VND) | ~$237 (~5.925.000 VND) |

---

## Tác giả

**Đào Anh Quân** — Thực tập VSF Healthcare AI, Phase 3
