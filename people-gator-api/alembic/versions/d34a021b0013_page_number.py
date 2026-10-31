"""Nullable page sequence annotation; preserve legacy unknowns."""
from alembic import op
import sqlalchemy as sa

revision = "d34a021b0013"
down_revision = "d34a021b0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pg_demo_pages", sa.Column("page_number", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_pg_demo_pages_page_number", "pg_demo_pages", "page_number > 0")
    op.create_index("ix_pg_demo_pages_number", "pg_demo_pages", ["library", "document_id", "page_number", "id"])


def downgrade():
    op.drop_index("ix_pg_demo_pages_number", table_name="pg_demo_pages")
    op.drop_constraint("ck_pg_demo_pages_page_number", "pg_demo_pages", type_="check")
    op.drop_column("pg_demo_pages", "page_number")
