"""
C2 — Chunking Service.
Converts an assembled + normalized EHR dict into a flat list of SourceChunks.
Principle: 1 chunk = 1 independently citable clinical fact.
"""

from __future__ import annotations
from src.schemas import SourceChunk


# ---------------------------------------------------------------------------
# Source ID convention:
#   {patient_id}-{encounter_id}-{TYPE}-{identifier}
#   e.g. P001-P001E001-LAB-HBA1C
#        P001-P001E001-MED-Metformin
#        P001-P001E001-DX-E11
#        P001-PATIENT-ALLERGY-Penicillin
# ---------------------------------------------------------------------------


def _sid(encounter_id: str, type_code: str, identifier: str) -> str:
    """
    Format: {encounter_id}-{TYPE}-{SHORT_ID}
    e.g.  P001-E001-LAB-HBA1C, P001-E001-MED-METFORMIN, P001-E001-DX-E11
    encounter_id already contains patient_id prefix, so no duplication.
    """
    # Strip known prefixes from identifier to keep it short
    clean = identifier
    for prefix in (f"{encounter_id}-", ):
        if clean.upper().startswith(prefix.upper()):
            clean = clean[len(prefix):]
            break
    safe_id = clean.replace(" ", "_").replace("/", "_").upper()[:20]
    return f"{encounter_id}-{type_code}-{safe_id}"


def _chunk_vitals(enc: dict, pid: str) -> list[SourceChunk]:
    chunks = []
    for vit in enc.get("vitals", []):
        bp_sys = vit.get("blood_pressure_systolic")
        bp_dia = vit.get("blood_pressure_diastolic")
        hr     = vit.get("heart_rate")
        temp   = vit.get("temperature_celsius")
        spo2   = vit.get("spo2_percent")
        weight = vit.get("weight_kg")
        height = vit.get("height_cm")
        bmi    = vit.get("bmi")
        flags  = vit.get("abnormal_flags", [])

        parts = []
        if bp_sys and bp_dia:
            parts.append(f"Huyết áp: {bp_sys}/{bp_dia} mmHg")
        if hr:
            parts.append(f"Mạch: {hr} lần/phút")
        if temp:
            parts.append(f"Nhiệt độ: {temp} C")
        if spo2:
            parts.append(f"SpO2: {spo2}%")
        if weight:
            parts.append(f"Cân nặng: {weight} kg")
        if height:
            parts.append(f"Chiều cao: {height} cm")
        if bmi:
            parts.append(f"BMI: {bmi}")

        if not parts:
            continue

        text = ". ".join(parts)
        if flags:
            text += f". Bất thường: {', '.join(flags)}"

        chunks.append(SourceChunk(
            source_id=_sid(enc["encounter_id"], "VIT", vit.get("vital_id", "VIT001")),
            source_type="vitals",
            patient_id=pid,
            encounter_id=enc["encounter_id"],
            date=enc.get("encounter_date"),
            content=text,
            metadata={
                "blood_pressure": f"{bp_sys}/{bp_dia}" if bp_sys else None,
                "abnormal_flags": flags,
                "bmi": bmi,
            },
        ))
    return chunks


def _chunk_labs(enc: dict, pid: str) -> list[SourceChunk]:
    chunks = []
    for lab in enc.get("labs", []):
        value = lab.get("value")
        unit  = lab.get("unit", "")
        ref   = lab.get("reference_range", "")
        name  = lab.get("test_name", lab.get("test_code", "XN"))
        comment = lab.get("comment", "")

        if value is None:
            continue

        text = f"{name}: {value} {unit}".strip()
        if ref:
            text += f" (tham chiếu: {ref})"
        if lab.get("is_abnormal"):
            direction = "cao" if lab.get("interpretation") == "high" else "thấp"
            text += f" [BẤT THƯỜNG - {direction}]"
        if lab.get("is_critical"):
            text += " [NGUY HIỂM]"
        if comment:
            text += f". {comment}"

        chunks.append(SourceChunk(
            source_id=_sid(enc["encounter_id"], "LAB", lab.get("test_code", name)),
            source_type="labs",
            patient_id=pid,
            encounter_id=enc["encounter_id"],
            date=lab.get("sample_date") or enc.get("encounter_date"),
            content=text,
            metadata={
                "test_code": lab.get("test_code"),
                "test_name": name,
                "value": value,
                "unit": unit,
                "reference_range": ref,
                "is_abnormal": lab.get("is_abnormal", False),
                "is_critical": lab.get("is_critical", False),
                "interpretation": lab.get("interpretation"),
            },
        ))
    return chunks


_DRUG_INDICATION: dict[str, str] = {
    "metformin": "Đái tháo đường type 2",
    "empagliflozin": "Đái tháo đường type 2",
    "glimepiride": "Đái tháo đường type 2",
    "gliclazide": "Đái tháo đường type 2",
    "sitagliptin": "Đái tháo đường type 2",
    "insulin": "Đái tháo đường",
    "amlodipine": "Tăng huyết áp",
    "perindopril": "Tăng huyết áp",
    "losartan": "Tăng huyết áp",
    "valsartan": "Tăng huyết áp",
    "lisinopril": "Tăng huyết áp",
    "hydrochlorothiazide": "Tăng huyết áp",
    "atorvastatin": "Rối loạn lipid máu",
    "rosuvastatin": "Rối loạn lipid máu",
    "simvastatin": "Rối loạn lipid máu",
    "aspirin": "Chống kết tập tiểu cầu",
    "clopidogrel": "Chống kết tập tiểu cầu",
    "warfarin": "Chống đông máu",
    "omeprazole": "Bảo vệ dạ dày",
    "esomeprazole": "Bảo vệ dạ dày",
    "pantoprazole": "Bảo vệ dạ dày",
    "lansoprazole": "Bảo vệ dạ dày",
    "levothyroxine": "Suy giáp",
    "methimazole": "Cường giáp",
    "propylthiouracil": "Cường giáp",
    "propranolol": "Cường giáp / Tăng huyết áp",
    "amoxicillin": "Kháng sinh",
    "clarithromycin": "Kháng sinh",
    "metronidazole": "Kháng sinh",
    "bismuth subsalicylate": "Bảo vệ dạ dày",
    "prednisolone": "Kháng viêm",
    "prednisone": "Kháng viêm",
    "salbutamol": "Giãn phế quản",
    "montelukast": "Hen phế quản",
    "cetirizine": "Dị ứng",
    "loratadine": "Dị ứng",
}


def _drug_indication(drug_name: str) -> str:
    key = drug_name.lower().strip()
    for k, v in _DRUG_INDICATION.items():
        if k in key or key in k:
            return v
    return ""


def _chunk_medications(enc: dict, pid: str) -> list[SourceChunk]:
    chunks = []
    for med in enc.get("medications", []):
        drug  = med.get("drug_name", "?")
        strength = med.get("strength", "")
        dose  = med.get("dose", "")
        freq  = med.get("frequency", "")
        instr = med.get("instruction", "")

        parts = [f"{drug}"]
        if strength:
            parts[0] += f" {strength}"
        if dose:
            parts.append(f"liều: {dose}")
        if freq:
            parts.append(f"tần suất: {freq}")
        if instr:
            parts.append(instr)

        text = ". ".join(parts)

        if not med.get("dose") and not med.get("strength"):
            text += " [THIẾU THÔNG TIN LIỀU]"

        chunks.append(SourceChunk(
            source_id=_sid(enc["encounter_id"], "MED", drug),
            source_type="medications",
            patient_id=pid,
            encounter_id=enc["encounter_id"],
            date=med.get("prescription_date") or enc.get("encounter_date"),
            content=text,
            metadata={
                "drug_name": drug,
                "strength": strength,
                "dose": dose,
                "frequency": freq,
                "indication": _drug_indication(drug),
                "is_current": med.get("is_current", True),
                "missing_dose": not (med.get("dose") or med.get("strength")),
            },
        ))
    return chunks


def _chunk_diagnoses(enc: dict, pid: str) -> list[SourceChunk]:
    chunks = []
    for dx in enc.get("diagnoses", []):
        icd  = dx.get("icd10_code", "")
        name = dx.get("diagnosis_name", "")
        text_detail = dx.get("diagnosis_text", "")
        dx_type = dx.get("diagnosis_type", "")

        text = f"{name} ({icd})"
        if dx_type:
            text = f"[{dx_type.upper()}] {text}"
        if text_detail:
            text += f". {text_detail}"

        chunks.append(SourceChunk(
            source_id=_sid(enc["encounter_id"], "DX", icd or name),
            source_type="diagnoses",
            patient_id=pid,
            encounter_id=enc["encounter_id"],
            date=dx.get("diagnosis_date") or enc.get("encounter_date"),
            content=text,
            metadata={
                "icd10_code": icd,
                "diagnosis_name": name,
                "diagnosis_type": dx_type,
                "is_active": dx.get("is_active", True),
            },
        ))
    return chunks


def _chunk_clinical_notes(enc: dict, pid: str) -> list[SourceChunk]:
    chunks = []
    for note in enc.get("clinical_notes", []):
        text = note.get("text", "").strip()
        if not text:
            continue
        section = note.get("section", "ghi chú")

        chunks.append(SourceChunk(
            source_id=_sid(enc["encounter_id"], "NOTE", note.get("note_id", section)),
            source_type="clinical_notes",
            patient_id=pid,
            encounter_id=enc["encounter_id"],
            date=note.get("note_date") or enc.get("encounter_date"),
            content=text,
            metadata={
                "section": section,
                "note_type": note.get("note_type"),
                "author": note.get("author_name"),
            },
        ))
    return chunks


def _chunk_imaging(enc: dict, pid: str) -> list[SourceChunk]:
    chunks = []
    for img in enc.get("imaging", []):
        findings = img.get("findings") or img.get("report_text", "")
        impression = img.get("impression", "")
        modality = img.get("modality", "CDHA")
        body_part = img.get("body_part", "")

        text = f"{modality} {body_part}: {findings}"
        if impression:
            text += f". Ket luan: {impression}"

        if not findings and not impression:
            continue

        chunks.append(SourceChunk(
            source_id=_sid(enc["encounter_id"], "IMG", img.get("imaging_id", modality)),
            source_type="imaging",
            patient_id=pid,
            encounter_id=enc["encounter_id"],
            date=img.get("study_date") or enc.get("encounter_date"),
            content=text,
            metadata={"modality": modality, "body_part": body_part},
        ))
    return chunks


def _chunk_procedures(enc: dict, pid: str) -> list[SourceChunk]:
    chunks = []
    for proc in enc.get("procedures", []):
        name   = proc.get("procedure_name", "")
        result = proc.get("result_summary") or proc.get("result", "")

        if not result:
            continue

        text = f"{name}: {result}"

        chunks.append(SourceChunk(
            source_id=_sid(enc["encounter_id"], "PROC", proc.get("procedure_id", name)),
            source_type="procedures",
            patient_id=pid,
            encounter_id=enc["encounter_id"],
            date=proc.get("procedure_date") or enc.get("encounter_date"),
            content=text,
            metadata={"procedure_name": name},
        ))
    return chunks


def _chunk_allergies(ehr: dict) -> list[SourceChunk]:
    chunks = []
    pid = ehr["patient_id"]
    for allergy in ehr.get("allergies", []):
        # Coerce null / "unknown" to natural Vietnamese — omit unknown fields rather than
        # listing them, so the sentence reads naturally instead of as a field dump.
        substance = allergy.get("substance") or "không rõ dị nguyên"
        reaction_raw = allergy.get("reaction")
        reaction  = None if not reaction_raw or reaction_raw == "unknown" else reaction_raw
        severity_raw = allergy.get("severity")
        severity  = None if not severity_raw or severity_raw == "unknown" else severity_raw
        status_raw = allergy.get("status")
        status    = None if not status_raw or status_raw == "unknown" else status_raw
        note      = allergy.get("source_text", "")
        needs_confirm = allergy.get("needs_patient_confirmation", False)

        text = f"Dị ứng {substance}"
        details = []
        if reaction:
            details.append(f"biểu hiện {reaction}")
        if severity:
            details.append(f"mức độ {severity}")
        if status:
            details.append(f"trạng thái ghi nhận: {status}")
        if details:
            text += ", " + ", ".join(details) + "."
        else:
            text += " (chưa ghi nhận chi tiết phản ứng/mức độ)."

        if needs_confirm:
            text += " Cần xác nhận lại thông tin này với bệnh nhân."
        if note:
            text += f" Ghi chú: {note}"

        chunks.append(SourceChunk(
            source_id=f"{pid}-PATIENT-ALLERGY-{substance.replace(' ', '_').upper()[:15]}",
            source_type="allergies",
            patient_id=pid,
            encounter_id="PATIENT_LEVEL",
            date=allergy.get("recorded_date"),
            content=text,
            metadata={
                "substance": substance,
                "reaction": reaction,
                "severity": severity,
                "status": status,
                "needs_patient_confirmation": needs_confirm,
            },
        ))
    return chunks


def _chunk_patient_info(ehr: dict) -> list[SourceChunk]:
    pid = ehr["patient_id"]
    p   = ehr.get("patient", {})
    name   = p.get("full_name", "BN")
    dob    = p.get("date_of_birth", p.get("dob", ""))
    age    = p.get("age")
    gender = p.get("gender", "")
    occ    = p.get("occupation", "")

    parts = [f"Bệnh nhân: {name}"]
    if age:
        parts.append(f"Tuổi: {age}")
    elif dob:
        parts.append(f"Ngày sinh: {dob}")
    if gender:
        parts.append(f"Giới tính: {gender}")
    if occ:
        parts.append(f" Nghề nghiệp: {occ}")

    return [SourceChunk(
        source_id=f"{pid}-PATIENT-INFO",
        source_type="patient_info",
        patient_id=pid,
        encounter_id="PATIENT_LEVEL",
        date=None,
        content=". ".join(parts),
        metadata={"age": age, "gender": gender},
    )]


def chunk_ehr(ehr: dict) -> list[SourceChunk]:
    """
    Main entry point: assembled EHR dict -> flat list of SourceChunks.
    Chunks are ordered: patient info, allergies, then per encounter (date asc).
    """
    pid = ehr["patient_id"]
    chunks: list[SourceChunk] = []

    # Patient-level chunks (order matters for display)
    chunks.extend(_chunk_patient_info(ehr))
    chunks.extend(_chunk_allergies(ehr))

    # Per-encounter chunks (encounters already sorted by date in assembler)
    for enc in ehr.get("encounters", []):
        chunks.extend(_chunk_vitals(enc, pid))
        chunks.extend(_chunk_clinical_notes(enc, pid))
        chunks.extend(_chunk_diagnoses(enc, pid))
        chunks.extend(_chunk_labs(enc, pid))
        chunks.extend(_chunk_medications(enc, pid))
        chunks.extend(_chunk_imaging(enc, pid))
        chunks.extend(_chunk_procedures(enc, pid))

    # Ensure source_ids are unique (deduplicate by appending index if needed)
    seen: dict[str, int] = {}
    deduped = []
    for chunk in chunks:
        if chunk.source_id in seen:
            seen[chunk.source_id] += 1
            chunk = chunk.model_copy(
                update={"source_id": f"{chunk.source_id}_{seen[chunk.source_id]}"}
            )
        else:
            seen[chunk.source_id] = 0
        deduped.append(chunk)

    return deduped
