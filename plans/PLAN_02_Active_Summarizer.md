# PLAN 02 — Active Summarizer (C4)

**Component:** C4 Active Summarizer  
**Interface:** `dict[section_id, list[SourceChunk]]` → `dict[section_id, SummarySection]`  
**Cập nhật cho:** `SourceChunk.content`, source types tiếng Anh, section IDs tiếng Anh

---

## 1. Mục tiêu

Active Summarizer sinh draft clinical summary theo từng section. Nó không nhận toàn bộ bệnh án raw, mà nhận evidence chunks đã được retrieve theo từng section.

Luồng:

```text
patient_id
→ section retrieval policy
→ evidence chunks
→ section prompt
→ LLM / template
→ SummarySection
```

---

## 2. Section-wise summarization

Final summary gồm 9 section:

| Section ID | Tên hiển thị | Mục tiêu |
|---|---|---|
| `patient_overview` | Tổng quan bệnh nhân | Tuổi, giới, bệnh nền chính |
| `chief_complaint` | Lý do khám | Lý do đến khám/lần khám gần nhất |
| `medical_history` | Tiền sử | Tiền sử bản thân, gia đình, thói quen, dị ứng nếu có |
| `current_medications` | Thuốc hiện tại | Thuốc đang dùng mới nhất/active |
| `allergies` | Dị ứng | Dị ứng đã ghi nhận |
| `abnormal_labs` | Xét nghiệm bất thường | Lab bất thường gần nhất và quan trọng |
| `diagnoses` | Chẩn đoán | Diagnosis + ICD-10 |
| `treatment_timeline` | Diễn biến điều trị | Thay đổi qua nhiều visits |
| `clinical_alerts` | Điểm cần lưu ý | Alert/risk/low-confidence/critical evidence |

---

## 3. Retrieval policy cho từng section

| Section | Source types | Logic |
|---|---|---|
| `patient_overview` | `patient_profile`, `diagnosis`, `clinical_note`, `vital` | lấy thông tin ổn định, bệnh nền chính |
| `chief_complaint` | `encounter`, `clinical_note` | ưu tiên encounter gần nhất |
| `medical_history` | `clinical_note`, `diagnosis`, `allergy` | lấy notes tiền sử, bệnh nền, gia đình |
| `current_medications` | `medication` | lấy latest/current meds |
| `allergies` | `allergy`, `clinical_note` | ưu tiên structured allergy |
| `abnormal_labs` | `lab_result` | filter `is_abnormal=true`, sort mới nhất |
| `diagnoses` | `diagnosis` | ưu tiên diagnosis gần nhất |
| `treatment_timeline` | `lab_result`, `medication`, `diagnosis`, `clinical_note` | lấy chuỗi thời gian |
| `clinical_alerts` | `lab_result`, `vital`, `allergy`, `diagnosis` | lấy high-risk/critical/need-review |

---

## 4. Prompt nguyên tắc chung

System prompt cần enforce:

```text
Bạn là hệ thống hỗ trợ bác sĩ Việt Nam tóm tắt hồ sơ bệnh án điện tử.

Nguyên tắc bắt buộc:
1. Chỉ dùng thông tin trong evidence được cung cấp.
2. Không tự thêm chẩn đoán, thuốc, xét nghiệm hoặc khuyến nghị điều trị.
3. Nếu thiếu thông tin, ghi: "Chưa thấy ghi nhận trong dữ liệu được cung cấp."
4. Giữ nguyên tên thuốc, liều, giá trị số, đơn vị, ICD-10.
5. Không tạo source_id mới.
6. Viết ngắn gọn, chuẩn lâm sàng, tiếng Việt có dấu.
```

---

## 5. Prompt theo section

### `current_medications`

```text
[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Viết section Thuốc hiện tại.
Yêu cầu:
- Chỉ liệt kê thuốc đang dùng mới nhất/active.
- Giữ nguyên tên thuốc, hàm lượng, liều, tần suất, cách dùng.
- Nếu thiếu liều, ghi "(thiếu thông tin liều)".
- Không suy luận thuốc ngoài evidence.
```

### `abnormal_labs`

```text
[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Viết section Xét nghiệm bất thường.
Yêu cầu:
- Nêu các xét nghiệm bất thường quan trọng.
- Giữ nguyên giá trị số, đơn vị, khoảng tham chiếu nếu có.
- Ưu tiên kết quả gần nhất.
- Nếu có trend, mô tả ngắn gọn theo thời gian.
```

### `treatment_timeline`

```text
[DỮ LIỆU BỆNH ÁN]
{evidence_text}

Viết section Diễn biến điều trị.
Yêu cầu:
- Mô tả thay đổi chính qua các lần khám.
- Tập trung vào HbA1c, huyết áp, LDL, UACR, thuốc và biến chứng.
- Không đưa khuyến nghị điều trị mới.
```

---

## 6. Rule/template vs LLM

Không phải section nào cũng cần LLM tự do.

| Section | Cách generate gợi ý |
|---|---|
| `current_medications` | Template/rule trước, LLM chỉ polish |
| `allergies` | Rule/template |
| `abnormal_labs` | Rule + LLM diễn đạt |
| `diagnoses` | Rule/template |
| `medical_history` | LLM |
| `treatment_timeline` | Trend builder + LLM |
| `clinical_alerts` | Rule + LLM |

Cách này an toàn hơn cho dữ liệu y tế.

---

## 7. Output schema

```json
{
  "section_id": "current_medications",
  "title": "Thuốc hiện tại",
  "content": "Bệnh nhân đang dùng Metformin 1000 mg, 1 viên, 2 lần/ngày sau ăn.",
  "cited_claims": []
}
```

Claims và citations có thể được thêm ở C5.

---

## 8. Acceptance criteria

| ID | Tiêu chí |
|---|---|
| C4-AC01 | Sinh được đủ 9 sections |
| C4-AC02 | Mỗi section chỉ dùng evidence của section đó |
| C4-AC03 | `current_medications` lấy thuốc mới nhất/active |
| C4-AC04 | `abnormal_labs` lấy lab bất thường |
| C4-AC05 | `treatment_timeline` mô tả được trend |
| C4-AC06 | Không có source_id giả |
| C4-AC07 | Output là tiếng Việt có dấu, ngắn gọn, dễ đọc |
