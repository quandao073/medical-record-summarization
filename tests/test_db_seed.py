"""Tests for database seed — import data/raw/ JSON into DB."""

import json
import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.db.models import Base, PatientDB, EncounterDB, LabDB, AllergyDB
from src.db.seed import seed_from_raw


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class TestSeedFromRaw:
    @pytest.mark.asyncio
    async def test_seed_patients(self, async_session, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        patients = [{"patient_id": "P001", "full_name": "Test", "age": 55, "gender": "male"}]
        for name in ["encounters", "labs", "medications", "diagnoses", "allergies",
                      "vitals", "clinical_notes", "imaging_reports", "procedures"]:
            (raw_dir / f"{name}.json").write_text("[]", encoding="utf-8")
        (raw_dir / "patients.json").write_text(json.dumps(patients), encoding="utf-8")

        counts = await seed_from_raw(async_session, raw_dir)
        await async_session.commit()

        assert counts["patients"] == 1
        result = await async_session.execute(select(PatientDB))
        assert len(result.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_seed_with_encounters_and_labs(self, async_session, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        (raw_dir / "patients.json").write_text(
            json.dumps([{"patient_id": "P001", "full_name": "An"}]), encoding="utf-8")
        (raw_dir / "encounters.json").write_text(
            json.dumps([{"encounter_id": "P001-E001", "patient_id": "P001",
                         "encounter_date": "2024-01-10"}]), encoding="utf-8")
        (raw_dir / "labs.json").write_text(
            json.dumps([{"lab_id": "P001-E001-LAB001", "patient_id": "P001",
                         "encounter_id": "P001-E001", "test_name": "HbA1c", "value": 9.2, "unit": "%"}]),
            encoding="utf-8")
        (raw_dir / "allergies.json").write_text(
            json.dumps([{"allergy_id": "P001-A001", "patient_id": "P001", "substance": "Penicillin"}]),
            encoding="utf-8")
        for name in ["medications", "diagnoses", "vitals", "clinical_notes",
                      "imaging_reports", "procedures"]:
            (raw_dir / f"{name}.json").write_text("[]", encoding="utf-8")

        counts = await seed_from_raw(async_session, raw_dir)
        await async_session.commit()

        assert counts["patients"] == 1
        assert counts["encounters"] == 1
        assert counts["labs"] == 1
        assert counts["allergies"] == 1

    @pytest.mark.asyncio
    async def test_seed_idempotent(self, async_session, tmp_path):
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        (raw_dir / "patients.json").write_text(
            json.dumps([{"patient_id": "P001", "full_name": "An"}]), encoding="utf-8")
        for name in ["encounters", "labs", "medications", "diagnoses", "allergies",
                      "vitals", "clinical_notes", "imaging_reports", "procedures"]:
            (raw_dir / f"{name}.json").write_text("[]", encoding="utf-8")

        await seed_from_raw(async_session, raw_dir)
        await async_session.commit()
        await seed_from_raw(async_session, raw_dir)
        await async_session.commit()

        result = await async_session.execute(select(func.count()).select_from(PatientDB))
        assert result.scalar() == 1
