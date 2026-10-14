"""Index normalized document names and archive identities.

Revision ID: d34a021b0006
Revises: d34a021b0005
"""
from alembic import op
import sqlalchemy as sa

revision = "d34a021b0006"
down_revision = "d34a021b0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pg_demo_documents", sa.Column("name_normalized", sa.Text(), sa.Computed("lower(demo_unaccent(name))", persisted=True)))
    op.create_index("ix_pg_demo_documents_name_trgm", "pg_demo_documents", ["name_normalized"], postgresql_using="gin", postgresql_ops={"name_normalized": "gin_trgm_ops"})
    op.create_index("ix_pg_demo_documents_library", "pg_demo_documents", ["library"])
    op.create_index("ix_pg_demo_documents_document_id", "pg_demo_documents", ["document_id"])


def downgrade() -> None:
    for name in ("document_id", "library", "name_trgm"):
        op.drop_index("ix_pg_demo_documents_" + name, table_name="pg_demo_documents")
    op.drop_column("pg_demo_documents", "name_normalized")
