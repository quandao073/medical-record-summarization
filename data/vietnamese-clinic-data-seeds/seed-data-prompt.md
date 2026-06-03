# Prompt Template — Seed Data Generation

## Mục tiêu

Prompt template này dùng để sinh **synthetic EHR seed data** phục vụ demo hệ thống Medical Record Summarization. Dữ liệu được sinh ra phải khớp chính xác với 10 JSON schemas trong `data-template.md`, nhất quán về `patient_id` / `encounter_id`, và đủ phức tạp để test citation pipeline + hallucination detection.

---

## 1. Phân tích data-template.md đối chiếu PRD

### 1.1 Coverage: data-template → PRD output sections

| PRD Output Section | Data files cần thiết | Đủ chưa? |
|---|---|---|
| Tổng quan | patients + encounters + vitals | ✅ |
| Lý do khám | encounters (chief_complaint, visit_reason) | ✅ |
| Tiền sử bệnh | clinical_notes (section: tien_su_ban_than, tien_su_gia_dinh) | ✅ |
| Thuốc đang dùng | medications (is_current=true) | ✅ |
| Dị ứng | allergies | ✅ |
| XN bất thường | labs (abnormal=true) | ✅ |
| Chẩn đoán | diagnoses (icd10_code) | ✅ |
| Diễn biến điều trị | medications (timeline) + clinical_notes (dien_bien) + procedures | ✅ |
| Điểm cần lưu ý | labs (critical) + vitals (abnormal_flags) + diagnoses (complication) | ✅ |

### 1.2 Coverage: PRD critical claims → data fields

| Critical claim type (PRD 3.4.1) | Field(s) cần có trong seed data |
|---|---|
| Chẩn đoán / ICD-10 | diagnoses.icd10_code + diagnosis_name + diagnosis_text |
| Thuốc / liều | medications.drug_name + strength + dose + frequency |
| Dị ứng | allergies.substance + reaction + severity |
| Xét nghiệm | labs.test_name + value + unit + reference_range + abnormal |
| Sinh hiệu bất thường | vitals.blood_pressure_* + abnormal_flags |
| Biến chứng | diagnoses (type=complication) + clinical_notes |
| Timeline điều trị | medications across encounters + clinical_notes (dien_bien) |

### 1.3 Yêu cầu edge cases (PRD DQ-10 + data-template DQ-10)

Seed data **phải bao gồm** ít nhất các edge cases sau:

| ID | Edge case | File ảnh hưởng |
|---|---|---|
| EC-01 | Thuốc thiếu liều (dose = null) | medications |
| EC-02 | XN thiếu đơn vị (unit = null) | labs |
| EC-03 | Dị ứng thiếu phản ứng (reaction = null) | allergies |
| EC-04 | ICD-10 không khớp clinical note | diagnoses + clinical_notes |
| EC-05 | Bệnh nhân không có dị ứng nào | allergies (empty array) |
| EC-06 | Encounter không có XN | labs (no records for that encounter) |
| EC-07 | Mâu thuẫn chẩn đoán giữa 2 encounters | diagnoses |
| EC-08 | Thuốc bị ngưng giữa chừng (is_current = false) | medications |
| EC-09 | Giá trị XN critical (ví dụ glucose < 2.8) | labs (critical = true) |
| EC-10 | Clinical note có nhiều viết tắt y khoa | clinical_notes |

---

## 2. Patient Profiles cần sinh

Mỗi profile tạo 1 bệnh nhân với 3–5 encounters, đủ dữ liệu cho cả 10 files.

### Profile A — ĐTĐ type 2 kiểm soát kém + THA + RLLPM (case phức tạp)

```yaml
patient:
  age: 50-65
  gender: Nam hoặc Nữ
  diseases: [ĐTĐ type 2, THA, RLLPM]
  icd10: [E11, I10, E78.5]
  complications: [thần kinh ngoại biên sớm, microalbuminuria]
  allergy: Penicillin (có reaction rõ)
  encounters: 4 (mỗi 3 tháng, qua 1 năm)
  progression: HbA1c tăng dần → tăng liều → thêm thuốc mới
  edge_cases: []
```

### Profile B — ĐTĐ type 2 kiểm soát tốt + THA ổn định (case đơn giản)

```yaml
patient:
  age: 45-55
  gender: Nữ
  diseases: [ĐTĐ type 2, THA]
  icd10: [E11.9, I10]
  complications: []
  allergy: không có (empty)
  encounters: 3 (mỗi 3 tháng)
  progression: HbA1c ổn định 6.5-6.8%, HA đạt mục tiêu
  edge_cases: [EC-05 (không có dị ứng)]
```

### Profile C — THA kháng trị + RLLPM + ĐTĐ mới phát hiện (case nhiều thay đổi thuốc)

```yaml
patient:
  age: 55-70
  gender: Nam
  diseases: [THA (10 năm), RLLPM (5 năm), ĐTĐ type 2 (mới)]
  icd10: [I10, E78.5, E11.9]
  complications: [phì đại thất trái, gan nhiễm mỡ]
  allergy: Sulfonamide (thiếu reaction — EC-03)
  encounters: 5 (qua 1.5 năm, bao gồm 1 encounter nhập viện)
  progression: Thay đổi thuốc HA nhiều lần, thêm metformin khi phát hiện ĐTĐ
  edge_cases: [EC-03, EC-07 (ICD thay đổi giữa encounters), EC-08 (thuốc ngưng)]
```

### Profile D — Bệnh nhân có edge cases tập trung (case dùng cho test pipeline)

```yaml
patient:
  age: 60-75
  gender: Nữ
  diseases: [ĐTĐ type 2, THA]
  icd10: [E11, I10]
  allergy: ghi "dị ứng thuốc" nhưng không rõ substance (EC-03)
  encounters: 3
  edge_cases:
    - EC-01: encounter 2 kê thuốc thiếu dose
    - EC-02: encounter 1 có XN thiếu unit
    - EC-04: encounter 3 ICD-10 ghi E11.9 nhưng note ghi "ĐTĐ type 1"
    - EC-06: encounter 2 không có XN
    - EC-09: encounter 3 glucose 2.5 mmol/L (critical low)
    - EC-10: clinical note viết tắt nhiều (BN, THA, ĐTĐ, XN, CLS, RLLPM, TSGĐ)
```

---

## 3. Prompt Template

### 3.1 System Prompt

```
Bạn là một chuyên gia tạo dữ liệu y tế mẫu (synthetic medical data) cho hệ thống
Medical Record Summarization tại bệnh viện Việt Nam.

NHIỆM VỤ:
Sinh dữ liệu bệnh án giả lập cho MỘT bệnh nhân, bao gồm đầy đủ 10 file JSON
theo schema được cung cấp. Dữ liệu phải thực tế về mặt lâm sàng, nhất quán nội bộ
và phù hợp với bối cảnh bệnh viện nội khoa tại Việt Nam.

QUY TẮC BẮT BUỘC:

1. NHẤT QUÁN DỮ LIỆU:
   - Mọi file phải dùng cùng patient_id.
   - Mọi dữ liệu theo lần khám phải có encounter_id khớp với encounters.json.
   - Ngày tháng phải hợp lý: encounter_date < lab result_date <= encounter_date + 1 day.
   - Tuổi phải khớp với dob và encounter_date.
   - BMI phải tính đúng từ weight_kg và height_cm.

2. THỰC TẾ LÂM SÀNG:
   - Giá trị xét nghiệm phải nằm trong khoảng sinh lý hợp lý.
   - Thuốc phải phù hợp với chẩn đoán (Metformin cho ĐTĐ, Amlodipine cho THA...).
   - Liều thuốc phải đúng liều thường dùng tại Việt Nam.
   - Khoảng tham chiếu XN phải đúng theo chuẩn y khoa.
   - Diễn biến qua các encounter phải hợp lý (ví dụ: HbA1c tăng → tăng liều thuốc).

3. NGÔN NGỮ:
   - clinical_notes.text viết bằng tiếng Việt, sử dụng viết tắt y khoa phổ biến
     (BN, THA, ĐTĐ, HA, XN, CLS, RRPN, NMCT, RLLPM, TSGĐ, CĐHA).
   - diagnoses.diagnosis_text viết bằng tiếng Việt.
   - medications.instruction viết bằng tiếng Việt (ví dụ: "Uống sau ăn sáng và tối").
   - imaging_reports.report_text và impression viết bằng tiếng Việt.

4. PII:
   - full_name: dùng tên Việt Nam giả lập (hoặc REDACTED).
   - address, insurance_id, citizen_id, phone: dùng REDACTED.

5. ID FORMAT:
   - patient_id: "P001", "P002"...
   - encounter_id: "P001-E001", "P001-E002"...
   - lab_id: "P001-E001-LAB001"...
   - medication_id: "P001-E001-MED001"...
   - Các ID khác theo pattern tương tự: "{patient_id}-{encounter_id}-{TYPE}{seq}"

6. EDGE CASES (nếu có yêu cầu):
   - Tạo đúng edge case được yêu cầu trong patient profile.
   - Mỗi edge case phải có comment hoặc data_note giải thích.

OUTPUT:
Trả về đúng 10 JSON arrays, mỗi array là nội dung của 1 file.
Dùng markdown code blocks với tên file:
```patients.json```, ```encounters.json```, etc.

KHÔNG được:
- Tự bịa mã ICD-10 không tồn tại.
- Sinh giá trị XN phi sinh lý (ví dụ HbA1c 25%, creatinine 5000 µmol/L).
- Sinh thuốc không phù hợp chẩn đoán.
- Để encounter_id trong data files mà không có trong encounters.json.
```

### 3.2 User Prompt Template

```
Tạo dữ liệu bệnh án cho bệnh nhân sau:

## Patient Profile
- Patient ID: {{patient_id}}
- Tuổi: {{age}}
- Giới tính: {{gender}}
- Bệnh chính: {{primary_diseases}}
- Mã ICD-10: {{icd10_codes}}
- Biến chứng: {{complications}}
- Dị ứng: {{allergies}}
- Số lần khám: {{num_encounters}}
- Khoảng cách giữa các lần: {{encounter_interval}}
- Diễn biến bệnh: {{progression_description}}

## Edge Cases cần tạo
{{edge_cases_list}}

## Yêu cầu output
Sinh đầy đủ 10 file JSON theo schema đã cho:
1. patients.json (1 record)
2. encounters.json ({{num_encounters}} records)
3. clinical_notes.json (ít nhất 2 notes/encounter)
4. diagnoses.json (ít nhất bệnh chính + bệnh kèm/encounter)
5. labs.json (ít nhất 5 XN/encounter: HbA1c, glucose, creatinine, lipid panel)
6. medications.json (tất cả thuốc đang dùng/encounter)
7. allergies.json (theo profile)
8. vitals.json (1 record/encounter)
9. imaging_reports.json (ít nhất 1 ECG + 1 siêu âm tổng thể)
10. procedures.json (nếu có khám chuyên biệt hoặc thủ thuật)

Viết clinical notes, chẩn đoán và hướng dẫn thuốc bằng tiếng Việt.
```

---

## 4. Ví dụ User Prompt đã điền (Profile A)

```
Tạo dữ liệu bệnh án cho bệnh nhân sau:

## Patient Profile
- Patient ID: P001
- Tuổi: 55
- Giới tính: Nam
- Bệnh chính: ĐTĐ type 2 kiểm soát kém, THA, RLLPM
- Mã ICD-10: E11, I10, E78.5
- Biến chứng: thần kinh ngoại biên giai đoạn sớm, microalbuminuria
- Dị ứng: Penicillin (phản ứng: nổi mề đay, mức độ: moderate)
- Số lần khám: 4 (encounter E001 → E004)
- Khoảng cách: mỗi 3 tháng (01/2024, 04/2024, 07/2024, 10/2024)
- Diễn biến:
  E001: HbA1c 9.2%, glucose đói 9.8 — phát hiện kiểm soát kém, tăng Metformin
        500→1000mg, thêm Empagliflozin 10mg. THA chưa đạt mục tiêu (148/92),
        thêm Perindopril 5mg. LDL 3.4 chưa đạt, tăng Atorvastatin 20→40mg.
        Phát hiện microalbuminuria 42 mg/g, TK ngoại biên sớm.
  E002: HbA1c cải thiện 8.1%, glucose 7.5. HA 138/88 — cải thiện nhưng chưa đạt.
        Microalbumin 38 — giảm nhẹ. Giữ nguyên phác đồ.
  E003: HbA1c 7.5%, glucose 6.8. HA 132/82 — gần đạt mục tiêu.
        LDL giảm còn 2.8. Giữ nguyên. Siêu âm bụng kiểm tra.
  E004: HbA1c 7.1%, glucose 6.2. HA 128/78 — đạt mục tiêu.
        Microalbumin 32 — giảm. Cân nhắc giảm liều nếu duy trì.

## Edge Cases cần tạo
- Không có edge case đặc biệt — đây là case "happy path" phức tạp.

## Yêu cầu output
Sinh đầy đủ 10 file JSON. Viết clinical notes bằng tiếng Việt,
có sử dụng viết tắt y khoa (THA, ĐTĐ, BN, XN, HA, RLLPM, TSGĐ).
```

---

## 5. Ví dụ User Prompt đã điền (Profile D — Edge Cases)

```
Tạo dữ liệu bệnh án cho bệnh nhân sau:

## Patient Profile
- Patient ID: P004
- Tuổi: 68
- Giới tính: Nữ
- Bệnh chính: ĐTĐ type 2, THA
- Mã ICD-10: E11, I10
- Biến chứng: không rõ ràng
- Dị ứng: ghi "dị ứng thuốc" nhưng không rõ substance (edge case)
- Số lần khám: 3 (encounter E001 → E003)
- Khoảng cách: mỗi 3 tháng (03/2024, 06/2024, 09/2024)
- Diễn biến:
  E001: Tái khám ĐTĐ + THA, HbA1c 7.8%, HA 142/90.
        Có 1 XN thiếu đơn vị (unit = null) — edge case EC-02.
  E002: Tái khám, KHÔNG có xét nghiệm (edge case EC-06).
        Thuốc kê thiếu dose (edge case EC-01).
  E003: Tái khám, glucose đói 2.5 mmol/L (critical low — EC-09).
        ICD-10 ghi E11.9 nhưng clinical note ghi "ĐTĐ type 1" (EC-04).
        Clinical note viết tắt nhiều (EC-10).

## Edge Cases BẮT BUỘC
- EC-01: encounter E002 — medications có 1 record dose = null.
- EC-02: encounter E001 — labs có 1 record unit = null.
- EC-03: allergies — substance = "thuốc (không rõ loại)", reaction = null.
- EC-04: encounter E003 — diagnoses ICD = E11.9 nhưng note ghi "ĐTĐ type 1".
- EC-06: encounter E002 — labs.json không có record nào cho encounter này.
- EC-09: encounter E003 — glucose value = 2.5, critical = true.
- EC-10: encounter E003 — clinical_notes.text dùng nhiều viết tắt y khoa.

## Yêu cầu output
Sinh đầy đủ 10 file JSON. Mỗi edge case PHẢI có comment hoặc data_note
giải thích đây là edge case test. Viết clinical notes bằng tiếng Việt.
```

---

## 6. Validation Checklist sau khi sinh data

Sau khi LLM sinh data, kiểm tra:

| # | Check | Command/Action |
|---|---|---|
| 1 | Mỗi file parse được JSON hợp lệ | `json.loads()` |
| 2 | Tất cả patient_id khớp | Set comparison across files |
| 3 | Tất cả encounter_id trong data files tồn tại trong encounters.json | Join check |
| 4 | Không có encounter_id trùng lặp | Unique check |
| 5 | Ngày tháng đúng format YYYY-MM-DD | Regex check |
| 6 | BMI = weight_kg / (height_cm/100)² ± 0.1 | Math check |
| 7 | Tuổi khớp với dob và encounter_date | Date calculation |
| 8 | labs.abnormal = true khi value ngoài reference_range | Logic check |
| 9 | medications.is_current = true cho encounter cuối cùng | Logic check |
| 10 | Edge cases đúng theo yêu cầu | Manual review |
| 11 | Clinical notes có viết tắt y khoa tiếng Việt | Grep for THA, ĐTĐ, BN... |
| 12 | PII fields = REDACTED | Grep check |

---

## 7. Quy trình sinh toàn bộ dataset MVP

```
Bước 1: Sinh P001 (Profile A — case phức tạp, happy path)
Bước 2: Sinh P002 (Profile B — case đơn giản, kiểm soát tốt)
Bước 3: Sinh P003 (Profile C — case nhiều thay đổi thuốc)
Bước 4: Sinh P004 (Profile D — edge cases tập trung)
Bước 5: Chạy validation checklist cho mỗi patient
Bước 6: Merge từng file type: patients.json = [P001, P002, P003, P004]
Bước 7: Chạy validation toàn bộ dataset (cross-patient)
Bước 8: Thêm 11-16 bệnh nhân nữa (variation của Profile A-D)
         để đạt 15-20 bệnh nhân cho MVP
```

Mỗi bước 1-4 là **một lần gọi LLM** với system prompt + user prompt tương ứng.