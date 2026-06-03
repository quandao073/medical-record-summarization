# PLAN 02 — Active Summarizer (C4)
**Component:** C4 Active Summarizer  
**Tuần chính:** Tuần 3  
**Interface:** `{section_id: List[SourceChunk]}` → `{section_id: draft_text}`

---

## 1. Overview

Active Summarizer là component sinh ra draft summary text cho từng section lâm sàng. Nó nhận evidence chunks từ Retriever (C3), inject vào prompt, gọi LLM, và trả về text ngắn gọn theo chuẩn tiếng Việt y khoa.

**Nguyên tắc thiết kế:**
- Mỗi section gọi LLM độc lập → dễ debug, dễ retry từng section
- Source ID được inject inline vào context → C5 có thể extract citation sau
- Không để LLM tự suy diễn — chỉ được paraphrase context, không được thêm thông tin

---

## 2. Chunking Strategy (C2 output → C4 input)

Mỗi chunk = 1 fact có thể cite độc lập. Quy tắc:

### 2.1 Source ID Convention

```
Format: {patient_id}_{visit_id}_{TYPE}_{ITEM_IDENTIFIER}

Ví dụ:
  BN001_LK001_XN_HBA1C          ← 1 xét nghiệm = 1 chunk
  BN001_LK001_XN_GLUCOSE
  BN001_LK001_THUOC_T001        ← 1 thuốc = 1 chunk
  BN001_LK001_THUOC_T002
  BN001_LK001_CHANDOAN_E11      ← 1 chẩn đoán = 1 chunk
  BN001_LK001_CHANDOAN_I10
  BN001_LK001_TIEUSU_BANTHAN    ← Tiền sử bản thân = 1 chunk/visit
  BN001_LK001_TIEUSU_GIADINH
  BN001_LK001_DIUNG             ← Dị ứng = 1 chunk/visit
  BN001_LK001_KHAM_SINHHIEU     ← Sinh hiệu nhóm lại thành 1 chunk
  BN001_LK001_KHAM_TOANPHAN     ← Khám toàn thân
  BN001_LK001_KHAM_TIMMACH      ← Khám từng cơ quan (nếu có)
  BN001_LK001_CDHA_SIENAM       ← CĐHA
  BN001_LK001_CDHA_ECG
  BN001_LK001_GHICHU_BACSI      ← Ghi chú bác sĩ (tổng hợp cuối visit)
  BN001_LK001_HANHCHINH         ← Thông tin hành chính (1 chunk/bệnh nhân)
  BN001_LK001_LYDOVAOVIEN
  BN001_LK001_BENHSU
```

### 2.2 Chunking Rules per Data Type

| Source Type | Granularity | `noi_dung` format |
|------------|-------------|-------------------|
| `xet_nghiem` | 1 xét nghiệm = 1 chunk | `{ten_xn}: {ket_qua} {don_vi} (tham chiếu: {range}). {nhan_xet}` |
| `thuoc` | 1 thuốc = 1 chunk | `{ten_thuoc} {ham_luong}: {lieu}, {cach_dung}, {so_ngay} ngày` |
| `chan_doan` | 1 chẩn đoán = 1 chunk | `{loai}: {ten_benh} ({ma_icd10}) — {chan_doan}` |
| `tien_su` | 1 loại/visit = 1 chunk | `Tiền sử {loai}: {noi_dung}` |
| `di_ung` | 1 chunk/visit | `Dị ứng đã biết: {join(di_ung)}` |
| `sinh_hieu` | Nhóm thành 1 chunk | `M:{mach}, HA:{huyet_ap}, T:{nhiet_do}, SpO2:{spo2}%, CN:{can_nang}kg` |
| `cdha` | 1 kỹ thuật = 1 chunk | `{loai_xet_nghiem}: {ket_luan}` |
| `ghi_chu` | 1 chunk/visit | `Ghi chú BS: {ghi_chu_bac_si}` |
| `hanh_chinh` | 1 chunk/patient | `BN {ho_ten}, {tinh_tuoi}, {gioi_tinh}. Nghề: {nghe_nghiep}` |
| `ly_do_kham` | 1 chunk/visit | `Lý do vào viện: {ly_do_vao_vien}` |
| `benh_su` | 1 chunk/visit | `Bệnh sử: {benh_su}` |

### 2.3 Special Rules

```python
def is_abnormal(xn: dict) -> bool:
    """
    Rule đơn giản cho MVP — không parse range phức tạp.
    Dùng nhan_xet field từ EHR nếu có.
    """
    nhan_xet = xn.get("nhan_xet", "").lower()
    keywords = ["tăng", "cao", "giảm", "thấp", "bất thường",
                "chưa đạt", "vượt", "cảnh báo"]
    return any(k in nhan_xet for k in keywords)

# Metadata per source_type
METADATA_SCHEMA = {
    "xet_nghiem": {
        "bat_thuong": bool,      # is_abnormal()
        "ten_xn": str,
        "ket_qua": float | str,
        "don_vi": str,
        "nhan_xet": str,
    },
    "thuoc": {
        "ten_thuoc": str,
        "ham_luong": str,
        "ly_do_dieu_chinh": str,  # Nếu có
    },
    "chan_doan": {
        "ma_icd10": str,
        "loai": str,             # "benh_chinh" | "benh_kem_theo_X"
    },
    "tien_su": {
        "loai_tien_su": str,     # "ban_than" | "gia_dinh"
    },
    "cdha": {
        "loai_cdha": str,        # "sieu_am" | "ecg" | "xray" | ...
    }
}
```

---

## 3. Retrieval Strategy (C3 → C4 evidence)

### 3.1 Section → Source Type Mapping

| Section | Priority source_types | Fallback |
|---------|----------------------|---------|
| `tong_quan` | hanh_chinh, tien_su, sinh_hieu | chan_doan |
| `ly_do_kham` | ly_do_kham, benh_su | — |
| `tien_su` | tien_su, di_ung, chan_doan (lịch sử) | ghi_chu |
| `thuoc_hien_tai` | thuoc | ghi_chu |
| `di_ung` | di_ung | tien_su, ghi_chu |
| `xn_bat_thuong` | xet_nghiem (bat_thuong=true first), cdha | — |
| `chan_doan` | chan_doan | ghi_chu |
| `luu_y` | xet_nghiem (bat_thuong), di_ung, chan_doan, tien_su, sinh_hieu | ghi_chu |

### 3.2 Section-Specific Queries (tiếng Việt)

```python
SECTION_QUERIES = {
    "tong_quan":      "thông tin bệnh nhân tuổi giới bệnh nền chính BMI thể trạng",
    "ly_do_kham":     "lý do vào viện triệu chứng chính khiếu nại mệt mỏi",
    "tien_su":        "tiền sử bệnh nền phẫu thuật dị ứng gia đình bản thân mắc bệnh",
    "thuoc_hien_tai": "thuốc đang dùng liều lượng cách dùng tên thuốc hàm lượng",
    "di_ung":         "dị ứng thuốc thức ăn phản ứng quá mẫn Penicillin",
    "xn_bat_thuong":  "xét nghiệm bất thường tăng cao giảm thấp HbA1c glucose LDL creatinine",
    "chan_doan":       "chẩn đoán bệnh chính bệnh kèm mã ICD-10 kết luận",
    "luu_y":          "cảnh báo nguy cơ biến chứng điểm quan trọng lưu ý theo dõi",
}

TOP_K_PER_SECTION = {
    "tong_quan": 5,
    "ly_do_kham": 4,
    "tien_su": 8,
    "thuoc_hien_tai": 8,    # Có thể nhiều thuốc
    "di_ung": 3,
    "xn_bat_thuong": 12,    # Nhiều XN
    "chan_doan": 5,
    "luu_y": 12,            # Tổng hợp nhiều nguồn
}
```

---

## 4. System Prompt Design

### 4.1 System Prompt (cố định cho tất cả sections)

```python
SYSTEM_PROMPT = """Bạn là hệ thống hỗ trợ bác sĩ Việt Nam tóm tắt hồ sơ bệnh án điện tử.

NGUYÊN TẮC BẮT BUỘC — vi phạm bất kỳ nguyên tắc nào là lỗi nghiêm trọng:
1. CHỈ dùng thông tin có trong phần [DỮ LIỆU BỆNH ÁN]. Không suy luận, không thêm thông tin ngoài context.
2. Nếu không có thông tin cho section: ghi chính xác "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
3. KHÔNG kê đơn, KHÔNG chẩn đoán thêm, KHÔNG gợi ý điều trị.
4. Giữ NGUYÊN mã ICD-10, tên thuốc, hàm lượng, giá trị số từ dữ liệu.
5. Không thêm disclaimer AI, không giải thích quy trình, không thêm ý kiến cá nhân.
6. Output ngắn gọn, chuẩn lâm sàng. Bác sĩ cần đọc nhanh trong 1-2 phút.
7. Các source_id dạng [BN001_LK001_XN_HBA1C] trong dữ liệu là nhãn truy xuất — KHÔNG đưa vào output.

Bạn đang tóm tắt section: {section_name_vi}"""
```

### 4.2 Per-Section User Prompts

```python
SECTION_PROMPTS = {

    "tong_quan": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Viết Tổng quan bệnh nhân (tối đa 2-3 câu ngắn):
- Tuổi, giới, bệnh nền chính (tên bệnh, thời gian mắc)
- BMI / thể trạng nếu có trong dữ liệu
Không liệt kê thuốc hay kết quả XN ở đây.""",

    "ly_do_kham": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Viết Lý do khám (1-2 câu):
- Lý do vào viện chính
- Triệu chứng hiện tại nếu có""",

    "tien_su": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Liệt kê Tiền sử bệnh:
- Bệnh nền (tên bệnh, thời gian mắc)
- Phẫu thuật (nếu có)
- Tiền sử gia đình (nếu có)
Không liệt kê dị ứng ở đây (có section riêng).""",

    "thuoc_hien_tai": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Liệt kê thuốc đang dùng theo format (1 dòng/thuốc):
• [Tên thuốc] [Hàm lượng] — [Liều], [Cách dùng]
Nếu thiếu thông tin liều → thêm "(thiếu thông tin liều)".
Giữ nguyên tên thuốc, hàm lượng từ dữ liệu.""",

    "di_ung": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Liệt kê dị ứng đã biết:
• [Chất gây dị ứng]: [Phản ứng nếu biết]
Nếu không có dữ liệu: ghi "Chưa thấy ghi nhận dị ứng trong dữ liệu được cung cấp."
ĐÂY LÀ THÔNG TIN CRITICAL — không được bỏ sót nếu có trong dữ liệu.""",

    "xn_bat_thuong": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Liệt kê xét nghiệm/CĐHA bất thường (chỉ kết quả THỰC SỰ bất thường trong dữ liệu):
• [Tên XN]: [Giá trị] [Đơn vị] ↑/↓ (tham chiếu: [range])
Chỉ liệt kê kết quả nằm ngoài khoảng tham chiếu. Bỏ qua kết quả bình thường.
Giữ nguyên giá trị số và đơn vị.""",

    "chan_doan": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Liệt kê chẩn đoán:
Bệnh chính: [Tên bệnh] ([Mã ICD-10])
Bệnh kèm 1: [Tên bệnh] ([Mã ICD-10])
...
Dùng đúng tên bệnh và mã ICD-10 từ dữ liệu — không tự chỉnh sửa.""",

    "luu_y": """[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Liệt kê điểm bác sĩ cần lưu ý (bullet points):
• Kết quả XN chưa đạt mục tiêu (nếu có)
• Biến chứng hoặc dấu hiệu cần theo dõi (nếu có)
• Cảnh báo dị ứng (nếu có)
• Nguy cơ lâm sàng tổng hợp (chỉ từ dữ liệu)
KHÔNG gợi ý điều trị hay thay đổi thuốc.""",
}
```

### 4.3 Evidence Injection Format

```python
def build_user_prompt(section_id: str, chunks: list[SourceChunk]) -> str:
    """
    Mỗi chunk được format: "[source_id] noi_dung"
    Source ID được embed trong context để C5 có thể tham chiếu.
    Chunks được sắp xếp theo ngày (mới nhất lên đầu) — LLM thường chú ý hơn đến đầu prompt.
    """
    # Sort: mới nhất → cũ nhất
    sorted_chunks = sorted(chunks, key=lambda c: c.ngay or date.min, reverse=True)
    
    evidence_lines = []
    for chunk in sorted_chunks:
        ngay_str = chunk.ngay.strftime("%d/%m/%Y") if chunk.ngay else "N/A"
        evidence_lines.append(f"[{chunk.source_id}] ({ngay_str}) {chunk.noi_dung}")
    
    evidence_text = "\n".join(evidence_lines)
    template = SECTION_PROMPTS[section_id]
    return template.format(evidence_text=evidence_text)
```

---

## 5. Model Configuration

```python
LLM_CONFIG = {
    "anthropic": {
        "model": "claude-sonnet-4-5",    # Thử claude-sonnet-4-6 nếu có access
        "max_tokens": 500,               # Đủ cho 1 section ngắn gọn
        "temperature": 0.1,              # Gần deterministic — y tế không cần creative
        "top_p": 0.9,
        "stop_sequences": [],            # Không cần stop sequences với Anthropic
    },
    "openai": {                          # Fallback
        "model": "gpt-4o",
        "max_tokens": 500,
        "temperature": 0.1,
    }
}

SECTIONS_ORDER = [
    "tong_quan",      # 1. Tổng quan
    "ly_do_kham",     # 2. Lý do khám
    "tien_su",        # 3. Tiền sử
    "thuoc_hien_tai", # 4. Thuốc đang dùng
    "di_ung",         # 5. Dị ứng — CRITICAL
    "xn_bat_thuong",  # 6. XN bất thường
    "chan_doan",       # 7. Chẩn đoán
    "luu_y",          # 8. Điểm cần lưu ý
]
```

---

## 6. Summarizer Implementation

```python
# src/c4_summarizer/summarizer.py
import anthropic
import time
from src.schemas import SourceChunk
from src.c4_summarizer.prompt_templates import (
    SYSTEM_PROMPT, SECTIONS_ORDER, build_user_prompt
)

class ActiveSummarizer:
    def __init__(self, config: dict):
        self.config = config
        self.client = anthropic.Anthropic()
        self.max_retries = 3
        self.base_delay = 1.0       # seconds

    def summarize_section(
        self,
        section_id: str,
        chunks: list[SourceChunk],
        section_name_vi: str
    ) -> str:
        if not chunks:
            return "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
        
        system = SYSTEM_PROMPT.format(section_name_vi=section_name_vi)
        user_msg = build_user_prompt(section_id, chunks)
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model=self.config["llm"]["model"],
                    max_tokens=self.config["llm"]["max_tokens"],
                    temperature=self.config["llm"]["temperature"],
                    system=system,
                    messages=[{"role": "user", "content": user_msg}]
                )
                return response.content[0].text.strip()
            
            except anthropic.RateLimitError:
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay * (2 ** attempt))
                else:
                    raise
            except anthropic.APITimeoutError:
                if attempt < self.max_retries - 1:
                    time.sleep(self.base_delay)
                else:
                    raise

    def summarize_patient(
        self,
        patient_id: str,
        section_chunks: dict[str, list[SourceChunk]]
    ) -> dict[str, str]:
        """
        Input: {section_id: [chunks]}
        Output: {section_id: draft_text}
        """
        SECTION_NAMES_VI = {
            "tong_quan":      "Tổng quan bệnh nhân",
            "ly_do_kham":     "Lý do khám hiện tại",
            "tien_su":        "Tiền sử bệnh",
            "thuoc_hien_tai": "Thuốc đang sử dụng",
            "di_ung":         "Dị ứng",
            "xn_bat_thuong":  "Xét nghiệm bất thường",
            "chan_doan":      "Chẩn đoán",
            "luu_y":          "Điểm cần lưu ý",
        }
        
        results = {}
        for section_id in SECTIONS_ORDER:
            chunks = section_chunks.get(section_id, [])
            name_vi = SECTION_NAMES_VI[section_id]
            results[section_id] = self.summarize_section(
                section_id, chunks, name_vi
            )
        return results
```

---

## 7. Serving Architecture

### 7.1 FastAPI Endpoint

```python
# api/main.py
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from src.pipeline import Pipeline
from src.schemas import FinalSummary, SourceChunk

app = FastAPI(title="Clinical Summarization API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = Pipeline.from_config("configs/config.yaml")

@app.post("/api/v1/summarize/{patient_id}", response_model=FinalSummary)
async def summarize_patient(patient_id: str):
    """
    Chạy full pipeline cho patient_id.
    Trả FinalSummary JSON với citations và metrics.
    Latency target: ≤ 30 giây.
    """
    try:
        result = pipeline.run(patient_id)
        return result
    except FileNotFoundError:
        raise HTTPException(404, f"Không tìm thấy EHR cho {patient_id}")
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/v1/source/{source_id}")
async def get_source(source_id: str) -> dict:
    """
    Citation viewer: trả SourceChunk gốc khi bác sĩ click citation.
    O(1) lookup từ structured store.
    """
    chunk = pipeline.structured_store.get(source_id)
    if not chunk:
        raise HTTPException(404, f"source_id {source_id} không tìm thấy")
    return chunk

@app.get("/api/v1/patients")
async def list_patients() -> list[str]:
    """Danh sách patient_id có trong hệ thống (cho dropdown UI)"""
    return pipeline.list_patients()

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "model": pipeline.config["llm"]["model"]}
```

### 7.2 Request/Response Flow

```
Next.js UI
  → POST /api/v1/summarize/BN001
  ← FinalSummary JSON (≤30s)

User clicks [BN001_LK001_XN_HBA1C]
  → GET /api/v1/source/BN001_LK001_XN_HBA1C
  ← {source_id, source_type, ngay, noi_dung, metadata}
```

### 7.3 Chạy local

```bash
# Backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd ui && npm run dev
# → http://localhost:3000

# API docs
# → http://localhost:8000/docs
```

---

## 8. Performance & Cost

### 8.1 Latency Breakdown (target ≤ 30s/patient)

| Step | Estimated time |
|------|---------------|
| C1 (validate + deidentify + normalize) | ~0.1s |
| C2 (chunk + embed + index) | ~3-5s (embedding 20-30 chunks) |
| C3 (retrieve 8 sections) | ~0.5s (FAISS fast) |
| C4 (8 LLM calls × 1-3s each) | ~10-15s |
| C5 (claim extraction + NLI matching) | ~8-12s |
| C6 (verify + finalize) | ~0.1s |
| **Total** | **~22-33s** |

**Optimization nếu cần:**
- Cache embedding (skip C2 nếu patient đã được process)
- Batch LLM calls nếu API hỗ trợ
- Giảm `max_chunks_per_claim` trong C5 (3 → 2)

### 8.2 Token Cost per Patient

| Step | Input tokens | Output tokens |
|------|-------------|--------------|
| C4: 8 section calls | 8 × ~1,500 = 12,000 | 8 × ~200 = 1,600 |
| C5: claim extraction (8×) | 8 × ~500 = 4,000 | 8 × ~300 = 2,400 |
| C5: NLI matching (~40 claims × 3) | 120 × ~250 = 30,000 | 120 × ~10 = 1,200 |
| **Tổng/patient** | **~46,000 input** | **~5,200 output** |

Claude Sonnet pricing ($3/M input + $15/M output):
- Per patient: ~$0.14 + ~$0.08 = **~$0.22/patient**
- 20 patients × 3 iterations = **~$13 total**

---

## 9. Tests

```python
# tests/test_c4_summarizer.py

def test_empty_chunks_returns_default_message():
    """Không có evidence → "Chưa thấy ghi nhận..." không crash"""
    summ = ActiveSummarizer(config)
    result = summ.summarize_section("di_ung", [], "Dị ứng")
    assert result == "Chưa thấy ghi nhận trong dữ liệu được cung cấp."

def test_drug_name_preserved_verbatim():
    """Tên thuốc không được tự động sửa"""
    chunk = make_thuoc_chunk("Metformin", "1000mg")
    result = summ.summarize_section("thuoc_hien_tai", [chunk], "Thuốc")
    assert "Metformin" in result
    assert "1000mg" in result

def test_icd10_preserved_verbatim():
    """Mã ICD-10 giữ nguyên"""
    chunk = make_chandoan_chunk("E11", "Đái tháo đường type 2")
    result = summ.summarize_section("chan_doan", [chunk], "Chẩn đoán")
    assert "E11" in result

def test_all_8_sections_generated():
    """summarize_patient trả đủ 8 sections"""
    section_chunks = {s: [] for s in SECTIONS_ORDER}
    result = summ.summarize_patient("BN001", section_chunks)
    assert set(result.keys()) == set(SECTIONS_ORDER)

def test_no_hallucinated_drug_in_output():
    """LLM không thêm thuốc không có trong context"""
    chunks = [make_thuoc_chunk("Metformin", "1000mg")]
    result = summ.summarize_section("thuoc_hien_tai", chunks, "Thuốc")
    # Nếu prompt đúng, không nên có thuốc khác xuất hiện
    assert "Amlodipine" not in result   # Chỉ đúng nếu không có trong chunk
    assert "Insulin" not in result

def test_llm_timeout_retries(mocker):
    """Timeout → retry 3 lần → raise"""
    mocker.patch.object(anthropic.Anthropic, "messages.create",
                        side_effect=anthropic.APITimeoutError())
    with pytest.raises(anthropic.APITimeoutError):
        summ.summarize_section("tong_quan", [make_hanh_chinh_chunk()], "Tổng quan")
```

---

## 10. Fine-tune Option (Optional — chỉ làm nếu còn thời gian)

Chỉ thực hiện nếu RAG baseline hoàn thành trước thứ 5 Tuần 3.

```
Model: Qwen2.5-3B-Instruct (≤8GB VRAM với 4-bit quantization)
Method: QLoRA (r=16, alpha=32, dropout=0.1)

Dataset format:
  Input:  [SYSTEM_PROMPT] + [USER_PROMPT với evidence]
  Output: [Expected summary text]
  Cần ≥50 (input, output) pairs — sinh bằng GPT-4o/Claude rồi review thủ công

Training config:
  batch_size: 2
  gradient_accumulation: 8  (effective batch = 16)
  epochs: 3
  lr: 2e-4
  scheduler: cosine

Evaluation: BERTScore (F1) giữa fine-tuned output vs RAG baseline output
Decision: nếu BERTScore tăng < 0.02 → không đáng — giữ RAG baseline

Libraries: transformers + peft + bitsandbytes
```
