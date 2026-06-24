"""
EMR Repository — reads raw EHR data from database for C1 Assembler.

Output of get_assembled_dict() matches the exact format produced by
src/c1_emr/assembler.assemble(), so downstream pipeline (C2-C7) works unchanged.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import (
    PatientDB, EncounterDB,
)


class EMRRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_patients(self) -> list[str]:
        result = await self._session.execute(
            select(PatientDB.patient_id).order_by(PatientDB.patient_id)
        )
        return [row[0] for row in result.all()]

    async def get_patient(self, patient_id: str) -> PatientDB | None:
        result = await self._session.execute(
            select(PatientDB)
            .where(PatientDB.patient_id == patient_id)
            .options(selectinload(PatientDB.allergies))
        )
        return result.scalar_one_or_none()

    async def get_encounters(self, patient_id: str) -> list[EncounterDB]:
        result = await self._session.execute(
            select(EncounterDB)
            .where(EncounterDB.patient_id == patient_id)
            .options(
                selectinload(EncounterDB.labs),
                selectinload(EncounterDB.medications),
                selectinload(EncounterDB.diagnoses),
                selectinload(EncounterDB.vitals),
                selectinload(EncounterDB.clinical_notes),
                selectinload(EncounterDB.imaging_reports),
                selectinload(EncounterDB.procedures),
            )
            .order_by(EncounterDB.encounter_date)
        )
        return list(result.scalars().all())

    async def get_assembled_dict(self, patient_id: str) -> dict | None:
        """
        Build assembled EHR dict from database — same format as
        src/c1_emr/assembler.assemble() output.
        """
        patient = await self.get_patient(patient_id)
        if patient is None:
            return None

        encounters = await self.get_encounters(patient_id)

        patient_block = {
            "patient_id": patient.patient_id,
            "full_name": patient.full_name or "",
            "date_of_birth": patient.date_of_birth,
            "age": patient.age,
            "gender": patient.gender,
            "occupation": patient.occupation,
            "address": patient.address,
            "insurance_id": patient.insurance_id,
            "citizen_id": patient.citizen_id,
            "phone": patient.phone,
        }

        allergies_list = [
            {
                "allergy_id": a.allergy_id,
                "patient_id": a.patient_id,
                "encounter_id": a.encounter_id,
                "recorded_date": a.recorded_date,
                "substance": a.substance,
                "reaction": a.reaction,
                "severity": a.severity,
                "status": a.status,
                "source_text": a.source_text,
                "needs_patient_confirmation": a.needs_patient_confirmation or False,
            }
            for a in (patient.allergies or [])
        ]

        encounter_list = []
        for enc in encounters:
            encounter_list.append({
                "encounter_id": enc.encounter_id,
                "patient_id": enc.patient_id,
                "encounter_date": enc.encounter_date,
                "encounter_type": enc.encounter_type,
                "department": enc.department,
                "doctor_name": enc.doctor_name,
                "chief_complaint": enc.chief_complaint,
                "visit_reason": enc.visit_reason,
                "vitals": [
                    {
                        "vital_id": v.vital_id,
                        "patient_id": v.patient_id,
                        "encounter_id": v.encounter_id,
                        "measured_at": v.measured_at,
                        "blood_pressure_systolic": v.blood_pressure_systolic,
                        "blood_pressure_diastolic": v.blood_pressure_diastolic,
                        "heart_rate": v.heart_rate,
                        "temperature_celsius": v.temperature_celsius,
                        "spo2_percent": v.spo2_percent,
                        "weight_kg": v.weight_kg,
                        "height_cm": v.height_cm,
                        "bmi": v.bmi,
                        "abnormal_flags": v.abnormal_flags_json or [],
                    }
                    for v in (enc.vitals or [])
                ],
                "labs": [
                    {
                        "lab_id": lab.lab_id,
                        "patient_id": lab.patient_id,
                        "encounter_id": lab.encounter_id,
                        "sample_date": lab.sample_date,
                        "result_date": lab.result_date,
                        "test_code": lab.test_code,
                        "test_name": lab.test_name,
                        "value": lab.value,
                        "unit": lab.unit,
                        "reference_range": lab.reference_range,
                        "interpretation": lab.interpretation,
                        "is_abnormal": lab.is_abnormal or False,
                        "is_critical": lab.is_critical or False,
                        "comment": lab.comment,
                    }
                    for lab in (enc.labs or [])
                ],
                "medications": [
                    {
                        "medication_id": m.medication_id,
                        "patient_id": m.patient_id,
                        "encounter_id": m.encounter_id,
                        "prescription_date": m.prescription_date,
                        "drug_name": m.drug_name,
                        "strength": m.strength,
                        "dose": m.dose,
                        "route": m.route,
                        "frequency": m.frequency,
                        "instruction": m.instruction,
                        "duration_days": m.duration_days,
                        "is_current": m.is_current if m.is_current is not None else True,
                    }
                    for m in (enc.medications or [])
                ],
                "diagnoses": [
                    {
                        "diagnosis_id": d.diagnosis_id,
                        "patient_id": d.patient_id,
                        "encounter_id": d.encounter_id,
                        "diagnosis_date": d.diagnosis_date,
                        "diagnosis_type": d.diagnosis_type,
                        "icd10_code": d.icd10_code,
                        "diagnosis_name": d.diagnosis_name,
                        "diagnosis_text": d.diagnosis_text,
                        "is_active": d.is_active if d.is_active is not None else True,
                    }
                    for d in (enc.diagnoses or [])
                ],
                "clinical_notes": [
                    {
                        "note_id": n.note_id,
                        "patient_id": n.patient_id,
                        "encounter_id": n.encounter_id,
                        "note_date": n.note_date,
                        "note_type": n.note_type,
                        "section": n.section,
                        "text": n.text,
                        "author_name": n.author_name,
                    }
                    for n in (enc.clinical_notes or [])
                ],
                "imaging": [
                    {
                        "imaging_id": i.imaging_id,
                        "patient_id": i.patient_id,
                        "encounter_id": i.encounter_id,
                        "study_date": i.study_date,
                        "modality": i.modality,
                        "body_part": i.body_part,
                        "findings": i.findings,
                        "impression": i.impression,
                    }
                    for i in (enc.imaging_reports or [])
                ],
                "procedures": [
                    {
                        "procedure_id": p.procedure_id,
                        "patient_id": p.patient_id,
                        "encounter_id": p.encounter_id,
                        "procedure_date": p.procedure_date,
                        "procedure_name": p.procedure_name,
                        "description": p.description,
                        "result": p.result,
                    }
                    for p in (enc.procedures or [])
                ],
            })

        return {
            "patient_id": patient_id,
            "patient": patient_block,
            "allergies": allergies_list,
            "encounters": encounter_list,
        }
