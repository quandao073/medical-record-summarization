# Báo cáo Tuần 2 — Prepare EHR Dataset cho Medical Record Summarization

**Tác giả:** Đào Anh Quân  
**Project:** Medical Record Summarization / Clinical Summarization & Citation Pipeline  
**Tuần:** Tuần 2 — Prepare EHR Dataset  
**Trọng tâm:** Thiết kế, chuẩn hóa và tạo seed EHR dataset phục vụ PoC kỹ thuật  
**Dataset version:** `poc_seed_v1_synthetic_raw_pii`  
**Ngày tạo báo cáo:** 2026-06-03

---

## 1. Tóm tắt điều hành

Trong tuần 2, trọng tâm công việc được chuyển từ mức **thiết kế sản phẩm/kiến trúc** sang mức **chuẩn bị dữ liệu và chứng minh tính khả thi kỹ thuật** cho bài toán Medical Record Summarization.

Theo kế hoạch, nhiệm vụ chính của tuần này là **Prepare EHR dataset**. Tuy nhiên, trong quá trình khảo sát, hiện chưa tìm được một bộ public dataset phù hợp trực tiếp với bài toán tóm tắt bệnh án tiếng Việt theo cấu trúc HIS/EMR, đặc biệt là dataset có đủ các thành phần cần thiết như lần khám, chẩn đoán, xét nghiệm, đơn thuốc, sinh hiệu, dị ứng, ghi chú lâm sàng, chẩn đoán hình ảnh và dữ liệu longitudinal qua nhiều lần tái khám.

Vì vậy, hướng tiếp cận trong tuần 2 là:

```text
Tham khảo cấu trúc bệnh án cá nhân tại Bệnh viện Bạch Mai
→ trừu tượng hóa thành template dữ liệu EHR
→ chuẩn hóa schema thành raw modular JSON dataset
→ dùng AI tạo synthetic seed data
→ thêm edge cases để test citation / hallucination / PII masking
→ validate dataset để sẵn sàng cho PoC kỹ thuật
```

Điểm quan trọng: dữ liệu được tạo ra trong tuần 2 là **dữ liệu giả lập/synthetic**, không phải dữ liệu bệnh nhân thật. Bệnh án cá nhân chỉ được dùng để tham khảo **kiểu trường dữ liệu, luồng thông tin và cách hồ sơ y tế được tổ chức**, không đưa nội dung bệnh án thật vào dataset.

---

## 2. Liên hệ với nhận xét mentor sau tuần 1

Nhận xét tuần 1 đánh giá cao phần PRD và workflow vì đã có tư duy product + system design khá hoàn chỉnh: citation grounding, Human-in-the-Loop, audit logging, safety review và evaluation framework. Tuy nhiên, mentor cũng chỉ ra rằng phần lớn kết quả vẫn ở mức thiết kế, cần chuyển sang PoC kỹ thuật để chứng minh tính khả thi.

Tuần 2 phản hồi trực tiếp nhận xét này theo 4 hướng:

| Nhận xét tuần 1 | Hành động trong tuần 2 |
|---|---|
| Kết quả còn ở mức thiết kế sản phẩm | Chuyển sang chuẩn bị dataset có thể chạy được bằng code |
| Cần triển khai PoC kỹ thuật | Tạo raw dataset đủ để chạy pipeline C1 → C7 |
| Cần citation verification pipeline | Thiết kế dataset có `patient_id`, `encounter_id`, record-level source để sinh `SourceChunk` |
| Cần đánh giá trên bộ dữ liệu mục tiêu | Tạo các case happy path + edge cases để phục vụ evaluation |

Như vậy, tuần 2 không chỉ tạo dữ liệu mẫu, mà còn xây dựng nền tảng để các tuần sau có thể triển khai:

```text
EMR Integration
→ Source Chunking
→ Section-wise Retrieval
→ Active Summarizer
→ Citation Pipeline
→ Hallucination Mitigation
→ Evaluation
```

---

## 3. Vấn đề khi tìm public EHR dataset

Mục tiêu ban đầu là tìm một public dataset có thể dùng trực tiếp cho bài toán Medical Record Summarization. Tuy nhiên, có một số khó khăn:

1. **Thiếu public dataset tiếng Việt về EHR/EMR.**  
   Các dataset y tế công khai thường là tiếng Anh hoặc tập trung vào medical QA, NER, imaging hoặc dialogue summarization, không phản ánh đầy đủ cấu trúc bệnh án tiếng Việt.

2. **Bệnh án là dữ liệu nhạy cảm.**  
   Dữ liệu EHR thật thường chứa thông tin định danh cá nhân, thông tin khám chữa bệnh, thuốc, chẩn đoán, xét nghiệm và lịch sử điều trị. Vì vậy, public dataset dạng raw EHR rất khó có sẵn.

3. **Dataset public không khớp workflow của project.**  
   Project này không chỉ cần text để summarize, mà còn cần dữ liệu có thể trace citation, gồm: source record, source type, encounter date, lab value, medication dose, diagnosis ICD-10, allergy status.

4. **PoC cần dữ liệu có intentional edge cases.**  
   Để test hallucination mitigation, dataset cần có các trường hợp như thiếu liều thuốc, thiếu đơn vị xét nghiệm, dị ứng không rõ, ICD mismatch. Public dataset nếu có cũng khó đảm bảo đúng các tình huống này.

Vì vậy, lựa chọn phù hợp cho giai đoạn PoC là tạo **synthetic EHR seed dataset** dựa trên template được thiết kế có kiểm soát.

---

## 4. Nguyên tắc thiết kế dataset

### 4.1 Mục tiêu của dataset

Dataset tuần 2 được thiết kế để phục vụ PoC, không nhằm thay thế clinical dataset thật. Các mục tiêu chính:

- Có đủ cấu trúc của một hồ sơ EHR cơ bản.
- Có dữ liệu longitudinal qua nhiều lần khám.
- Có dữ liệu structured và unstructured.
- Có thể tạo source chunks để citation.
- Có thể test PII masking.
- Có thể test edge cases liên quan đến hallucination và low-confidence claims.
- Có thể dùng làm input cho FastAPI/Streamlit demo.

### 4.2 Chính sách ngôn ngữ và schema

Dataset dùng chính sách chuẩn hóa sau:

| Layer | Chuẩn sử dụng | Lý do |
|---|---|---|
| Field names | Tiếng Anh `snake_case` | Dễ dùng với Python, Pydantic, FastAPI, SQL |
| Controlled values | Tiếng Anh enum/code | Dễ validate và map sang chuẩn quốc tế |
| Clinical free-text | Tiếng Việt có dấu, UTF-8 | Giữ đúng ngữ cảnh bệnh án Việt Nam |
| IDs / codes | ASCII-safe stable IDs | Tránh lỗi encoding, dễ dùng trong citation |
| Tiếng Việt không dấu | Không dùng làm canonical text | Tránh mất nghĩa và giảm chất lượng embedding |

Ví dụ:

```json
{
  "patient_id": "P001",
  "encounter_id": "P001-E001",
  "test_code": "HBA1C",
  "test_name": "HbA1c (Hemoglobin glycated)",
  "value": 9.2,
  "unit": "%",
  "is_abnormal": true,
  "comment": "Kiểm soát đường huyết kém."
}
```

---

## 5. Phương pháp tạo dataset

### 5.1 Nguồn tham khảo template

Do không tìm được dataset phù hợp, tôi tham khảo cấu trúc bệnh án cá nhân tại Bệnh viện Bạch Mai để hiểu các nhóm thông tin thường xuất hiện trong hồ sơ khám chữa bệnh, ví dụ:

- Thông tin hành chính bệnh nhân.
- Lý do khám.
- Bệnh sử.
- Tiền sử bản thân/gia đình.
- Khám lâm sàng.
- Chẩn đoán.
- Xét nghiệm.
- Thuốc điều trị.
- Dị ứng.
- Chẩn đoán hình ảnh/thăm dò chức năng.
- Diễn biến qua các lần tái khám.

Sau đó, các nhóm thông tin này được trừu tượng hóa thành schema JSON, không dùng dữ liệu thật.

### 5.2 Tạo synthetic data bằng AI

AI được dùng để tạo các seed records theo template đã xác định. Quy trình:

```text
1. Xác định bệnh cảnh mục tiêu: ĐTĐ type 2, THA, RLLPM
2. Tạo hồ sơ bệnh nhân synthetic
3. Tạo nhiều encounters theo timeline
4. Tạo labs, medications, diagnoses, vitals, notes tương ứng
5. Thêm edge cases có chủ đích
6. Chuẩn hóa field names
7. Validate quan hệ patient_id / encounter_id
8. Đóng gói raw dataset
```

AI không được dùng để tạo output summary cuối ở bước này. Tuần 2 chỉ tập trung vào dataset.

---

## 6. Cấu trúc raw dataset

Dataset được chia thành 10 file raw JSON, mô phỏng dữ liệu đến từ các module khác nhau của HIS/EMR:

```text
data/raw/
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

### 6.1 Mô tả từng file

| File | Vai trò trong PoC |
|---|---|
| `patients.json` | Thông tin hành chính và định danh bệnh nhân, dùng để test PII masking |
| `encounters.json` | Các lần khám/điều trị, làm trục thời gian chính |
| `clinical_notes.json` | Ghi chú lâm sàng tiếng Việt, dùng cho retrieval narrative |
| `diagnoses.json` | Chẩn đoán, ICD-10, bệnh chính/bệnh kèm/biến chứng |
| `labs.json` | Kết quả xét nghiệm có giá trị số, đơn vị, khoảng tham chiếu |
| `medications.json` | Đơn thuốc, hàm lượng, liều, tần suất, cách dùng |
| `allergies.json` | Dị ứng đã biết hoặc dị ứng chưa rõ cần xác nhận |
| `vitals.json` | Sinh hiệu, huyết áp, mạch, SpO2, BMI |
| `imaging_reports.json` | ECG, siêu âm, chẩn đoán hình ảnh dạng text |
| `procedures.json` | Thủ thuật/khám chuyên biệt như khám bàn chân ĐTĐ |

### 6.2 Số lượng records

| File | Số records |
|---|---:|
| `allergies.json` | 3 |
| `clinical_notes.json` | 35 |
| `diagnoses.json` | 44 |
| `encounters.json` | 15 |
| `imaging_reports.json` | 13 |
| `labs.json` | 69 |
| `medications.json` | 65 |
| `patients.json` | 4 |
| `procedures.json` | 9 |
| `vitals.json` | 15 |

Tổng dataset hiện tại có 4 bệnh nhân, 15 encounters, 69 lab records, 65 medication records và 35 clinical notes. Đây là quy mô nhỏ nhưng đủ cho PoC kỹ thuật.

---

## 7. Thiết kế patient profiles

Dataset gồm 4 patient profiles, mỗi profile phục vụ một mục tiêu test khác nhau.

| Patient | Tuổi | Giới | Vai trò trong PoC |
|---|---:|---|---|
| P001 | 55 | male | Profile A — ĐTĐ type 2 kiểm soát kém + THA + RLLPM. 4 encounters mỗi 3 tháng. Case phức tạp happy path. |
| P002 | 50 | female | Profile B — ĐTĐ type 2 kiểm soát tốt + THA ổn định. 3 encounters. EC-05: không có dị ứng. |
| P003 | 62 | male | Profile C — THA kháng trị 10 năm + RLLPM 5 năm + ĐTĐ type 2 mới phát hiện. 5 encounters (1 nhập viện). EC-03, EC-07, EC-08. |
| P004 | 68 | female | Profile D — Edge cases tập trung. EC-01 (thiếu dose), EC-02 (thiếu unit XN), EC-03 (dị ứng không rõ), EC-04 (ICD mismatch), EC-06 (không có XN E002), EC-09 (glucose critical low), EC-10 (nhiều viết tắt). |

### 7.1 P001 — Complex happy path

P001 là case chính để demo pipeline hoàn chỉnh. Bệnh nhân có:

- Đái tháo đường type 2.
- Tăng huyết áp.
- Rối loạn lipid máu.
- Nhiều lần tái khám.
- Lab trend rõ: HbA1c, LDL, UACR.
- Điều chỉnh thuốc theo thời gian.
- Biến chứng nhẹ như microalbuminuria và thần kinh ngoại biên.

Case này dùng để test:

```text
patient_overview
current_medications
abnormal_labs
diagnoses
treatment_timeline
clinical_alerts
```

### 7.2 P002 — Stable chronic disease

P002 là case tương đối ổn định, ít edge case, dùng để kiểm tra hệ thống có tránh over-warning hay không. Mục tiêu là kiểm tra summary khi bệnh nhân kiểm soát tốt và không có dị ứng.

### 7.3 P003 — Longitudinal / complex condition

P003 có nhiều bệnh nền và diễn biến dài hơn, dùng để test khả năng tổng hợp nhiều encounters, đặc biệt khi bệnh nhân có tăng huyết áp kháng trị, rối loạn lipid máu và đái tháo đường mới phát hiện.

### 7.4 P004 — Edge-case patient

P004 tập trung vào các tình huống lỗi có chủ đích:

- Thuốc thiếu liều.
- Xét nghiệm thiếu đơn vị.
- Dị ứng không rõ loại thuốc/phản ứng.
- ICD mismatch.
- Encounter không có một số nhóm dữ liệu.
- Giá trị xét nghiệm có nguy cơ critical.
- Clinical notes có nhiều viết tắt.

Case này đặc biệt quan trọng để test `LOW_CONFIDENCE`, `NEED_REVIEW`, `NO_CITATION` và `CONTRADICTED`.

---

## 8. Thông tin cá nhân synthetic phục vụ PII masking

Ban đầu dataset dùng `REDACTED` cho các trường cá nhân. Tuy nhiên, để test module PII masking bằng code, dataset đã được cập nhật để có thông tin cá nhân giả lập nhưng đúng format.

Các trường trong `patients.json` gồm:

```json
{
  "full_name": "Nguyễn Văn An",
  "address": "Phường Cầu Giấy, Quận Cầu Giấy, Thành phố Hà Nội",
  "citizen_id": "001069123456",
  "phone": "0912345678",
  "insurance_id": "0123456789"
}
```

### 8.1 Format được sử dụng

| Field | Format trong dataset | Mục đích |
|---|---|---|
| `citizen_id` | 12 chữ số | Test masking CCCD/số định danh cá nhân |
| `phone` | 10 chữ số, đầu số di động Việt Nam | Test masking số điện thoại |
| `insurance_id` | 10 chữ số | Test masking mã BHYT/BHXH |
| `address` | Phường/xã, quận/huyện, tỉnh/thành phố | Test masking địa chỉ |

Các thông tin trên là giả lập theo format, không phải thông tin thật và không nên push lên GitHub.

### 8.2 Lý do không dùng `pii_status`

Trường `pii_status` đã được loại bỏ khỏi raw dataset vì mục tiêu của tuần 2 là test PII masking bằng code. Nếu để sẵn `pii_status`, pipeline có thể phụ thuộc vào metadata nhân tạo thay vì thực sự phát hiện và mask thông tin nhạy cảm từ các field thực tế.

---

## 9. Edge cases được thiết kế có chủ đích

Dataset không chỉ chứa happy path mà còn chứa intentional edge cases để test robustness.

| Edge case | Mục tiêu test |
|---|---|
| Medication thiếu dose | Citation/verifier phải flag `LOW_CONFIDENCE` hoặc `NEED_REVIEW` |
| Lab thiếu unit | Claim có value nhưng thiếu unit phải bị flag |
| Allergy thiếu reaction/severity | Allergy section không được bỏ qua, cần yêu cầu xác nhận |
| ICD mismatch | Test `CONTRADICTED` hoặc `NEED_REVIEW` |
| Encounter thiếu labs | Summary không được hallucinate xét nghiệm |
| Critical low glucose | Clinical alerts phải phát hiện được rủi ro |
| Nhiều viết tắt y khoa | Test abbreviation normalizer |
| Nhiều lần tái khám | Test treatment timeline và trend summarization |

---

## 10. Validation dataset

Validation summary hiện tại:

```json
{
  "errors": 0,
  "warnings": 2
}
```

Các warning còn lại:

| File | Index | Severity | Message |
|---|---:|---|---|
| labs.json | 63 | warning | lab P004-E001-LAB003 has value but missing unit |
| medications.json | 60 | warning | medication P004-E002-MED004 missing dose |

Hai warning này được giữ lại có chủ đích để test pipeline, không phải lỗi cần xóa.

### 10.1 Validation rules

Các rule kiểm tra chính:

- Mọi record phải có `patient_id`.
- Record theo lần khám phải có `encounter_id`.
- `patient_id` trong các file phải tồn tại trong `patients.json`.
- `encounter_id` phải tồn tại trong `encounters.json`.
- Date format phải nhất quán.
- Lab có `value` nhưng thiếu `unit` được warning.
- Medication thiếu `dose` được warning.
- Dữ liệu cá nhân synthetic phải đúng format để test masking.

---

## 11. Mapping dataset với pipeline PoC

### 11.1 C1 — EMR Integration

Dataset hỗ trợ C1 bằng cách cung cấp nhiều raw files modular. C1 sẽ thực hiện:

```text
load raw JSON files
→ validate schema
→ assemble by patient_id + encounter_id
→ de-identify PII
→ normalize abbreviations
```

### 11.2 C2 — Source Chunking

Mỗi raw record có thể chuyển thành `SourceChunk`. Ví dụ:

| Raw record | SourceChunk type |
|---|---|
| One lab result | `lab_result` |
| One medication | `medication` |
| One diagnosis | `diagnosis` |
| One clinical note section | `clinical_note` |
| One allergy record | `allergy` |
| One vital record | `vital` |
| One imaging report | `imaging` |
| One procedure | `procedure` |

### 11.3 C3 — Section-wise Retrieval

Dataset hỗ trợ retrieval theo section:

| Summary section | Data source |
|---|---|
| `patient_overview` | patients, diagnoses, vitals, clinical_notes |
| `chief_complaint` | encounters, clinical_notes |
| `medical_history` | clinical_notes, diagnoses, allergies |
| `current_medications` | medications |
| `allergies` | allergies, clinical_notes |
| `abnormal_labs` | labs |
| `diagnoses` | diagnoses |
| `treatment_timeline` | encounters, labs, medications, diagnoses, notes |
| `clinical_alerts` | allergies, abnormal labs, abnormal vitals, edge cases |

### 11.4 C5/C6 — Citation and Hallucination Mitigation

Dataset được thiết kế để test claim verification:

```text
claim → candidate source chunks → evidence matching → status
```

Các field như `lab_id`, `medication_id`, `diagnosis_id`, `allergy_id`, `encounter_id` là cơ sở để sinh `source_id` và trace citation.

---

## 12. Dataset readiness cho PoC

Dataset hiện đã sẵn sàng cho PoC ở mức raw input. Các deliverables đã có:

| Deliverable | Status |
|---|---|
| Raw modular JSON files | Done |
| Standardized English field names | Done |
| Vietnamese clinical text with diacritics | Done |
| Synthetic patient profiles | Done |
| Synthetic personal identifiers for PII masking | Done |
| Edge cases for verifier | Done |
| Dataset manifest | Done |
| Validation summary | Done |

---

## 13. Hạn chế của dataset tuần 2

Dataset tuần 2 có một số hạn chế cần nêu rõ:

1. **Synthetic dataset không đại diện đầy đủ dữ liệu bệnh viện thật.**  
   Dữ liệu thật có nhiều nhiễu hơn, viết tắt không nhất quán hơn, missing fields nhiều hơn.

2. **Quy mô còn nhỏ.**  
   4 bệnh nhân đủ cho PoC nhưng chưa đủ cho evaluation nghiêm túc hoặc model benchmark lớn.

3. **Clinical correctness cần được review thêm.**  
   Vì dữ liệu seed được tạo bằng AI, cần có bác sĩ/mentor rà soát nếu dùng cho demo nghiêm túc.

4. **Chưa map sang FHIR.**  
   Dataset hiện là custom EHR schema, chưa phải FHIR resources.

5. **Không dùng để huấn luyện model.**  
   Dataset này phù hợp để test pipeline, không phù hợp để fine-tune summarization model.

---

## 14. Kế hoạch tiếp theo sau tuần 2

Sau khi hoàn thành Prepare EHR dataset, tuần tiếp theo nên tập trung triển khai PoC kỹ thuật:

### 14.1 Ưu tiên 1 — C1/C2

```text
Raw dataset
→ AssembledEHR
→ SourceChunk[]
→ structured store
```

### 14.2 Ưu tiên 2 — Section-wise retrieval

Triển khai retrieval policy cho 3–4 section trước:

```text
current_medications
abnormal_labs
diagnoses
allergies
```

### 14.3 Ưu tiên 3 — Baseline summarization

Chạy baseline LLM prompt trên P001 và P004:

- P001 để test happy path.
- P004 để test edge cases.

### 14.4 Ưu tiên 4 — Citation verification prototype

Tạo prototype:

```text
summary text
→ atomic claims
→ match source chunks
→ attach citations
→ flag unsupported claims
```

---

## 15. Kết luận

Tuần 2 đã chuyển trọng tâm từ thiết kế hệ thống sang chuẩn bị tài sản dữ liệu để triển khai PoC. Mặc dù không tìm được public EHR dataset phù hợp, hướng tạo synthetic EHR seed dataset là hợp lý trong bối cảnh bài toán yêu cầu dữ liệu tiếng Việt, có cấu trúc HIS/EMR, có citation traceability và có edge cases để test hallucination mitigation.

Kết quả chính của tuần 2 là một bộ raw EHR dataset đã chuẩn hóa, có thể dùng trực tiếp cho các bước:

```text
validation
→ de-identification
→ normalization
→ source chunking
→ section-wise retrieval
→ summarization
→ citation verification
→ evaluation
```

Dataset này không nhằm chứng minh chất lượng mô hình cuối cùng, mà nhằm chứng minh rằng pipeline kỹ thuật có thể được triển khai, debug và đánh giá theo hướng an toàn, có citation và có khả năng truy vết.

---

## 16. References về format thông tin cá nhân synthetic

- Công an Thanh Hóa — Ý nghĩa của dãy 12 số trên CCCD gắn chip hiện nay: https://conganthanhhoa.gov.vn/de-an-06/y-nghia-cua-day-12-so-tren-cccd-gan-chip-hien-nay.html
- Bộ Thông tin và Truyền thông — Chuyển đổi SIM 11 số về 10 số: https://spdv.mic.gov.vn/chuyen-doi-sim-11-so-ve-10-so-viettel-vinaphone-mobifone-len-phuong-an-197118144.htm
- BHXH Bình Dương — Giải mã ý nghĩa 10 ký tự mã số thẻ BHYT mới: https://binhduong.baohiemxahoi.gov.vn/tintuc/Pages/tin-tuc-tong-hop.aspx?CateID=0&ItemID=4740
