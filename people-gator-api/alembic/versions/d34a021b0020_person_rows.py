"""Keep a pg_demo_persons row for every person entity (#123).

A writer that inserts only the entity row, such as the previous backend while a
release migrates, would leave a person without its subtype row and unreadable.
A deferred constraint trigger adds the row at commit, and this revision
backfills any person stored without one.

Revision ID: d34a021b0020
Revises: d34a021b0019
"""
from alembic import op

revision = "d34a021b0020"
down_revision = "d34a021b0019"
branch_labels = None
depends_on = None

# Frozen copies: later application changes must not rewrite this revision.
FUNCTION = """CREATE OR REPLACE FUNCTION pg_demo_ensure_person() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        INSERT INTO pg_demo_persons (entity_id)
        SELECT e.id FROM pg_demo_entities e WHERE e.id = NEW.id AND e.kind = 'person'
        ON CONFLICT (entity_id) DO NOTHING;
        RETURN NULL;
    END $$"""


def upgrade():
    op.execute(FUNCTION)
    op.execute("DROP TRIGGER IF EXISTS ensure_person ON pg_demo_entities")
    op.execute(
        """CREATE CONSTRAINT TRIGGER ensure_person AFTER INSERT ON pg_demo_entities
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION pg_demo_ensure_person()"""
    )
    op.execute(
        """INSERT INTO pg_demo_persons (entity_id)
    SELECT id FROM pg_demo_entities WHERE kind = 'person'
    ON CONFLICT (entity_id) DO NOTHING"""
    )


def downgrade():
    op.execute("DROP TRIGGER ensure_person ON pg_demo_entities")
    op.execute("DROP FUNCTION pg_demo_ensure_person()")
