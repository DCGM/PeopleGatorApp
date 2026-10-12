"""Register stable API-key identities without credentials.

Revision ID: d34a021b0001
Revises: c82e7f4a901d
"""

from alembic import op
import sqlalchemy as sa

revision = "d34a021b0001"
down_revision = "c82e7f4a901d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pg_demo_api_keys",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("identifier", sa.Text(), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("pg_demo_users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index("ix_pg_demo_api_keys_user_id", "pg_demo_api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_table("pg_demo_api_keys")
