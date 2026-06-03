# PLAN 01 — EMR Integration (C1)

**Component:** C1 EMR Integration  
**Interface:** modular raw JSON files → `AssembledEHR`  
**Cập nhật cho:** dataset chuẩn hóa với field tiếng Anh `snake_case`

---

## 1. Mục tiêu

C1 là lớp đầu tiên của pipeline. Nhiệm vụ là biến nhiều raw JSON files thành một object thống nhất theo từng bệnh nhân.

Pipeline C1:

```text
load raw files
→ validate schema
→ validate relationships
→ assemble by patient_id + encounter_id
→ de-identify PII
→ normalize Vietnamese medical abbreviations
→ output AssembledEHR
```

---

## 2. Input files

```text
patients.json
encounters.json
clinical_notes.json
diagnoses.json
labs.json
medications.json
allergies.json
vitals.json
imaging_reports.json
procedures.json
```

Các file này không phải là một EHR object duy nhất. Chúng mô phỏng dữ liệu từ nhiều module HIS/EMR khác nhau.

---

## 3. Validation

### 3.1 Required fields

| File | Required fields |
|---|---|
| `patients.json` | `patient_id`, `full_name` |
| `encounters.json` | `encounter_id`, `patient_id`, `encounter_date` |
| `clinical_notes.json` | `note_id`, `patient_id`, `encounter_id`, `text` |
| `diagnoses.json` | `diagnosis_id`, `patient_id`, `encounter_id`, `icd10_code`, `diagnosis_name` |
| `labs.json` | `lab_id`, `patient_id`, `encounter_id`, `test_name` |
| `medications.json` | `medication_id`, `patient_id`, `encounter_id`, `drug_name` |
| `allergies.json` | `allergy_id`, `patient_id`, `substance` |
| `vitals.json` | `vital_id`, `patient_id`, `encounter_id` |
| `imaging_reports.json` | `imaging_id`, `patient_id`, `encounter_id` |
| `procedures.json` | `procedure_id`, `patient_id`, `encounter_id`, `procedure_name` |

### 3.2 Relationship validation

Kiểm tra:

```text
record.patient_id ∈ patients.patient_id
record.encounter_id ∈ encounters.encounter_id
record.patient_id == encounter.patient_id
```

### 3.3 Warning thay vì error

Một số edge cases intentional không nên làm pipeline fail:

- Lab có `value` nhưng thiếu `unit`.
- Medication thiếu `dose`.
- Allergy thiếu `reaction` hoặc `severity`.
- ICD mismatch giữa note và diagnosis.
- Encounter thiếu một số nhóm dữ liệu.

Các case này nên ghi warning để test `LOW_CONFIDENCE` và `NEED_REVIEW`.

---

## 4. Assembler

Assembler tạo `AssembledEHR` cho từng bệnh nhân.

```python
def assemble_patient_ehr(patient_id: str) -> AssembledEHR:
    patient = find_patient(patient_id)
    encounters = find_encounters(patient_id)

    for encounter in encounters:
        encounter.labs = find_labs(encounter.encounter_id)
        encounter.medications = find_medications(encounter.encounter_id)
        encounter.diagnoses = find_diagnoses(encounter.encounter_id)
        encounter.clinical_notes = find_notes(encounter.encounter_id)
        encounter.vitals = find_vitals(encounter.encounter_id)
        encounter.imaging = find_imaging(encounter.encounter_id)
        encounter.procedures = find_procedures(encounter.encounter_id)

    allergies = find_allergies(patient_id)

    return AssembledEHR(
        patient_id=patient_id,
        patient=patient,
        allergies=allergies,
        encounters=encounters
    )
```

---

## 5. De-identification

### 5.1 PII fields

| Field | Action |
|---|---|
| `full_name` | Có thể giữ trong local demo, nhưng nên mask khi gửi external API |
| `address` | `[REDACTED]` |
| `insurance_id` | `[REDACTED]` |
| `citizen_id` | `[REDACTED]` |
| `phone` | `[REDACTED]` |

Trong PoC, nên dùng data synthetic. Tuy vậy vẫn nên có deidentifier để chứng minh pipeline an toàn.

### 5.2 Audit log

Mỗi lần de-identify nên ghi log:

```json
{
  "timestamp": "2026-06-03T10:00:00+07:00",
  "patient_id": "P001",
  "action": "de_identification",
  "fields_masked": ["address", "insurance_id", "citizen_id", "phone"]
}
```

---

## 6. Normalizer viết tắt y khoa

Clinical notes giữ tiếng Việt có dấu và viết tắt như thực tế. Normalizer tạo thêm text chuẩn hóa, không xóa text gốc.

Ví dụ:

```text
BN → bệnh nhân
ĐTĐ → đái tháo đường
THA → tăng huyết áp
RLLPM → rối loạn lipid máu
HA → huyết áp
XN → xét nghiệm
TSGĐ → tiền sử gia đình
NMCT → nhồi máu cơ tim
```

Output nên giữ cả:

```json
{
  "original_text": "BN nam 55 tuổi, tiền sử ĐTĐ type 2, THA 5 năm.",
  "normalized_text": "Bệnh nhân nam 55 tuổi, tiền sử đái tháo đường type 2, tăng huyết áp 5 năm."
}
```

---

## 7. Acceptance criteria

| ID | Tiêu chí |
|---|---|
| C1-AC01 | Load được 10 raw JSON files |
| C1-AC02 | Validate được required fields |
| C1-AC03 | Validate quan hệ `patient_id` và `encounter_id` |
| C1-AC04 | Assemble được `AssembledEHR` cho mọi patient |
| C1-AC05 | Mask được PII fields |
| C1-AC06 | Normalize được viết tắt trong clinical notes |
| C1-AC07 | Edge cases được ghi warning, không crash |
