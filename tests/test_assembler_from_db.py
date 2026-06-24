"""Tests for C1 assembler reading from database instead of JSON files."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.db.models import (
    Base, PatientDB, EncounterDB, LabDB, MedicationDB,
    DiagnosisDB, AllergyDB,
)
from src.c1_emr.assembler import assemble_from_db


@pytest_asyncio.fixture
async def seeded_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add(PatientDB(
            patient_id="P001", full_name="Nguyễn Văn An", age=55,
            gender="male", phone="0912345678",
        ))
        session.add(EncounterDB(
            encounter_id="P001-E001", patient_id="P001",
            encounter_date="2024-01-10", encounter_type="outpatient",
            department="Nội tiết", doctor_name="BS. Hoa",
        ))
        session.add(LabDB(
            lab_id="P001-E001-LAB001", patient_id="P001", encounter_id="P001-E001",
            test_name="HbA1c", value=9.2, unit="%", is_abnormal=True,
        ))
        session.add(MedicationDB(
            medication_id="P001-E001-MED001", patient_id="P001", encounter_id="P001-E001",
            drug_name="Metformin", strength="1000 mg",
        ))
        session.add(DiagnosisDB(
            diagnosis_id="P001-E001-DX001", patient_id="P001", encounter_id="P001-E001",
            icd10_code="E11", diagnosis_name="ĐTĐ type 2",
        ))
        session.add(AllergyDB(
            allergy_id="P001-A001", patient_id="P001",
            substance="Penicillin", severity="moderate", status="active",
        ))
        await session.commit()
        yield session
    await engine.dispose()


class TestAssembleFromDB:
    @pytest.mark.asyncio
    async def test_returns_assembled_dict(self, seeded_session):
        result = await assemble_from_db(seeded_session, "P001")
        assert result is not None
        assert result["patient_id"] == "P001"
        assert result["patient"]["full_name"] == "Nguyễn Văn An"

    @pytest.mark.asyncio
    async def test_encounters_have_nested_data(self, seeded_session):
        result = await assemble_from_db(seeded_session, "P001")
        enc = result["encounters"][0]
        assert enc["encounter_id"] == "P001-E001"
        assert len(enc["labs"]) == 1
        assert enc["labs"][0]["test_name"] == "HbA1c"
        assert len(enc["medications"]) == 1
        assert len(enc["diagnoses"]) == 1

    @pytest.mark.asyncio
    async def test_allergies_at_patient_level(self, seeded_session):
        result = await assemble_from_db(seeded_session, "P001")
        assert len(result["allergies"]) == 1
        assert result["allergies"][0]["substance"] == "Penicillin"

    @pytest.mark.asyncio
    async def test_format_matches_file_assembler(self, seeded_session):
        result = await assemble_from_db(seeded_session, "P001")
        assert set(result.keys()) == {"patient_id", "patient", "allergies", "encounters"}
        enc = result["encounters"][0]
        expected_enc_keys = {
            "encounter_id", "patient_id", "encounter_date", "encounter_type",
            "department", "doctor_name", "chief_complaint", "visit_reason",
            "vitals", "labs", "medications", "diagnoses",
            "clinical_notes", "imaging", "procedures",
        }
        assert expected_enc_keys.issubset(set(enc.keys()))

    @pytest.mark.asyncio
    async def test_nonexistent_patient(self, seeded_session):
        result = await assemble_from_db(seeded_session, "P999")
        assert result is None
