"""EMR router: CRUD for raw EHR data in database."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.dependencies import DBSessionDep
from src.db.repositories.emr_repo import EMRRepository

router = APIRouter(prefix="/emr", tags=["EMR"])


@router.get("/patients")
async def list_emr_patients(db: DBSessionDep):
    """List all patients in the EMR database."""
    repo = EMRRepository(db)
    patients = await repo.list_patients()
    return {"patients": patients, "count": len(patients), "source": "database"}


@router.get("/patients/{patient_id}")
async def get_emr_patient(patient_id: str, db: DBSessionDep):
    """Get assembled EHR for a patient from database."""
    repo = EMRRepository(db)
    data = await repo.get_assembled_dict(patient_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found in database")
    return data


@router.get("/patients/{patient_id}/encounters")
async def list_encounters(patient_id: str, db: DBSessionDep):
    """List encounters for a patient."""
    repo = EMRRepository(db)
    encounters = await repo.get_encounters(patient_id)
    return {
        "patient_id": patient_id,
        "encounters": [
            {
                "encounter_id": e.encounter_id,
                "encounter_date": e.encounter_date,
                "encounter_type": e.encounter_type,
                "department": e.department,
                "doctor_name": e.doctor_name,
                "chief_complaint": e.chief_complaint,
            }
            for e in encounters
        ],
        "count": len(encounters),
    }


@router.get("/stats")
async def emr_stats(db: DBSessionDep):
    """Database statistics."""
    from sqlalchemy import select, func
    from src.db.models import (
        PatientDB, EncounterDB, LabDB, MedicationDB,
        DiagnosisDB, AllergyDB, VitalDB, ClinicalNoteDB,
        ImagingReportDB, ProcedureDB,
    )

    tables = {
        "patients": PatientDB,
        "encounters": EncounterDB,
        "labs": LabDB,
        "medications": MedicationDB,
        "diagnoses": DiagnosisDB,
        "allergies": AllergyDB,
        "vitals": VitalDB,
        "clinical_notes": ClinicalNoteDB,
        "imaging_reports": ImagingReportDB,
        "procedures": ProcedureDB,
    }

    stats = {}
    for name, model in tables.items():
        result = await db.execute(select(func.count()).select_from(model))
        stats[name] = result.scalar()

    stats["total"] = sum(stats.values())
    return stats
