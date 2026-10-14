"""Opt-in end-to-end checks for the PostgreSQL contract implementation."""

import os
import uuid

import pytest
from pydantic import AnyUrl
from sqlalchemy.engine import make_url

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListFilter,
    EntityListRequest,
    EntityPatchRequest,
)
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceKeypointType,
)
from people_gator_api.schemas.faces import (
    BoundingBox,
    FaceCreateRequest,
    FaceEmbedding,
    FaceListFilter,
    FaceListRequest,
    Keypoint,
)
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListFilter,
    TextMentionListRequest,
    TextMentionPatchRequest,
)
from people_gator_api.schemas.search import (
    QueryBase,
    SearchDocumentsRequest,
    SearchEntitiesRequest,
    SearchFacesRequest,
    SearchPagesRequest,
)
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentListFilter,
    ImageCreateRequest,
    PageCreateRequest,
    PageListFilter,
    PageListRequest,
)
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListFilter,
    UserListRequest,
    UserPatchRequest,
)
from people_gator_api.services.database_service import (
    create_postgres_schema,
    make_postgres_engine,
    make_postgres_session_factory,
)


POSTGRES_TEST_URL = os.getenv("PEOPLE_GATOR_POSTGRES_TEST_URL")


@pytest.mark.skipif(
    POSTGRES_TEST_URL is None,
    reason="set PEOPLE_GATOR_POSTGRES_TEST_URL to run PostgreSQL integration tests",
)
@pytest.mark.asyncio
async def test_postgres_contract_round_trip() -> None:
    assert POSTGRES_TEST_URL is not None
    engine = make_postgres_engine(make_url(POSTGRES_TEST_URL))
    await create_postgres_schema(engine)
    sessions = make_postgres_session_factory(engine)
    marker = uuid.uuid4().hex

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
                display_name=f"Integration {marker}",
                is_active=True,
                external_subject=marker,
                external_issuer="postgres-integration",
            )
        )
        created_entity_ids: list[uuid.UUID] = []
        created_source_ids: list[uuid.UUID] = []

        try:
            document_id = uuid.uuid4()
            page_id = uuid.uuid4()
            document, _ = await database.sources.get_or_create_document(
                DocumentCreateRequest(library="integration", document_id=document_id)
            )
            page, _ = await database.sources.get_or_create_page(
                PageCreateRequest(
                    library="integration",
                    document_id=document_id,
                    page_id=page_id,
                )
            )
            image, _ = await database.sources.get_or_create_image(
                ImageCreateRequest(url=AnyUrl(f"https://example.test/{marker}.jpg"))
            )
            created_source_ids.extend(
                [document.source_id, page.source_id, image.source_id]
            )

            entities = await database.entities.create_batch(
                [
                    EntityCreateRequest(
                        entity_type=EntityType.person,
                        name=f"Ada {marker}",
                        aliases=[f"Countess {marker}"],
                    ),
                    EntityCreateRequest(
                        entity_type=EntityType.person,
                        name=f"Grace {marker}",
                    ),
                ],
                user,
            )
            created_entity_ids.extend(item.entity_id for item in entities)

            first_page = await database.entities.list(
                EntityListRequest(
                    filter_=EntityListFilter(entity_id=created_entity_ids),
                    limit=1,
                    return_total_count=True,
                )
            )
            assert first_page.total_count == 2
            assert len(first_page.items) == 1
            assert first_page.cursor is not None

            second_page = await database.entities.list(
                EntityListRequest(
                    filter_=EntityListFilter(entity_id=created_entity_ids),
                    limit=1,
                    return_total_count=True,
                    cursor=first_page.cursor,
                )
            )
            assert len(second_page.items) == 1
            assert second_page.cursor is None
            with pytest.raises(ValueError, match="different query"):
                await database.entities.list(
                    EntityListRequest(
                        filter_=EntityListFilter(entity_id=[entities[0].entity_id]),
                        limit=1,
                        return_total_count=True,
                        cursor=first_page.cursor,
                    )
                )

            patched = await database.entities.patch(
                entities[0].entity_id,
                EntityPatchRequest(description="mathematician"),
                user,
            )
            assert patched is not None
            assert patched.description == "mathematician"

            face = await database.faces.create(
                FaceCreateRequest(
                    identifier=marker,
                    bounding_box=BoundingBox(x=1, y=2, width=20, height=30),
                    keypoints=[
                        Keypoint(type=keypoint_type, x=float(i), y=float(i + 1))
                        for i, keypoint_type in enumerate(FaceKeypointType)
                    ],
                    confidence=0.9,
                    embeddings=[
                        FaceEmbedding(
                            model_identifier=DEFAULT_FACE_EMBEDDING_MODEL,
                            vector=[1.0] + [0.0] * 511,
                        )
                    ],
                    source_id=image.source_id,
                    entity_id=entities[0].entity_id,
                ),
                user,
            )
            assert face.embeddings == [DEFAULT_FACE_EMBEDDING_MODEL]
            other_face = await database.faces.create(
                FaceCreateRequest(
                    identifier=f"other-{marker}",
                    bounding_box=BoundingBox(x=2, y=3, width=20, height=30),
                    keypoints=[
                        Keypoint(type=keypoint_type, x=float(i + 1), y=float(i + 2))
                        for i, keypoint_type in enumerate(FaceKeypointType)
                    ],
                    confidence=0.8,
                    embeddings=[
                        FaceEmbedding(
                            model_identifier=DEFAULT_FACE_EMBEDDING_MODEL,
                            vector=[0.9, 0.1] + [0.0] * 510,
                        )
                    ],
                    source_id=image.source_id,
                    entity_id=entities[1].entity_id,
                ),
                user,
            )
            assert other_face.embeddings == [DEFAULT_FACE_EMBEDDING_MODEL]
            entities_for_image = await database.entities.list(
                EntityListRequest(
                    filter_=EntityListFilter(source_id=[image.source_id]),
                    limit=10,
                    return_total_count=True,
                )
            )
            assert {item.entity_id for item in entities_for_image.items} == set(
                created_entity_ids
            )
            assert entities_for_image.total_count == 2
            listed_face = (
                await database.faces.list(
                    FaceListRequest(
                        filter_=FaceListFilter(entity_id=[entities[0].entity_id]),
                        limit=10,
                    )
                )
            ).items[0]
            assert listed_face.detection_id == face.detection_id
            assert listed_face.embeddings == [DEFAULT_FACE_EMBEDDING_MODEL]

            mention = await database.text_mentions.create(
                TextMentionCreateRequest(
                    name=f"Ada {marker}",
                    context="integration",
                    entity_id=entities[0].entity_id,
                    source_id=page.source_id,
                ),
                user,
            )
            annotated_page = await database.sources.list_pages(
                PageListRequest(
                    filter_=PageListFilter(
                        source_id=[page.source_id],
                        has_mentions=True,
                        has_faces=False,
                        has_entities=True,
                    ),
                    limit=10,
                )
            )
            assert [item.source_id for item in annotated_page.items] == [page.source_id]
            linked_entities_for_page = await database.entities.list(
                EntityListRequest(
                    filter_=EntityListFilter(source_id=[page.source_id]),
                    limit=10,
                )
            )
            assert [item.entity_id for item in linked_entities_for_page.items] == [
                entities[0].entity_id
            ]
            mention = await database.text_mentions.patch(
                mention.mention_id,
                TextMentionPatchRequest(entity_id=None),
                user,
            )
            assert mention is not None
            assert mention.entity_id is None
            page_without_assigned_entities = await database.sources.list_pages(
                PageListRequest(
                    filter_=PageListFilter(
                        source_id=[page.source_id],
                        has_mentions=True,
                        has_entities=False,
                    ),
                    limit=10,
                )
            )
            assert [
                item.source_id for item in page_without_assigned_entities.items
            ] == [page.source_id]
            entities_for_page = await database.entities.list(
                EntityListRequest(
                    filter_=EntityListFilter(source_id=[page.source_id]),
                    limit=10,
                    return_total_count=True,
                )
            )
            assert entities_for_page.items == []
            assert entities_for_page.total_count == 0
            assert (
                len(
                    (
                        await database.text_mentions.list(
                            TextMentionListRequest(
                                filter_=TextMentionListFilter(
                                    source_id=[page.source_id]
                                ),
                                limit=10,
                            )
                        )
                    ).items
                )
                == 1
            )

            search = await database.entities.search(
                SearchEntitiesRequest(
                    query=QueryBase(text=[f"Ada {marker}"]),
                    filter_=EntityListFilter(entity_id=created_entity_ids),
                    limit=10,
                    return_total_count=True,
                )
            )
            assert search.total_count
            assert search.items[0].entity_id == entities[0].entity_id

            face_search = await database.faces.search(
                SearchFacesRequest(
                    query=QueryBase(face_id=[face.detection_id]),
                    filter_=FaceListFilter(detection_id=[other_face.detection_id]),
                    limit=10,
                )
            )
            assert face_search.items[0].detection_id == other_face.detection_id
            assert face_search.items[0].face_score is not None
            assert face_search.items[0].embeddings == [DEFAULT_FACE_EMBEDDING_MODEL]

            entity_face_search = await database.entities.search(
                SearchEntitiesRequest(
                    query=QueryBase(face_id=[face.detection_id]),
                    filter_=EntityListFilter(entity_id=[entities[1].entity_id]),
                    limit=10,
                )
            )
            assert entity_face_search.items[0].entity_id == entities[1].entity_id

            page_search = await database.sources.search_pages(
                SearchPagesRequest(
                    query=QueryBase(text=["integration"]),
                    filter_=PageListFilter(source_id=[page.source_id]),
                    limit=10,
                )
            )
            assert page_search.items[0].source_id == page.source_id

            document_search = await database.sources.search_documents(
                SearchDocumentsRequest(
                    query=QueryBase(text=["integration"]),
                    filter_=DocumentListFilter(source_id=[document.source_id]),
                    limit=10,
                )
            )
            assert document_search.items[0].source_id == document.source_id

            changed_user = await database.users.patch(
                user.user_id,
                UserPatchRequest(display_name=f"Changed {marker}"),
            )
            assert changed_user is not None
            assert (
                await database.users.list(
                    UserListRequest(
                        filter_=UserListFilter(display_name=[f"Changed {marker}"]),
                        limit=10,
                    )
                )
            ).items[0].user_id == user.user_id
            with pytest.raises(ValueError, match="referenced"):
                await database.users.delete(user.user_id)

            assert await database.entities.delete(entities[0].entity_id)
            created_entity_ids.remove(entities[0].entity_id)
            unassigned_face = await database.faces.get(face.detection_id)
            assert unassigned_face is not None
            assert unassigned_face.entity_id is None

            assert await database.sources.delete(image.source_id, context=user)
            created_source_ids.remove(image.source_id)
            assert await database.faces.get(face.detection_id) is None
            assert await database.faces.get(other_face.detection_id) is None

            assert await database.sources.delete(page.source_id, context=user)
            created_source_ids.remove(page.source_id)
            assert await database.text_mentions.get(mention.mention_id) is None
        finally:
            await session.rollback()
            await database.sources.delete_batch(created_source_ids, context=user)
            await database.entities.delete_batch(created_entity_ids, context=user)
            await database.users.delete(user.user_id)

    await engine.dispose()
