"""Record source creation without inventing history for registered sources."""
from alembic import op
import sqlalchemy as sa

revision = "d34a021b0015"
down_revision = "d34a021b0014"
branch_labels = None
depends_on = None


def upgrade():
    table = "pg_demo_sources"
    op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    for field, target in (
        ("created_by_user_id", "pg_demo_users"),
        ("created_by_api_key_id", "pg_demo_api_keys"),
    ):
        op.add_column(table, sa.Column(field, sa.UUID(), nullable=True))
        op.create_foreign_key("fk_" + table + "_" + field, table, target, [field], ["id"], ondelete="RESTRICT")


def downgrade():
    for field in ("created_by_api_key_id", "created_by_user_id", "created_at"):
        op.drop_column("pg_demo_sources", field)
