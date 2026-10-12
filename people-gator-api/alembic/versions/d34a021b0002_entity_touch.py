"""Track entity processing without fabricating historical metadata.

Revision ID: d34a021b0002
Revises: d34a021b0001
"""

from alembic import op
import sqlalchemy as sa

revision = "d34a021b0002"
down_revision = "d34a021b0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pg_demo_entities",
        sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True),
    )
    for field, table in (
        ("last_touched_by_user_id", "pg_demo_users"),
        ("last_touched_by_api_key_id", "pg_demo_api_keys"),
    ):
        op.add_column("pg_demo_entities", sa.Column(field, sa.UUID(), nullable=True))
        op.create_foreign_key(
            "fk_pg_demo_entities_" + field,
            "pg_demo_entities",
            table,
            [field],
            ["id"],
            ondelete="RESTRICT",
        )
    for field in (
        "last_touched_at",
        "last_touched_by_user_id",
        "last_touched_by_api_key_id",
    ):
        op.create_index("ix_pg_demo_entities_" + field, "pg_demo_entities", [field])


def downgrade() -> None:
    for field in (
        "last_touched_by_api_key_id",
        "last_touched_by_user_id",
        "last_touched_at",
    ):
        op.drop_index("ix_pg_demo_entities_" + field, table_name="pg_demo_entities")
        if field != "last_touched_at":
            op.drop_constraint(
                "fk_pg_demo_entities_" + field, "pg_demo_entities", type_="foreignkey"
            )
        op.drop_column("pg_demo_entities", field)
