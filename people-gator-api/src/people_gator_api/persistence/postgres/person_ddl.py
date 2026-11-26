"""Every person entity has its pg_demo_persons subtype row (#123).

The ORM writes both rows for people it creates. Writers that insert only the
entity row (an older backend serving while a release migrates, or raw SQL)
get the subtype row from a deferred trigger at commit, so no person becomes
unreadable. The function skips an entity deleted later in the same
transaction and rows the ORM already wrote.
"""

PERSON_FUNCTION = """CREATE OR REPLACE FUNCTION pg_demo_ensure_person() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        INSERT INTO pg_demo_persons (entity_id)
        SELECT e.id FROM pg_demo_entities e WHERE e.id = NEW.id AND e.kind = 'person'
        ON CONFLICT (entity_id) DO NOTHING;
        RETURN NULL;
    END $$"""

PERSON_TRIGGER = "ensure_person"

PERSON_DDL = (
    PERSON_FUNCTION,
    # Constraint triggers have no CREATE OR REPLACE; recreate idempotently.
    f"DROP TRIGGER IF EXISTS {PERSON_TRIGGER} ON pg_demo_entities",
    f"""CREATE CONSTRAINT TRIGGER {PERSON_TRIGGER} AFTER INSERT ON pg_demo_entities
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
    EXECUTE FUNCTION pg_demo_ensure_person()""",
)

# Fills subtype rows for people stored before the table or trigger existed.
PERSON_BACKFILL = """INSERT INTO pg_demo_persons (entity_id)
    SELECT id FROM pg_demo_entities WHERE kind = 'person'
    ON CONFLICT (entity_id) DO NOTHING"""
