"""Tests for SQLAlchemy ORM models — 10 raw EHR tables."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from src.db.models import (
    Base, PatientDB, EncounterDB, LabDB, MedicationDB,
    DiagnosisDB, AllergyDB, VitalDB, ClinicalNoteDB,
    ImagingReportDB, ProcedureDB,
)


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


class TestTableCreation:
    def test_all_10_tables_created(self, sync_engine):
        inspector = inspect(sync_engine)
        tables = set(inspector.get_table_names())
        expected = {
            "patients", "encounters", "labs", "medications", "diagnoses",
            "allergies", "vitals", "clinical_notes", "imaging_reports", "procedures",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"


class TestPatientDB:
    def test_insert_and_query(self, session):
        p = PatientDB(
            patient_id="P001", full_name="Nguyễn Văn An", age=55,
            gender="male", occupation="Công chức",
            address="Hà Nội", insurance_id="012345", citizen_id="001069",
            phone="0912345678", date_of_birth="1969-01-15",
        )
        session.add(p)
        session.commit()
        result = session.query(PatientDB).filter_by(patient_id="P001").first()
        assert result.full_name == "Nguyễn Văn An"
        assert result.age == 55

    def test_patient_id_unique(self, session):
        session.add(PatientDB(patient_id="P001", full_name="A"))
        session.commit()
        session.add(PatientDB(patient_id="P001", full_name="B"))
        with pytest.raises(Exception):
            session.commit()


class TestEncounterDB:
    def test_insert_encounter(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        enc = EncounterDB(
            encounter_id="P001-E001", patient_id="P001",
            encounter_date="2024-01-10", encounter_type="outpatient",
            department="Nội tiết", doctor_name="BS. Hoa",
            chief_complaint="Tái khám ĐTĐ", visit_reason="Kiểm tra HbA1c",
        )
        session.add(enc)
        session.commit()
        result = session.query(EncounterDB).filter_by(encounter_id="P001-E001").first()
        assert result.department == "Nội tiết"


class TestLabDB:
    def test_insert_lab(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        session.add(EncounterDB(encounter_id="P001-E001", patient_id="P001", encounter_date="2024-01-10"))
        session.commit()
        lab = LabDB(
            lab_id="P001-E001-LAB001", patient_id="P001", encounter_id="P001-E001",
            sample_date="2024-01-10", test_code="HBA1C",
            test_name="HbA1c", value=9.2, unit="%",
            reference_range="4.0 - 5.6", interpretation="high",
            is_abnormal=True, is_critical=False,
            comment="Kiểm soát kém",
        )
        session.add(lab)
        session.commit()
        result = session.query(LabDB).filter_by(lab_id="P001-E001-LAB001").first()
        assert result.value == 9.2
        assert result.is_abnormal is True


class TestMedicationDB:
    def test_insert_medication(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        session.add(EncounterDB(encounter_id="P001-E001", patient_id="P001", encounter_date="2024-01-10"))
        session.commit()
        med = MedicationDB(
            medication_id="P001-E001-MED001", patient_id="P001", encounter_id="P001-E001",
            prescription_date="2024-01-10", drug_name="Metformin",
            strength="1000 mg", dose="1 viên", route="oral",
            frequency="2 lần/ngày", instruction="Uống sau ăn",
            duration_days=90, is_current=True,
        )
        session.add(med)
        session.commit()
        result = session.query(MedicationDB).filter_by(medication_id="P001-E001-MED001").first()
        assert result.drug_name == "Metformin"


class TestDiagnosisDB:
    def test_insert_diagnosis(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        session.add(EncounterDB(encounter_id="P001-E001", patient_id="P001", encounter_date="2024-01-10"))
        session.commit()
        dx = DiagnosisDB(
            diagnosis_id="P001-E001-DX001", patient_id="P001", encounter_id="P001-E001",
            diagnosis_date="2024-01-10", diagnosis_type="primary",
            icd10_code="E11", diagnosis_name="Đái tháo đường type 2",
            diagnosis_text="ĐTĐ type 2 kiểm soát kém", is_active=True,
        )
        session.add(dx)
        session.commit()
        result = session.query(DiagnosisDB).filter_by(diagnosis_id="P001-E001-DX001").first()
        assert result.icd10_code == "E11"


class TestAllergyDB:
    def test_insert_allergy(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        allergy = AllergyDB(
            allergy_id="P001-ALLERGY001", patient_id="P001",
            recorded_date="2021-03-15", substance="Penicillin",
            reaction="Nổi mề đay", severity="moderate", status="active",
            source_text="Dị ứng Penicillin", needs_patient_confirmation=False,
        )
        session.add(allergy)
        session.commit()
        result = session.query(AllergyDB).filter_by(allergy_id="P001-ALLERGY001").first()
        assert result.substance == "Penicillin"
        assert result.severity == "moderate"


class TestVitalDB:
    def test_insert_vital(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        session.add(EncounterDB(encounter_id="P001-E001", patient_id="P001", encounter_date="2024-01-10"))
        session.commit()
        vital = VitalDB(
            vital_id="P001-E001-VIT001", patient_id="P001", encounter_id="P001-E001",
            measured_at="2024-01-10T08:20:00", blood_pressure_systolic=148,
            blood_pressure_diastolic=92, heart_rate=82,
            weight_kg=82.0, height_cm=168.0, bmi=29.1,
            temperature_celsius=36.8, spo2_percent=98,
            abnormal_flags_json=["high_blood_pressure", "overweight_bmi"],
        )
        session.add(vital)
        session.commit()
        result = session.query(VitalDB).filter_by(vital_id="P001-E001-VIT001").first()
        assert result.blood_pressure_systolic == 148
        assert "high_blood_pressure" in result.abnormal_flags_json


class TestClinicalNoteDB:
    def test_insert_note(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        session.add(EncounterDB(encounter_id="P001-E001", patient_id="P001", encounter_date="2024-01-10"))
        session.commit()
        note = ClinicalNoteDB(
            note_id="P001-E001-NOTE001", patient_id="P001", encounter_id="P001-E001",
            note_date="2024-01-10", note_type="doctor_note",
            section="history_of_present_illness",
            text="BN nam 55 tuổi, tiền sử ĐTĐ type 2",
            author_name="BS. Hoa",
        )
        session.add(note)
        session.commit()
        result = session.query(ClinicalNoteDB).filter_by(note_id="P001-E001-NOTE001").first()
        assert "ĐTĐ type 2" in result.text


class TestImagingReportDB:
    def test_insert_imaging(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        session.add(EncounterDB(encounter_id="P001-E001", patient_id="P001", encounter_date="2024-01-10"))
        session.commit()
        img = ImagingReportDB(
            imaging_id="P001-E001-IMG001", patient_id="P001", encounter_id="P001-E001",
            study_date="2024-01-10", modality="ECG", body_part="Tim",
            findings="Nhịp xoang bình thường",
            impression="Không bất thường",
        )
        session.add(img)
        session.commit()
        result = session.query(ImagingReportDB).filter_by(imaging_id="P001-E001-IMG001").first()
        assert result.modality == "ECG"


class TestProcedureDB:
    def test_insert_procedure(self, session):
        session.add(PatientDB(patient_id="P001", full_name="Test"))
        session.commit()
        session.add(EncounterDB(encounter_id="P001-E001", patient_id="P001", encounter_date="2024-01-10"))
        session.commit()
        proc = ProcedureDB(
            procedure_id="P001-E001-PROC001", patient_id="P001", encounter_id="P001-E001",
            procedure_date="2024-01-10",
            procedure_name="Khám thần kinh ngoại biên",
            description="Kiểm tra monofilament 10g",
            result="Mất cảm giác ngón 1 và 3 bàn chân phải",
        )
        session.add(proc)
        session.commit()
        result = session.query(ProcedureDB).filter_by(procedure_id="P001-E001-PROC001").first()
        assert "thần kinh" in result.procedure_name
