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
        temp   = vit.get("temperature_c")
        spo2   = vit.get("spo2")
        weight = vit.get("weight_kg")
        height = vit.get("height_cm")
        bmi    = vit.get("bmi")
        flags  = vit.get("abnormal_flags", [])

        parts = []
        if bp_sys and bp_dia:
            parts.append(f"Huyet ap: {bp_sys}/{bp_dia} mmHg")
        if hr:
            parts.append(f"Mach: {hr} lan/phut")
        if temp:
            parts.append(f"Nhiet do: {temp} C")
        if spo2:
            parts.append(f"SpO2: {spo2}%")
        if weight:
            parts.append(f"Can nang: {weight} kg")
        if height:
            parts.append(f"Chieu cao: {height} cm")
        if bmi:
            parts.append(f"BMI: {bmi}")

        if not parts:
            continue

        text = ". ".join(parts)
        if flags:
            text += f". Bat thuong: {', '.join(flags)}"

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
            text += f" (tham chieu: {ref})"
        if lab.get("abnormal"):
            direction = "cao" if lab.get("interpretation") == "high" else "thap"
            text += f" [BAT THUONG - {direction}]"
        if lab.get("critical"):
            text += " [NGUY HIEM]"
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
                "abnormal": lab.get("abnormal", False),
                "critical": lab.get("critical", False),
                "interpretation": lab.get("interpretation"),
            },
        ))
    return chunks


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
            parts.append(f"lieu: {dose}")
        if freq:
            parts.append(f"tan suat: {freq}")
        if instr:
            parts.append(instr)

        text = ". ".join(parts)

        if not med.get("dose") and not med.get("strength"):
            text += " [THIEU THONG TIN LIEU]"

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
        section = note.get("section", "ghi_chu")

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
        substance = allergy.get("substance", "?")
        reaction  = allergy.get("reaction", "khong ro")
        severity  = allergy.get("severity", "unknown")
        status    = allergy.get("status", "unknown")
        note      = allergy.get("source_text", "")
        needs_confirm = allergy.get("needs_patient_confirmation", False)

        text = f"Di ung: {substance}. Phan ung: {reaction}. Muc do: {severity}. Trang thai: {status}."
        if needs_confirm:
            text += " [CAN XAC NHAN LAI VOI BENH NHAN]"
        if note:
            text += f" Ghi chu: {note}"

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
    dob    = p.get("dob", "")
    age    = p.get("age")
    gender = p.get("gender", "")
    occ    = p.get("occupation", "")

    parts = [f"Benh nhan: {name}"]
    if age:
        parts.append(f"Tuoi: {age}")
    elif dob:
        parts.append(f"Ngay sinh: {dob}")
    if gender:
        parts.append(f"Gioi tinh: {gender}")
    if occ:
        parts.append(f"Nghe nghiep: {occ}")

    return [SourceChunk(
        source_id=f"{pid}-PATIENT-INFO",
        source_type="patient_info",
        patient_id=pid,
        encounter_id="PATIENT_LEVEL",
        ngay=None,
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
