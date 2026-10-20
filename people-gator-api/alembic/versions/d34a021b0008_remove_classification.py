"""Remove the unused classification payload while preserving recorded actors/times.

Revision ID: d34a021b0008
Revises: d34a021b0007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d34a021b0008"
down_revision = "d34a021b0007"
branch_labels = None
depends_on = None

TABLES = ("pg_demo_entities", "pg_demo_image_occurrences", "pg_demo_text_mentions")


def upgrade():
    for table in TABLES:
        op.drop_column(table, "provenance")


def downgrade():
    for table in TABLES:
        op.add_column(table, sa.Column("provenance", JSONB(), nullable=True))
