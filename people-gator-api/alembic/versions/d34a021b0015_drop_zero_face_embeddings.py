"""Drop zero face embeddings and refuse new ones.

Cosine similarity is undefined for a zero vector, so such an embedding can
never be searched and only makes its face fail as a search reference (#134).
The faces stay; they simply have no vector for that model.

Revision ID: d34a021b0015
Revises: d34a021b0014
"""
from alembic import op

revision = "d34a021b0015"
down_revision = "d34a021b0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DELETE FROM pg_demo_face_embeddings WHERE vector_norm(embedding) = 0")
    op.create_check_constraint(
        "ck_pg_demo_face_embedding_nonzero", "pg_demo_face_embeddings", "vector_norm(embedding) > 0"
    )


def downgrade():
    # Deleted zero vectors are not restored: they carried no searchable data.
    op.drop_constraint("ck_pg_demo_face_embedding_nonzero", "pg_demo_face_embeddings", type_="check")
