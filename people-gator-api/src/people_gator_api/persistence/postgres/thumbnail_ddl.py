"""Database portrait invariants, including cascades outside repository methods.

Functions run with invoker privileges and use the application's search_path.
No function writes actor/timestamp metadata: repositories attribute the evidence
mutation that caused a repair in the same transaction.
"""

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
