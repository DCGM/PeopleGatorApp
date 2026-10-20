"""Record provenance and annotation edits without inventing historical events.

Revision ID: d34a021b0007
Revises: d34a021b0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d34a021b0007"
down_revision = "d34a021b0006"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("pg_demo_entities", "pg_demo_image_occurrences", "pg_demo_text_mentions"):
        op.add_column(table, sa.Column("provenance", JSONB(), nullable=True))
        op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        for field, target in (("created_by_user_id", "pg_demo_users"), ("created_by_api_key_id", "pg_demo_api_keys")):
            op.add_column(table, sa.Column(field, sa.UUID(), nullable=True))
            op.create_foreign_key("fk_" + table + "_" + field, table, target, [field], ["id"], ondelete="RESTRICT")
        if table == "pg_demo_entities":
            continue
        op.add_column(table, sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True))
        for field, target in (("last_touched_by_user_id", "pg_demo_users"), ("last_touched_by_api_key_id", "pg_demo_api_keys")):
            op.add_column(table, sa.Column(field, sa.UUID(), nullable=True))
            op.create_foreign_key("fk_" + table + "_" + field, table, target, [field], ["id"], ondelete="RESTRICT")
        for field in ("last_touched_at", "last_touched_by_user_id", "last_touched_by_api_key_id"):
            op.create_index("ix_" + table + "_" + field, table, [field])
        op.create_check_constraint("ck_" + table + "_touch", table,
            "(last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)")


def downgrade():
    for table in ("pg_demo_text_mentions", "pg_demo_image_occurrences", "pg_demo_entities"):
        if table != "pg_demo_entities":
            op.drop_constraint("ck_" + table + "_touch", table, type_="check")
            for field in ("last_touched_by_api_key_id", "last_touched_by_user_id", "last_touched_at"):
                op.drop_index("ix_" + table + "_" + field, table_name=table)
                op.drop_column(table, field)
        for field in ("created_by_api_key_id", "created_by_user_id", "created_at", "provenance"):
            op.drop_column(table, field)
