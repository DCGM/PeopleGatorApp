"""Index creation metadata used by creation date and creator filters.

These two creation revisions were first deployed to a retained preview as
d34a021b0016/0017, before page verification took d34a021b0016. Such a database
is stamped d34a021b0017 with the indexes present and page verification missing,
so this revision applies the skipped one and keeps existing indexes.

Revision ID: d34a021b0018
Revises: d34a021b0017
"""
from alembic import op
import sqlalchemy as sa

revision = "d34a021b0018"
down_revision = "d34a021b0017"
branch_labels = None
depends_on = None

TABLES = ("pg_demo_sources", "pg_demo_entities", "pg_demo_image_occurrences", "pg_demo_text_mentions")
FIELDS = ("created_at", "created_by_user_id", "created_by_api_key_id")


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("pg_demo_pages")}
    if "verification_state" not in columns:
        op.get_context().script.get_revision("d34a021b0016").module.upgrade()
    for table in TABLES:
        for field in FIELDS:
            op.create_index("ix_" + table + "_" + field, table, [field], if_not_exists=True)


def downgrade():
    for table in TABLES:
        for field in FIELDS:
            op.drop_index("ix_" + table + "_" + field, table_name=table)
