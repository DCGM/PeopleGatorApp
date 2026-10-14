"""Record actual source annotation changes without inventing history.

Revision ID: d34a021b0005
Revises: d34a021b0004
"""
from alembic import op
import sqlalchemy as sa

revision = "d34a021b0005"
down_revision = "d34a021b0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pg_demo_sources", sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True))
    for field, table in (("last_touched_by_user_id", "pg_demo_users"), ("last_touched_by_api_key_id", "pg_demo_api_keys")):
        op.add_column("pg_demo_sources", sa.Column(field, sa.UUID(), nullable=True))
        op.create_foreign_key("fk_pg_demo_sources_" + field, "pg_demo_sources", table, [field], ["id"], ondelete="RESTRICT")
    for field in ("last_touched_at", "last_touched_by_user_id", "last_touched_by_api_key_id"):
        op.create_index("ix_pg_demo_sources_" + field, "pg_demo_sources", [field])
    op.create_check_constraint("ck_pg_demo_sources_touch", "pg_demo_sources", "(last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)")


def downgrade() -> None:
    op.drop_constraint("ck_pg_demo_sources_touch", "pg_demo_sources", type_="check")
    for field in ("last_touched_by_api_key_id", "last_touched_by_user_id", "last_touched_at"):
        op.drop_index("ix_pg_demo_sources_" + field, table_name="pg_demo_sources")
        if field != "last_touched_at":
            op.drop_constraint("fk_pg_demo_sources_" + field, "pg_demo_sources", type_="foreignkey")
        op.drop_column("pg_demo_sources", field)
