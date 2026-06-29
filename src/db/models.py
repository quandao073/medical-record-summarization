"""
SQLAlchemy ORM models — 10 raw EHR tables.

Mirrors the 10 JSON files in data/raw/:
  patients.json       → PatientDB
  encounters.json     → EncounterDB
  labs.json           → LabDB
  medications.json    → MedicationDB
  diagnoses.json      → DiagnosisDB
  allergies.json      → AllergyDB
  vitals.json         → VitalDB
  clinical_notes.json → ClinicalNoteDB
  imaging_reports.json → ImagingReportDB
  procedures.json     → ProcedureDB
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean, Column, Float, ForeignKey, Index,
    Integer, String, Text,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ─── 1. patients ─────────────────────────────────────────────────────────────

class PatientDB(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(10), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False, default="")
    date_of_birth = Column(String(20), nullable=True)
    age = Column(Integer, nullable=True)
    gender = Column(String(10), nullable=True)
    occupation = Column(String(200), nullable=True)
    address = Column(Text, nullable=True)
    insurance_id = Column(String(50), nullable=True)
    citizen_id = Column(String(50), nullable=True)
    phone = Column(String(20), nullable=True)
    created_at = Column(String(50), nullable=True)
    updated_at = Column(String(50), nullable=True)

    encounters = relationship("EncounterDB", back_populates="patient", cascade="all, delete-orphan")
    allergies = relationship("AllergyDB", back_populates="patient", cascade="all, delete-orphan")


# ─── 2. encounters ───────────────────────────────────────────────────────────

class EncounterDB(Base):
    __tablename__ = "encounters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    encounter_id = Column(String(30), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_date = Column(String(20), nullable=False)
    encounter_type = Column(String(30), nullable=True)
    department = Column(String(200), nullable=True)
    doctor_id = Column(String(20), nullable=True)
    doctor_name = Column(String(200), nullable=True)
    chief_complaint = Column(Text, nullable=True)
    visit_reason = Column(Text, nullable=True)

    patient = relationship("PatientDB", back_populates="encounters")
    labs = relationship("LabDB", back_populates="encounter", cascade="all, delete-orphan")
    medications = relationship("MedicationDB", back_populates="encounter", cascade="all, delete-orphan")
    diagnoses = relationship("DiagnosisDB", back_populates="encounter", cascade="all, delete-orphan")
    vitals = relationship("VitalDB", back_populates="encounter", cascade="all, delete-orphan")
    clinical_notes = relationship("ClinicalNoteDB", back_populates="encounter", cascade="all, delete-orphan")
    imaging_reports = relationship("ImagingReportDB", back_populates="encounter", cascade="all, delete-orphan")
    procedures = relationship("ProcedureDB", back_populates="encounter", cascade="all, delete-orphan")


# ─── 3. labs ──────────────────────────────────────────────────────────────────

class LabDB(Base):
    __tablename__ = "labs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lab_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), nullable=False, index=True)
    encounter_id = Column(String(30), ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    sample_date = Column(String(20), nullable=True)
    result_date = Column(String(20), nullable=True)
    test_code = Column(String(30), nullable=True)
    test_name = Column(String(200), nullable=False)
    value = Column(Float, nullable=True)
    unit = Column(String(30), nullable=True)
    reference_range = Column(String(50), nullable=True)
    interpretation = Column(String(30), nullable=True)
    is_abnormal = Column(Boolean, default=False)
    is_critical = Column(Boolean, default=False)
    comment = Column(Text, nullable=True)

    encounter = relationship("EncounterDB", back_populates="labs")


# ─── 4. medications ──────────────────────────────────────────────────────────

class MedicationDB(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medication_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), nullable=False, index=True)
    encounter_id = Column(String(30), ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    prescription_date = Column(String(20), nullable=True)
    drug_name = Column(String(200), nullable=False)
    strength = Column(String(50), nullable=True)
    dose = Column(String(50), nullable=True)
    route = Column(String(30), nullable=True)
    frequency = Column(String(200), nullable=True)
    instruction = Column(Text, nullable=True)
    duration_days = Column(Integer, nullable=True)
    is_current = Column(Boolean, default=True)

    encounter = relationship("EncounterDB", back_populates="medications")


# ─── 5. diagnoses ────────────────────────────────────────────────────────────

class DiagnosisDB(Base):
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    diagnosis_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), nullable=False, index=True)
    encounter_id = Column(String(30), ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    diagnosis_date = Column(String(20), nullable=True)
    diagnosis_type = Column(String(30), nullable=True)
    icd10_code = Column(String(10), nullable=False)
    diagnosis_name = Column(String(300), nullable=False)
    diagnosis_text = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    encounter = relationship("EncounterDB", back_populates="diagnoses")


# ─── 6. allergies ────────────────────────────────────────────────────────────

class AllergyDB(Base):
    __tablename__ = "allergies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    allergy_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), ForeignKey("patients.patient_id", ondelete="CASCADE"), nullable=False, index=True)
    encounter_id = Column(String(30), nullable=True)
    recorded_date = Column(String(20), nullable=True)
    substance = Column(String(200), nullable=False)
    reaction = Column(Text, nullable=True)
    severity = Column(String(30), nullable=True)
    status = Column(String(30), nullable=True)
    source_text = Column(Text, nullable=True)
    needs_patient_confirmation = Column(Boolean, default=False)

    patient = relationship("PatientDB", back_populates="allergies")


# ─── 7. vitals ───────────────────────────────────────────────────────────────

class VitalDB(Base):
    __tablename__ = "vitals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vital_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), nullable=False, index=True)
    encounter_id = Column(String(30), ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    measured_at = Column(String(50), nullable=True)
    blood_pressure_systolic = Column(Integer, nullable=True)
    blood_pressure_diastolic = Column(Integer, nullable=True)
    heart_rate = Column(Integer, nullable=True)
    temperature_celsius = Column(Float, nullable=True)
    spo2_percent = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)
    bmi = Column(Float, nullable=True)
    abnormal_flags_json = Column(JSON, default=list)

    encounter = relationship("EncounterDB", back_populates="vitals")


# ─── 8. clinical_notes ───────────────────────────────────────────────────────

class ClinicalNoteDB(Base):
    __tablename__ = "clinical_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), nullable=False, index=True)
    encounter_id = Column(String(30), ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    note_date = Column(String(20), nullable=True)
    note_type = Column(String(50), nullable=True)
    section = Column(String(100), nullable=True)
    text = Column(Text, nullable=False)
    author_name = Column(String(200), nullable=True)

    encounter = relationship("EncounterDB", back_populates="clinical_notes")


# ─── 9. imaging_reports ──────────────────────────────────────────────────────

class ImagingReportDB(Base):
    __tablename__ = "imaging_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    imaging_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), nullable=False, index=True)
    encounter_id = Column(String(30), ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    study_date = Column(String(20), nullable=True)
    modality = Column(String(30), nullable=True)
    body_part = Column(String(100), nullable=True)
    findings = Column(Text, nullable=True)
    impression = Column(Text, nullable=True)

    encounter = relationship("EncounterDB", back_populates="imaging_reports")


# ─── 10. procedures ──────────────────────────────────────────────────────────

class ProcedureDB(Base):
    __tablename__ = "procedures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    procedure_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(10), nullable=False, index=True)
    encounter_id = Column(String(30), ForeignKey("encounters.encounter_id", ondelete="CASCADE"), nullable=False)
    procedure_date = Column(String(20), nullable=True)
    procedure_name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    result = Column(Text, nullable=True)

    encounter = relationship("EncounterDB", back_populates="procedures")


# ─── 11. chunks ──────────────────────────────────────────────────────────────

class ChunkDB(Base):
    __tablename__ = "chunks"

    source_id    = Column(String(100), primary_key=True)
    patient_id   = Column(String(10), nullable=False, index=True)
    source_type  = Column(String(30), nullable=False)
    encounter_id = Column(String(30), nullable=True)
    date         = Column(String(20), nullable=True)
    content      = Column(Text, nullable=False, default="")
    metadata_json = Column("metadata", JSON, nullable=True, default=dict)

    __table_args__ = (
        Index("ix_chunks_patient_type", "patient_id", "source_type"),
    )
