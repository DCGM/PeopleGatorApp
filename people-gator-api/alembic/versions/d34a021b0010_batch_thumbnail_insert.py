"""Repair portraits once per assigned owner during bulk face insertion.

Revision ID: d34a021b0010
Revises: d34a021b0009
"""
from alembic import op

revision = "d34a021b0010"
down_revision = "d34a021b0009"
branch_labels = None
depends_on = None

# Frozen definitions: retained previews upgrade without rewriting any selection.
INSERT_DDL = (
    """CREATE OR REPLACE FUNCTION pg_demo_thumbnail_face_insert() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        PERFORM pg_demo_repair_thumbnail(io.entity_id)
        FROM (SELECT DISTINCT io.entity_id
              FROM inserted_faces f JOIN pg_demo_image_occurrences io ON io.id = f.id
              JOIN pg_demo_entities e ON e.id = io.entity_id
              WHERE e.kind = 'person' AND e.thumbnail_face_id IS NULL
              ORDER BY io.entity_id) io;
        RETURN NULL;
    END $$""",
    """CREATE OR REPLACE TRIGGER thumbnail_face_insert AFTER INSERT ON pg_demo_faces
    REFERENCING NEW TABLE AS inserted_faces
    FOR EACH STATEMENT EXECUTE FUNCTION pg_demo_thumbnail_face_insert()""",
)

PREVIOUS_INSERT_DDL = (
    """CREATE OR REPLACE FUNCTION pg_demo_thumbnail_face_insert() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        PERFORM pg_demo_repair_thumbnail(io.entity_id)
        FROM pg_demo_image_occurrences io WHERE io.id = NEW.id;
        RETURN NEW;
    END $$""",
    """CREATE OR REPLACE TRIGGER thumbnail_face_insert AFTER INSERT ON pg_demo_faces
    FOR EACH ROW EXECUTE FUNCTION pg_demo_thumbnail_face_insert()""",
)


def upgrade():
    op.execute("DROP TRIGGER thumbnail_face_insert ON pg_demo_faces")
    for statement in INSERT_DDL:
        op.execute(statement)


def downgrade():
    op.execute("DROP TRIGGER thumbnail_face_insert ON pg_demo_faces")
    for statement in PREVIOUS_INSERT_DDL:
        op.execute(statement)
