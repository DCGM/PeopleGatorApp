"""Drop the page document index covered by the page number index.

Revision ID: d34a021b0014
Revises: d34a021b0013
"""
from alembic import op

revision = "d34a021b0014"
down_revision = "d34a021b0013"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_pg_demo_page_document", table_name="pg_demo_pages")


def downgrade():
    op.create_index("ix_pg_demo_page_document", "pg_demo_pages", ["library", "document_id"], unique=False)
