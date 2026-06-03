# PLAN 01 — EMR Integration (C1)
**Component:** C1 EMR Integration  
**Tuần chính:** Tuần 2  
**Interface:** `raw_ehr_json (dict)` → `safe_normalized_ehr (dict)` | raises `EHRValidationError`

---

## 1. Overview

C1 là lớp đầu tiên của pipeline — xử lý raw EHR JSON thành dữ liệu an toàn, sạch, sẵn sàng chunk. Bao gồm 3 bước tuần tự: **Validate → De-identify → Normalize**.

Quy tắc: C1 **không mất dữ liệu** — chỉ transform và mask. Mọi field gốc vẫn tồn tại, chỉ thay nội dung nhạy cảm bằng `[REDACTED]` hoặc chuẩn hóa text.

---

## 2. Schema Validation (`src/c1_emr/validator.py`)

### 2.1 Required Fields

```python
REQUIRED_FIELDS = {
    "benh_nhan": ["ma_benh_nhan", "ho_ten", "ngay_sinh", "gioi_tinh"],
    "benh_an":   ["ma_benh_an", "ngay_kham", "chan_doan"]
}

# chan_doan phải có ít nhất 1 item với ma_icd10 và ten_benh
# benh_an không được là list rỗng
```

### 2.2 Validation Rules

```python
def validate_ehr(raw: dict) -> tuple[bool, list[EHRValidationError]]:
    errors = []

    # 1. Required top-level keys
    for field in ["benh_nhan", "benh_an"]:
        if field not in raw:
            errors.append(EHRValidationError(field=field, message="Missing required key"))

    # 2. benh_nhan required fields
    bn = raw.get("benh_nhan", {})
    for f in REQUIRED_FIELDS["benh_nhan"]:
        if not bn.get(f):
            errors.append(EHRValidationError(field=f"benh_nhan.{f}", message="Missing or empty"))

    # 3. benh_an không rỗng
    benh_an_list = raw.get("benh_an", [])
    if not benh_an_list:
        errors.append(EHRValidationError(field="benh_an", message="Empty list"))

    # 4. Per-visit validation
    for i, visit in enumerate(benh_an_list):
        for f in REQUIRED_FIELDS["benh_an"]:
            if not visit.get(f):
                errors.append(EHRValidationError(
                    field=f"benh_an[{i}].{f}",
                    message="Missing or empty"
                ))

        # ngay_kham format: YYYY-MM-DD
        ngay = visit.get("ngay_kham", "")
        if ngay and not re.match(r"^\d{4}-\d{2}-\d{2}$", ngay):
            errors.append(EHRValidationError(
                field=f"benh_an[{i}].ngay_kham",
                message=f"Invalid date format: {ngay}"
            ))

        # chan_doan: phải là list có ít nhất 1 item
        cdlist = visit.get("chan_doan", [])
        if not cdlist:
            errors.append(EHRValidationError(
                field=f"benh_an[{i}].chan_doan",
                message="Empty diagnosis list"
            ))
        else:
            for j, cd in enumerate(cdlist):
                if not cd.get("ma_icd10"):
                    errors.append(EHRValidationError(
                        field=f"benh_an[{i}].chan_doan[{j}].ma_icd10",
                        message="Missing ICD-10 code"
                    ))

    # 5. gioi_tinh enum
    if bn.get("gioi_tinh") and bn["gioi_tinh"] not in ["Nam", "Nữ", "Khác"]:
        errors.append(EHRValidationError(
            field="benh_nhan.gioi_tinh",
            message=f"Invalid value: {bn['gioi_tinh']}"
        ))

    return (len(errors) == 0, errors)
```

### 2.3 Behavior on Validation Error

```python
class EHRPipeline:
    def validate(self, raw: dict) -> dict:
        is_valid, errors = validate_ehr(raw)
        if not is_valid:
            error_msgs = "; ".join(f"{e.field}: {e.message}" for e in errors)
            raise ValueError(f"EHR validation failed: {error_msgs}")
        return raw  # Pass-through nếu valid
```

---

## 3. De-identification (`src/c1_emr/deidentifier.py`)

### 3.1 PII Classification

| Mức độ | Field | Action |
|--------|-------|--------|
| **Full REDACT** | `cccd`, `so_dien_thoai` | `"[REDACTED]"` |
| **Full REDACT** | `so_bhyt` | `"[REDACTED]"` |
| **Partial mask** | `dia_chi` | Giữ quận/tỉnh, bỏ số nhà + tên đường |
| **Keep** | `ho_ten` | Giữ nguyên (cần cho display) |
| **Keep** | `ngay_sinh` | Giữ nguyên (tính tuổi) |
| **Keep** | `ma_benh_nhan` | ID nội bộ — không phải PII thật |

### 3.2 De-identifier Implementation

```python
import copy
import re

PII_FULL_REDACT = ["cccd", "so_dien_thoai", "so_bhyt"]

def _mask_address(addr: str) -> str:
    """
    "Số 10, phường Hoàng Mai, Hà Nội" → "Hoàng Mai, Hà Nội"
    "123 Nguyễn Trãi, Quận 1, TP.HCM" → "Quận 1, TP.HCM"
    
    Strategy: giữ 2 token cuối sau split bằng dấu phẩy.
    """
    parts = [p.strip() for p in addr.split(",")]
    if len(parts) >= 2:
        return ", ".join(parts[-2:])
    return addr  # Không đủ parts → giữ nguyên

def deidentify(ehr: dict) -> dict:
    """
    Deep copy — không mutate input.
    Chỉ mask PII, không thay đổi cấu trúc.
    """
    safe = copy.deepcopy(ehr)
    bn = safe.get("benh_nhan", {})

    # Full redact
    for field in PII_FULL_REDACT:
        if field in bn:
            bn[field] = "[REDACTED]"

    # Partial mask địa chỉ
    if "dia_chi" in bn and bn["dia_chi"]:
        bn["dia_chi"] = _mask_address(bn["dia_chi"])

    # Redact trong benh_an nếu có lặp PII
    for visit in safe.get("benh_an", []):
        for field in PII_FULL_REDACT:
            if field in visit:
                visit[field] = "[REDACTED]"

    return safe
```

### 3.3 Audit Log

```python
def log_deidentification(patient_id: str, fields_masked: list[str]):
    """
    Log ra file audit (không log nội dung, chỉ log field names và timestamp).
    Phục vụ NFR-S04: audit log bắt buộc.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "patient_id": patient_id,
        "action": "de-identification",
        "fields_masked": fields_masked
    }
    # Ghi vào logs/deident_audit.jsonl
```

---

## 4. Medical Abbreviation Normalizer (`src/c1_emr/normalizer.py`)

### 4.1 Từ điển (`data/abbrev_dict.json`)

```json
{
  "THA":    "tăng huyết áp",
  "ĐTĐ":    "đái tháo đường",
  "BN":     "bệnh nhân",
  "HA":     "huyết áp",
  "NMCT":   "nhồi máu cơ tim",
  "RLLPM":  "rối loạn lipid máu",
  "RRPN":   "rì rào phế nang",
  "CLS":    "cận lâm sàng",
  "CĐHA":   "chẩn đoán hình ảnh",
  "SpO2":   "độ bão hòa oxy",
  "BMI":    "chỉ số khối cơ thể",
  "ECG":    "điện tâm đồ",
  "BT":     "bình thường",
  "BHYT":   "bảo hiểm y tế",
  "BV":     "bệnh viện",
  "TK":     "thần kinh",
  "TSGĐ":   "tiền sử gia đình",
  "ACEi":   "thuốc ức chế men chuyển",
  "SGLT2i": "thuốc ức chế SGLT2",
  "COPD":   "bệnh phổi tắc nghẽn mạn tính",
  "TDMP":   "tràn dịch màng phổi",
  "GPB":    "giải phẫu bệnh",
  "XN":     "xét nghiệm",
  "BS":     "bác sĩ",
  "ĐD":     "điều dưỡng",
  "KQ":     "kết quả",
  "PH":     "phẫu thuật",
  "TPHCM":  "Thành phố Hồ Chí Minh"
}
```

### 4.2 Normalizer Implementation

```python
import re
import json

def load_abbrev_dict(path: str = "data/abbrev_dict.json") -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

ABBREV_DICT = load_abbrev_dict()

def normalize_text(text: str, abbrev_dict: dict = ABBREV_DICT) -> str:
    """
    Word-boundary regex replacement.
    "THA" → "tăng huyết áp", nhưng "THAY" không bị replace.
    Case-sensitive: chỉ replace uppercase (viết tắt y khoa thường viết hoa).
    
    Log các viết tắt không map được vào unknown_abbrevs.txt.
    """
    # Tìm tất cả token dạng viết hoa liên tiếp (2-8 ký tự)
    unknown = []
    def replace_match(m):
        abbr = m.group(0)
        if abbr in abbrev_dict:
            return abbrev_dict[abbr]
        # Log unknown nếu có vẻ là viết tắt y khoa (≥2 ký tự hoa)
        if len(abbr) >= 2 and abbr.isupper():
            unknown.append(abbr)
        return abbr  # Giữ nguyên nếu không trong dict
    
    # Pattern: word boundary + 2-8 ký tự hoa (có thể có số) + word boundary
    pattern = r'\b[A-ZĐÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂẮẶẦẤỔỢƯỨ][A-ZĐÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂẮẶẦẤỔỢƯỨ0-9]{1,7}\b'
    result = re.sub(pattern, replace_match, text)
    
    if unknown:
        _log_unknown_abbrevs(unknown)
    return result

# Fields cần normalize (text tiếng Việt có chứa viết tắt lâm sàng)
NORMALIZE_FIELDS = [
    ("benh_an", "ly_do_vao_vien"),
    ("benh_an", "benh_su"),
    ("benh_an", "tien_su", "ban_than"),
    ("benh_an", "tien_su", "gia_dinh"),
    ("benh_an", "kham_benh", "toan_than"),
    ("benh_an", "kham_benh", "kham_co_quan", "*"),  # Tất cả cơ quan
    ("benh_an", "don_thuoc", "ghi_chu_bac_si"),
]

# Fields KHÔNG normalize (giữ nguyên giá trị gốc — số liệu, tên riêng)
NO_NORMALIZE_FIELDS = [
    "ho_ten", "ma_benh_nhan", "ma_benh_an",
    "ma_icd10", "ten_thuoc", "ham_luong",
    "ket_qua",  # Giá trị số XN
    "ngay_kham", "ngay_sinh",
    "huyet_ap",  # "148/92" — không normalize
    "so_bhyt",   # Đã bị REDACT
]
```

### 4.3 Normalizer cho nested fields

```python
def normalize_ehr(safe_ehr: dict) -> dict:
    """
    Duyệt qua các field cần normalize, apply normalize_text.
    Return deep copy — không mutate input.
    """
    import copy
    result = copy.deepcopy(safe_ehr)

    for visit in result.get("benh_an", []):
        # Top-level visit fields
        for field in ["ly_do_vao_vien", "benh_su"]:
            if visit.get(field):
                visit[field] = normalize_text(visit[field])

        # Tiền sử
        tien_su = visit.get("tien_su", {})
        for key in ["ban_than", "gia_dinh"]:
            if tien_su.get(key):
                tien_su[key] = normalize_text(tien_su[key])

        # Khám bệnh
        kham = visit.get("kham_benh", {})
        if kham.get("toan_than"):
            kham["toan_than"] = normalize_text(kham["toan_than"])
        for organ, text in kham.get("kham_co_quan", {}).items():
            if isinstance(text, str):
                kham["kham_co_quan"][organ] = normalize_text(text)

        # Ghi chú bác sĩ
        if visit.get("don_thuoc", {}).get("ghi_chu_bac_si"):
            visit["don_thuoc"]["ghi_chu_bac_si"] = normalize_text(
                visit["don_thuoc"]["ghi_chu_bac_si"]
            )

        # XN: normalize nhan_xet (text mô tả)
        for kq_group in visit.get("ket_qua_xet_nghiem", []):
            for xn in kq_group.get("danh_sach_ket_qua", []):
                if xn.get("nhan_xet"):
                    xn["nhan_xet"] = normalize_text(xn["nhan_xet"])

    return result
```

---

## 5. C1 Pipeline Orchestrator

```python
# src/c1_emr/emr_integration.py
import json
from pathlib import Path

class EMRIntegration:
    def __init__(self, config: dict):
        self.config = config
        self.data_dir = Path(config.get("data_dir", "data/raw"))

    def load_raw(self, patient_id: str) -> dict:
        path = self.data_dir / f"{patient_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"EHR not found: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def process(self, raw: dict) -> dict:
        """
        Validate → De-identify → Normalize
        Raise ValueError nếu validation fail.
        Return safe normalized EHR.
        """
        # Step 1: Validate
        is_valid, errors = validate_ehr(raw)
        if not is_valid:
            raise ValueError(f"Validation failed: {errors}")

        # Step 2: De-identify
        safe = deidentify(raw)
        patient_id = safe["benh_nhan"]["ma_benh_nhan"]
        log_deidentification(patient_id, PII_FULL_REDACT + ["dia_chi"])

        # Step 3: Normalize
        normalized = normalize_ehr(safe)

        return normalized

    def process_from_id(self, patient_id: str) -> dict:
        raw = self.load_raw(patient_id)
        return self.process(raw)
```

---

## 6. Synthetic Data Generation

### 6.1 Dataset Plan

| Nhóm | Cases | Mục đích |
|------|-------|---------|
| Golden set | BN001–BN005 | Baseline evaluation, expect high quality |
| Edge cases | BN006–BN015 | Test robustness của pipeline |

### 6.2 Edge Cases cần tạo

| Case | Edge scenario |
|------|--------------|
| BN006 | Không có XN nào — test "Chưa thấy ghi nhận..." |
| BN007 | Không có đơn thuốc |
| BN008 | Có 2 chẩn đoán mâu thuẫn (ICD-10 khác nhau 2 visit) |
| BN009 | Thuốc thiếu liều (ham_luong không có) |
| BN010 | HbA1c > 12% — XN nguy hiểm → test luu_y section |
| BN011 | Kali thấp nguy hiểm (2.5 mEq/L) |
| BN012 | Clinical notes lẫn tiếng Anh ("Patient has DM type 2...") |
| BN013 | ICD-10 code trong EHR không khớp với tên bệnh |
| BN014 | 5 visits — test longitudinal summary |
| BN015 | Dị ứng Penicillin không trong field di_ung mà trong ghi_chu_bac_si |

### 6.3 Generation Script

```python
# notebooks/01_data_generation.ipynb
# Dùng Claude API để sinh variation từ BN001 template

GENERATION_PROMPT = """
Tạo EHR JSON cho bệnh nhân mới với các thay đổi sau so với template:
{modifications}

Schema: [paste BN001 structure]
Yêu cầu:
- Giữ đúng schema format
- Thông tin lâm sàng phải nhất quán (thuốc phù hợp với chẩn đoán)
- Giá trị số phải trong range thực tế
- Output chỉ JSON, không giải thích
"""

# Sau khi sinh: manual review 5 cases để kiểm tra tính nhất quán lâm sàng
```

---

## 7. Tests

```python
# tests/test_c1_emr.py

class TestValidator:
    def test_passes_valid_ehr(self, bn001_ehr):
        is_valid, errors = validate_ehr(bn001_ehr)
        assert is_valid
        assert errors == []

    def test_catches_missing_ma_benh_nhan(self, bn001_ehr):
        del bn001_ehr["benh_nhan"]["ma_benh_nhan"]
        is_valid, errors = validate_ehr(bn001_ehr)
        assert not is_valid
        assert any("ma_benh_nhan" in e.field for e in errors)

    def test_catches_empty_benh_an(self, bn001_ehr):
        bn001_ehr["benh_an"] = []
        is_valid, errors = validate_ehr(bn001_ehr)
        assert not is_valid

    def test_catches_missing_chan_doan(self, bn001_ehr):
        bn001_ehr["benh_an"][0]["chan_doan"] = []
        is_valid, errors = validate_ehr(bn001_ehr)
        assert not is_valid

    def test_catches_invalid_date_format(self, bn001_ehr):
        bn001_ehr["benh_an"][0]["ngay_kham"] = "15/01/2024"  # Wrong format
        is_valid, errors = validate_ehr(bn001_ehr)
        assert not is_valid

class TestDeidentifier:
    def test_masks_cccd(self, bn001_ehr):
        safe = deidentify(bn001_ehr)
        assert safe["benh_nhan"]["cccd"] == "[REDACTED]"

    def test_masks_so_bhyt(self, bn001_ehr):
        safe = deidentify(bn001_ehr)
        assert safe["benh_nhan"]["so_bhyt"] == "[REDACTED]"

    def test_preserves_ho_ten(self, bn001_ehr):
        safe = deidentify(bn001_ehr)
        assert safe["benh_nhan"]["ho_ten"] == bn001_ehr["benh_nhan"]["ho_ten"]

    def test_partial_masks_address(self, bn001_ehr):
        bn001_ehr["benh_nhan"]["dia_chi"] = "Số 10, phường Hoàng Mai, Hà Nội"
        safe = deidentify(bn001_ehr)
        assert "Số 10" not in safe["benh_nhan"]["dia_chi"]
        assert "Hà Nội" in safe["benh_nhan"]["dia_chi"]

    def test_does_not_mutate_input(self, bn001_ehr):
        original_cccd = bn001_ehr["benh_nhan"]["cccd"]
        _ = deidentify(bn001_ehr)
        assert bn001_ehr["benh_nhan"]["cccd"] == original_cccd  # Input unchanged

class TestNormalizer:
    def test_expands_THA_not_THAY(self):
        text = "BN có THA 5 năm, THAY thuốc gần đây"
        result = normalize_text(text)
        assert "tăng huyết áp" in result
        assert "THAY" in result  # Không thay THAY

    def test_expands_multiple_abbrevs(self):
        text = "BN ĐTĐ type 2, THA, RLLPM"
        result = normalize_text(text)
        assert "đái tháo đường" in result
        assert "tăng huyết áp" in result
        assert "rối loạn lipid máu" in result

    def test_preserves_drug_names(self, bn001_normalized):
        # Tên thuốc không được normalize
        for visit in bn001_normalized["benh_an"]:
            for t in visit.get("don_thuoc", {}).get("danh_sach_thuoc", []):
                assert t["ten_thuoc"] is not None  # Không bị xóa

    def test_preserves_numeric_values(self):
        text = "HA 148/92 mmHg"
        result = normalize_text(text)
        assert "148/92" in result  # Số không bị thay
```
