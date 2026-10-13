"""Add optional document names without changing archive identities."""

from alembic import op
import sqlalchemy as sa

revision = "d34a021b0003"
down_revision = "d34a021b0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pg_demo_documents", sa.Column("name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("pg_demo_documents", "name")
