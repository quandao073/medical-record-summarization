"""add performance indexes

Revision ID: a1b2c3d4e5f6
Revises: 22d56e922de5
Create Date: 2026-06-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "22d56e922de5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("idx_encounters_patient_date", "encounters", ["patient_id", "encounter_date"])
    op.create_index("idx_labs_encounter", "labs", ["encounter_id"])
    op.create_index("idx_medications_encounter", "medications", ["encounter_id"])
    op.create_index("idx_diagnoses_encounter", "diagnoses", ["encounter_id"])
    op.create_index("idx_allergies_patient", "allergies", ["patient_id"])
    op.create_index("idx_clinical_notes_encounter", "clinical_notes", ["encounter_id"])


def downgrade() -> None:
    op.drop_index("idx_clinical_notes_encounter", table_name="clinical_notes")
    op.drop_index("idx_allergies_patient", table_name="allergies")
    op.drop_index("idx_diagnoses_encounter", table_name="diagnoses")
    op.drop_index("idx_medications_encounter", table_name="medications")
    op.drop_index("idx_labs_encounter", table_name="labs")
    op.drop_index("idx_encounters_patient_date", table_name="encounters")
