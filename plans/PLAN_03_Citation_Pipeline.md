# PLAN 03 — Citation Pipeline (C5)
**Component:** C5 Citation Builder  
**Tuần chính:** Tuần 4  
**Interface:** `{section_id: draft_text}` + `List[SourceChunk]` → `{section_id: List[CitedClaim]}`

---

## 1. Overview

Citation Pipeline có nhiệm vụ:
1. **Claim Extraction:** Tách draft summary text thành atomic claims (1 fact = 1 claim)
2. **Evidence Matching:** Match mỗi claim với source chunks → xác định SUPPORTED / PARTIAL / UNSUPPORTED / CONTRADICTED
3. **Citation Attachment:** Gắn source_id vào mỗi claim → `CitedClaim`

**Nguyên tắc thiết kế:**
- LLM-as-judge cho cả 2 bước (extraction + NLI) — không dùng cosine threshold alone vì medical text cần semantic understanding
- Cost control: pre-filter candidates bằng cosine similarity trước khi gọi NLI
- Critical claims (thuốc/XN/chẩn đoán/dị ứng) được xử lý nghiêm ngặt hơn

---

## 2. Claim Extraction (`src/c5_citation/claim_extractor.py`)

### 2.1 Định nghĩa Atomic Claim

```
Atomic claim = 1 fact có thể verify độc lập, không phụ thuộc vào context khác.

Ví dụ section "thuoc_hien_tai":
  Input text: "Metformin 1000mg 2 viên/ngày sau ăn. Empagliflozin 10mg 1 viên sáng."

  Đúng (atomic):
    - "Bệnh nhân đang dùng Metformin 1000mg, 2 viên/ngày, uống sau ăn"  [is_critical: true]
    - "Bệnh nhân đang dùng Empagliflozin 10mg, 1 viên sáng"             [is_critical: true]

  Sai (không atomic):
    - "Bệnh nhân đang dùng Metformin và Empagliflozin"  (1 claim chứa 2 facts)
```

### 2.2 is_critical Classification

```
is_critical = True nếu claim liên quan đến:
  - Tên thuốc VÀ liều lượng
  - Kết quả xét nghiệm cụ thể (số + đơn vị)
  - Chẩn đoán / mã ICD-10
  - Dị ứng thuốc / thức ăn
  - Giá trị sinh hiệu bất thường

is_critical = False nếu:
  - Mô tả chung (thể trạng, tuổi, nghề nghiệp)
  - Tiền sử mơ hồ không có thời gian/giá trị cụ thể
  - Chuỗi "Bác sĩ lưu ý..." không có fact cụ thể
```

### 2.3 Extraction Prompt

```python
CLAIM_EXTRACTION_PROMPT = """Tách đoạn summary y tế sau thành danh sách atomic claims.

Quy tắc:
- Mỗi claim = 1 fact độc lập, có thể verify riêng bằng hồ sơ bệnh án
- Giữ nguyên tên thuốc, giá trị số, mã ICD-10, đơn vị
- is_critical = true nếu claim liên quan: tên thuốc+liều, kết quả XN+số, chẩn đoán/ICD-10, dị ứng
- Không tạo claim mới — chỉ tách, không diễn giải thêm

Output JSON array (CHỈ JSON, không giải thích, không markdown):
[
  {{"claim": "...", "is_critical": true}},
  {{"claim": "...", "is_critical": false}}
]

Summary text:
{summary_text}"""

def extract_claims(summary_text: str, llm_client) -> list[dict]:
    """
    Gọi LLM để extract claims.
    Parse JSON output.
    Fallback nếu JSON malformed: treat toàn bộ text là 1 claim non-critical.
    """
    if not summary_text or summary_text.strip() == "Chưa thấy ghi nhận trong dữ liệu được cung cấp.":
        return []

    prompt = CLAIM_EXTRACTION_PROMPT.format(summary_text=summary_text)
    response_text = llm_client.call(
        prompt=prompt,
        max_tokens=800,
        temperature=0.0   # Deterministic cho structured output
    )

    try:
        claims = json.loads(response_text)
        # Validate structure
        validated = []
        for c in claims:
            if isinstance(c, dict) and "claim" in c and "is_critical" in c:
                validated.append({
                    "claim": str(c["claim"]),
                    "is_critical": bool(c["is_critical"])
                })
        return validated
    except (json.JSONDecodeError, KeyError, TypeError):
        # Fallback: 1 claim từ toàn bộ text
        return [{"claim": summary_text, "is_critical": False}]
```

### 2.4 Expected Output per Section

| Section | Avg claims | Critical % |
|---------|-----------|-----------|
| tong_quan | 3-4 | ~30% |
| ly_do_kham | 2-3 | ~10% |
| tien_su | 4-6 | ~40% |
| thuoc_hien_tai | N (= số thuốc) | ~100% |
| di_ung | 1-2 | ~100% |
| xn_bat_thuong | N (= số XN bất thường) | ~100% |
| chan_doan | N (= số chẩn đoán) | ~100% |
| luu_y | 4-7 | ~60% |

---

## 3. Evidence Matching (`src/c5_citation/evidence_matcher.py`)

### 3.1 Pre-filtering (Cost Optimization)

Trước khi gọi LLM NLI, pre-filter candidates bằng cosine similarity:

```python
def prefilter_candidates(
    claim: str,
    all_chunks: list[SourceChunk],
    section_id: str,
    top_n: int = 5,
    embedder = None
) -> list[SourceChunk]:
    """
    1. Filter by source_type nếu section có mapping rõ ràng
    2. Cosine similarity claim vs chunk.noi_dung
    3. Return top-n closest
    """
    # Step 1: Type filter
    TYPE_FILTER = {
        "thuoc_hien_tai": ["thuoc"],
        "xn_bat_thuong":  ["xet_nghiem", "cdha"],
        "chan_doan":       ["chan_doan"],
        "di_ung":         ["di_ung", "tien_su", "ghi_chu"],
    }
    allowed_types = TYPE_FILTER.get(section_id, None)
    if allowed_types:
        candidates = [c for c in all_chunks if c.source_type in allowed_types]
    else:
        candidates = all_chunks

    if not candidates:
        return []

    # Step 2: Cosine similarity
    claim_embed = embedder.encode(f"query: {claim}", normalize_embeddings=True)
    chunk_embeds = embedder.encode(
        [f"passage: {c.noi_dung}" for c in candidates],
        normalize_embeddings=True
    )
    scores = chunk_embeds @ claim_embed  # cosine sim (normalized)
    top_idx = scores.argsort()[-top_n:][::-1]
    return [candidates[i] for i in top_idx if scores[i] > 0.4]  # Min threshold
```

### 3.2 NLI Prompt

```python
NLI_PROMPT = """Bạn là chuyên gia kiểm tra tính xác thực của thông tin y tế.

[NGUỒN DỮ LIỆU GỐC]:
{source_text}

[CLAIM CẦN KIỂM TRA]:
{claim_text}

Câu hỏi: NGUỒN DỮ LIỆU GỐC có hỗ trợ (support) CLAIM không?

Tiêu chí:
- SUPPORTED: NGUỒN có đủ thông tin để xác nhận CLAIM là đúng
- PARTIAL: NGUỒN có liên quan nhưng chỉ support một phần CLAIM
- UNSUPPORTED: NGUỒN không đề cập hoặc không đủ thông tin
- CONTRADICTED: NGUỒN nói điều ngược lại với CLAIM

Trả lời đúng 1 từ: SUPPORTED / PARTIAL / UNSUPPORTED / CONTRADICTED"""

def nli_check(claim: str, source_chunk: SourceChunk, llm_client) -> str:
    """Return một trong 4 labels."""
    prompt = NLI_PROMPT.format(
        source_text=source_chunk.noi_dung,
        claim_text=claim
    )
    response = llm_client.call(prompt=prompt, max_tokens=10, temperature=0.0)
    label = response.strip().upper()
    if label not in ["SUPPORTED", "PARTIAL", "UNSUPPORTED", "CONTRADICTED"]:
        return "UNSUPPORTED"  # Default safe
    return label
```

### 3.3 Evidence Matching Logic

```python
MAX_CHUNKS_PER_CLAIM = 3  # Cost control — không NLI quá nhiều chunks

def match_evidence(
    claim: str,
    candidates: list[SourceChunk],
    llm_client
) -> tuple[str, list[str]]:
    """
    Input: claim text + pre-filtered candidates (≤MAX_CHUNKS_PER_CLAIM)
    Output: (overall_status, list_of_supporting_source_ids)
    
    Logic:
    1. Gọi NLI cho từng candidate (tối đa MAX_CHUNKS_PER_CLAIM)
    2. CONTRADICTED từ bất kỳ candidate → kết quả CONTRADICTED
    3. Có ít nhất 1 SUPPORTED → kết quả SUPPORTED + collect source_ids
    4. Chỉ có PARTIAL → kết quả PARTIAL + collect source_ids
    5. Còn lại → UNSUPPORTED
    """
    if not candidates:
        return ("NO_CITATION", [])

    results = []
    for chunk in candidates[:MAX_CHUNKS_PER_CLAIM]:
        label = nli_check(claim, chunk, llm_client)
        results.append((label, chunk.source_id))

    # Priority: CONTRADICTED > SUPPORTED > PARTIAL > UNSUPPORTED
    labels = [r[0] for r in results]

    if "CONTRADICTED" in labels:
        return ("CONTRADICTED", [])

    supported_ids = [sid for lbl, sid in results if lbl == "SUPPORTED"]
    if supported_ids:
        return ("SUPPORTED", supported_ids)

    partial_ids = [sid for lbl, sid in results if lbl == "PARTIAL"]
    if partial_ids:
        return ("PARTIAL", partial_ids)

    return ("UNSUPPORTED", [])
```

---

## 4. Citation Builder Orchestrator (`src/c5_citation/citation_builder.py`)

```python
class CitationBuilder:
    def __init__(self, config: dict, llm_client, embedder):
        self.config = config
        self.llm = llm_client
        self.embedder = embedder
        self.max_chunks = config["citation"]["max_chunks_per_claim"]

    def build_cited_section(
        self,
        section_id: str,
        draft_text: str,
        all_chunks: list[SourceChunk]
    ) -> list[CitedClaim]:
        # Step 1: Extract atomic claims
        claims_raw = extract_claims(draft_text, self.llm)

        if not claims_raw:
            return []  # Empty section (e.g., "Chưa thấy ghi nhận...")

        cited_claims = []
        for c in claims_raw:
            # Step 2: Pre-filter candidates
            candidates = prefilter_candidates(
                claim=c["claim"],
                all_chunks=all_chunks,
                section_id=section_id,
                top_n=self.max_chunks,
                embedder=self.embedder
            )

            # Step 3: NLI match
            status, source_ids = match_evidence(c["claim"], candidates, self.llm)

            cited_claims.append(CitedClaim(
                claim_text=c["claim"],
                status=status,
                citations=source_ids,
                is_critical=c["is_critical"]
            ))

        return cited_claims

    def build_all_sections(
        self,
        draft_sections: dict[str, str],
        all_chunks: list[SourceChunk]
    ) -> dict[str, list[CitedClaim]]:
        result = {}
        for section_id, draft_text in draft_sections.items():
            result[section_id] = self.build_cited_section(
                section_id, draft_text, all_chunks
            )
        return result
```

---

## 5. Output Format

### 5.1 CitedClaim Examples

```python
# SUPPORTED — claim có source
CitedClaim(
    claim_text="Bệnh nhân đang dùng Metformin 1000mg, 2 viên/ngày, uống sau ăn sáng và tối",
    status="SUPPORTED",
    citations=["BN001_LK001_THUOC_T001"],
    is_critical=True
)

# PARTIAL — source có nhưng không đủ
CitedClaim(
    claim_text="HbA1c kiểm soát kém trong 3 tháng gần đây",
    status="PARTIAL",
    citations=["BN001_LK001_XN_HBA1C"],
    is_critical=True
)

# UNSUPPORTED — không tìm thấy evidence
CitedClaim(
    claim_text="Bệnh nhân có khả năng biến chứng tim mạch trong tương lai",
    status="UNSUPPORTED",
    citations=[],
    is_critical=False
)

# CONTRADICTED — source nói ngược lại
CitedClaim(
    claim_text="Creatinine bình thường",
    status="CONTRADICTED",
    citations=[],
    is_critical=True
)
# (Nếu source thực ra nói creatinine tăng cao)
```

### 5.2 Section-level Output

```json
{
  "thuoc_hien_tai": [
    {
      "claim_text": "Bệnh nhân đang dùng Metformin 1000mg, 2 viên/ngày",
      "status": "SUPPORTED",
      "citations": ["BN001_LK001_THUOC_T001"],
      "is_critical": true
    },
    {
      "claim_text": "Bệnh nhân đang dùng Empagliflozin 10mg, 1 viên sáng",
      "status": "SUPPORTED",
      "citations": ["BN001_LK001_THUOC_T002"],
      "is_critical": true
    }
  ],
  "xn_bat_thuong": [
    {
      "claim_text": "HbA1c: 9.2% (mục tiêu < 7.0%)",
      "status": "SUPPORTED",
      "citations": ["BN001_LK001_XN_HBA1C"],
      "is_critical": true
    }
  ]
}
```

---

## 6. Tests

```python
# tests/test_c5_citation.py

class TestClaimExtractor:
    def test_extracts_atomic_drug_claims(self, llm_mock):
        text = "Metformin 1000mg 2 viên/ngày. Empagliflozin 10mg 1 viên sáng."
        claims = extract_claims(text, llm_mock)
        assert len(claims) == 2
        assert all(c["is_critical"] for c in claims)

    def test_drug_claim_is_critical(self, llm_mock):
        text = "Bệnh nhân đang dùng Amlodipine 5mg, 1 viên sáng"
        claims = extract_claims(text, llm_mock)
        assert claims[0]["is_critical"] is True

    def test_empty_section_returns_empty(self, llm_mock):
        text = "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
        claims = extract_claims(text, llm_mock)
        assert claims == []

    def test_handles_malformed_json_gracefully(self, llm_mock):
        llm_mock.response = "This is not JSON"
        text = "Some summary text"
        claims = extract_claims(text, llm_mock)
        # Fallback: 1 claim, non-critical
        assert len(claims) == 1
        assert claims[0]["is_critical"] is False

class TestEvidenceMatcher:
    def test_matching_drug_returns_supported(self, llm_mock, thuoc_chunk):
        llm_mock.response = "SUPPORTED"
        status, ids = match_evidence(
            "Bệnh nhân đang dùng Metformin 1000mg", [thuoc_chunk], llm_mock
        )
        assert status == "SUPPORTED"
        assert thuoc_chunk.source_id in ids

    def test_contradicted_takes_priority(self, llm_mock, chunks):
        llm_mock.responses = ["SUPPORTED", "CONTRADICTED", "PARTIAL"]
        status, ids = match_evidence("claim text", chunks[:3], llm_mock)
        assert status == "CONTRADICTED"
        assert ids == []

    def test_no_candidates_returns_no_citation(self, llm_mock):
        status, ids = match_evidence("claim text", [], llm_mock)
        assert status == "NO_CITATION"
        assert ids == []

    def test_max_chunks_limit_respected(self, llm_mock, many_chunks):
        llm_mock.responses = ["SUPPORTED"] * 10
        match_evidence("claim text", many_chunks, llm_mock)
        # Chỉ được gọi MAX_CHUNKS_PER_CLAIM = 3 lần
        assert llm_mock.call_count <= MAX_CHUNKS_PER_CLAIM

class TestCitationBuilder:
    def test_citation_coverage_golden_case(self, bn001_pipeline_output):
        """Golden case BN001 phải đạt ≥ 85% citation coverage"""
        all_claims = []
        for section_claims in bn001_pipeline_output.values():
            all_claims.extend(section_claims)
        
        supported = sum(1 for c in all_claims if c.status == "SUPPORTED")
        coverage = supported / len(all_claims)
        assert coverage >= 0.85

    def test_allergy_claim_is_critical(self, llm_mock):
        text = "Dị ứng Penicillin"
        claims = extract_claims(text, llm_mock)
        assert all(c["is_critical"] for c in claims)
```

---

## 7. Cost Analysis

| Operation | Calls/patient | Tokens/call | Total/patient |
|-----------|--------------|-------------|--------------|
| Claim extraction (8 sections) | 8 | ~500 in + ~300 out | ~6,400 tokens |
| NLI matching (avg 5 claims/section × 3 chunks) | 120 | ~300 in + ~10 out | ~37,200 tokens |
| **Total C5** | | | **~43,600 tokens** |

Optimization options:
1. Giảm `MAX_CHUNKS_PER_CLAIM` từ 3 → 2: tiết kiệm ~33%
2. Batch claim extraction (1 call cho tất cả sections): tiết kiệm ~7 calls
3. Skip NLI cho PARTIAL khi already have SUPPORTED candidate
