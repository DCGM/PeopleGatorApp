"""Skip portrait repairs for owners that are already resolved.

Row-level reassignment repairs both owners for every moved face. Bulk unlinks
and merges therefore rewrote an owner without faces once per moved face.

Revision ID: d34a021b0011
Revises: d34a021b0010
"""
from alembic import op

revision = "d34a021b0011"
down_revision = "d34a021b0010"
branch_labels = None
depends_on = None

# Frozen definitions; never import the current application's DDL.
REPAIR_DDL = """CREATE OR REPLACE FUNCTION pg_demo_repair_thumbnail(owner_id uuid) RETURNS void
    LANGUAGE plpgsql AS $$ BEGIN
        UPDATE pg_demo_entities e SET thumbnail_face_id = NULL, thumbnail_mode = 'automatic'
        WHERE e.id = owner_id AND e.kind = 'person' AND CASE
            -- Skip owners already resolved: row-level reassignment calls this
            -- once per moved face, and an empty owner stays without a portrait.
            WHEN e.thumbnail_face_id IS NULL THEN EXISTS (
                SELECT 1 FROM pg_demo_faces f JOIN pg_demo_image_occurrences io ON io.id = f.id
                WHERE io.entity_id = e.id
            )
            ELSE NOT EXISTS (
                SELECT 1 FROM pg_demo_faces f JOIN pg_demo_image_occurrences io ON io.id = f.id
                WHERE f.id = e.thumbnail_face_id AND io.entity_id = e.id
            )
        END;
    END $$"""

PREVIOUS_REPAIR_DDL = """CREATE OR REPLACE FUNCTION pg_demo_repair_thumbnail(owner_id uuid) RETURNS void
    LANGUAGE plpgsql AS $$ BEGIN
        UPDATE pg_demo_entities e SET thumbnail_face_id = NULL, thumbnail_mode = 'automatic'
        WHERE e.id = owner_id AND e.kind = 'person' AND (
            e.thumbnail_face_id IS NULL OR NOT EXISTS (
                SELECT 1 FROM pg_demo_faces f JOIN pg_demo_image_occurrences io ON io.id = f.id
                WHERE f.id = e.thumbnail_face_id AND io.entity_id = e.id
            )
        );
    END $$"""


def upgrade():
    op.execute(REPAIR_DDL)


def downgrade():
    op.execute(PREVIOUS_REPAIR_DDL)
