# Báo cáo Tuần 2: EHR Dataset Preparation & Technical PoC

**Project:** Medical Record Summarization  
**Author:** Đào Anh Quân  
**Week:** 2  
**Nhiệm vụ được giao:** Prepare EHR Dataset  

---

## Mục lục

- [Phần 1: Tổng quan tuần 2](#phần-1-tổng-quan-tuần-2)
- [Phần 2: Thách thức về dữ liệu và quyết định thiết kế](#phần-2-thách-thức-về-dữ-liệu-và-quyết-định-thiết-kế)
- [Phần 3: Thiết kế dataset](#phần-3-thiết-kế-dataset)
- [Phần 4: Quy trình tạo dữ liệu tổng hợp](#phần-4-quy-trình-tạo-dữ-liệu-tổng-hợp)
- [Phần 5: Kết quả dataset](#phần-5-kết-quả-dataset)
- [Phần 6: Triển khai kỹ thuật — C1 & C2 Pipeline](#phần-6-triển-khai-kỹ-thuật--c1--c2-pipeline)
- [Phần 7: Kết quả kiểm thử](#phần-7-kết-quả-kiểm-thử)
- [Phần 8: Phản hồi nhận xét tuần 1](#phần-8-phản-hồi-nhận-xét-tuần-1)
- [Phần 9: Hạn chế và hướng tiếp theo](#phần-9-hạn-chế-và-hướng-tiếp-theo)
- [Appendix A: Cấu trúc thư mục dữ liệu](#appendix-a-cấu-trúc-thư-mục-dữ-liệu)
- [Appendix B: Thống kê dataset chi tiết](#appendix-b-thống-kê-dataset-chi-tiết)
- [Appendix C: Edge cases đã cài đặt](#appendix-c-edge-cases-đã-cài-đặt)

---

# Phần 1: Tổng quan tuần 2

## 1.1 Nhiệm vụ

Mentor giao nhiệm vụ tuần 2: **"Prepare EHR Dataset"** — xây dựng bộ dữ liệu hồ sơ bệnh án điện tử phục vụ pipeline Medical Record Summarization.

## 1.2 Kết quả đạt được

| Hạng mục | Kết quả |
|---|---|
| Dataset thô (`data/raw/`) | 10 file JSON modular, 4 bệnh nhân, 15 encounters |
| Tổng số bản ghi | 273 records (labs: 69, meds: 65, diagnoses: 44, notes: 35, vitals: 15, imaging: 13, procedures: 9, allergies: 3, encounters: 15, patients: 4) |
| Edge cases | 10 loại edge case được cài đặt có chủ đích |
| C1 Pipeline | Validator + De-identifier + Normalizer |
| C2 Pipeline | Assembler + Chunker + Store Builder |
| SourceChunks | 257 chunks (P001: 83, P002: 41, P003: 93, P004: 40) |
| Unit tests | 44 tests, 100% pass |
| Checkpoint script | 23/23 checks passed |

## 1.3 Demo kết quả pipeline

Kết quả chạy `poc/dry_run.py` trên toàn bộ dataset:

```
Patient: P001 | 4 encounters | 1 allergy
  Chunks: 83 total
    labs                       23
    medications                20
    clinical_notes             11
    diagnoses                  16
    imaging                     3
    procedures                  4
    vitals                      4
    allergies                   1
    patient_info                1
  Warnings: 0 — clean case, no edge cases
  Context chars: 12,249

Patient: P002 | 3 encounters | 0 allergies
  Chunks: 41 total
  Warnings: 0 — clean case, no allergy

Patient: P003 | 5 encounters | 1 allergy
  Chunks: 93 total
  Warnings: 0

Patient: P004 | 3 encounters | 1 allergy
  Chunks: 40 total
  Warnings: 2
    [W] encounters[0].labs[2]: Lab 'ALT' missing unit         ← EC-02
    [W] encounters[1].medications[3]: 'Gliclazide MR' missing dose  ← EC-01

Dry-run PASSED. C1+C2 pipeline works for all patients.
```

P004 sinh ra đúng 2 warnings theo edge cases đã thiết kế — đây là hành vi kỳ vọng, không phải lỗi.

---

# Phần 2: Thách thức về dữ liệu và quyết định thiết kế

## 2.1 Không có public dataset phù hợp

Trong quá trình tìm kiếm public dataset cho bài toán này, tôi đã khảo sát các nguồn sau:

| Nguồn | Vấn đề |
|---|---|
| **MIMIC-III / MIMIC-IV** (PhysioNet) | Tiếng Anh, cần chứng nhận đặc biệt, schema quá phức tạp cho PoC 4 tuần |
| **i2b2 NLP datasets** | Tiếng Anh, giới hạn truy cập, không có bối cảnh Việt Nam |
| **VinBigData** | Dataset ảnh X-quang, không phải clinical notes |
| **Bộ Y tế Việt Nam** | Không có dataset công khai dạng EHR cấu trúc |
| **Bệnh viện tư nhân** | Cần NDA + quy trình pháp lý dài |

**Kết luận:** Không có public dataset nào phù hợp với yêu cầu — tiếng Việt, có cấu trúc, đủ chi tiết cho citation pipeline, và có thể dùng ngay trong 4 tuần.

## 2.2 Quyết định: Dùng bệnh án cá nhân làm template

Để giải quyết vấn đề trên, tôi sử dụng **bệnh án điều trị ĐTĐ type 2 + THA tại bệnh viện Bạch Mai** làm tài liệu tham khảo cho việc thiết kế template, với các điều chỉnh sau:

**Những gì được lấy từ bệnh án thật:**
- Cấu trúc thực tế của bệnh án bệnh viện Việt Nam (thứ tự sections, fields bắt buộc, cách ghi chép của bác sĩ tại Bạch Mai)
- Các loại xét nghiệm thực tế được chỉ định (HbA1c, lipid panel, microalbumin, creatinine...)
- Khoảng tham chiếu xét nghiệm theo chuẩn Việt Nam
- Phác đồ điều trị điển hình (Metformin → tăng liều → thêm SGLT2i, kết hợp điều trị THA + RLLPM)
- Các viết tắt y khoa thực tế (THA, ĐTĐ, BN, XN, CLS, RLLPM, NMCT...)
- Diễn biến bệnh thực tế qua các lần tái khám

**Những gì được tổng hợp / thay đổi:**
- Toàn bộ thông tin cá nhân (tên, ngày sinh, địa chỉ, CCCD, BHYT, số điện thoại): thay thế bằng dữ liệu tổng hợp hoặc REDACTED
- Giá trị số cụ thể: thay đổi để tạo độ đa dạng cho các profile
- Thêm 3 bệnh nhân với profile khác nhau (P002, P003, P004) hoàn toàn tổng hợp

**Lý do chọn cách tiếp cận này:**
1. **Độ chính xác lâm sàng:** Bệnh án thật đảm bảo các trường dữ liệu phản ánh quy trình thực tế tại bệnh viện Việt Nam, không phải cấu trúc giả định.
2. **Viết tắt y khoa xác thực:** Clinical notes được viết tắt đúng theo thói quen của bác sĩ Bạch Mai, phục vụ tốt cho bước normalization.
3. **ICD-10 đúng phác đồ:** Mã E11, I10, E78.5 và cách ghi diagnoses phản ánh thực tế BHYT tại Việt Nam.
4. **Không vi phạm quyền riêng tư:** Toàn bộ PII đã được de-identify, không có thông tin cá nhân thật nào trong dataset.

---

# Phần 3: Thiết kế dataset

## 3.1 Quyết định dùng 10 file JSON modular

Thay vì một file EHR monolithic duy nhất, dataset được thiết kế theo mô hình **10 bảng phẳng modular**, mô phỏng cách dữ liệu thực sự được lưu trong HIS tại Việt Nam:

```
HIS Module          →  File JSON
─────────────────────────────────────────────
Module tiếp nhận    →  patients.json
Module khám bệnh    →  encounters.json
EMR ghi chú         →  clinical_notes.json
Module chẩn đoán    →  diagnoses.json
LIS (xét nghiệm)    →  labs.json
Module dược         →  medications.json
EMR dị ứng          →  allergies.json
Module sinh hiệu    →  vitals.json
PACS/RIS (hình ảnh) →  imaging_reports.json
Module thủ thuật    →  procedures.json
```

**Ưu điểm so với monolithic JSON:**
- Phản ánh đúng kiến trúc HIS thực tế (dữ liệu đến từ nhiều module)
- Cho phép test assembler pipeline riêng biệt
- Dễ thêm bệnh nhân mới bằng cách append vào từng file
- Cho phép simulate data quality issues ở từng module riêng (edge cases)

## 3.2 Schema chuẩn hóa

So với schema tiếng Việt trong báo cáo tuần 1 (`ho_ten`, `ngay_sinh`, `benh_su`...), dataset tuần 2 chuyển toàn bộ sang **field names tiếng Anh snake_case** theo chuẩn engineering:

| Field tuần 1 (PRD) | Field tuần 2 (implementation) | Lý do |
|---|---|---|
| `ngay_sinh` / `dob` | `date_of_birth` | Rõ nghĩa hơn, tránh nhầm với date-of-birth vs age |
| `bat_thuong` | `is_abnormal` | Boolean flag theo convention Python |
| `nguy_hiem` | `is_critical` | Nhất quán với is_abnormal |
| `nhiet_do` | `temperature_celsius` | Đơn vị rõ ràng trong tên field |
| `spo2` | `spo2_percent` | Đơn vị rõ ràng trong tên field |
| `noi_dung` | `content` | Tiếng Anh chuẩn |

**Nguyên tắc thiết kế schema:**

```
Field names      → Tiếng Anh, snake_case
Clinical text    → Tiếng Việt có dấu (authentic)
Enum values      → Tiếng Anh (male/female, outpatient/inpatient, high/low/normal)
ICD-10 codes     → Tiếng Anh/quốc tế (E11, I10, E78.5)
Abbreviations    → Giữ nguyên trong free text, normalize ở preprocessing
```

## 3.3 Bốn patient profiles

Dataset gồm 4 bệnh nhân với các profile thiết kế có chủ đích:

### Profile A — P001: ĐTĐ type 2 kiểm soát kém + THA + RLLPM (Happy Path phức tạp)

```
Tuổi: 55, Nam
4 encounters (1/2024 → 10/2024, mỗi 3 tháng)
Diễn biến: HbA1c 9.2% → 8.1% → 7.5% → 7.1% (cải thiện dần)
           HA 148/92 → 138/88 → 132/82 → 128/78 (đạt mục tiêu)
Biến chứng: thần kinh ngoại biên sớm, microalbuminuria
Dị ứng: Penicillin (reaction rõ: nổi mề đay)
Edge cases: Không có — đây là case "happy path" phức tạp nhất
Mục đích: Case chính để test toàn bộ pipeline, citation đầy đủ
```

### Profile B — P002: ĐTĐ type 2 kiểm soát tốt + THA ổn định (Simple Case)

```
Tuổi: 50, Nữ
3 encounters (1/2024 → 7/2024)
Diễn biến: HbA1c ổn định 6.5-6.8%, HA đạt mục tiêu
Dị ứng: Không có (allergies = [])
Edge cases: EC-05 (không có dị ứng)
Mục đích: Test behavior khi không có allergy data
          "Chưa thấy ghi nhận dị ứng trong dữ liệu được cung cấp"
```

### Profile C — P003: THA kháng trị 10 năm + RLLPM + ĐTĐ mới phát hiện (Complex Timeline)

```
Tuổi: 62, Nam
5 encounters (6/2023 → 10/2024, bao gồm 1 lần nhập viện)
Diễn biến: Thay đổi phác đồ thuốc HA nhiều lần, phát hiện ĐTĐ mới giữa chừng
Biến chứng: Phì đại thất trái, gan nhiễm mỡ
Dị ứng: Sulfonamide (thiếu reaction — EC-03)
Edge cases: EC-03 (dị ứng thiếu thông tin), EC-07 (ICD thay đổi giữa encounters),
            EC-08 (thuốc bị ngưng giữa chừng), 1 encounter inpatient
Mục đích: Test treatment_timeline section, thuốc discontinued
```

### Profile D — P004: Edge Cases tập trung (Stress Test)

```
Tuổi: 68, Nữ
3 encounters (3/2024 → 9/2024)
Dị ứng: "Dị ứng thuốc" — không rõ loại thuốc, không rõ reaction
Edge cases: EC-01 (thuốc thiếu dose), EC-02 (XN thiếu đơn vị),
            EC-03 (dị ứng thiếu thông tin), EC-04 (ICD vs note mismatch),
            EC-06 (encounter không có XN), EC-09 (glucose critical low 2.5 mmol/L),
            EC-10 (clinical note nhiều viết tắt)
Mục đích: Test toàn bộ edge cases, validator warnings, khả năng chịu lỗi của pipeline
```

## 3.4 Thiết kế edge cases

10 loại edge case được cài đặt có chủ đích vào dataset, mỗi loại phục vụ test một hành vi cụ thể của pipeline:

| ID | Edge Case | Patient/Encounter | Phục vụ test |
|---|---|---|---|
| EC-01 | Thuốc thiếu liều (`dose = null`) | P004-E002 | Validator warning, chunker flag `[THIẾU THÔNG TIN LIỀU]` |
| EC-02 | XN thiếu đơn vị (`unit = null`) | P004-E001 | Validator warning, lab chunk thiếu unit |
| EC-03 | Dị ứng thiếu reaction (`reaction = null`) | P003, P004 | Allergy chunk `[CAN XAC NHAN LAI]`, C6 verifier flag |
| EC-04 | ICD-10 không khớp clinical note | P004-E003 | Citation verifier `CONTRADICTED` |
| EC-05 | Bệnh nhân không có dị ứng | P002 | Summary: "Chưa thấy ghi nhận dị ứng..." |
| EC-06 | Encounter không có XN | P004-E002 | Validator warning, section `abnormal_labs` rỗng |
| EC-07 | Mâu thuẫn chẩn đoán giữa 2 encounters | P003 | Timeline analysis, NEED_REVIEW |
| EC-08 | Thuốc discontinued (`is_current = false`) | P003 | `current_medications` chỉ lấy is_current=true |
| EC-09 | Glucose critical low (2.5 mmol/L) | P004-E003 | `is_critical = true`, `[NGUY HIỂM]` trong chunk |
| EC-10 | Clinical note nhiều viết tắt | P004-E003 | Normalizer expansion: THA → tăng huyết áp, ĐTĐ → đái tháo đường |

---

# Phần 4: Quy trình tạo dữ liệu tổng hợp

## 4.1 Bước 1: Thiết kế data template

Trước khi gọi AI, tôi thiết kế `data-template.md` — tài liệu mô tả schema của 10 file JSON, bao gồm:
- Mô tả từng field và kiểu dữ liệu
- Enum values được chấp nhận
- Quan hệ khóa giữa các bảng
- Data quality checklist (DQ-01 đến DQ-10)
- Ví dụ cho từng file

Template này được tham khảo từ:
1. Bệnh án điều trị cá nhân tại bệnh viện Bạch Mai (cấu trúc thực tế)
2. Thông tư 13/2025/TT-BYT (yêu cầu pháp lý về hồ sơ bệnh án điện tử)
3. Cấu trúc FHIR R4 resource types (để đảm bảo tương thích trong tương lai)

## 4.2 Bước 2: Thiết kế seed-data-prompt.md

`seed-data-prompt.md` là tài liệu kỹ thuật hướng dẫn AI tạo seed data, gồm:

**System prompt** với các ràng buộc bắt buộc:
```
- Nhất quán dữ liệu: patient_id, encounter_id phải khớp xuyên suốt 10 files
- Thực tế lâm sàng: giá trị XN trong khoảng sinh lý, thuốc đúng phác đồ Việt Nam
- Ngôn ngữ: clinical notes tiếng Việt có viết tắt y khoa
- PII: tên REDACTED hoặc tên giả, địa chỉ/CCCD/BHYT/SĐT = REDACTED
- IDs: patient_id "P001", encounter_id "P001-E001", lab_id "P001-E001-LAB001"
```

**User prompt templates** được điền theo từng patient profile (xem Appendix B trong seed-data-prompt.md).

**Validation checklist** 12 điểm để verify sau khi AI sinh data.

## 4.3 Bước 3: Gọi AI và tạo data

Mỗi bệnh nhân (P001–P004) được sinh trong một lần gọi LLM riêng biệt với system prompt + user prompt tương ứng. Quy trình:

```
Bước 1: Profile A (P001) — case phức tạp, happy path
Bước 2: Profile B (P002) — case đơn giản, EC-05
Bước 3: Profile C (P003) — case nhiều thay đổi thuốc, EC-03/07/08
Bước 4: Profile D (P004) — edge cases tập trung, EC-01/02/03/04/06/09/10
Bước 5: Validate mỗi patient
Bước 6: Merge 4 patients vào 10 file JSON chung
```

## 4.4 Bước 4: Chuẩn hóa schema sau khi nhận output

Sau khi nhận output từ AI, một số field names cần chuẩn hóa để khớp với Pydantic schemas trong `src/schemas.py`:

| Field AI sinh ra | Field chuẩn hóa | Lý do |
|---|---|---|
| `dob` | `date_of_birth` | Khớp PatientRecord schema |
| `abnormal: true` | `is_abnormal: true` | Khớp LabRecord schema |
| `critical: true` | `is_critical: true` | Khớp LabRecord schema |
| `temperature_c` | `temperature_celsius` | Khớp VitalRecord schema |
| `spo2` | `spo2_percent` | Khớp VitalRecord schema |
| `report_text` | `findings` | Khớp ImagingRecord schema |
| `result_summary` | `result` | Khớp ProcedureRecord schema |
| `gender: Nam/Nu` | `gender: male/female` | Enum tiếng Anh nhất quán |

Đây là bước quan trọng để đảm bảo raw data → assembled EHR → pipeline không có lỗi field name.

## 4.5 Tính xác thực lâm sàng của dataset

Để đảm bảo dữ liệu phản ánh thực tế y tế Việt Nam, tôi thực hiện các kiểm tra:

| Kiểm tra | Kết quả |
|---|---|
| ICD-10 codes hợp lệ | E11 (ĐTĐ type 2), I10 (THA), E78.5 (RLLPM) — đúng theo QĐ 4469/QĐ-BYT |
| Giá trị HbA1c hợp lý | 7.1–9.2% — nằm trong dải quan sát thực tế bệnh nhân ĐTĐ kiểm soát không tốt |
| Phác đồ thuốc đúng | Metformin → SGLT2i → GLP-1 theo hướng dẫn điều trị ĐTĐ type 2 Việt Nam 2023 |
| Khoảng tham chiếu XN | HbA1c ref 4.0–5.6%, Glucose đói 3.9–6.1 mmol/L, LDL <2.6 mmol/L (high risk) |
| Viết tắt y khoa | THA, ĐTĐ, BN, XN, CLS, RLLPM, NMCT, ĐTNKD, TSGĐ — phổ biến trong bệnh án Việt Nam |
| Mã BHYT format | insurance_id format 10 chữ số phù hợp thực tế |

---

# Phần 5: Kết quả dataset

## 5.1 Thống kê tổng thể

| File | Records | Ghi chú |
|---|---|---|
| `patients.json` | 4 | P001–P004 |
| `encounters.json` | 15 | P001:4, P002:3, P003:5, P004:3 |
| `labs.json` | 69 | Trung bình 4.6 XN/encounter |
| `medications.json` | 65 | Trung bình 4.3 thuốc/encounter |
| `diagnoses.json` | 44 | Trung bình 2.9 chẩn đoán/encounter |
| `clinical_notes.json` | 35 | Trung bình 2.3 notes/encounter |
| `vitals.json` | 15 | 1 bản ghi sinh hiệu/encounter |
| `imaging_reports.json` | 13 | ECG, siêu âm bụng, siêu âm tim |
| `procedures.json` | 9 | Test monofilament, UACR, khám bàn chân ĐTĐ |
| `allergies.json` | 3 | P001: Penicillin, P002: không có, P003: Sulfonamide, P004: unknown |
| **Tổng** | **273** | |

## 5.2 Thống kê SourceChunks sau pipeline C1+C2

| Patient | Encounters | Allergies | Tổng chunks | Labs | Meds | Diagnoses | Notes | Vitals | Imaging | Proc |
|---|---|---|---|---|---|---|---|---|---|---|
| P001 | 4 | 1 | **83** | 23 | 20 | 16 | 11 | 4 | 3 | 4 |
| P002 | 3 | 0 | **41** | 13 | 9 | 6 | 7 | 3 | 2 | 0 |
| P003 | 5 | 1 | **93** | 25 | 25 | 16 | 11 | 5 | 6 | 3 |
| P004 | 3 | 1 | **40** | 8 | 11 | 6 | 6 | 3 | 2 | 2 |
| **Tổng** | **15** | **3** | **257** | 69 | 65 | 44 | 35 | 15 | 13 | 9 |

**Mỗi SourceChunk** có:
- `source_id` duy nhất (ví dụ: `P001-E001-LAB-HBA1C`)
- `source_type` (labs, medications, diagnoses, clinical_notes, vitals, imaging, procedures, allergies, patient_info)
- `date` (ngày lấy mẫu/kê đơn/ghi chú)
- `content` (text ngắn gọn, embed-ready)
- `metadata` (structured fields cho filter: test_code, value, unit, abnormal, drug_name, icd10_code...)

## 5.3 Cấu trúc thư mục dữ liệu

```text
data/
├── raw/                    ← 10 file JSON flat từ HIS (INPUT, không sửa)
│   ├── patients.json
│   ├── encounters.json
│   ├── labs.json
│   ├── medications.json
│   ├── diagnoses.json
│   ├── vitals.json
│   ├── clinical_notes.json
│   ├── allergies.json
│   ├── imaging_reports.json
│   └── procedures.json
│
├── processed/              ← Output của C1+C2 pipeline
│   ├── assembled/          ← Per-patient assembled EHR (joined từ 10 bảng)
│   │   ├── P001.json
│   │   ├── P002.json
│   │   ├── P003.json
│   │   └── P004.json
│   ├── stores/             ← SourceChunk lookup stores (O(1) lookup)
│   │   ├── P001_store.json
│   │   ├── P002_store.json
│   │   ├── P003_store.json
│   │   └── P004_store.json
│   └── outputs/            ← LLM summary outputs (sau khi có API key)
│
├── dictionaries/           ← Reference data
│   └── medical_abbreviations_vi.json  ← 40+ viết tắt y khoa Việt Nam
│
└── seeds/                  ← Template và scripts (không thay đổi)
    ├── data-template.md
    ├── seed-data-prompt.md
    └── seed-dataset/       ← Dataset phiên bản cũ (giữ lại tham khảo)
```

---

# Phần 6: Triển khai kỹ thuật — C1 & C2 Pipeline

Phần này mô tả kỹ thuật triển khai pipeline xử lý dữ liệu, đáp ứng yêu cầu từ nhận xét tuần 1 về việc chuyển từ thiết kế sang PoC kỹ thuật.

## 6.1 C1 — EMR Integration (4 components)

### 6.1.1 Assembler (`src/c1_emr/assembler.py`)

Đọc 10 file raw và join theo `patient_id` + `encounter_id` để tạo `AssembledEHR` per patient:

```python
def assemble(raw_dir: Path) -> dict[str, dict]:
    """
    Load 10 flat tables → join per patient.
    Returns {patient_id: assembled_ehr_dict}
    """
    patients     = _load(raw_dir / "patients.json")
    encounters   = _load(raw_dir / "encounters.json")
    labs_by_enc  = _group_by(_load(raw_dir / "labs.json"), "encounter_id")
    # ... 7 tables more
    
    for pat in patients:
        pid = pat["patient_id"]
        encounter_list = []
        for enc in sorted(encs_by_pat[pid], key=lambda e: e["encounter_date"]):
            eid = enc["encounter_id"]
            encounter_list.append({
                **enc,
                "vitals":         vitals_by_enc.get(eid, []),
                "labs":           labs_by_enc.get(eid, []),
                "medications":    meds_by_enc.get(eid, []),
                "diagnoses":      dx_by_enc.get(eid, []),
                "clinical_notes": notes_by_enc.get(eid, []),
                "imaging":        imaging_records,
                "procedures":     proc_records,
            })
```

Output là `AssembledEHR` với cấu trúc: `patient_id → patient block + allergies + encounters[]`.

### 6.1.2 Validator (`src/c1_emr/validator.py`)

Kiểm tra dữ liệu trước khi vào pipeline. Phân biệt hai mức độ:

| Mức độ | Ví dụ | Hành vi |
|---|---|---|
| `error` | Missing `patient_id`, missing `encounter_date` | Block pipeline, raise `C1ProcessingError` |
| `warning` | Thuốc thiếu dose, XN thiếu unit | Cho phép tiếp tục, log warning |

Điều này đảm bảo pipeline không crash khi gặp edge cases (EC-01, EC-02), nhưng vẫn thông báo vấn đề để evaluator biết.

### 6.1.3 De-identifier (`src/c1_emr/deidentifier.py`)

Mask PII trước khi dữ liệu đến LLM API:

```python
PII_FIELDS_FULL    = {"citizen_id", "insurance_id", "phone"}  # → [REDACTED]
PII_FIELDS_PARTIAL = {"address"}  # Giữ quận/tỉnh, xóa số nhà
```

Kiểm tra bổ sung: pattern CCCD 12 chữ số và BHYT format — không để lọt qua dù field name khác.

### 6.1.4 Normalizer (`src/c1_emr/normalizer.py`)

Mở rộng viết tắt y khoa trong clinical free text trước khi chunking:

```python
"THA"   → "tăng huyết áp"
"ĐTĐ"   → "đái tháo đường"
"RLLPM" → "rối loạn lipid máu"
"BN"    → "bệnh nhân"
```

**Kỹ thuật quan trọng:** Dùng word-boundary regex để tránh thay thế sai:
```python
pattern = r'(?<![a-zA-ZÀ-ɏ])' + re.escape(abbr) + r'(?![a-zA-ZÀ-ɏ])'
```
→ "THA" khớp nhưng "THAY" không bị thay thế.

## 6.2 C2 — Chunking Service (2 components)

### 6.2.1 Chunker (`src/c2_chunking/chunker.py`)

Nguyên tắc: **1 chunk = 1 fact có thể cite độc lập**.

Mỗi loại dữ liệu được chuyển thành SourceChunk theo logic riêng:

```python
# Lab chunk — ví dụ output:
"HbA1c (Hemoglobin glycated): 9.2 %
 (tham chieu: 4.0 - 5.6) [BẤT THƯỜNG - cao]
 Kiểm soát đường huyết kém. Mục tiêu <7.5% cho BN 55 tuổi."

source_id = "P001-E001-LAB-HBA1C"
metadata  = {"value": 9.2, "unit": "%", "abnormal": True}

# Medication chunk — ví dụ output:
"Metformin 1000 mg. lieu: 1 viên. tan suat: 2 lần/ngày (sáng và tối).
 Uống sau ăn sáng và sau ăn tối. Tăng từ 500mg lên 1000mg."

source_id = "P001-E001-MED-METFORMIN"
metadata  = {"drug_name": "Metformin", "is_current": True, "missing_dose": False}
```

**Source ID convention:**
```
{encounter_id}-{TYPE}-{IDENTIFIER}
P001-E001-LAB-HBA1C
P001-E001-MED-METFORMIN
P001-E001-DX-E11
P001-E001-NOTE-P001-E001-NOTE001
P001-PATIENT-ALLERGY-PENICILLIN
P001-PATIENT-INFO
```

### 6.2.2 Store Builder (`src/c2_chunking/store_builder.py`)

Xây dựng lookup dict `{source_id: chunk_dict}` — O(1) để citation verification:

```python
store = build_structured_store(chunks)
chunk = get_chunk(store, "P001-E001-LAB-HBA1C")  # instant lookup
```

Store được serialize sang JSON và lưu vào `data/processed/stores/P001_store.json`.

## 6.3 Từ điển viết tắt y khoa (`data/dictionaries/medical_abbreviations_vi.json`)

40+ viết tắt y khoa Việt Nam phổ biến được compile từ bệnh án thực tế:

```json
{
  "THA":   "tăng huyết áp",
  "ĐTĐ":   "đái tháo đường",
  "RLLPM": "rối loạn lipid máu",
  "BN":    "bệnh nhân",
  "NMCT":  "nhồi máu cơ tim",
  "ĐTNKD": "đau thắt ngực không ổn định",
  "TBMMN": "tai biến mạch máu não",
  "MLCT":  "mức lọc cầu thận",
  ...
}
```

---

# Phần 7: Kết quả kiểm thử

## 7.1 Unit tests (44 tests — 100% pass)

```
tests/test_c1_emr.py    — 22 tests
  TestValidator    (8):  Missing fields, empty encounters, duplicate IDs,
                         warning-only edge cases
  TestDeidentifier (7):  PII fields redacted, full_name preserved,
                         no mutation of input, nested PII
  TestNormalizer   (7):  THA/ĐTĐ expanded, partial word not replaced,
                         normalize_ehr no crash, empty string handling

tests/test_c2_chunking.py — 22 tests
  TestChunker      (14): Non-empty chunks, all SourceChunk instances,
                         unique IDs, has lab/med/dx/allergy/vital chunks,
                         P001 has Penicillin, P002 no allergy,
                         P004 edge case no crash, ICD-10 preserved
  TestStoreBuilder  (7): All chunk IDs in store, O(1) lookup < 0.1s,
                         get_chunk returns SourceChunk, filter_by_type,
                         store serializable to JSON

44 passed in 0.26s
```

## 7.2 Week 2 checkpoint (23/23 — ALL PASSED)

```
============================================================
  WEEK 2 CHECKPOINT
============================================================
  [OK]   data/processed/assembled/P001.json exists
  [OK]   data/processed/assembled/P002.json exists
  [OK]   data/processed/assembled/P003.json exists
  [OK]   data/processed/assembled/P004.json exists
  [OK]   data/processed/stores/P001_store.json exists
  [OK]   src/schemas.py exists
  ... (16 more source files) ...
  [OK]   P001 chunks >= 20 (got 83)
  [OK]   P001 source_ids all unique
  [OK]   P001 has allergy chunk
  [OK]   PoC output P001 exists (needs API run)
  [OK]   PoC sections == 8 (got 8)
  [OK]   PoC citation coverage >= 30% (got 100%)
  [OK]   PoC latency <= 120s (got 29.7s)

Result: 23/23 checks passed
ALL PASSED — Week 2 deliverables complete!
```

## 7.3 PoC Pipeline end-to-end

Pipeline đầy đủ (C1 + C2 + LLM) đã chạy thành công cho P001:

```
Latency:   29.7s
Tokens:    ~12,000
Coverage:  100% (8/8 sections có citation)
Model:     gpt-4o (sẽ chuyển sang Claude tuần 3)
```

Kết quả PoC xác nhận dữ liệu đủ chất lượng để pipeline hoạt động — không có section nào trả về lỗi hoặc "Chưa thấy ghi nhận..." không đúng chỗ.

---

# Phần 8: Phản hồi nhận xét tuần 1

## 8.1 "Cần tập trung triển khai PoC kỹ thuật"

**Tuần 1:** 100% thiết kế (PRD, workflow, architecture diagram)  
**Tuần 2:** Chuyển sang triển khai thực tế — 2,000+ dòng code Python, 44 unit tests, pipeline chạy được end-to-end

| Component | Trạng thái tuần 2 |
|---|---|
| Schema (`src/schemas.py`) | ✅ Pydantic models cho 11 data types + citation types |
| C1 Assembler | ✅ Raw tables → AssembledEHR per patient |
| C1 Validator | ✅ Error/warning taxonomy, blocking vs non-blocking |
| C1 De-identifier | ✅ PII masking với regex guards |
| C1 Normalizer | ✅ 40+ abbreviations, word-boundary matching |
| C2 Chunker | ✅ 9 source types, 257 chunks từ dataset |
| C2 Store Builder | ✅ O(1) citation lookup |
| PoC Pipeline | ✅ 8 sections, 100% citation coverage |

## 8.2 "Benchmark các mô hình summarization"

Tuần 2 chưa benchmark nhiều mô hình — ưu tiên hoàn thiện data pipeline trước. Tuần 3 sẽ:
- Chuyển từ OpenAI sang Claude API (như thiết kế gốc)
- So sánh `claude-haiku-4-5` vs `claude-sonnet-4-6` về chất lượng citation và latency

## 8.3 "Xây dựng citation verification pipeline"

Tuần 2 triển khai foundation:
- `source_id` convention nhất quán (ví dụ `P001-E001-LAB-HBA1C`)
- Structured store cho O(1) lookup
- PoC pipeline đã sinh source_ids và verify existence

Tuần 3 sẽ mở rộng thành claim-level citation: extract atomic claims → match evidence → SUPPORTED/UNSUPPORTED/CONTRADICTED.

## 8.4 "Thực hiện đánh giá trên các bộ dữ liệu mục tiêu"

Dataset tuần 2 có 4 bệnh nhân với độ phức tạp khác nhau, đủ để:
- Test citation pipeline (P001 — happy path phức tạp)
- Test missing allergy behavior (P002)
- Test treatment timeline (P003)
- Test edge cases + hallucination detection (P004)

---

# Phần 9: Hạn chế và hướng tiếp theo

## 9.1 Hạn chế của dataset tuần 2

| Hạn chế | Ảnh hưởng | Kế hoạch giải quyết |
|---|---|---|
| Chỉ có 4 bệnh nhân | Không đủ cho statistical evaluation | Tuần 4 mở rộng thêm 4–6 bệnh nhân với profiles khác nhau |
| Chỉ 1 chuyên khoa (nội tiết) | Không phản ánh đa dạng clinical notes | Post-MVP: thêm tim mạch, thận học |
| AI-generated text | Clinical notes có thể không 100% authentic | Đủ cho PoC; production cần real de-identified data |
| 40 viết tắt trong dictionary | Bỏ sót một số viết tắt hiếm | Cần domain expert review |
| Chưa có real clinical validation | Không bác sĩ review dataset | Kế hoạch tuần 4: human evaluation form |

## 9.2 Quyết định thiết kế quan trọng nhất

**Quyết định 1:** Dùng 10 file JSON modular thay vì monolithic EHR  
→ Phản ánh đúng kiến trúc HIS thực tế, dễ test từng module

**Quyết định 2:** Tách biệt `data/raw/` (input không thay đổi) với `data/processed/` (pipeline output)  
→ Đảm bảo reproducibility — có thể chạy lại assembler bất kỳ lúc nào

**Quyết định 3:** Edge cases được cài đặt có chủ đích với `data_note` annotation  
→ Pipeline có thể test behavior cụ thể, không phụ thuộc vào lỗi ngẫu nhiên

**Quyết định 4:** Schema field names tiếng Anh ngay từ đầu  
→ Loại bỏ toàn bộ class bug về field name mismatch trong pipeline

## 9.3 Kế hoạch tuần 3-4

Theo `plans/PLAN_Week3_Week4_ActionPlan.md`:

| Tuần | Trọng tâm | Deliverable |
|---|---|---|
| Tuần 3 | Citation Pipeline (C5) + Hallucination Mitigation (C6) | Claim extraction, evidence matching, KEEP/FLAG/REMOVE verifier |
| Tuần 4 | Evaluation + FastAPI + Streamlit Demo | Auto metrics, human eval package, demo end-to-end |

---

# Appendix A: Cấu trúc thư mục dữ liệu

```text
data/
├── raw/                           ← INPUT (không sửa trực tiếp)
│   ├── patients.json              4 records
│   ├── encounters.json            15 records
│   ├── labs.json                  69 records
│   ├── medications.json           65 records
│   ├── diagnoses.json             44 records
│   ├── vitals.json                15 records
│   ├── clinical_notes.json        35 records
│   ├── allergies.json             3 records
│   ├── imaging_reports.json       13 records
│   └── procedures.json            9 records
│
├── processed/                     ← PIPELINE OUTPUT
│   ├── assembled/
│   │   ├── P001.json              83-chunk equivalent
│   │   ├── P002.json
│   │   ├── P003.json
│   │   └── P004.json
│   ├── stores/
│   │   ├── P001_store.json        83 chunks, O(1) lookup
│   │   ├── P002_store.json        41 chunks
│   │   ├── P003_store.json        93 chunks
│   │   └── P004_store.json        40 chunks
│   └── outputs/                   ← LLM summaries (generated)
│       └── P001_summary.json
│
├── dictionaries/
│   └── medical_abbreviations_vi.json   40+ abbreviations
│
└── seeds/                         ← REFERENCE (không thay đổi)
    ├── data-template.md           Schema documentation
    ├── seed-data-prompt.md        AI generation prompts
    └── seed-dataset/              Phiên bản dataset gốc (v1)
```

---

# Appendix B: Thống kê dataset chi tiết

## Encounters per patient

| Patient | Encounter IDs | Loại khám |
|---|---|---|
| P001 | E001–E004 | 4 outpatient (mỗi 3 tháng) |
| P002 | E001–E003 | 3 outpatient (mỗi 3 tháng) |
| P003 | E001–E005 | 4 outpatient + 1 inpatient |
| P004 | E001–E003 | 3 outpatient (mỗi 3 tháng) |

## Labs — phân bố theo encounter

```
P001: 5–6 XN/encounter (HbA1c, FPG, LDL, TC, TG, HDL, Creatinine, eGFR, UACR...)
P002: 4–5 XN/encounter
P003: 5–6 XN/encounter + panel thêm khi nghi ngờ biến chứng
P004: 3–4 XN/encounter (E002 không có XN — EC-06)
```

## Medications — tiến triển qua các encounter

```
P001-E001: Metformin 500mg → 1000mg, thêm Empagliflozin, tăng Atorvastatin 20→40mg, thêm Perindopril
P001-E002: Giữ nguyên phác đồ
P001-E003: Giữ nguyên
P001-E004: Cân nhắc giảm liều nếu duy trì

P003: Thay Amlodipine → Losartan → kết hợp, Statin tăng liều, thêm Metformin E003
      Bisoprolol E002 → ngưng E004 (EC-08: is_current = false)
```

---

# Appendix C: Edge cases đã cài đặt

## Kiểm tra tự động bằng dry_run.py

| Edge Case | File | Validator behavior | Chunker behavior |
|---|---|---|---|
| EC-01: missing dose | P004-E002 medication | `[W] missing dose and strength` | `[THIẾU THÔNG TIN LIỀU]` trong content |
| EC-02: missing unit | P004-E001 lab | `[W] missing unit` | chunk hiển thị value không có unit |
| EC-03: allergy no reaction | P003, P004 allergy | — | `[CAN XAC NHAN LAI VOI BENH NHAN]` trong content |
| EC-05: no allergy | P002 | — | Không có allergy chunk → summary "Chưa thấy ghi nhận..." |
| EC-06: no labs in encounter | P004-E002 | — | 0 lab chunks cho encounter đó |
| EC-09: critical glucose | P004-E003 lab | — | `[NGUY HIỂM]` trong lab chunk |

## Kiểm tra bằng mắt (manual review khi có LLM)

| Edge Case | Expected behavior |
|---|---|
| EC-04: ICD vs note mismatch | Citation verifier: `CONTRADICTED` hoặc `NEED_REVIEW` |
| EC-07: conflicting diagnoses | Timeline: hiển thị cả hai kèm ngày, flag NEED_REVIEW |
| EC-08: discontinued medication | `current_medications` section chỉ lấy `is_current=true` |
| EC-10: heavy abbreviations | Normalizer: expand THA, ĐTĐ, RLLPM... trước khi chunk |
