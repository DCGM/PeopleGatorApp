"""Migration d34a021b0015 drops zero face embeddings and refuses new ones (#134)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def _migrate(sync, target, downgrade=False):
    from alembic import command
    from people_gator_api.persistence.postgres.schema import migration_config

    config = migration_config()
    config.attributes["connection"] = sync
    (command.downgrade if downgrade else command.upgrade)(config, target)


@pytest.mark.asyncio
async def test_migration_drops_only_zero_embeddings_and_keeps_faces(migrated_postgres):
    from people_gator_api.persistence.postgres.schema import validate_schema

    async with migrated_postgres.begin() as connection:
        await connection.run_sync(lambda sync: _migrate(sync, "d34a021b0014", True))
        user, page, zero, useful = (uuid.uuid4() for _ in range(4))
        await connection.execute(text(
            "INSERT INTO pg_demo_users (id, display_name, is_active, external_subject, external_issuer)"
            " VALUES (:id, 'Migration', true, 'migration', 'test')"), {"id": user})
        await connection.execute(text(
            "INSERT INTO pg_demo_sources (id, source_type, url) VALUES (:id, 'page', :url)"),
            {"id": page, "url": f"https://example.test/{page}"})
        await connection.execute(text(
            "INSERT INTO pg_demo_pages (id, library, document_id, page_id)"
            " VALUES (:id, 'synthetic', :document, :page)"),
            {"id": page, "document": uuid.uuid4(), "page": uuid.uuid4()})
        await connection.execute(text(
            "INSERT INTO pg_demo_face_models (stub, embedding_dim) VALUES ('synthetic', 2)"))
        for face, vector in ((zero, "[0,0]"), (useful, "[1,0]")):
            await connection.execute(text(
                "INSERT INTO pg_demo_image_occurrences (id, source_id, occurrence_type, roi)"
                " VALUES (:id, :source, 'face', CAST(:roi AS jsonb))"),
                {"id": face, "source": page, "roi": '{"x": 1, "y": 1, "width": 5, "height": 5}'})
            await connection.execute(text(
                "INSERT INTO pg_demo_faces (id, user_id, confidence, keypoints, keypoint_types)"
                " VALUES (:id, :user, 0.9, '{{1,1},{2,1},{1,2},{1,3},{2,3}}',"
                " '{left_eye,right_eye,nose,right_mouth_corner,left_mouth_corner}')"),
                {"id": face, "user": user})
            await connection.execute(text(
                "INSERT INTO pg_demo_face_embeddings (face_id, model_id, embedding)"
                " VALUES (:id, 'synthetic', CAST(:vector AS vector))"), {"id": face, "vector": vector})

        await connection.run_sync(lambda sync: _migrate(sync, "head"))
        await connection.run_sync(validate_schema)
        kept = (await connection.execute(text("SELECT face_id FROM pg_demo_face_embeddings"))).scalars().all()
        faces = (await connection.execute(text("SELECT id FROM pg_demo_faces"))).scalars().all()
        assert kept == [useful]
        assert set(faces) == {zero, useful}

        with pytest.raises(IntegrityError, match="ck_pg_demo_face_embedding_nonzero"):
            async with connection.begin_nested():
                await connection.execute(text(
                    "INSERT INTO pg_demo_face_embeddings (face_id, model_id, embedding)"
                    " VALUES (:id, 'synthetic', '[0,0]')"), {"id": zero})

        # Downgrade only removes the constraint; dropped vectors are not restored.
        await connection.run_sync(lambda sync: _migrate(sync, "d34a021b0014", True))
        await connection.execute(text(
            "INSERT INTO pg_demo_face_embeddings (face_id, model_id, embedding)"
            " VALUES (:id, 'synthetic', '[0,0]')"), {"id": zero})
