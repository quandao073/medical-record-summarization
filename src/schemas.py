"""
Central data contracts for the entire pipeline.
All components import from here — never define types elsewhere.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Source / Evidence layer
# ---------------------------------------------------------------------------

class SourceChunk(BaseModel):
    """One citable unit of clinical information."""

    source_id: str                      # e.g. "P001-E001-LAB-HBA1C"
    source_type: str                    # "labs" | "medications" | "diagnoses" | ...
    patient_id: str
    encounter_id: Optional[str] = None
    date: Optional[str] = None          # ISO date string, e.g. "2024-01-15"
    content: str                        # Normalized, embed-ready text
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Citation / Claim layer
# ---------------------------------------------------------------------------

ClaimStatus = Literal[
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "LOW_CONFIDENCE",
    "UNSUPPORTED",
    "NO_CITATION",
    "CONTRADICTED",
    "NEED_REVIEW",
]

VerificationStatus = Literal[
    "PENDING",
    "CONFIRMED",
    "UNVERIFIED",
    "INCORRECT",
]


class CitedClaim(BaseModel):
    """One atomic claim generated in the summary."""

    claim_text: str
    status: ClaimStatus = "NO_CITATION"
    citations: list[str] = Field(default_factory=list)   # List of source_id
    confidence_score: Optional[float] = None
    is_critical: bool = False
    verification_status: VerificationStatus = "PENDING"


# ---------------------------------------------------------------------------
# Summary layer
# ---------------------------------------------------------------------------

class SummarySection(BaseModel):
    """One section in the final clinical summary."""

    section_id: str                     # e.g. "current_medications", "abnormal_labs"
    title: Optional[str] = None         # e.g. "Current Medications"
    content: str = ""
    cited_claims: list[CitedClaim] = Field(default_factory=list)


class SummaryMetrics(BaseModel):
    citation_coverage: float = 0.0
    unsupported_claim_rate: float = 0.0
    hallucination_rate: float = 0.0
    missing_section_rate: float = 0.0
    total_claims: int = 0
    latency_seconds: float = 0.0
    token_count: int = 0


class FinalSummary(BaseModel):
    patient_id: str
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    prompt_version: str = "poc_v1"
    model_version: str = "claude-sonnet-4-6"
    sections: list[SummarySection] = Field(default_factory=list)
    metrics: SummaryMetrics = Field(default_factory=SummaryMetrics)


# ---------------------------------------------------------------------------
# EHR Input layer — assembled format
# ---------------------------------------------------------------------------

class AllergyRecord(BaseModel):
    allergy_id: str
    patient_id: str
    encounter_id: Optional[str] = None
    recorded_date: Optional[str] = None
    substance: str
    reaction: Optional[str] = None
    severity: Optional[str] = None       # "mild" | "moderate" | "severe" | "unknown"
    status: Optional[str] = None         # "active" | "inactive" | "unknown"
    source_text: Optional[str] = None
    needs_patient_confirmation: bool = False


class LabRecord(BaseModel):
    lab_id: str
    patient_id: str
    encounter_id: str
    sample_date: Optional[str] = None
    result_date: Optional[str] = None
    test_code: Optional[str] = None
    test_name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    interpretation: Optional[str] = None  # "normal" | "high" | "low" | "critical"
    is_abnormal: bool = False
    is_critical: bool = False
    comment: Optional[str] = None


class MedicationRecord(BaseModel):
    medication_id: str
    patient_id: str
    encounter_id: str
    prescription_date: Optional[str] = None
    drug_name: str
    strength: Optional[str] = None
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    instruction: Optional[str] = None
    duration_days: Optional[int] = None
    is_current: bool = True


class DiagnosisRecord(BaseModel):
    diagnosis_id: str
    patient_id: str
    encounter_id: str
    diagnosis_date: Optional[str] = None
    diagnosis_type: Optional[str] = None   # "primary" | "comorbidity" | "complication"
    icd10_code: str
    diagnosis_name: str
    diagnosis_text: Optional[str] = None
    is_active: bool = True


class VitalRecord(BaseModel):
    vital_id: str
    patient_id: str
    encounter_id: str
    measured_at: Optional[str] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    heart_rate: Optional[int] = None
    temperature_celsius: Optional[float] = None
    spo2_percent: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    bmi: Optional[float] = None
    abnormal_flags: list[str] = Field(default_factory=list)


class ClinicalNoteRecord(BaseModel):
    note_id: str
    patient_id: str
    encounter_id: str
    note_date: Optional[str] = None
    note_type: Optional[str] = None       # "doctor_note" | "nursing_note" | ...
    section: Optional[str] = None         # "history" | "physical_exam" | ...
    text: str
    author_name: Optional[str] = None


class ImagingRecord(BaseModel):
    imaging_id: str
    patient_id: str
    encounter_id: str
    study_date: Optional[str] = None
    modality: Optional[str] = None        # "X-ray" | "CT" | "MRI" | "ECG" | ...
    body_part: Optional[str] = None
    findings: Optional[str] = None
    impression: Optional[str] = None


class ProcedureRecord(BaseModel):
    procedure_id: str
    patient_id: str
    encounter_id: str
    procedure_date: Optional[str] = None
    procedure_name: str
    description: Optional[str] = None
    result: Optional[str] = None


class EncounterRecord(BaseModel):
    encounter_id: str
    patient_id: str
    encounter_date: str
    encounter_type: Optional[str] = None   # "outpatient" | "inpatient" | "emergency"
    department: Optional[str] = None
    doctor_name: Optional[str] = None
    chief_complaint: Optional[str] = None
    visit_reason: Optional[str] = None

    # Joined data
    vitals: list[VitalRecord] = Field(default_factory=list)
    labs: list[LabRecord] = Field(default_factory=list)
    medications: list[MedicationRecord] = Field(default_factory=list)
    diagnoses: list[DiagnosisRecord] = Field(default_factory=list)
    clinical_notes: list[ClinicalNoteRecord] = Field(default_factory=list)
    imaging: list[ImagingRecord] = Field(default_factory=list)
    procedures: list[ProcedureRecord] = Field(default_factory=list)


class PatientRecord(BaseModel):
    patient_id: str
    full_name: str
    date_of_birth: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None


class AssembledEHR(BaseModel):
    """Unified EHR per patient — output of the assembler script."""

    patient_id: str
    patient: PatientRecord
    allergies: list[AllergyRecord] = Field(default_factory=list)
    encounters: list[EncounterRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class ValidationError(BaseModel):
    field: str
    message: str
    severity: Literal["error", "warning"] = "error"