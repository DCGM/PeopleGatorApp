"""Creation survives retries, mixed imports, edits and legacy schema upgrades."""
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from alembic import command
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.contracts import CreateResult
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.persistence.postgres.schema import migration_config, validate_schema
from people_gator_api.routes.v1 import router
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.sources import (
    DocumentCreateRequest, DocumentListRequest, PageCreateRequest, PageListRequest,
    PagePatchRequest, DocumentResponse, PageResponse, SourceResponseBase, ImageResponse,
    GenericSourceResponse, document_url, page_url,
)
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services import database_service, auth_service
from people_gator_api.services.auth_service import AuthContext


def creation(source):
    return {key: value for key, value in source.model_dump().items() if key.startswith('created_')}


async def actors(db):
    user = await db.users.get_or_create(UserCreateRequest(
        display_name='Creation reviewer', external_subject='creator',
        external_issuer='issue128', is_active=True,
    ))
    key = await db.api_keys.get_or_create(APIKeyCreateRequest(
        identifier='creation-importer', display_name='Creation importer', user_id=user.user_id,
    ))
    return (
        GenericActor(user_id=user.user_id),
        AuthContext(user_id=user.user_id, api_key_id=key.api_key_id,
                    authentication_method='api_key', scopes={'people-gator:ingest', 'people-gator:browse'}),
    )


@pytest.mark.asyncio
async def test_registration_creation_is_immutable_in_single_and_batch_imports(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        reviewer, importer = await actors(db)
        spec = DocumentCreateRequest(library='creation', document_id=uuid.uuid4(), name='Creation example')
        before = datetime.now(timezone.utc)
        doc, status = await db.sources.get_or_create_document(spec, context=reviewer)
        assert status == CreateResult.CREATED
        assert before <= doc.created_at <= datetime.now(timezone.utc)
        assert doc.created_by_user_id == reviewer.user_id
        assert doc.created_by_user_name == 'Creation reviewer'
        assert doc.created_by_api_key_id is None and doc.created_by_api_key_name is None
        assert doc.last_touched_at is None
        repeated, status = await db.sources.get_or_create_document(spec, context=importer)
        assert status == CreateResult.EXISTING and creation(repeated) == creation(doc)
        page_spec = PageCreateRequest(library=spec.library, document_id=spec.document_id, page_id=uuid.uuid4(), page_number=1)
        results = await db.sources.get_or_create_batch([
            spec.to_generic(), page_spec.to_generic(), page_spec.to_generic(),
        ], context=importer)
        assert [status for _, status in results] == [CreateResult.EXISTING, CreateResult.CREATED, CreateResult.EXISTING]
        assert creation(results[0][0]) == creation(doc)
        page = results[1][0]
        assert page.created_at and page.created_by_api_key_id == importer.api_key_id
        assert page.created_by_user_name == 'Creation reviewer'
        assert page.created_by_api_key_name == 'Creation importer'
        assert creation(page) == creation(results[2][0])
        assert creation((await db.sources.get_or_create_page_batch([page_spec], context=reviewer))[0][0]) == creation(page)
        assert creation((await db.sources.list_pages(PageListRequest(limit=10))).items[0]) == creation(page)
        assert creation((await db.sources.list_documents(DocumentListRequest(limit=10))).items[0]) == creation(doc)
        edited = await db.sources.patch_page(page.source_id, PagePatchRequest(page_number=2), context=reviewer)
        assert creation(edited) == creation(page)
        assert creation(await db.sources.get_document(doc.source_id)) == creation(doc)
        # Restoring a historical source must never erase known creation.
        restored, status = await db.sources.restore_legacy_source(spec.to_generic(), context=reviewer)
        assert status == CreateResult.EXISTING and creation(restored) == creation(doc)


@pytest.mark.asyncio
async def test_source_creation_alone_protects_creator_and_api_key_owner(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        reviewer, importer = await actors(db)
        document, _ = await db.sources.get_or_create_document(
            DocumentCreateRequest(library='creator-reference', document_id=uuid.uuid4()), context=importer,
        )
        assert document.last_touched_at is None
        other = await db.users.get_or_create(UserCreateRequest(
            display_name='Other user', external_subject='other', external_issuer='issue128', is_active=True,
        ))
        with pytest.raises(ValueError, match='referenced API key'):
            await db.api_keys.get_or_create(APIKeyCreateRequest(
                identifier='creation-importer', display_name='Creation importer', user_id=other.user_id,
            ))
        # A user without an API key is protected by source creation alone.
        await db.sources.get_or_create_document(
            DocumentCreateRequest(library='creator-reference', document_id=uuid.uuid4()), context=other,
        )
        with pytest.raises(ValueError, match='referenced'):
            await db.users.delete(other.user_id)
        assert await db.sources.get_document(document.source_id) is not None


@pytest.mark.asyncio
async def test_registration_routes_use_ingest_actor_for_documents_and_pages(migrated_postgres, monkeypatch):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        reviewer, importer = await actors(db)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[database_service.get_database] = lambda: db
        async def authenticate(token):
            return importer
        monkeypatch.setattr(auth_service, 'authenticate_bearer', authenticate)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'Authorization': 'Bearer synthetic'}) as client:
            for kind in ['documents', 'pages']:
                spec = {'library': 'http-creation', 'document_id': str(uuid.uuid4())}
                if kind == 'pages':
                    spec['page_id'] = str(uuid.uuid4())
                response = await client.post('/api/v1/' + kind, json=spec)
                assert response.status_code == 201, response.text
                saved = response.json()
                assert saved['created_at']
                assert saved['created_by_user_id'] == str(importer.user_id)
                assert saved['created_by_api_key_id'] == str(importer.api_key_id)
                assert saved['created_by_user_name'] == 'Creation reviewer'
                assert saved['created_by_api_key_name'] == 'Creation importer'
                # Existing registration is a conflict, and batch retry retains creation.
                assert (await client.post('/api/v1/' + kind, json=spec)).status_code == 409
                response = await client.post('/api/v1/' + kind + ':batch', json=[spec, spec])
                assert response.status_code == 201, response.text
                assert all(creation(GenericSourceResponse.model_validate(item)) == creation(GenericSourceResponse.model_validate(saved)) for item in response.json())
            importer.scopes.clear()
            assert (await client.post('/api/v1/documents', json={'library': 'denied', 'document_id': str(uuid.uuid4())})).status_code == 403


@pytest.mark.asyncio
async def test_populated_migration_preserves_unknown_creation(migrated_postgres):
    source_id, archive_id = uuid.uuid4(), uuid.uuid4()
    async with migrated_postgres.begin() as connection:
        def migrate(sync, target, downgrade=False):
            config = migration_config()
            config.attributes['connection'] = sync
            (command.downgrade if downgrade else command.upgrade)(config, target)
        await connection.run_sync(lambda sync: migrate(sync, 'd34a021b0015', True))
        await connection.execute(text('INSERT INTO pg_demo_sources (id, source_type, url) VALUES (:id, :kind, :url)'),
                                 {'id': source_id, 'kind': 'document', 'url': f'https://www.digitalniknihovna.cz/legacy/view/uuid:{archive_id}'})
        await connection.execute(text('INSERT INTO pg_demo_documents (id, library, document_id, name) VALUES (:id, :library, :archive, :name)'),
                                 {'id': source_id, 'library': 'legacy', 'archive': archive_id, 'name': 'Legacy document'})
        await connection.run_sync(lambda sync: migrate(sync, 'head'))
        await connection.run_sync(lambda sync: migrate(sync, 'head'))
        row = (await connection.execute(text('SELECT id, created_at, created_by_user_id, created_by_api_key_id FROM pg_demo_sources'))).one()
        assert tuple(row) == (source_id, None, None, None)
        await connection.run_sync(validate_schema)
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        reviewer, _ = await actors(db)
        original = await db.sources.get_document(source_id)
        assert all(value is None for value in creation(original).values())
        repeated, status = await db.sources.get_or_create_document(DocumentCreateRequest(library='legacy', document_id=archive_id), context=reviewer)
        assert status == CreateResult.EXISTING and creation(repeated) == creation(original)


@pytest.mark.parametrize('response', [DocumentResponse, PageResponse, SourceResponseBase, ImageResponse])
def test_unknown_creation_survives_typed_projection(response):
    kind = {DocumentResponse: 'document', PageResponse: 'page', ImageResponse: 'image'}.get(response, 'document')
    document_id, page_id = uuid.uuid4(), uuid.uuid4()
    fields = {} if kind == 'image' else {'library': 'legacy', 'document_id': document_id}
    if kind == 'page':
        fields['page_id'] = page_id
    url = ('https://example.invalid/source' if kind == 'image' else
           page_url('legacy', document_id, page_id) if kind == 'page' else document_url('legacy', document_id))
    generic = GenericSourceResponse(source_id=uuid.uuid4(), source_type=kind, url=url, **fields)
    assert all(value is None for value in creation(response.from_generic(generic)).values())
