"""Store person names and life dates in a Person subtype table (#123).

Entities stay the shared identity base. Every existing person entity receives
a subtype row with all structured fields unknown; no entity data changes.
Rows of other historical kinds get no subtype row and keep loading as entities.
Downgrade drops the subtype table and its values.

Revision ID: d34a021b0019
Revises: d34a021b0018
"""
from alembic import op
import sqlalchemy as sa

revision = "d34a021b0019"
down_revision = "d34a021b0018"
branch_labels = None
depends_on = None

TABLE = "pg_demo_persons"


def upgrade():
    # ORM bootstrap may already have created the table, possibly with rows for
    # people it created; schema validation after migration checks its shape.
    op.create_table(
        TABLE,
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=True),
        sa.Column("middle_names", sa.Text(), nullable=True),
        sa.Column("surname", sa.Text(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("death_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["entity_id"], ["pg_demo_entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entity_id"),
        sa.CheckConstraint(
            "death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date",
            name="ck_pg_demo_persons_life_dates",
        ),
        if_not_exists=True,
    )
    op.create_index("ix_pg_demo_persons_birth_date", TABLE, ["birth_date"], if_not_exists=True)
    op.create_index("ix_pg_demo_persons_death_date", TABLE, ["death_date"], if_not_exists=True)
    op.execute(
        "INSERT INTO pg_demo_persons (entity_id) "
        "SELECT id FROM pg_demo_entities WHERE kind = 'person' "
        "ON CONFLICT (entity_id) DO NOTHING"
    )


def downgrade():
    op.drop_index("ix_pg_demo_persons_death_date", table_name=TABLE)
    op.drop_index("ix_pg_demo_persons_birth_date", table_name=TABLE)
    op.drop_table(TABLE)
