"""PostgreSQL checks for atomic entity consolidation."""

import os
import uuid

import pytest
from pydantic import AnyUrl

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.persistence.postgres import entity_repository
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityMergeTargetPatch,
)
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceKeypointType,
)
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.faces import (
    BoundingBox,
    FaceCreateRequest,
    FaceEmbedding,
    FacePatchRequest,
    Keypoint,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionPatchRequest,
)
from people_gator_api.schemas.sources import ImageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.database_service import (
    create_postgres_schema,
    make_postgres_engine,
    make_postgres_session_factory,
)


@pytest.mark.skipif(
    not os.getenv("PEOPLE_GATOR_POSTGRES_TEST_URL"),
    reason="set PEOPLE_GATOR_POSTGRES_TEST_URL to run PostgreSQL integration tests",
)
@pytest.mark.asyncio
async def test_entity_merge_reassigns_annotations_and_rolls_back_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["PEOPLE_GATOR_POSTGRES_TEST_URL"]
    engine = make_postgres_engine(database_url)
    await create_postgres_schema(engine)
    sessions = make_postgres_session_factory(engine)
    marker = uuid.uuid4().hex

    try:
        async with sessions() as session:
            database = postgres_database(session)
            await database.face_models.register(
                FaceModelRegisterRequest(
                    model_stub=DEFAULT_FACE_EMBEDDING_MODEL,
                    embedding_dim=512,
                )
            )
            user = await database.users.get_or_create(
                UserCreateRequest(
                    display_name=f"Merge {marker}",
                    is_active=True,
                    external_subject=marker,
                    external_issuer="postgres-merge-test",
                )
            )
            source, _ = await database.sources.get_or_create_image(
                ImageCreateRequest(url=AnyUrl(f"https://example.test/{marker}.jpg"))
            )
            entities = await database.entities.create_batch(
                [
                    EntityCreateRequest(
                        entity_type=EntityType.person,
                        name=f"Source {marker}",
                        aliases=["Shared alias", "Source alias"],
                    ),
                    EntityCreateRequest(
                        entity_type=EntityType.person,
                        name=f"Target {marker}",
                        aliases=["Shared alias", "Target alias"],
                        description="Original description",
                        short_description="Original short description",
                    ),
                ],
                user,
            )
            source_id, target_id = [entity.entity_id for entity in entities]
            face = await database.faces.create(
                FaceCreateRequest(
                    bounding_box=BoundingBox(x=1, y=2, width=20, height=30),
                    keypoints=[
                        Keypoint(type=kind, x=float(i), y=float(i + 1))
                        for i, kind in enumerate(FaceKeypointType)
                    ],
                    confidence=0.9,
                    embeddings=[
                        FaceEmbedding(
                            model_identifier=DEFAULT_FACE_EMBEDDING_MODEL,
                            vector=[1.0] + [0.0] * 511,
                        )
                    ],
                    source_id=source.source_id,
                    entity_id=source_id,
                ),
                user,
            )
            mention = await database.text_mentions.create(
                TextMentionCreateRequest(
                    name=f"Source {marker}",
                    source_id=source.source_id,
                    entity_id=source_id,
                ),
                user,
            )

            async def fail_commit(*_args: object) -> None:
                raise RuntimeError("injected failure before commit")

            with monkeypatch.context() as patch:
                patch.setattr(entity_repository, "commit", fail_commit)
                with pytest.raises(RuntimeError, match="injected failure"):
                    await database.entities.merge(
                        target_id,
                        source_id,
                        target_patch=EntityMergeTargetPatch(
                            description="Replacement description",
                            short_description=None,
                        ),
                    )

            assert await database.entities.get(source_id) is not None
            unchanged_target = await database.entities.get(target_id)
            assert unchanged_target is not None
            assert set(unchanged_target.aliases or []) == {"Shared alias", "Target alias"}
            assert unchanged_target.description == "Original description"
            assert unchanged_target.short_description == "Original short description"
            stored_face = await database.faces.get(face.detection_id)
            stored_mention = await database.text_mentions.get(mention.mention_id)
            assert stored_face is not None and stored_face.entity_id == source_id
            assert stored_mention is not None and stored_mention.entity_id == source_id

            result = await database.entities.merge(
                target_id,
                source_id,
                target_patch=EntityMergeTargetPatch(
                    description="Replacement description",
                    short_description=None,
                ),
            )
            assert result is not None
            assert result.faces_reassigned == 1
            assert result.text_mentions_reassigned == 1
            assert result.merged_entity.entity_id == target_id
            assert result.merged_entity.name == f"Target {marker}"
            assert result.merged_entity.description == "Replacement description"
            assert result.merged_entity.short_description is None
            assert set(result.merged_entity.aliases or []) == {
                "Shared alias", "Source alias", "Target alias"
            }
            assert await database.entities.get(source_id) is None
            stored_face = await database.faces.get(face.detection_id)
            stored_mention = await database.text_mentions.get(mention.mention_id)
            assert stored_face is not None and stored_face.entity_id == target_id
            assert stored_mention is not None and stored_mention.entity_id == target_id

            assert await database.entities.merge(target_id, source_id) is None
            with pytest.raises(ValueError, match="must differ"):
                await database.entities.merge(target_id, target_id)

            more_sources = await database.entities.create_batch(
                [
                    EntityCreateRequest(
                        entity_type=EntityType.person,
                        name=f"More A {marker}",
                        aliases=["Source alias", "Batch shared", "Batch A"],
                    ),
                    EntityCreateRequest(
                        entity_type=EntityType.person,
                        name=f"More B {marker}",
                        aliases=["Batch shared", "Batch B"],
                    ),
                ],
                user,
            )
            more_source_ids = [entity.entity_id for entity in more_sources]
            await database.faces.patch(
                face.detection_id,
                FacePatchRequest(entity_id=more_source_ids[0]),
                user,
            )
            await database.text_mentions.patch(
                mention.mention_id,
                TextMentionPatchRequest(entity_id=more_source_ids[1]),
                user,
            )

            assert await database.entities.merge_batch(
                target_id,
                [more_source_ids[0], uuid.uuid4()],
                target_patch=EntityMergeTargetPatch(description="Must not persist"),
            ) is None
            unchanged_target = await database.entities.get(target_id)
            assert unchanged_target is not None
            assert set(unchanged_target.aliases or []) == {
                "Shared alias", "Source alias", "Target alias"
            }
            assert unchanged_target.description == "Replacement description"
            stored_face = await database.faces.get(face.detection_id)
            stored_mention = await database.text_mentions.get(mention.mention_id)
            assert stored_face is not None and stored_face.entity_id == more_source_ids[0]
            assert stored_mention is not None and stored_mention.entity_id == more_source_ids[1]

            batch_result = await database.entities.merge_batch(
                target_id,
                more_source_ids,
                target_patch=EntityMergeTargetPatch(
                    short_description="Batch short description"
                ),
            )
            assert batch_result is not None
            assert batch_result.source_entity_ids == more_source_ids
            assert batch_result.faces_reassigned == 1
            assert batch_result.text_mentions_reassigned == 1
            assert batch_result.merged_entity.entity_id == target_id
            assert batch_result.merged_entity.description == "Replacement description"
            assert batch_result.merged_entity.short_description == "Batch short description"
            assert set(batch_result.merged_entity.aliases or []) == {
                "Shared alias", "Source alias", "Target alias",
                "Batch shared", "Batch A", "Batch B",
            }
            assert len(batch_result.merged_entity.aliases or []) == 6
            for merged_source_id in more_source_ids:
                assert await database.entities.get(merged_source_id) is None
            stored_face = await database.faces.get(face.detection_id)
            stored_mention = await database.text_mentions.get(mention.mention_id)
            assert stored_face is not None and stored_face.entity_id == target_id
            assert stored_mention is not None and stored_mention.entity_id == target_id

            with pytest.raises(ValueError, match="unique"):
                await database.entities.merge_batch(target_id, [target_id, target_id])

            final_source = await database.entities.create(
                EntityCreateRequest(entity_type=EntityType.person, name=f"Final {marker}"),
                user,
            )
            cleared = await database.entities.merge(
                target_id,
                final_source.entity_id,
                target_patch=EntityMergeTargetPatch(description=None),
            )
            assert cleared is not None
            assert cleared.merged_entity.description is None
            assert cleared.merged_entity.short_description == "Batch short description"

            await database.sources.delete(source.source_id)
            await database.entities.delete(target_id)
            await database.users.delete(user.user_id)
    finally:
        await engine.dispose()
