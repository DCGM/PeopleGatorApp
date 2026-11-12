"""Store page verification with attribution; documents derive theirs (#149).

Existing pages start as not verified.

Revision ID: d34a021b0016
Revises: d34a021b0015
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d34a021b0016"
down_revision = "d34a021b0015"
branch_labels = None
depends_on = None

ENUM = postgresql.ENUM("not_verified", "verified", name="pg_demo_verification_state", create_type=False)
TABLE = "pg_demo_pages"


def upgrade():
    ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(TABLE, sa.Column("verification_state", ENUM, nullable=False, server_default="not_verified"))
    op.add_column(TABLE, sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("verified_by_user_id", sa.UUID(), nullable=True))
    op.add_column(TABLE, sa.Column("verified_by_api_key_id", sa.UUID(), nullable=True))
    op.create_foreign_key("pg_demo_pages_verified_by_user_id_fkey", TABLE, "pg_demo_users", ["verified_by_user_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("pg_demo_pages_verified_by_api_key_id_fkey", TABLE, "pg_demo_api_keys", ["verified_by_api_key_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint(
        "ck_pg_demo_pages_verification", TABLE,
        "(verification_state = 'verified' AND verified_at IS NOT NULL AND verified_by_user_id IS NOT NULL) OR (verification_state = 'not_verified' AND verified_at IS NULL AND verified_by_user_id IS NULL AND verified_by_api_key_id IS NULL)",
    )


def downgrade():
    op.drop_constraint("ck_pg_demo_pages_verification", TABLE, type_="check")
    op.drop_constraint("pg_demo_pages_verified_by_api_key_id_fkey", TABLE, type_="foreignkey")
    op.drop_constraint("pg_demo_pages_verified_by_user_id_fkey", TABLE, type_="foreignkey")
    for column in ("verified_by_api_key_id", "verified_by_user_id", "verified_at", "verification_state"):
        op.drop_column(TABLE, column)
    ENUM.drop(op.get_bind(), checkfirst=True)
