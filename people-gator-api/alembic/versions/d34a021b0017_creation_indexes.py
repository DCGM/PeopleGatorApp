"""Index creation metadata used by creation date and creator filters.

Revision ID: d34a021b0017
Revises: d34a021b0016
"""
from alembic import op

revision = "d34a021b0017"
down_revision = "d34a021b0016"
branch_labels = None
depends_on = None

TABLES = ("pg_demo_sources", "pg_demo_entities", "pg_demo_image_occurrences", "pg_demo_text_mentions")
FIELDS = ("created_at", "created_by_user_id", "created_by_api_key_id")


def upgrade():
    for table in TABLES:
        for field in FIELDS:
            op.create_index("ix_" + table + "_" + field, table, [field])


def downgrade():
    for table in TABLES:
        for field in FIELDS:
            op.drop_index("ix_" + table + "_" + field, table_name=table)
