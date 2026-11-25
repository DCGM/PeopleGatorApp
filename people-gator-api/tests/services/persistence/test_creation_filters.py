"""Creation filters apply to each returned record, regardless of source or editor."""
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.common import CreationFilter, GenericActor
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.schemas.entities import EntityCreateRequest, EntityPatchRequest, EntityListRequest, EntityListFilter
from people_gator_api.schemas.faces import FaceCreateRequest, FacePatchRequest, FaceListRequest, FaceListFilter
from people_gator_api.schemas.mentions import TextMentionCreateRequest, TextMentionPatchRequest, TextMentionListRequest, TextMentionListFilter, TextMentionGroupListRequest
from people_gator_api.schemas.sources import (
    DocumentCreateRequest, DocumentListRequest, DocumentListFilter,
    PageCreateRequest, PageListRequest, PageListFilter,
    ImageCreateRequest, ImageListRequest, ImageListFilter, SourceListRequest, SourceListFilter,
)
from people_gator_api.schemas.search import (
    QueryBase, SearchEntitiesRequest, SearchFacesRequest, SearchDocumentsRequest, SearchPagesRequest,
)
from people_gator_api.services.auth_service import AuthContext, get_auth_context
from people_gator_api.services.database_service import get_database
from people_gator_api.routes.v1 import router
from people_gator_api.seeding.fixtures import Face as FixtureFace
from people_gator_api.seeding.media import face_box, face_keypoints


@pytest.mark.parametrize('fields', [
    {'created_from': '2026-11-02T00:00:00Z', 'created_to': '2026-11-01T00:00:00Z'},
    {'created_from': '2026-11-01T00:00:00'},
    {'created_to': 'invalid'},
    {'created_by_user_id': []},
    {'created_by_api_key_id': ['invalid']},
])
def test_creation_filter_rejects_invalid_bounds_and_creators(fields):
    with pytest.raises(ValidationError):
        CreationFilter(**fields)


PATHS = ['/api/v1/entities', '/api/v1/search-entities', '/api/v1/faces', '/api/v1/search-faces',
         '/api/v1/text-mentions', '/api/v1/text-mention-groups', '/api/v1/documents',
         '/api/v1/search-documents', '/api/v1/pages', '/api/v1/search-pages', '/api/v1/images', '/api/v1/sources']


@pytest.mark.parametrize('path', PATHS)
def test_creation_filters_are_advertised_and_invalid_ranges_rejected(path):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: SimpleNamespace()
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(user_id=uuid.uuid4())
    names = {p['name'] for p in app.openapi()['paths'][path]['get']['parameters']}
    assert {'filter.created_from', 'filter.created_to', 'filter.created_by_user_id', 'filter.created_by_api_key_id'} <= names
    response = TestClient(app).get(path, params={
        'filter.created_from': '2026-11-02T00:00:00Z', 'filter.created_to': '2026-11-01T00:00:00Z', 'query.text': 'Creation',
    })
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_own_creation_filters_for_every_resource_and_search(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        users = [await db.users.get_or_create(UserCreateRequest(display_name=f'Creator {i}', external_subject=str(i), external_issuer='creation-filters', is_active=True)) for i in range(2)]
        a = GenericActor(user_id=users[0].user_id)
        key = await db.api_keys.get_or_create(APIKeyCreateRequest(identifier='creation-filter-key', display_name='Creation key', user_id=users[1].user_id))
        b = AuthContext(user_id=users[1].user_id, api_key_id=key.api_key_id, authentication_method='api_key', scopes=set())
        documents, pages, images, entities, faces, mentions = [], [], [], [], [], []
        for i, actor in enumerate([a, b]):
            doc, _ = await db.sources.get_or_create_document(DocumentCreateRequest(library='creation-filters', document_id=uuid.uuid4(), name=f'Creation {i}'), context=actor)
            documents.append(doc)
            entities.append(await db.entities.create(EntityCreateRequest(entity_type='person', name=f'Creation person {i}'), actor))
            image, _ = await db.sources.get_or_create_image(ImageCreateRequest(url=f'https://example.invalid/creation-{i}.png'), context=actor)
            images.append(image)
        # Page/annotation creators differ from their containing document's creator.
        for i, actor in enumerate([a, b]):
            parent = documents[1-i]
            page, _ = await db.sources.get_or_create_page(PageCreateRequest(library=parent.library, document_id=parent.document_id, page_id=uuid.uuid4()), context=actor)
            pages.append(page)
            fixture = FixtureFace(f'creation-{i}', None, 0, 0)
            faces.append(await db.faces.create(FaceCreateRequest(source_id=page.source_id, entity_id=entities[i].entity_id, confidence=0.9, bounding_box=face_box(fixture), keypoints=face_keypoints(fixture)), actor))
            mentions.append(await db.text_mentions.create(TextMentionCreateRequest(source_id=page.source_id, entity_id=entities[i].entity_id, name='Creation mention'), actor))
        legacy, _ = await db.sources.restore_legacy_source(DocumentCreateRequest(library='creation-filters', document_id=uuid.uuid4(), name='Creation legacy').to_generic(), context=a)
        await db.entities.patch(entities[0].entity_id, EntityPatchRequest(short_description='Later editor'), b)
        await db.faces.patch(faces[0].detection_id, FacePatchRequest(entity_id=entities[1].entity_id), b)
        await db.text_mentions.patch(mentions[0].mention_id, TextMentionPatchRequest(entity_id=entities[1].entity_id), b)
        resources = [
            (db.sources.list_documents, DocumentListRequest, DocumentListFilter, 'source_id', documents[0]),
            (db.sources.list_pages, PageListRequest, PageListFilter, 'source_id', pages[0]),
            (db.sources.list_images, ImageListRequest, ImageListFilter, 'source_id', images[0]),
            (db.entities.list, EntityListRequest, EntityListFilter, 'entity_id', entities[0]),
            (db.faces.list, FaceListRequest, FaceListFilter, 'detection_id', faces[0]),
            (db.text_mentions.list, TextMentionListRequest, TextMentionListFilter, 'mention_id', mentions[0]),
        ]
        for listing, request, filter_type, identity, original in resources:
            result = await listing(request(limit=100, filter_=filter_type(created_by_user_id=[a.user_id])))
            assert [getattr(item, identity) for item in result.items] == [getattr(original, identity)]
            own_time = original.created_at
            exact = await listing(request(limit=100, filter_=filter_type(created_from=own_time, created_to=own_time)))
            assert [getattr(item, identity) for item in exact.items] == [getattr(original, identity)]
            assert not (await listing(request(limit=100, filter_=filter_type(created_from=own_time + timedelta(microseconds=1), created_to=own_time + timedelta(microseconds=1))))).items
            imported = await listing(request(limit=100, filter_=filter_type(created_by_user_id=[b.user_id], created_by_api_key_id=[key.api_key_id])))
            assert len(imported.items) == 1 and imported.items[0].created_by_user_id == b.user_id
            mismatch = await listing(request(limit=100, filter_=filter_type(created_by_user_id=[a.user_id], created_by_api_key_id=[key.api_key_id])))
            assert not mismatch.items
            combined = await listing(request(limit=100, filter_=filter_type(created_by_user_id=[a.user_id, b.user_id])))
            assert len(combined.items) == 2
        all_sources = await db.sources.list_sources(SourceListRequest(limit=100))
        assert legacy.source_id in {s.source_id for s in all_sources.items}
        known = await db.sources.list_sources(SourceListRequest(limit=100, filter_=SourceListFilter(created_by_user_id=[a.user_id,b.user_id])))
        assert legacy.source_id not in {s.source_id for s in known.items}
        first = await db.sources.list_sources(SourceListRequest(limit=1, filter_=SourceListFilter(created_by_user_id=[a.user_id])))
        with pytest.raises(ValueError):
            await db.sources.list_sources(SourceListRequest(limit=1, cursor=first.cursor, filter_=SourceListFilter(created_by_user_id=[b.user_id])))
        for search, request, filter_type in [
            (db.sources.search_documents, SearchDocumentsRequest, DocumentListFilter),
            (db.sources.search_pages, SearchPagesRequest, PageListFilter),
            (db.entities.search, SearchEntitiesRequest, EntityListFilter),
            (db.faces.search, SearchFacesRequest, FaceListFilter),
        ]:
            result = await search(request(limit=100, query=QueryBase(text=['Creation']), filter_=filter_type(created_by_user_id=[a.user_id])))
            assert result.items and all(item.created_by_user_id == a.user_id for item in result.items)
        grouped = await db.text_mentions.list_groups(TextMentionGroupListRequest(limit=100, filter_=TextMentionListFilter(created_by_user_id=[a.user_id])))
        assert sum(group.occurrence_count for group in grouped.items) == 1


@pytest.mark.asyncio
async def test_legacy_adapter_rejects_creation_filters_instead_of_ignoring_them():
    from people_gator_api.persistence.weaviate import (
        WeaviateEntityRepository, WeaviateFaceRepository, WeaviateTextMentionRepository, WeaviateSourceRepository,
    )
    from people_gator_api.schemas.sources import GenericSourceListRequest, GenericSourceListFilter
    for repository, request, filter_type in [
        (WeaviateEntityRepository, EntityListRequest, EntityListFilter),
        (WeaviateFaceRepository, FaceListRequest, FaceListFilter),
        (WeaviateTextMentionRepository, TextMentionListRequest, TextMentionListFilter),
        (WeaviateSourceRepository, GenericSourceListRequest, GenericSourceListFilter),
    ]:
        with pytest.raises(NotImplementedError, match='PostgreSQL'):
            await repository(Mock()).list(request(limit=10, filter_=filter_type(created_by_user_id=[uuid.uuid4()])))
