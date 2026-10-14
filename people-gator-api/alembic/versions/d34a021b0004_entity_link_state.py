"""Track the current entity link and its verification on both annotation kinds."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d34a021b0004"
down_revision = "d34a021b0003"
branch_labels = None
depends_on = None

TABLES = ("text_mentions", "image_occurrences")
ENUM = postgresql.ENUM(
    "automatic",
    "manual",
    "verified",
    name="pg_demo_entity_link_state",
    create_type=False,
)


def upgrade() -> None:
    connection = op.get_bind()
    # create_all may have installed the type before discovering that the old
    # annotation tables already exist. Reuse only a matching type in this
    # schema; a visible type from another search_path schema must not win.
    existing = connection.execute(sa.text("""
        SELECT t.typtype::text, array_agg(e.enumlabel::text ORDER BY e.enumsortorder)
        FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        LEFT JOIN pg_enum e ON e.enumtypid = t.oid
        WHERE n.nspname = current_schema() AND t.typname = 'pg_demo_entity_link_state'
        GROUP BY t.oid, t.typtype
    """)).first()
    if existing is None:
        ENUM.create(connection, checkfirst=False)
    elif existing[0] != "e" or list(existing[1]) != list(ENUM.enums):
        raise ValueError("Existing pg_demo_entity_link_state type does not match the migration")
    op.execute("""CREATE OR REPLACE FUNCTION pg_demo_clear_entity_link() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
    IF NEW.entity_id IS NULL THEN
        NEW.entity_link_state := NULL;
        NEW.entity_link_verified_by_user_id := NULL;
        NEW.entity_link_verified_at := NULL;
    END IF;
    RETURN NEW;
    END $$""")
    for table in TABLES:
        name = "pg_demo_" + table
        op.add_column(name, sa.Column("entity_link_state", ENUM, nullable=True))
        op.add_column(
            name, sa.Column("entity_link_verified_by_user_id", sa.UUID(), nullable=True)
        )
        op.add_column(
            name,
            sa.Column(
                "entity_link_verified_at", sa.DateTime(timezone=True), nullable=True
            ),
        )
        op.create_foreign_key(
            f"fk_pg_demo_{table}_verifier",
            name,
            "pg_demo_users",
            ["entity_link_verified_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        # Historical origin is unknown; automatic is a compatibility convention.
        op.execute(
            f"UPDATE {name} SET entity_link_state = 'automatic' WHERE entity_id IS NOT NULL"
        )
        op.create_check_constraint(
            f"ck_pg_demo_{table}_link",
            name,
            "(entity_id IS NULL) = (entity_link_state IS NULL)",
        )
        op.create_check_constraint(
            f"ck_pg_demo_{table}_verification",
            name,
            "(entity_link_state IS NOT DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NOT NULL AND entity_link_verified_at IS NOT NULL) OR (entity_link_state IS DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NULL AND entity_link_verified_at IS NULL)",
        )
        for field in ("source", "entity"):
            op.create_index(
                f"ix_pg_demo_{table}_{field}_state",
                name,
                [field + "_id", "entity_link_state"],
            )
        op.execute(
            f"CREATE OR REPLACE TRIGGER clear_entity_link BEFORE UPDATE OF entity_id ON {name} FOR EACH ROW EXECUTE FUNCTION pg_demo_clear_entity_link()"
        )


def downgrade() -> None:
    for table in reversed(TABLES):
        name = "pg_demo_" + table
        op.execute(f"DROP TRIGGER clear_entity_link ON {name}")
        for field in ("source", "entity"):
            op.drop_index(f"ix_pg_demo_{table}_{field}_state", table_name=name)
        op.drop_constraint(f"ck_pg_demo_{table}_verification", name, type_="check")
        op.drop_constraint(f"ck_pg_demo_{table}_link", name, type_="check")
        op.drop_constraint(f"fk_pg_demo_{table}_verifier", name, type_="foreignkey")
        for column in (
            "entity_link_verified_at",
            "entity_link_verified_by_user_id",
            "entity_link_state",
        ):
            op.drop_column(name, column)
    op.execute("DROP FUNCTION pg_demo_clear_entity_link()")
    ENUM.drop(op.get_bind())
