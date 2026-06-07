# Kế hoạch Tuần 3 — Nâng cấp chất lượng bản tóm tắt
**Medical Record Summarization — Citation Pipeline**
**Tác giả:** Đào Anh Quân | **Ngày tạo:** 2026-06-07
**Trọng tâm:** Chất lượng bản tóm tắt (độ chính xác, độ tin cậy citation, an toàn lâm sàng)

> Plan này thay thế phần "Tuần 3" trong `PLAN_Week3_Week4_ActionPlan.md` (đã lỗi thời).
> Lý do: C3/C5/C6 **đã hoàn thành** trong Tuần 2; pipeline đang dùng **gpt-4o-mini**
> (không migrate sang Claude theo quyết định dự án); frontend là **Next.js** (không phải Streamlit).

---

## 0. Trạng thái thực tế (đầu Tuần 3)

| Hạng mục | Trạng thái | Ghi chú |
|---|---|---|
| C1 EMR (assemble/validate/deid/normalize) | ✅ Done | |
| C2 Chunking (9 source types) | ✅ Done | 1 chunk = 1 đơn vị cite |
| C3 Retrieval (rule-based, per-section) | ✅ Done | patient-level chunks giữ qua encounter filter |
| C5 Claim Extractor + Evidence Matcher | ✅ Done | high-overlap ≥70%, punctuation-aware |
| C6 Verifier | ✅ Done | nhưng `verification_status` chưa ghi vào output |
| Benchmark gpt-4o-mini vs gpt-4o | ✅ Done | mini tốt hơn về citation: 90%/93% |
| 158 unit tests | ✅ Pass | |
| Frontend Next.js (T-C-R) | ✅ Done | MetricsBar, SectionCard, SourcePanel |
| C7 Evaluation | ❌ Trống | chỉ có docstring |
| FastAPI backend | ❌ Chưa có | (Tuần 4) |

**Số đo hiện tại (P004 — ca khó nhất):** coverage 83.3%, critical 84.2%, low-confidence 8.3%, hallucination 0%.

---

## 1. Phát hiện vấn đề chất lượng — từ output thực tế

Phân tích `data/processed/outputs/P004_summary.json` lộ ra **9 vấn đề chất lượng** cụ thể.
Đây là cơ sở để định hướng tuần 3 (không phải giả định).

| # | Vấn đề | Bằng chứng (P004) | Mức độ |
|---|---|---|---|
| Q1 | **Mâu thuẫn nội bộ không bị bắt** | `overview` ghi "ĐTĐ type 2", `reason_for_visit` ghi "ĐTĐ **type 1**" — cả hai đều `SUPPORTED` | 🔴 Nghiêm trọng |
| Q2 | **False SUPPORTED** | Claim "type 1" được gán SUPPORTED dù source là type 2 (high-overlap che lấp sai khác then chốt) | 🔴 Nghiêm trọng |
| Q3 | **Allergy → NO_CITATION sai** | Dị ứng "Thuốc/unknown" có source record nhưng bị `NO_CITATION` + `is_critical=true`; đúng phải là `NEED_REVIEW` | 🟠 Cao |
| Q4 | **Render dữ liệu thiếu/None thô** | `"phản ứng: None; mức độ: unknown"` — lộ giá trị English/null ra cho bác sĩ | 🟠 Cao |
| Q5 | **Claim trùng lặp** | `"Uống buổi sáng."` xuất hiện 2 lần trong `current_medications` | 🟡 Trung bình |
| Q6 | **Claim suy luận không match được** | `"Xu hướng: 7.8% xuống 7.5%, cải thiện"` → `UNSUPPORTED` (trend phải tính từ 2 lab values) | 🟡 Trung bình |
| Q7 | **Claim đa dữ kiện, citation thiếu** | Timeline `"HbA1c 7.8%, HA 142/90, glucose 8.2"` chỉ cite HBA1C, thiếu BP + glucose | 🟡 Trung bình |
| Q8 | **`verification_status` luôn PENDING** | C6 KEEP/FLAG/REMOVE không phản ánh vào JSON output → bác sĩ không thấy quyết định verify | 🟠 Cao |
| Q9 | **`confidence_score` luôn null** | Trường tồn tại trong schema nhưng không bao giờ điền | 🟡 Trung bình |

---

## 2. Mục tiêu Tuần 3

**Tiêu chí thành công (đo được):**

| ID | Mục tiêu | Hiện tại | Target |
|---|---|---|---|
| G1 | Critical citation coverage (trung bình 4 BN) | 93% | **≥ 95%** |
| G2 | **Precision** citation (SUPPORTED đúng / SUPPORTED tổng) — chỉ số mới | chưa đo | **≥ 95%** |
| G3 | Mâu thuẫn nội bộ bị phát hiện (Q1) | 0% bắt | **100% trên test case** |
| G4 | Allergy "cần xác nhận" → NEED_REVIEW (Q3) | sai | **đúng** |
| G5 | Claim trùng lặp (Q5) | có | **0** |
| G6 | `verification_status` ghi đúng vào output (Q8) | PENDING | **KEEP/FLAG/REMOVE** |
| G7 | Hallucination rate | 0% | **giữ 0%** |
| G8 | C7 auto-eval + LLM-as-judge chạy được | chưa có | **4 BN có điểm** |

**Nguyên tắc xuyên suốt:** *Ưu tiên precision hơn recall.* Một citation SUPPORTED sai
nguy hiểm hơn một claim bị FLAG thừa — bác sĩ tin "đã verify" rồi bỏ qua.

---

## 3. Hạng mục cải thiện chi tiết

### 3.1 [Q2, Q1] Contradiction-aware matching — chặn false SUPPORTED 🔴

**File:** `src/c5_citation/evidence_matcher.py`

Vấn đề: high-overlap ≥70% bỏ qua các "token then chốt" (negation, type number, đơn vị).
"ĐTĐ type **1**" vs "ĐTĐ type **2**" khác nhau 1 token nhưng overlap vẫn > 70% → SUPPORTED sai.

**Đề xuất:**
1. Định nghĩa **discriminative tokens** — nếu khác nhau thì KHÔNG được SUPPORTED:
   - Số phân loại bệnh: `type 1/2`, `độ I/II/III`, `giai đoạn`
   - Phủ định: `không`, `chưa`, `âm tính` vs `dương tính`
   - Con số đo lường + đơn vị (đã có một phần)
   - Mã ICD (so khớp chính xác)
2. Trước khi nâng lên SUPPORTED qua high-overlap, chạy `_has_conflicting_token(claim, chunk)`.
   Nếu có xung đột → hạ xuống `PARTIALLY_SUPPORTED` hoặc `CONTRADICTED`.

```python
def _has_conflicting_token(claim_text: str, chunk_text: str) -> bool:
    """True nếu claim và chunk chứa các giá trị phân biệt mâu thuẫn
    (type 1 vs 2, có/không, giá trị số khác nhau)."""
    ...
```

**Acceptance:**
- Claim "ĐTĐ type 1" với source "ĐTĐ type 2" → KHÔNG còn SUPPORTED
- Test: `test_conflicting_type_not_supported`, `test_negation_not_supported`

---

### 3.2 [Q1] Cross-section consistency check (C6) 🔴

**File:** `src/c6_verifier/verifier.py` (thêm bước hậu kiểm toàn cục)

Hiện C6 verify từng claim độc lập → không thấy `overview` (type 2) mâu thuẫn `reason_for_visit` (type 1).

**Đề xuất:** thêm `check_internal_consistency(sections)` chạy sau khi verify từng claim:
- Trích các "fact đối chiếu được" (loại bệnh, giá trị lab cùng tên + ngày, mã ICD chính)
- Nếu cùng một thực thể có 2 giá trị khác nhau giữa các section → gán `CONTRADICTED` cho claim yếu hơn + thêm vào `clinical_alerts` mục "⚠ Mâu thuẫn nội bộ".

**Acceptance:**
- P004 (nếu tái tạo lỗi type1/type2) → 1 cảnh báo mâu thuẫn được sinh ra
- Test: `test_internal_contradiction_flagged`

---

### 3.3 [Q3, Q4] Allergy NEED_REVIEW + render sạch 🟠

**File:** `src/c5_citation/evidence_matcher.py`, `src/c2_chunking/chunker.py` (render)

Vấn đề (Q3): dị ứng có `needs_patient_confirmation=true` và CÓ source allergy record,
nhưng matcher trả `NO_CITATION` (vì content rỗng/unknown) thay vì `NEED_REVIEW`.

**Đề xuất:**
1. Trong matcher: nếu claim thuộc section `allergies` **và** tồn tại allergy chunk cho bệnh nhân
   → status = `NEED_REVIEW`, citation = allergy chunk id (KHÔNG để rỗng).
2. Render (Q4): thay giá trị null/English bằng tiếng Việt:
   - `reaction: None` → "phản ứng: chưa rõ"
   - `severity: unknown` → "mức độ: chưa xác định"
   - `status: unknown` → "trạng thái: chưa xác nhận"

**Acceptance:**
- P004 allergy claim → `NEED_REVIEW` (không phải NO_CITATION), `is_critical=true`, có citation
- Không còn chuỗi "None"/"unknown" trong content
- Test: `test_allergy_unconfirmed_is_need_review`

---

### 3.4 [Q5] Khử trùng lặp claim 🟡

**File:** `src/c5_citation/claim_extractor.py`

"Uống buổi sáng." bị tách thành 2 claim giống hệt (Amlodipine + Losartan).

**Đề xuất:**
- Sau khi extract, gộp các claim có `claim_text` chuẩn hóa trùng nhau trong cùng section
  → 1 claim, union citations.
- Hoặc tốt hơn: cải thiện prompt để mỗi dòng thuốc là 1 claim hoàn chỉnh
  ("Amlodipine 5 mg — 1 viên/ngày, uống buổi sáng.") thay vì tách "Uống buổi sáng" rời.

**Acceptance:**
- Không có 2 claim `claim_text` trùng trong cùng section
- Test: `test_no_duplicate_claims_in_section`

---

### 3.5 [Q7] Multi-fact claim → multi-citation 🟡

**File:** `src/c5_citation/evidence_matcher.py`

Claim timeline chứa 3 dữ kiện (HbA1c, HA, glucose) nhưng chỉ cite 1 nguồn.

**Đề xuất:**
- Khi claim chứa nhiều giá trị số có đơn vị, match **từng** giá trị với chunk tương ứng,
  union tất cả citation tìm được.
- Nếu một dữ kiện không có nguồn → hạ status xuống `PARTIALLY_SUPPORTED` (minh bạch là cite chưa đủ).

**Acceptance:**
- Timeline claim "HbA1c..., HA..., glucose..." cite ≥ 2 nguồn khi có sẵn
- Test: `test_multifact_claim_collects_multiple_citations`

---

### 3.6 [Q8] Ghi `verification_status` vào output (C6) 🟠

**File:** `src/c6_verifier/verifier.py`, `poc/poc_pipeline.py`

Output JSON luôn `verification_status: "PENDING"` → quyết định KEEP/FLAG/REMOVE của C6 bị mất.

**Đề xuất:**
- C6 ghi `verification_status` ∈ {`KEEP`, `FLAG`, `REMOVE`} cho từng claim theo decision matrix.
- Pipeline serialize trường này. Frontend dùng để hiển thị badge (đã có chỗ render).
- Claim `REMOVE` (critical + không nguồn): ẩn khỏi content nhưng vẫn log trong `removed_claims`
  để audit (không xóa âm thầm).

**Acceptance:**
- Mọi claim trong output có `verification_status` ≠ PENDING
- Output có khối `removed_claims` (audit) nếu có claim bị remove
- Test: `test_verification_status_written`, `test_removed_claims_logged`

---

### 3.7 [Q9] Điền `confidence_score` 🟡

**File:** `src/c5_citation/evidence_matcher.py`

**Đề xuất:** map tier match → điểm số để frontend xếp hạng & lọc:
- exact metadata match → 1.0
- high-overlap (≥70%) → 0.8
- keyword (≥2 token) → 0.5
- weak → 0.3
- no match → 0.0

**Acceptance:**
- `confidence_score` không còn null cho claim đã match
- Test: `test_confidence_score_populated`

---

### 3.8 [Q6] Derived/trend claims 🟡 (tùy chọn — nếu còn thời gian)

**File:** `src/c5_citation/evidence_matcher.py`

"Xu hướng 7.8% → 7.5%, cải thiện" là claim **suy luận** từ 2 lab cùng tên khác ngày.

**Đề xuất:**
- Nhận diện pattern "X → Y" / "xu hướng" / "cải thiện/xấu đi".
- Nếu tìm được ≥ 2 lab cùng `test_name` khớp 2 giá trị → `SUPPORTED` với cả 2 citation.
- Verify chiều biến thiên (giảm = "cải thiện" với HbA1c) để chống đảo nghĩa.

**Acceptance:** trend claim hợp lệ → SUPPORTED với 2 citation, không còn UNSUPPORTED oan.

---

### 3.9 [G8] C7 — Auto-eval + LLM-as-judge

**File mới:** `src/c7_evaluation/evaluator.py`, `tests/test_c7_evaluation.py`

C7 hiện trống. Đây là phần "chứng minh tính khả thi bằng số" mentor yêu cầu (feedback tuần 1).

**Đề xuất 2 lớp:**

**Lớp A — Metrics tự động (rule-based, rẻ, deterministic):**
```text
citation_precision   = SUPPORTED đúng / SUPPORTED tổng   (cần gold labels)
citation_coverage    = (đã có)
critical_coverage    = (đã có)
contradiction_count  = số mâu thuẫn nội bộ
duplicate_claim_count
unsupported_critical_count
```

**Lớp B — LLM-as-judge (gpt-4o-mini, theo rubric):**
Chấm mỗi summary trên 5 tiêu chí (thang 1–5), output JSON có lý do:
faithfulness · completeness · conciseness · vietnamese_fluency · clinical_safety.
Prompt judge nhận source EHR + summary, yêu cầu chỉ ra câu sai sự thật nếu có.

> Ràng buộc: dùng **gpt-4o-mini** cho cả pipeline và judge (theo quyết định dự án).

**Acceptance:**
- `python -m src.c7_evaluation.evaluator --all` sinh `data/processed/eval/{Pxxx}_eval.json`
- Có bảng tổng hợp 4 BN (metrics + điểm judge)
- Test: `test_evaluator_outputs_all_metrics`, `test_judge_parses_json`

---

### 3.10 Cải thiện prompt C4 (đòn bẩy chất lượng rẻ nhất)

**File:** `poc/poc_pipeline.py` (SYSTEM_PROMPT + section guidelines)

Nhiều lỗi trên gốc ở bước sinh (LLM), sửa prompt rẻ hơn sửa hậu kỳ:
- **Q1:** thêm quy tắc "giữ nhất quán loại bệnh/giá trị giữa các section; copy nguyên văn từ chẩn đoán gốc, không suy diễn type."
- **Q5:** "mỗi mục thuốc viết thành 1 câu hoàn chỉnh, không tách phần liều/thời điểm thành câu rời."
- **Q4:** "nếu dữ liệu thiếu, ghi 'chưa rõ'/'cần xác nhận', tuyệt đối không in 'None'/'unknown'/null."
- Few-shot 1 ví dụ tốt cho `treatment_timeline` và `allergies`.

**Acceptance:** chạy lại 4 BN, đối chiếu trước/sau, các lỗi Q1/Q4/Q5 giảm trên output thô.

---

## 4. Chỉ số chất lượng nâng cấp

Bổ sung vào `SummaryMetrics` (ngoài coverage hiện có):

| Chỉ số mới | Ý nghĩa | Vì sao quan trọng |
|---|---|---|
| `citation_precision` | SUPPORTED đúng / SUPPORTED tổng | Bắt false SUPPORTED (Q2) — coverage cao mà sai thì vô nghĩa |
| `contradiction_count` | số mâu thuẫn nội bộ | An toàn lâm sàng (Q1) |
| `duplicate_claim_count` | claim trùng | Chất lượng trình bày (Q5) |
| `need_review_count` | claim cần bác sĩ xác nhận | HITL minh bạch (Q3) |
| `judge_faithfulness` | điểm LLM-judge 1–5 | Đánh giá toàn cục độ trung thực |

**Gold labels cho precision:** tạo `data/eval/gold/{Pxxx}_claims.jsonl` — nhãn thủ công
SUPPORTED/đúng-sai cho ~30 claim/BN. Đây là tài sản đánh giá tái sử dụng được.

---

## 5. Thứ tự triển khai

```text
Ngày 1  Q2+Q1: contradiction-aware matching + cross-section check (3.1, 3.2)   🔴 ưu tiên cao nhất
Ngày 2  Q3+Q4: allergy NEED_REVIEW + render sạch (3.3); Q5 dedup (3.4)
Ngày 3  Q8: verification_status + removed_claims audit (3.6); Q9 confidence (3.7)
Ngày 4  Q7 multi-citation (3.5); cải thiện prompt C4 (3.10); chạy lại 4 BN
Ngày 5  C7 evaluator lớp A + gold labels (3.9-A); cập nhật SummaryMetrics (4)
Ngày 6  C7 LLM-as-judge lớp B (3.9-B); Q6 trend nếu còn giờ (3.8)
Ngày 7  Tests mới all green; benchmark before/after; cập nhật báo cáo
```

**Quy tắc làm việc:** mỗi hạng mục = 1 nhánh logic + test trước khi sang hạng mục sau.
KHÔNG commit nếu chưa có xác nhận của bạn.

---

## 6. File thay đổi / tạo mới

```text
Sửa:
  src/c5_citation/evidence_matcher.py   ← 3.1, 3.3, 3.5, 3.7, 3.8
  src/c5_citation/claim_extractor.py    ← 3.4
  src/c6_verifier/verifier.py           ← 3.2, 3.6
  src/schemas.py                        ← thêm metrics mới (mục 4)
  poc/poc_pipeline.py                   ← 3.6 serialize, 3.10 prompt

Tạo mới:
  src/c7_evaluation/evaluator.py        ← 3.9
  tests/test_c7_evaluation.py
  data/eval/gold/{P001..P004}_claims.jsonl   ← gold labels precision
  data/processed/eval/{P001..P004}_eval.json ← output (gitignored)

Bổ sung test:
  tests/test_c5_citation.py  ← conflicting token, multifact, dedup, confidence, allergy
  tests/test_c6_verifier.py  ← internal contradiction, verification_status, removed_claims
```

---

## 7. Rủi ro & giảm thiểu

| Rủi ro | Khả năng | Giảm thiểu |
|---|---|---|
| Contradiction check quá nhạy → FLAG oan claim đúng | Trung bình | Bắt đầu hẹp (chỉ type/negation/ICD), mở rộng dần; log để review |
| Sửa matcher làm tụt coverage số đẹp ở report | Cao | Đo precision song song; coverage giảm nhưng precision tăng = đúng hướng, ghi rõ trong báo cáo |
| LLM-judge không ổn định (variance) | Trung bình | temperature=0, chạy 2 lần lấy trung bình, lưu lý do để audit |
| Gold labels tốn công thủ công | Trung bình | Chỉ nhãn ~30 claim/BN cho critical sections; tái dùng nhiều tuần |
| Prompt thay đổi làm regress section khác | Trung bình | So sánh diff 4 BN trước/sau; giữ prompt cũ làng backup |

---

## 8. Định nghĩa "hoàn thành" Tuần 3

- [ ] G1–G8 đạt target (mục 2)
- [ ] False SUPPORTED type1/type2 không còn (Q1/Q2)
- [ ] Allergy → NEED_REVIEW đúng (Q3), không còn "None/unknown" lộ ra (Q4)
- [ ] Không claim trùng (Q5), `verification_status` ghi đúng (Q8)
- [ ] C7 sinh eval cho 4 BN gồm cả điểm LLM-judge
- [ ] Toàn bộ test xanh; benchmark before/after được ghi vào báo cáo Tuần 3
- [ ] Hallucination giữ 0%
```