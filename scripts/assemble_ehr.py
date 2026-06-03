"""
Merge separate seed JSON files into one AssembledEHR JSON per patient.
Output: data/assembled/P001.json, P002.json, ...

Usage:
    python scripts/assemble_ehr.py
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
SEED_DIR = ROOT / "data" / "vietnamese-clinic-data-seeds" / "seed-dataset"
OUT_DIR  = ROOT / "data" / "medical_summarization" / "assembled"


def load(filename: str) -> list[dict]:
    path = SEED_DIR / filename
    if not path.exists():
        print(f"[WARN] {filename} not found, skipping.")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def group_by(records: list[dict], key: str) -> dict[str, list[dict]]:
    result = defaultdict(list)
    for r in records:
        result[r[key]].append(r)
    return result


def assemble_patient(
    patient: dict,
    encounters_by_pid: dict,
    allergies_by_pid: dict,
    labs_by_eid: dict,
    meds_by_eid: dict,
    diagnoses_by_eid: dict,
    vitals_by_eid: dict,
    notes_by_eid: dict,
    imaging_by_eid: dict,
    procedures_by_eid: dict,
) -> dict:
    pid = patient["patient_id"]

    assembled_encounters = []
    for enc in sorted(
        encounters_by_pid.get(pid, []),
        key=lambda e: e["encounter_date"],
    ):
        eid = enc["encounter_id"]
        assembled_encounters.append({
            "encounter_id": eid,
            "patient_id": pid,
            "encounter_date": enc["encounter_date"],
            "encounter_type": enc.get("encounter_type"),
            "department": enc.get("department"),
            "doctor_name": enc.get("doctor_name"),
            "chief_complaint": enc.get("chief_complaint"),
            "visit_reason": enc.get("visit_reason"),
            "vitals": vitals_by_eid.get(eid, []),
            "labs": labs_by_eid.get(eid, []),
            "medications": meds_by_eid.get(eid, []),
            "diagnoses": diagnoses_by_eid.get(eid, []),
            "clinical_notes": notes_by_eid.get(eid, []),
            "imaging": imaging_by_eid.get(eid, []),
            "procedures": procedures_by_eid.get(eid, []),
        })

    return {
        "patient_id": pid,
        "patient": {
            "patient_id": pid,
            "full_name": patient.get("full_name"),
            "dob": patient.get("dob"),
            "age": patient.get("age"),
            "gender": patient.get("gender"),
            "occupation": patient.get("occupation"),
        },
        "allergies": allergies_by_pid.get(pid, []),
        "encounters": assembled_encounters,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    patients    = load("patients.json")
    encounters  = load("encounters.json")
    labs        = load("labs.json")
    medications = load("medications.json")
    diagnoses   = load("diagnoses.json")
    vitals      = load("vitals.json")
    notes       = load("clinical_notes.json")
    allergies   = load("allergies.json")
    imaging     = load("imaging_reports.json")
    procedures  = load("procedures.json")

    encounters_by_pid  = group_by(encounters, "patient_id")
    allergies_by_pid   = group_by(allergies, "patient_id")
    labs_by_eid        = group_by(labs, "encounter_id")
    meds_by_eid        = group_by(medications, "encounter_id")
    diagnoses_by_eid   = group_by(diagnoses, "encounter_id")
    vitals_by_eid      = group_by(vitals, "encounter_id")
    notes_by_eid       = group_by(notes, "encounter_id")
    imaging_by_eid     = group_by(imaging, "encounter_id")
    procedures_by_eid  = group_by(procedures, "encounter_id")

    for patient in patients:
        pid = patient["patient_id"]
        assembled = assemble_patient(
            patient,
            encounters_by_pid,
            allergies_by_pid,
            labs_by_eid,
            meds_by_eid,
            diagnoses_by_eid,
            vitals_by_eid,
            notes_by_eid,
            imaging_by_eid,
            procedures_by_eid,
        )

        out_path = OUT_DIR / f"{pid}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(assembled, f, ensure_ascii=False, indent=2)

        n_enc = len(assembled["encounters"])
        n_allergy = len(assembled["allergies"])
        n_labs = sum(len(e["labs"]) for e in assembled["encounters"])
        n_meds = sum(len(e["medications"]) for e in assembled["encounters"])
        print(
            f"[OK] {pid} -> {out_path.name} "
            f"| {n_enc} encounters, {n_labs} labs, {n_meds} meds, {n_allergy} allergies"
        )

    print(f"\nDone. {len(patients)} patients assembled -> {OUT_DIR}")


if __name__ == "__main__":
    main()
