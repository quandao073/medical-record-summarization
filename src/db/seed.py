"""
Seed database from data/raw/ JSON files.

Usage:
    python -m src.db.seed                    # Seed from default data/raw/
    python -m src.db.seed --raw-dir path/    # Seed from custom directory
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    PatientDB, EncounterDB, LabDB, MedicationDB,
    DiagnosisDB, AllergyDB, VitalDB, ClinicalNoteDB,
    ImagingReportDB, ProcedureDB,
)

ROOT = Path(__file__).parent.parent.parent
DEFAULT_RAW_DIR = ROOT / "data" / "raw"


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


async def _upsert(session: AsyncSession, model, records: list[dict], id_field: str) -> int:
    """Insert records, skip if id already exists."""
    count = 0
    valid_cols = {c.key for c in model.__table__.columns}
    for rec in records:
        if id_field not in rec:
            continue
        existing = await session.execute(
            select(model).where(getattr(model, id_field) == rec[id_field])
        )
        if existing.scalar_one_or_none() is not None:
            continue
        filtered = {k: v for k, v in rec.items() if k in valid_cols}
        session.add(model(**filtered))
        count += 1
    return count


async def seed_from_raw(session: AsyncSession, raw_dir: Path | None = None) -> dict[str, int]:
    """Import all 10 raw JSON files into database tables."""
    if raw_dir is None:
        raw_dir = DEFAULT_RAW_DIR

    counts: dict[str, int] = {}

    patients_raw = _load_json(raw_dir / "patients.json")
    counts["patients"] = await _upsert(session, PatientDB, patients_raw, "patient_id")

    encounters_raw = _load_json(raw_dir / "encounters.json")
    counts["encounters"] = await _upsert(session, EncounterDB, encounters_raw, "encounter_id")

    await session.flush()

    allergies_raw = _load_json(raw_dir / "allergies.json")
    counts["allergies"] = await _upsert(session, AllergyDB, allergies_raw, "allergy_id")

    labs_raw = _load_json(raw_dir / "labs.json")
    counts["labs"] = await _upsert(session, LabDB, labs_raw, "lab_id")

    meds_raw = _load_json(raw_dir / "medications.json")
    counts["medications"] = await _upsert(session, MedicationDB, meds_raw, "medication_id")

    dx_raw = _load_json(raw_dir / "diagnoses.json")
    counts["diagnoses"] = await _upsert(session, DiagnosisDB, dx_raw, "diagnosis_id")

    vitals_raw = _load_json(raw_dir / "vitals.json")
    for v in vitals_raw:
        if "abnormal_flags" in v:
            v["abnormal_flags_json"] = v.pop("abnormal_flags")
    counts["vitals"] = await _upsert(session, VitalDB, vitals_raw, "vital_id")

    notes_raw = _load_json(raw_dir / "clinical_notes.json")
    counts["clinical_notes"] = await _upsert(session, ClinicalNoteDB, notes_raw, "note_id")

    imaging_raw = _load_json(raw_dir / "imaging_reports.json")
    counts["imaging_reports"] = await _upsert(session, ImagingReportDB, imaging_raw, "imaging_id")

    procs_raw = _load_json(raw_dir / "procedures.json")
    counts["procedures"] = await _upsert(session, ProcedureDB, procs_raw, "procedure_id")

    return counts


async def _main():
    import argparse
    parser = argparse.ArgumentParser(description="Seed database from raw JSON files")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    args = parser.parse_args()

    from src.db.engine import init_db, get_db, close_db

    await init_db()
    async for session in get_db():
        counts = await seed_from_raw(session, Path(args.raw_dir))
        print("Seed results:")
        total = 0
        for table, count in counts.items():
            print(f"  {table}: {count} records")
            total += count
        print(f"  Total: {total} records")
    await close_db()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
