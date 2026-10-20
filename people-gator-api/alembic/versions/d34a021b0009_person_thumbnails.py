"""Persist person portraits without changing historical evidence or edit metadata.

Revision ID: d34a021b0009
Revises: d34a021b0008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d34a021b0009"
down_revision = "d34a021b0008"
branch_labels = None
depends_on = None

# Frozen migration definitions; never import the current application's DDL.
THUMBNAIL_DDL = (
    """CREATE OR REPLACE FUNCTION pg_demo_select_thumbnail() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.thumbnail_face_id IS NULL THEN
            NEW.thumbnail_mode := 'automatic';
            IF NEW.kind = 'person' THEN
                SELECT f.id INTO NEW.thumbnail_face_id
                FROM pg_demo_faces f JOIN pg_demo_image_occurrences io ON io.id = f.id
                WHERE io.entity_id = NEW.id ORDER BY f.id LIMIT 1;
            END IF;
        END IF;
        IF NEW.thumbnail_face_id IS NOT NULL AND (
            NEW.kind IS DISTINCT FROM 'person' OR NOT EXISTS (
                SELECT 1 FROM pg_demo_faces f
                JOIN pg_demo_image_occurrences io ON io.id = f.id
                WHERE f.id = NEW.thumbnail_face_id AND io.entity_id = NEW.id
            )
        ) THEN
            RAISE EXCEPTION 'thumbnail must be a face linked to this person' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END $$""",
    """CREATE OR REPLACE TRIGGER select_thumbnail
    BEFORE INSERT OR UPDATE OF thumbnail_face_id, thumbnail_mode, kind ON pg_demo_entities
    FOR EACH ROW EXECUTE FUNCTION pg_demo_select_thumbnail()""",
    """CREATE OR REPLACE FUNCTION pg_demo_repair_thumbnail(owner_id uuid) RETURNS void
    LANGUAGE plpgsql AS $$ BEGIN
        UPDATE pg_demo_entities e SET thumbnail_face_id = NULL, thumbnail_mode = 'automatic'
        WHERE e.id = owner_id AND e.kind = 'person' AND (
            e.thumbnail_face_id IS NULL OR NOT EXISTS (
                SELECT 1 FROM pg_demo_faces f JOIN pg_demo_image_occurrences io ON io.id = f.id
                WHERE f.id = e.thumbnail_face_id AND io.entity_id = e.id
            )
        );
    END $$""",
    """CREATE OR REPLACE FUNCTION pg_demo_thumbnail_face_insert() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        PERFORM pg_demo_repair_thumbnail(io.entity_id)
        FROM pg_demo_image_occurrences io WHERE io.id = NEW.id;
        RETURN NEW;
    END $$""",
    """CREATE OR REPLACE TRIGGER thumbnail_face_insert AFTER INSERT ON pg_demo_faces
    FOR EACH ROW EXECUTE FUNCTION pg_demo_thumbnail_face_insert()""",
    """CREATE OR REPLACE FUNCTION pg_demo_thumbnail_reassignment() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.entity_id IS DISTINCT FROM NEW.entity_id THEN
            -- Existing graph mutations acquire the outer advisory lock before
            -- annotation/entity rows. Both owners are repaired in UUID order.
            PERFORM pg_demo_repair_thumbnail(owner_id)
            FROM (SELECT DISTINCT id AS owner_id FROM unnest(ARRAY[OLD.entity_id, NEW.entity_id]) AS id
                  WHERE id IS NOT NULL ORDER BY id) owners;
        END IF;
        RETURN NEW;
    END $$""",
    """CREATE OR REPLACE TRIGGER thumbnail_reassignment AFTER UPDATE OF entity_id ON pg_demo_image_occurrences
    FOR EACH ROW EXECUTE FUNCTION pg_demo_thumbnail_reassignment()""",
)


def upgrade():
    op.add_column("pg_demo_entities", sa.Column("thumbnail_face_id", UUID(as_uuid=True), nullable=True))
    op.add_column("pg_demo_entities", sa.Column("thumbnail_mode", sa.String(16), nullable=False, server_default="automatic"))
    op.create_foreign_key("fk_pg_demo_entities_thumbnail_face", "pg_demo_entities", "pg_demo_faces", ["thumbnail_face_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_pg_demo_entities_thumbnail_face_id", "pg_demo_entities", ["thumbnail_face_id"])
    op.create_check_constraint("ck_pg_demo_entities_thumbnail_mode", "pg_demo_entities", "thumbnail_mode IN ('automatic', 'manual')")
    op.create_check_constraint("ck_pg_demo_entities_manual_thumbnail", "pg_demo_entities", "thumbnail_mode <> 'manual' OR thumbnail_face_id IS NOT NULL")
    op.create_check_constraint("ck_pg_demo_entities_person_thumbnail", "pg_demo_entities", "kind = 'person' OR (thumbnail_face_id IS NULL AND thumbnail_mode = 'automatic')")
    for statement in THUMBNAIL_DDL:
        op.execute(statement)
    # Existing people gain an automatic choice. This intentionally does not
    # assign historical actors, advance touch times or modify review states.
    op.execute("UPDATE pg_demo_entities SET thumbnail_face_id = NULL WHERE kind = 'person'")


def downgrade():
    op.execute("DROP TRIGGER thumbnail_reassignment ON pg_demo_image_occurrences")
    op.execute("DROP TRIGGER thumbnail_face_insert ON pg_demo_faces")
    op.execute("DROP TRIGGER select_thumbnail ON pg_demo_entities")
    for function in ("pg_demo_thumbnail_reassignment()", "pg_demo_thumbnail_face_insert()", "pg_demo_repair_thumbnail(uuid)", "pg_demo_select_thumbnail()"):
        op.execute("DROP FUNCTION " + function)
    for name in ("ck_pg_demo_entities_thumbnail_mode", "ck_pg_demo_entities_manual_thumbnail", "ck_pg_demo_entities_person_thumbnail"):
        op.drop_constraint(name, "pg_demo_entities", type_="check")
    op.drop_index("ix_pg_demo_entities_thumbnail_face_id", table_name="pg_demo_entities")
    op.drop_constraint("fk_pg_demo_entities_thumbnail_face", "pg_demo_entities", type_="foreignkey")
    op.drop_column("pg_demo_entities", "thumbnail_face_id")
    op.drop_column("pg_demo_entities", "thumbnail_mode")
