"""Stored sequence metadata, registered totals and shared numeric pagination."""
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.sources import (
    PageCreateRequest, PagePatchRequest, PageListFilter, PageListRequest,
    DocumentCreateRequest, DocumentListRequest, DocumentListFilter,
)
from people_gator_api.schemas.search import SearchPagesRequest, QueryBase
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext


@pytest.mark.parametrize('value', [0, -1, 1.5, True, False, '3', 2147483648])
def test_page_number_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        PageCreateRequest(library='x', document_id=uuid.uuid4(), page_id=uuid.uuid4(), page_number=value)
    with pytest.raises(ValidationError):
        PagePatchRequest(page_number=value)


@pytest.mark.asyncio
async def test_numbering_roundtrip_order_totals_and_edits(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(UserCreateRequest(display_name='Number editor', is_active=True, external_subject='editor', external_issuer='issue53'))
        actor = AuthContext(user_id=user.user_id, api_key_id=None, authentication_method='bearer', scopes=set())
        doc = uuid.uuid4()
        parent, _ = await db.sources.get_or_create_document(DocumentCreateRequest(library='numbers', document_id=doc))
        records = []
        for i, number in enumerate([10, None, 2, 1, 2, None]):
            spec = PageCreateRequest(library='numbers', document_id=doc, page_id=uuid.UUID(int=100-i), page_number=number)
            page, _ = await db.sources.get_or_create_page(spec)
            assert page.page_number == number
            assert page.registered_page_count == i+1
            repeated, _ = await db.sources.get_or_create_page(spec.model_copy(update={'page_number': 999}))
            assert repeated.page_number == number  # imports never overwrite
            records.append(page)
        # Same document UUID in another library, plus another document in this library.
        for library, document in [('elsewhere', doc), ('numbers', uuid.uuid4())]:
            page, _ = await db.sources.get_or_create_page(PageCreateRequest(library=library, document_id=document, page_id=uuid.uuid4(), page_number=1))
            assert page.registered_page_count == 1
        scope = PageListFilter(library=['numbers'], document_id=[doc])
        async def collect(direction):
            found, cursor = [], None
            while True:
                batch = await db.sources.list_pages(PageListRequest(filter_=scope, sort='page_number', sort_direction=direction, limit=2, cursor=cursor, return_total_count=True))
                assert batch.total_count == 6
                assert all(p.registered_page_count == 6 for p in batch.items)
                found += batch.items
                cursor = batch.cursor
                if cursor is None:
                    return found
        for direction in ['asc', 'desc']:
            ordered = await collect(direction)
            known = sorted([p for p in records if p.page_number is not None], key=lambda p: ((-p.page_number if direction == 'desc' else p.page_number), p.source_id))
            unknown = sorted([p for p in records if p.page_number is None], key=lambda p: p.source_id)
            assert [p.source_id for p in ordered] == [p.source_id for p in known+unknown]
        # Global numeric order compares local positions, retaining membership.
        global_scope = PageListFilter(library=['numbers'])
        global_order = await db.sources.list_pages(PageListRequest(filter_=global_scope, sort='page_number', limit=100))
        assert [p.page_number for p in global_order.items] == [1, 1, 2, 2, 10, None, None]
        assert sorted(p.registered_page_count for p in global_order.items) == [1, 6, 6, 6, 6, 6, 6]
        # Counts are one grouped query per response, regardless of page size.
        from sqlalchemy import event
        statements = []
        def capture(*args):
            statements.append(args[2])
        event.listen(migrated_postgres.sync_engine, 'before_cursor_execute', capture)
        try:
            await db.sources.list_pages(PageListRequest(filter_=scope, limit=1))
            small_query_count = len(statements)
            statements.clear()
            await db.sources.list_pages(PageListRequest(filter_=scope, limit=6))
            assert len(statements) == small_query_count
        finally:
            event.remove(migrated_postgres.sync_engine, 'before_cursor_execute', capture)
        batch = await db.sources.list_pages(PageListRequest(filter_=scope, sort='page_number', limit=2))
        with pytest.raises(ValueError):
            await db.sources.list_pages(PageListRequest(filter_=scope, sort='page_number', sort_direction='desc', cursor=batch.cursor))
        first = records[0]
        untouched = await db.sources.patch_page(first.source_id, PagePatchRequest(), context=actor)
        assert untouched.page_number == 10 and untouched.last_touched_at is None
        updated = await db.sources.patch_page(first.source_id, PagePatchRequest(page_number=3), context=actor)
        assert updated.page_number == 3
        assert updated.last_touched_by_user_id == user.user_id and updated.last_touched_at
        assert updated.registered_page_count == 6
        parent_after = await db.sources.get_document(parent.source_id)
        assert parent_after.last_touched_by_user_id == user.user_id
        cleared = await db.sources.patch_page(first.source_id, PagePatchRequest(page_number=None), context=actor)
        assert cleared.page_number is None
        assert (await db.sources.get_or_create_page(PageCreateRequest(library=first.library, document_id=doc, page_id=first.page_id, page_number=10)))[0].page_number is None
        assert await db.sources.patch_page(parent.source_id, PagePatchRequest(page_number=1), context=actor) is None
        filtered = await db.sources.list_pages(PageListRequest(filter_=PageListFilter(source_id=[records[2].source_id]), limit=1))
        assert filtered.items[0].registered_page_count == 6
        documents = await db.sources.list_documents(DocumentListRequest(limit=1, filter_=DocumentListFilter(source_id=[parent.source_id])))
        assert documents.items[0].first_page_number == 1
        # Direct library search gives a bounded scored set; numeric override pages it.
        search = await db.sources.search_pages(SearchPagesRequest(query=QueryBase(text=['numbers']), filter_=scope, sort='page_number', sort_direction='desc', limit=100))
        assert [p.page_number for p in search.items] == [2, 2, 1, None, None, None]
        assert all(p.registered_page_count == 6 for p in search.items)
        assert (await db.sources.get_page(first.source_id)).page_number is None


@pytest.mark.asyncio
async def test_migration_retains_legacy_identity_and_unknowns(migrated_postgres):
    from alembic import command
    from people_gator_api.persistence.postgres.schema import migration_config, validate_schema
    async with migrated_postgres.begin() as connection:
        def migrate(sync, target, downgrade=False):
            config = migration_config()
            config.attributes['connection'] = sync
            (command.downgrade if downgrade else command.upgrade)(config, target)
        await connection.run_sync(lambda sync: migrate(sync, 'd34a021b0012', True))
        source, document, page = (uuid.uuid4() for _ in range(3))
        url = f'https://www.digitalniknihovna.cz/legacy/view/uuid:{document}?page=uuid:{page}'
        await connection.execute(text('INSERT INTO pg_demo_sources (id, source_type, url) VALUES (:id, :kind, :url)'), {'id': source, 'kind': 'page', 'url': url})
        await connection.execute(text('INSERT INTO pg_demo_pages (id, library, document_id, page_id) VALUES (:id, :library, :document, :page)'), {'id': source, 'library': 'legacy', 'document': document, 'page': page})
        await connection.run_sync(lambda sync: migrate(sync, 'head'))
        row = (await connection.execute(text('SELECT p.id, p.page_id, p.page_number, s.url FROM pg_demo_pages p JOIN pg_demo_sources s ON s.id=p.id'))).one()
        assert tuple(row) == (source, page, None, url)
        await connection.run_sync(validate_schema)


@pytest.mark.asyncio
async def test_numbering_api_validation_scopes_and_key_attribution(migrated_postgres, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from people_gator_api.routes.v1 import router
    from people_gator_api.services import database_service, auth_service
    from people_gator_api.schemas.api_keys import APIKeyCreateRequest
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(UserCreateRequest(display_name='Importer', is_active=True, external_subject='key-editor', external_issuer='issue53'))
        key = await db.api_keys.get_or_create(APIKeyCreateRequest(identifier='number-importer', display_name='Number importer', user_id=user.user_id))
        actor = AuthContext(user_id=user.user_id, api_key_id=key.api_key_id, authentication_method='api_key', scopes={'people-gator:browse', 'people-gator:data:ingest'})
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[database_service.get_database] = lambda: db
        async def authenticated_token(token):
            return actor
        monkeypatch.setattr(auth_service, 'authenticate_bearer', authenticated_token)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test', headers={'Authorization': 'Bearer synthetic'}) as client:
            spec = {'library': 'http', 'document_id': str(uuid.uuid4()), 'page_id': str(uuid.uuid4()), 'page_number': 10}
            # Repository creation avoids depending on ingest scope aliases here.
            page, _ = await db.sources.get_or_create_page(PageCreateRequest(**spec))
            url = f'/api/v1/pages/{page.source_id}'
            assert (await client.patch(url, json={'page_number': 2})).status_code == 403
            actor.scopes.add('people-gator:annotate')
            for invalid in [True, 0, -1, 2.5, '2']:
                assert (await client.patch(url, json={'page_number': invalid})).status_code == 422
            response = await client.patch(url, json={'page_number': 2})
            assert response.status_code == 200, response.text
            assert response.json()['page_number'] == 2
            assert response.json()['last_touched_by_api_key_id'] == str(key.api_key_id)
            assert response.json()['last_touched_by_user_id'] == str(user.user_id)
            assert response.json()['registered_page_count'] == 1
            lookup = await client.get('/api/v1/pages/lookup', params={k: v for k, v in spec.items() if k != 'page_number'})
            assert lookup.status_code == 200 and lookup.json()['page_number'] == 2
            assert (await client.patch(url, json={})).json()['page_number'] == 2
            assert (await client.patch(url, json={'page_number': None})).json()['page_number'] is None
