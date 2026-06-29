"""Tests for ChunkDB SQLAlchemy model."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from src.db.models import Base, ChunkDB


@pytest.fixture
def sync_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(sync_engine):
    with Session(sync_engine) as s:
        yield s


class TestChunkDBTable:
    def test_chunks_table_created(self, sync_engine):
        inspector = inspect(sync_engine)
        assert "chunks" in inspector.get_table_names()

    def test_chunks_table_columns(self, sync_engine):
        inspector = inspect(sync_engine)
        cols = {c["name"] for c in inspector.get_columns("chunks")}
        assert cols >= {"source_id", "patient_id", "source_type",
                        "encounter_id", "date", "content", "metadata"}


class TestChunkDBCRUD:
    def test_insert_and_query_by_source_id(self, session):
        session.add(ChunkDB(
            source_id="P001-E001-LAB-HBA1C",
            patient_id="P001",
            source_type="labs",
            encounter_id="P001-E001",
            date="2024-01-10",
            content="HbA1c = 8.5%",
            metadata_json={"is_abnormal": True, "test_name": "HbA1c"},
        ))
        session.commit()

        row = session.query(ChunkDB).filter_by(source_id="P001-E001-LAB-HBA1C").first()
        assert row is not None
        assert row.patient_id == "P001"
        assert row.source_type == "labs"
        assert row.metadata_json["is_abnormal"] is True

    def test_insert_multiple_patients(self, session):
        session.add_all([
            ChunkDB(source_id="P001-PATIENT-INFO", patient_id="P001",
                    source_type="patient_info", content="Patient info P001", metadata_json={}),
            ChunkDB(source_id="P002-PATIENT-INFO", patient_id="P002",
                    source_type="patient_info", content="Patient info P002", metadata_json={}),
        ])
        session.commit()
        p1 = session.query(ChunkDB).filter_by(patient_id="P001").all()
        p2 = session.query(ChunkDB).filter_by(patient_id="P002").all()
        assert len(p1) == 1
        assert len(p2) == 1

    def test_source_id_is_primary_key(self, session):
        session.add(ChunkDB(
            source_id="DUP-001", patient_id="P001",
            source_type="labs", content="x", metadata_json={},
        ))
        session.commit()
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            session.add(ChunkDB(
                source_id="DUP-001", patient_id="P002",
                source_type="labs", content="y", metadata_json={},
            ))
            session.commit()

    def test_nullable_fields_accept_none(self, session):
        session.add(ChunkDB(
            source_id="P001-ALLERGY-PEN", patient_id="P001",
            source_type="allergies", content="Penicillin allergy",
            encounter_id=None, date=None, metadata_json=None,
        ))
        session.commit()
        row = session.query(ChunkDB).filter_by(source_id="P001-ALLERGY-PEN").first()
        assert row.encounter_id is None
        assert row.date is None
