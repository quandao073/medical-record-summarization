"""Tests for EMR repository — raw data access for C1 pipeline."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.db.models import (
    Base, PatientDB, EncounterDB, LabDB, MedicationDB,
    DiagnosisDB, AllergyDB, VitalDB, ClinicalNoteDB,
    ImagingReportDB, ProcedureDB,
)
from src.db.repositories.emr_repo import EMRRepository


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_p001(session: AsyncSession):
    """Insert minimal P001 data for testing."""
    session.add(PatientDB(
        patient_id="P001", full_name="Nguyễn Văn An", age=55,
        gender="male", occupation="Công chức",
    ))
    session.add(EncounterDB(
        encounter_id="P001-E001", patient_id="P001",
        encounter_date="2024-01-10", encounter_type="outpatient",
        department="Nội tiết", doctor_name="BS. Hoa",
        chief_complaint="Tái khám ĐTĐ", visit_reason="Kiểm tra HbA1c",
    ))
    session.add(LabDB(
        lab_id="P001-E001-LAB001", patient_id="P001", encounter_id="P001-E001",
        sample_date="2024-01-10", test_code="HBA1C", test_name="HbA1c",
        value=9.2, unit="%", reference_range="4.0 - 5.6",
        interpretation="high", is_abnormal=True,
    ))
    session.add(MedicationDB(
        medication_id="P001-E001-MED001", patient_id="P001", encounter_id="P001-E001",
        prescription_date="2024-01-10", drug_name="Metformin",
        strength="1000 mg", dose="1 viên", frequency="2 lần/ngày",
    ))
    session.add(DiagnosisDB(
        diagnosis_id="P001-E001-DX001", patient_id="P001", encounter_id="P001-E001",
        diagnosis_date="2024-01-10", diagnosis_type="primary",
        icd10_code="E11", diagnosis_name="ĐTĐ type 2",
    ))
    session.add(AllergyDB(
        allergy_id="P001-ALLERGY001", patient_id="P001",
        recorded_date="2021-03-15", substance="Penicillin",
        reaction="Nổi mề đay", severity="moderate", status="active",
    ))
    session.add(VitalDB(
        vital_id="P001-E001-VIT001", patient_id="P001", encounter_id="P001-E001",
        blood_pressure_systolic=148, blood_pressure_diastolic=92, heart_rate=82,
    ))
    session.add(ClinicalNoteDB(
        note_id="P001-E001-NOTE001", patient_id="P001", encounter_id="P001-E001",
        note_date="2024-01-10", note_type="doctor_note", text="BN nam 55 tuổi",
    ))
    session.add(ImagingReportDB(
        imaging_id="P001-E001-IMG001", patient_id="P001", encounter_id="P001-E001",
        study_date="2024-01-10", modality="ECG", findings="Nhịp xoang",
    ))
    session.add(ProcedureDB(
        procedure_id="P001-E001-PROC001", patient_id="P001", encounter_id="P001-E001",
        procedure_date="2024-01-10", procedure_name="Test monofilament",
        result="Bình thường",
    ))
    await session.commit()


class TestEMRRepository:
    @pytest.mark.asyncio
    async def test_list_patients_empty(self, async_session):
        repo = EMRRepository(async_session)
        assert await repo.list_patients() == []

    @pytest.mark.asyncio
    async def test_list_patients_sorted(self, async_session):
        async_session.add(PatientDB(patient_id="P003", full_name="C"))
        async_session.add(PatientDB(patient_id="P001", full_name="A"))
        await async_session.commit()
        repo = EMRRepository(async_session)
        assert await repo.list_patients() == ["P001", "P003"]

    @pytest.mark.asyncio
    async def test_get_assembled_dict_full(self, async_session):
        await _seed_p001(async_session)
        repo = EMRRepository(async_session)
        result = await repo.get_assembled_dict("P001")

        assert result is not None
        assert result["patient_id"] == "P001"
        assert result["patient"]["full_name"] == "Nguyễn Văn An"
        assert result["patient"]["age"] == 55
        assert len(result["encounters"]) == 1
        assert len(result["allergies"]) == 1

        enc = result["encounters"][0]
        assert enc["encounter_id"] == "P001-E001"
        assert enc["encounter_date"] == "2024-01-10"
        assert len(enc["labs"]) == 1
        assert enc["labs"][0]["test_name"] == "HbA1c"
        assert enc["labs"][0]["value"] == 9.2
        assert len(enc["medications"]) == 1
        assert enc["medications"][0]["drug_name"] == "Metformin"
        assert len(enc["diagnoses"]) == 1
        assert enc["diagnoses"][0]["icd10_code"] == "E11"
        assert len(enc["vitals"]) == 1
        assert len(enc["clinical_notes"]) == 1
        assert len(enc["imaging"]) == 1
        assert len(enc["procedures"]) == 1

    @pytest.mark.asyncio
    async def test_get_assembled_dict_nonexistent(self, async_session):
        repo = EMRRepository(async_session)
        assert await repo.get_assembled_dict("P999") is None

    @pytest.mark.asyncio
    async def test_allergies_at_patient_level(self, async_session):
        await _seed_p001(async_session)
        repo = EMRRepository(async_session)
        result = await repo.get_assembled_dict("P001")
        assert result["allergies"][0]["substance"] == "Penicillin"
        assert result["allergies"][0]["severity"] == "moderate"

    @pytest.mark.asyncio
    async def test_format_matches_file_assembler(self, async_session):
        await _seed_p001(async_session)
        repo = EMRRepository(async_session)
        result = await repo.get_assembled_dict("P001")
        assert set(result.keys()) == {"patient_id", "patient", "allergies", "encounters"}
        enc = result["encounters"][0]
        expected_enc_keys = {
            "encounter_id", "patient_id", "encounter_date", "encounter_type",
            "department", "doctor_name", "chief_complaint", "visit_reason",
            "vitals", "labs", "medications", "diagnoses",
            "clinical_notes", "imaging", "procedures",
        }
        assert expected_enc_keys.issubset(set(enc.keys()))
