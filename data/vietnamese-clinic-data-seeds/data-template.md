# Raw Input Dataset Schema — Medical Record Summarization

Tài liệu này mô tả các loại dữ liệu đầu vào thô (*raw input dataset*) dùng để tạo seed data cho demo hệ thống **Medical Record Summarization**.

Mục tiêu của các file raw input là mô phỏng dữ liệu đến từ nhiều module khác nhau trong HIS/EMR, ví dụ: module tiếp nhận, khám bệnh, xét nghiệm, dược, chẩn đoán hình ảnh và ghi chú lâm sàng.

Các file raw input này sẽ được xử lý qua pipeline:

```text
Raw input dataset
→ schema validation
→ join by patient_id + encounter_id
→ de-identification
→ normalization
→ source chunking
→ retrieval / RAG
→ summarization
→ citation verification
```

---

## 1. `patients.json`

### Mô tả

File `patients.json` lưu thông tin hành chính của bệnh nhân. Đây là dữ liệu thường đến từ module tiếp nhận hoặc hồ sơ bệnh nhân trong HIS.

Trong demo, các trường định danh cá nhân như họ tên, địa chỉ, số BHYT, CCCD, số điện thoại nên được mask hoặc dùng dữ liệu giả lập. Trước khi gửi dữ liệu vào LLM API, các trường PII phải được de-identify.

### Schema

```json
[
  {
    "patient_id": "string",
    "full_name": "string | REDACTED",
    "dob": "YYYY-MM-DD",
    "age": "number",
    "gender": "Nam | Nu | Khac",
    "occupation": "string",
    "address": "string | REDACTED",
    "insurance_id": "string | REDACTED",
    "citizen_id": "string | REDACTED",
    "phone": "string | REDACTED",
    "created_at": "ISO-8601 datetime",
    "updated_at": "ISO-8601 datetime",
    "data_note": "string"
  }
]
```

---

## 2. `encounters.json`

### Mô tả

File `encounters.json` lưu thông tin từng lần khám hoặc lần điều trị của bệnh nhân. Một bệnh nhân có thể có nhiều encounters, ví dụ tái khám nhiều lần trong năm.

Đây là file trung tâm để liên kết các dữ liệu khác như chẩn đoán, xét nghiệm, thuốc, sinh hiệu và clinical notes thông qua `patient_id` và `encounter_id`.

### Schema

```json
[
  {
    "encounter_id": "string",
    "patient_id": "string",
    "encounter_date": "YYYY-MM-DD",
    "encounter_type": "outpatient | inpatient | emergency | transfer",
    "department": "string",
    "doctor_id": "string",
    "doctor_name": "string",
    "chief_complaint": "string",
    "visit_reason": "string",
    "source_system": "string",
    "created_at": "ISO-8601 datetime"
  }
]
```

---

## 3. `clinical_notes.json`

### Mô tả

File `clinical_notes.json` lưu các ghi chú lâm sàng dạng văn bản tự do hoặc bán cấu trúc. Đây là nhóm dữ liệu quan trọng cho các section như bệnh sử, tiền sử, diễn biến điều trị và điểm cần lưu ý.

Clinical notes thường có nhiều viết tắt y khoa tiếng Việt như `BN`, `THA`, `ĐTĐ`, `HA`, `XN`, `CLS`, nên cần đi qua bước abbreviation normalization trước khi chunking và retrieval.

### Schema

```json
[
  {
    "note_id": "string",
    "patient_id": "string",
    "encounter_id": "string",
    "note_date": "YYYY-MM-DD",
    "note_type": "doctor_note | nursing_note | discharge_note | progress_note",
    "section": "benh_su | tien_su_ban_than | tien_su_gia_dinh | kham_lam_sang | dien_bien | ghi_chu_khac",
    "text": "string",
    "author_id": "string",
    "author_name": "string",
    "source_system": "string"
  }
]
```

---

## 4. `diagnoses.json`

### Mô tả

File `diagnoses.json` lưu danh sách chẩn đoán của từng lần khám, bao gồm chẩn đoán chính, bệnh kèm theo và mã ICD-10.

Đây là dữ liệu critical, vì các claim liên quan đến chẩn đoán và mã ICD-10 phải có citation rõ ràng. Hệ thống không được tự sửa hoặc suy luận mã ICD-10 nếu source không ghi nhận.

### Schema

```json
[
  {
    "diagnosis_id": "string",
    "patient_id": "string",
    "encounter_id": "string",
    "diagnosis_date": "YYYY-MM-DD",
    "diagnosis_type": "primary | comorbidity | complication | differential",
    "icd10_code": "string",
    "diagnosis_name": "string",
    "diagnosis_text": "string",
    "is_active": "boolean",
    "source_system": "string"
  }
]
```

---

## 5. `labs.json`

### Mô tả

File `labs.json` lưu kết quả xét nghiệm từ LIS hoặc module xét nghiệm. Đây là nhóm dữ liệu có cấu trúc rõ, phù hợp với retrieval bằng metadata/filter hơn là chỉ dùng vector search.

Các field như `value`, `unit`, `reference_range`, `abnormal`, `result_date` rất quan trọng để tạo citation, kiểm tra factuality và tính confidence score cho claim.

### Schema

```json
[
  {
    "lab_id": "string",
    "patient_id": "string",
    "encounter_id": "string",
    "sample_date": "YYYY-MM-DD",
    "result_date": "YYYY-MM-DD",
    "test_code": "string",
    "test_name": "string",
    "value": "number | string",
    "unit": "string",
    "reference_range": "string",
    "interpretation": "normal | high | low | critical | abnormal | unknown",
    "abnormal": "boolean",
    "critical": "boolean",
    "comment": "string",
    "source_system": "string"
  }
]
```

---

## 6. `medications.json`

### Mô tả

File `medications.json` lưu thông tin thuốc được kê trong từng lần khám hoặc lần điều trị. Đây là dữ liệu critical vì thông tin thuốc, hàm lượng, liều dùng, đường dùng và cách dùng nếu sai có thể ảnh hưởng trực tiếp đến an toàn lâm sàng.

Với section `thuoc_hien_tai`, hệ thống nên ưu tiên đơn thuốc mới nhất hoặc thuốc còn hiệu lực thay vì lấy toàn bộ lịch sử thuốc.

### Schema

```json
[
  {
    "medication_id": "string",
    "patient_id": "string",
    "encounter_id": "string",
    "prescription_date": "YYYY-MM-DD",
    "drug_name": "string",
    "strength": "string",
    "dose": "string",
    "route": "oral | injection | topical | inhalation | other",
    "frequency": "string",
    "instruction": "string",
    "duration_days": "number | null",
    "is_current": "boolean",
    "source_system": "string"
  }
]
```

---

## 7. `allergies.json`

### Mô tả

File `allergies.json` lưu thông tin dị ứng của bệnh nhân, ví dụ dị ứng thuốc, thức ăn hoặc tác nhân khác.

Dị ứng là dữ liệu critical và phải được ưu tiên hiển thị. Nếu source chỉ ghi “dị ứng Penicillin” nhưng thiếu phản ứng hoặc mức độ, hệ thống nên gắn trạng thái cần xác nhận thêm với bệnh nhân.

### Schema

```json
[
  {
    "allergy_id": "string",
    "patient_id": "string",
    "encounter_id": "string | null",
    "recorded_date": "YYYY-MM-DD",
    "substance": "string",
    "reaction": "string | null",
    "severity": "mild | moderate | severe | unknown | null",
    "status": "active | inactive | unknown",
    "source_text": "string",
    "needs_patient_confirmation": "boolean",
    "source_system": "string"
  }
]
```

---

## 8. `vitals.json`

### Mô tả

File `vitals.json` lưu sinh hiệu và chỉ số cơ bản của bệnh nhân như huyết áp, mạch, nhiệt độ, SpO2, cân nặng, chiều cao và BMI.

Dữ liệu này dùng cho các section như tổng quan, khám lâm sàng, xét nghiệm/sinh hiệu bất thường và điểm cần lưu ý. Với các chỉ số bất thường như huyết áp cao hoặc BMI thừa cân, hệ thống nên gắn metadata để retrieval dễ hơn.

### Schema

```json
[
  {
    "vital_id": "string",
    "patient_id": "string",
    "encounter_id": "string",
    "measured_at": "ISO-8601 datetime",
    "blood_pressure_systolic": "number | null",
    "blood_pressure_diastolic": "number | null",
    "heart_rate": "number | null",
    "temperature_c": "number | null",
    "spo2": "number | null",
    "weight_kg": "number | null",
    "height_cm": "number | null",
    "bmi": "number | null",
    "abnormal_flags": ["string"],
    "source_system": "string"
  }
]
```

---

## 9. `imaging_reports.json`

### Mô tả

File `imaging_reports.json` lưu kết quả chẩn đoán hình ảnh hoặc thăm dò chức năng như X-quang, siêu âm, CT, MRI, ECG.

Trong MVP text-only, dữ liệu này nên được lưu dưới dạng report text đã có sẵn. Nếu dữ liệu đến từ ảnh scan hoặc PDF thì có thể đánh dấu là out-of-scope hoặc post-MVP OCR.

### Schema

```json
[
  {
    "imaging_id": "string",
    "patient_id": "string",
    "encounter_id": "string",
    "study_date": "YYYY-MM-DD",
    "modality": "X-ray | Ultrasound | CT | MRI | ECG | Echocardiography | Other",
    "body_part": "string",
    "report_text": "string",
    "impression": "string",
    "radiologist_or_reader": "string",
    "source_system": "string"
  }
]
```

---

## 10. `procedures.json`

### Mô tả

File `procedures.json` lưu các thủ thuật, khám chuyên biệt hoặc can thiệp lâm sàng. Trong bối cảnh bệnh nhân nội khoa mạn tính, file này có thể dùng để lưu các hoạt động như khám bàn chân đái tháo đường, đo ECG, test thần kinh ngoại biên hoặc các thủ thuật nhỏ.

Dữ liệu này có thể hỗ trợ section diễn biến điều trị, biến chứng, điểm cần lưu ý hoặc khám lâm sàng.

### Schema

```json
[
  {
    "procedure_id": "string",
    "patient_id": "string",
    "encounter_id": "string",
    "procedure_date": "YYYY-MM-DD",
    "procedure_name": "string",
    "procedure_text": "string",
    "result_summary": "string",
    "source_system": "string"
  }
]
```

---

## 11. Quan hệ giữa các file raw input

Các file raw input nên được join theo khóa:

```text
patient_id
encounter_id
```

Quan hệ dữ liệu gợi ý:

```text
patients.patient_id
  └── encounters.patient_id
        ├── clinical_notes.encounter_id
        ├── diagnoses.encounter_id
        ├── labs.encounter_id
        ├── medications.encounter_id
        ├── allergies.encounter_id
        ├── vitals.encounter_id
        ├── imaging_reports.encounter_id
        └── procedures.encounter_id
```

---

## 12. Gợi ý folder structure cho raw input dataset

```text
data/
└── raw/
    ├── patients.json
    ├── encounters.json
    ├── clinical_notes.json
    ├── diagnoses.json
    ├── labs.json
    ├── medications.json
    ├── allergies.json
    ├── vitals.json
    ├── imaging_reports.json
    └── procedures.json
```

---

## 13. Data quality checklist cho raw input

| ID | Requirement |
|---|---|
| DQ-01 | Mỗi record phải có `patient_id` |
| DQ-02 | Các dữ liệu theo lần khám phải có `encounter_id` |
| DQ-03 | `patient_id` trong các file phải tồn tại trong `patients.json` |
| DQ-04 | `encounter_id` trong các file phải tồn tại trong `encounters.json` |
| DQ-05 | Các trường ngày tháng dùng format nhất quán |
| DQ-06 | Thuốc phải có ít nhất `drug_name`, `dose` hoặc flag thiếu liều |
| DQ-07 | Xét nghiệm phải có `test_name`, `value`, `unit`, `result_date` nếu có |
| DQ-08 | Chẩn đoán nên có `icd10_code` nếu dùng cho citation/evaluation |
| DQ-09 | PII phải được mask trước khi gửi ra external LLM API |
| DQ-10 | Dữ liệu seed nên có edge cases: thiếu liều thuốc, thiếu đơn vị xét nghiệm, dị ứng thiếu reaction, ICD-note mismatch |
