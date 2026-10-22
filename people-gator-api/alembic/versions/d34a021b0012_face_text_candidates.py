"""Index face identifiers for bounded discovery text retrieval.

Revision ID: d34a021b0012
Revises: d34a021b0011
"""
from alembic import op

revision = "d34a021b0012"
down_revision = "d34a021b0011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_pg_demo_faces_identifier_trgm", "pg_demo_faces", ["identifier"],
        postgresql_using="gin", postgresql_ops={"identifier": "gin_trgm_ops"},
    )


def downgrade():
    op.drop_index("ix_pg_demo_faces_identifier_trgm", table_name="pg_demo_faces")
