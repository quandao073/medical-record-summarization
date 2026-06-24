"""
C1 — EMR Integration: Raw table assembler.
Joins flat raw JSON tables (data/raw/) into per-patient AssembledEHR JSON.
Output: data/processed/assembled/P{id}.json

Usage:
    python -m src.c1_emr.assembler
    python -m src.c1_emr.assembler --raw-dir data/raw --out-dir data/processed/assembled
"""

from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DEFAULT_RAW_DIR = ROOT / "data" / "raw"
DEFAULT_OUT_DIR = ROOT / "data" / "processed" / "assembled"


def _load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _group_by(records: list[dict], key: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        grouped[rec[key]].append(rec)
    return grouped


def assemble(raw_dir: Path = DEFAULT_RAW_DIR) -> dict[str, dict]:
    """
    Load all raw tables and return {patient_id: assembled_ehr_dict}.
    Does NOT write files — call write_assembled() for that.
    """
    patients     = _load(raw_dir / "patients.json")
    encounters   = _load(raw_dir / "encounters.json")
    labs         = _load(raw_dir / "labs.json")
    medications  = _load(raw_dir / "medications.json")
    diagnoses    = _load(raw_dir / "diagnoses.json")
    vitals       = _load(raw_dir / "vitals.json")
    clinical_notes = _load(raw_dir / "clinical_notes.json")
    imaging      = _load(raw_dir / "imaging_reports.json")
    procedures   = _load(raw_dir / "procedures.json")
    allergies    = _load(raw_dir / "allergies.json")

    # Group encounter-level records by encounter_id
    labs_by_enc       = _group_by(labs,           "encounter_id")
    meds_by_enc       = _group_by(medications,    "encounter_id")
    dx_by_enc         = _group_by(diagnoses,      "encounter_id")
    vitals_by_enc     = _group_by(vitals,         "encounter_id")
    notes_by_enc      = _group_by(clinical_notes, "encounter_id")
    imaging_by_enc    = _group_by(imaging,        "encounter_id")
    procs_by_enc      = _group_by(procedures,     "encounter_id")

    # Group allergies by patient_id (allergies are patient-level)
    allergies_by_pat  = _group_by(allergies, "patient_id")

    # Group encounters by patient_id
    encs_by_pat = _group_by(encounters, "patient_id")

    assembled: dict[str, dict] = {}

    for pat in patients:
        pid = pat["patient_id"]

        patient_block = {
            "patient_id": pid,
            "full_name":  pat.get("full_name", ""),
            "date_of_birth": pat.get("date_of_birth", pat.get("dob")),
            "age":         pat.get("age"),
            "gender":      pat.get("gender"),
            "occupation":  pat.get("occupation"),
            "address":     pat.get("address"),
            "insurance_id": pat.get("insurance_id"),
            "citizen_id":  pat.get("citizen_id"),
            "phone":       pat.get("phone"),
        }

        encounter_list = []
        for enc in sorted(encs_by_pat.get(pid, []), key=lambda e: e["encounter_date"]):
            eid = enc["encounter_id"]

            # Normalize imaging: imaging_reports uses `findings` + `impression`
            imaging_records = []
            for img in imaging_by_enc.get(eid, []):
                imaging_records.append({
                    "imaging_id":   img.get("imaging_id"),
                    "patient_id":   img.get("patient_id"),
                    "encounter_id": img.get("encounter_id"),
                    "study_date":   img.get("study_date"),
                    "modality":     img.get("modality"),
                    "body_part":    img.get("body_part"),
                    "findings":     img.get("findings", img.get("report_text", "")),
                    "impression":   img.get("impression"),
                })

            # Normalize procedures: raw uses `result`, template used `result_summary`
            proc_records = []
            for proc in procs_by_enc.get(eid, []):
                proc_records.append({
                    "procedure_id":   proc.get("procedure_id"),
                    "patient_id":     proc.get("patient_id"),
                    "encounter_id":   proc.get("encounter_id"),
                    "procedure_date": proc.get("procedure_date"),
                    "procedure_name": proc.get("procedure_name"),
                    "description":    proc.get("description", proc.get("procedure_text", "")),
                    "result":         proc.get("result", proc.get("result_summary", "")),
                })

            encounter_list.append({
                "encounter_id":    eid,
                "patient_id":      pid,
                "encounter_date":  enc.get("encounter_date"),
                "encounter_type":  enc.get("encounter_type"),
                "department":      enc.get("department"),
                "doctor_name":     enc.get("doctor_name"),
                "chief_complaint": enc.get("chief_complaint"),
                "visit_reason":    enc.get("visit_reason"),
                "vitals":          vitals_by_enc.get(eid, []),
                "labs":            labs_by_enc.get(eid, []),
                "medications":     meds_by_enc.get(eid, []),
                "diagnoses":       dx_by_enc.get(eid, []),
                "clinical_notes":  notes_by_enc.get(eid, []),
                "imaging":         imaging_records,
                "procedures":      proc_records,
            })

        assembled[pid] = {
            "patient_id": pid,
            "patient":    patient_block,
            "allergies":  allergies_by_pat.get(pid, []),
            "encounters": encounter_list,
        }

    return assembled


def write_assembled(assembled: dict[str, dict], out_dir: Path = DEFAULT_OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for pid, ehr in assembled.items():
        out_path = out_dir / f"{pid}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ehr, f, ensure_ascii=False, indent=2)
        print(f"  Wrote {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Assemble raw EHR tables into per-patient JSON")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir)

    print(f"Assembling from: {raw_dir}")
    assembled = assemble(raw_dir)
    write_assembled(assembled, out_dir)
    print(f"\nAssembled {len(assembled)} patients -> {out_dir}")


async def assemble_from_db(session, patient_id: str) -> dict | None:
    """
    Assemble EHR from database for a single patient.

    Returns the same dict format as assemble()[patient_id], so downstream
    pipeline (C1 process_ehr → C2 → C3 → ... → C7) works unchanged.

    Returns None if patient not found in database.
    """
    from src.db.repositories.emr_repo import EMRRepository
    repo = EMRRepository(session)
    return await repo.get_assembled_dict(patient_id)


if __name__ == "__main__":
    main()
