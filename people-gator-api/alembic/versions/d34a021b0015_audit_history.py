"""Independent current versions and durable predecessor snapshots.

Revision ID: d34a021b0015
Revises: d34a021b0014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "d34a021b0015"
down_revision = "d34a021b0014"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("entities", "sources", "image_occurrences", "text_mentions"):
        op.add_column(
            "pg_demo_" + table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
    op.create_table(
        "pg_demo_audit_changes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_api_key_id", UUID(as_uuid=True)),
    )
    for field in ("changed_at", "actor_user_id"):
        op.create_index(
            "ix_pg_demo_audit_changes_" + field, "pg_demo_audit_changes", [field]
        )
    op.create_table(
        "pg_demo_object_history",
        sa.Column("object_type", sa.String(16), primary_key=True),
        sa.Column("object_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column(
            "change_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pg_demo_audit_changes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True)),
        sa.Column("source_id", UUID(as_uuid=True)),
        sa.Column("state", JSONB(), nullable=False),
    )
    for field in ("change_id", "entity_id", "source_id"):
        op.create_index(
            "ix_pg_demo_object_history_" + field, "pg_demo_object_history", [field]
        )


def downgrade():
    op.drop_table("pg_demo_object_history")
    op.drop_table("pg_demo_audit_changes")
    for table in ("entities", "sources", "image_occurrences", "text_mentions"):
        op.drop_column("pg_demo_" + table, "version")
