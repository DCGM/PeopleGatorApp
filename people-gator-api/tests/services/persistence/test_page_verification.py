"""Issue #149: page verification with attribution; documents derive theirs from pages."""
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.entities import EntityCreateRequest
from people_gator_api.schemas.enums import EntityLinkState, EntityType, VerificationState
from people_gator_api.schemas.mentions import TextMentionCreateRequest, TextMentionPatchRequest
from people_gator_api.schemas.sources import (
    DocumentCreateRequest, DocumentListFilter, DocumentListRequest, PageCreateRequest,
    PageListFilter, PageListRequest, PagePatchRequest,
)
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext

VERIFIED, NOT_VERIFIED = VerificationState.verified, VerificationState.not_verified


def test_patch_rejects_null_and_unknown_states():
    for value in (None, "partially_verified", True):
        with pytest.raises(ValidationError):
            PagePatchRequest(verification_state=value)
    assert "verification_state" not in PagePatchRequest().model_fields_set


async def _actor(db, name):
    user = await db.users.get_or_create(UserCreateRequest(
        display_name=name, is_active=True, external_subject=name, external_issuer="issue149",
    ))
    return AuthContext(user_id=user.user_id, api_key_id=None, authentication_method="bearer", scopes=set())


async def _document(db, library, document=None, pages=0):
    document = document or uuid.uuid4()
    parent, _ = await db.sources.get_or_create_document(DocumentCreateRequest(library=library, document_id=document))
    created = [
        (await db.sources.get_or_create_page(PageCreateRequest(
            library=library, document_id=document, page_id=uuid.uuid4(), page_number=number,
        )))[0]
        for number in range(1, pages + 1)
    ]
    return parent, created


async def _verify(db, page, actor, state=VERIFIED):
    return await db.sources.patch_page(page.source_id, PagePatchRequest(verification_state=state), context=actor)


@pytest.mark.asyncio
async def test_verify_remove_attribution_and_idempotency(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        actor, other = await _actor(db, "Verifier"), await _actor(db, "Other")
        parent, [page, _] = await _document(db, "verify", pages=2)
        assert page.verification_state == NOT_VERIFIED and page.verified_at is None

        verified = await _verify(db, page, actor)
        assert verified.verification_state == VERIFIED
        assert verified.verified_by_user_id == actor.user_id and verified.verified_by_api_key_id is None
        assert verified.verified_at is not None
        assert verified.last_touched_by_user_id == actor.user_id
        assert verified.page_number == 1  # other fields keep their values
        touched_document = await db.sources.get_document(parent.source_id)
        assert touched_document.last_touched_by_user_id == actor.user_id

        # Repeating the current state, or omitting it, records nothing new.
        for payload in (PagePatchRequest(verification_state=VERIFIED), PagePatchRequest(page_number=1), PagePatchRequest()):
            repeated = await db.sources.patch_page(page.source_id, payload, context=other)
            assert repeated.verified_by_user_id == actor.user_id
            assert repeated.verified_at == verified.verified_at
            assert repeated.last_touched_at == verified.last_touched_at

        # Number and state can change together; unchanged fields stay.
        both = await db.sources.patch_page(page.source_id, PagePatchRequest(page_number=5, verification_state=NOT_VERIFIED), context=other)
        assert (both.page_number, both.verification_state) == (5, NOT_VERIFIED)
        assert both.verified_at is None and both.verified_by_user_id is None and both.verified_by_api_key_id is None
        assert both.last_touched_by_user_id == other.user_id
        assert await db.sources.patch_page(uuid.uuid4(), PagePatchRequest(verification_state=VERIFIED), context=actor) is None


@pytest.mark.asyncio
async def test_documents_derive_state_counts_filters_and_sort(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        actor = await _actor(db, "Deriver")
        library, mirror = "derive-a", "derive-b"
        shared = uuid.uuid4()
        empty, _ = await _document(db, library)
        mixed, mixed_pages = await _document(db, library, pages=3)
        complete, complete_pages = await _document(db, library, pages=2)
        # Same archive document ID in another library: its pages never count here.
        same_id, same_id_pages = await _document(db, library, document=shared, pages=1)
        mirrored, mirrored_pages = await _document(db, mirror, document=shared, pages=2)
        await _verify(db, mixed_pages[0], actor)
        for page in (*complete_pages, *same_id_pages, mirrored_pages[0]):
            await _verify(db, page, actor)

        documents = {
            item.source_id: item for item in (await db.sources.list_documents(DocumentListRequest(
                limit=100, filter_=DocumentListFilter(library=[library, mirror]),
            ))).items
        }
        expected = {
            empty.source_id: (NOT_VERIFIED, 0, 0),
            mixed.source_id: (NOT_VERIFIED, 1, 3),
            complete.source_id: (VERIFIED, 2, 2),
            same_id.source_id: (VERIFIED, 1, 1),
            mirrored.source_id: (NOT_VERIFIED, 1, 2),
        }
        assert {
            key: (item.verification_state, item.verified_page_count, item.registered_page_count)
            for key, item in documents.items()
        } == expected
        detail = await db.sources.get_document(complete.source_id)
        assert (detail.verification_state, detail.verified_page_count) == (VERIFIED, 2)

        async def document_ids(**values):
            result = await db.sources.list_documents(DocumentListRequest(
                limit=100, return_total_count=True,
                filter_=DocumentListFilter(library=[library, mirror], **values),
            ))
            assert result.total_count == len(result.items)
            return {item.source_id for item in result.items}

        verified_documents = {complete.source_id, same_id.source_id}
        assert await document_ids(verification_state=[VERIFIED]) == verified_documents
        assert await document_ids(verification_state=[NOT_VERIFIED]) == set(expected) - verified_documents
        assert await document_ids(verification_state=[VERIFIED, NOT_VERIFIED]) == set(expected)
        # Composes with other filters: the shared archive ID matches both libraries.
        assert await document_ids(verification_state=[NOT_VERIFIED], document_id=[shared]) == {mirrored.source_id}
        assert await document_ids(verification_state=[VERIFIED], document_id=[shared]) == {same_id.source_id}

        async def page_ids(**values):
            result = await db.sources.list_pages(PageListRequest(
                limit=100, filter_=PageListFilter(library=[library], **values),
            ))
            return {item.source_id for item in result.items}

        verified_pages = {mixed_pages[0].source_id, *(p.source_id for p in complete_pages), same_id_pages[0].source_id}
        assert await page_ids(verification_state=[VERIFIED]) == verified_pages
        assert await page_ids(verification_state=[NOT_VERIFIED]) == {p.source_id for p in mixed_pages[1:]}
        assert await page_ids(verification_state=[VERIFIED], document_id=[shared]) == {same_id_pages[0].source_id}

        # Removing one page's verification makes its document not verified.
        await _verify(db, complete_pages[1], actor, NOT_VERIFIED)
        assert (await db.sources.get_document(complete.source_id)).verification_state == NOT_VERIFIED
        assert await document_ids(verification_state=[VERIFIED]) == {same_id.source_id}

        # Verified-page count sorts numerically with source UUID ties, across cursor batches.
        async def ordered(direction):
            found, cursor = [], None
            while True:
                batch = await db.sources.list_documents(DocumentListRequest(
                    limit=2, cursor=cursor, sort="verified_page_count", sort_direction=direction,
                    filter_=DocumentListFilter(library=[library, mirror]),
                ))
                found += batch.items
                cursor = batch.cursor
                if cursor is None:
                    return found
        for direction in ("asc", "desc"):
            items = await ordered(direction)
            sign = -1 if direction == "desc" else 1
            assert [item.source_id for item in items] == [
                item.source_id for item in sorted(items, key=lambda item: (sign * item.verified_page_count, item.source_id))
            ]
            assert len(items) == len(expected)
        default = await db.sources.list_documents(DocumentListRequest(
            limit=100, sort="verified_page_count", filter_=DocumentListFilter(library=[library, mirror]),
        ))
        # Counts default to descending.
        assert [item.source_id for item in default.items] == [item.source_id for item in await ordered("desc")]
        assert [item.verified_page_count for item in default.items] == [1, 1, 1, 1, 0]


@pytest.mark.asyncio
async def test_page_and_link_verification_stay_independent(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        actor = await _actor(db, "Independent")
        parent, [page] = await _document(db, "independent", pages=1)
        person = await db.entities.create(EntityCreateRequest(entity_type=EntityType.person, name="Page Person"), actor)
        mention = await db.text_mentions.create(TextMentionCreateRequest(
            name="Page Person", entity_id=person.entity_id, source_id=page.source_id,
        ), actor)
        assert mention.entity_link_state == EntityLinkState.automatic

        verified = await _verify(db, page, actor)
        assert verified.entity_link_stats.mentions.automatic == 1
        assert verified.entity_link_stats.mentions.verified == 0
        unchanged = await db.text_mentions.get(mention.mention_id)
        assert unchanged.entity_link_state == EntityLinkState.automatic
        assert unchanged.entity_link_verified_at is None

        await db.text_mentions.patch(mention.mention_id, TextMentionPatchRequest(entity_link_state=EntityLinkState.verified), actor)
        await db.text_mentions.patch(mention.mention_id, TextMentionPatchRequest(entity_link_state=EntityLinkState.manual), actor)
        after_links = await db.sources.get_page(page.source_id)
        assert after_links.verification_state == VERIFIED
        assert after_links.verified_at == verified.verified_at
        assert (await db.sources.get_document(parent.source_id)).verification_state == VERIFIED


@pytest.mark.asyncio
async def test_migration_defaults_existing_pages_and_downgrades(migrated_postgres):
    from alembic import command
    from people_gator_api.persistence.postgres.schema import migration_config, validate_schema
    async with migrated_postgres.begin() as connection:
        def migrate(sync, target, downgrade=False):
            config = migration_config()
            config.attributes["connection"] = sync
            (command.downgrade if downgrade else command.upgrade)(config, target)
        await connection.run_sync(lambda sync: migrate(sync, "d34a021b0015", True))
        assert await connection.scalar(text("SELECT to_regtype('pg_demo_verification_state')")) is None
        source, document, page = (uuid.uuid4() for _ in range(3))
        url = f"https://www.digitalniknihovna.cz/legacy/view/uuid:{document}?page=uuid:{page}"
        await connection.execute(text("INSERT INTO pg_demo_sources (id, source_type, url) VALUES (:id, 'page', :url)"), {"id": source, "url": url})
        await connection.execute(text("INSERT INTO pg_demo_pages (id, library, document_id, page_id) VALUES (:id, 'legacy', :document, :page)"), {"id": source, "document": document, "page": page})
        await connection.run_sync(lambda sync: migrate(sync, "head"))
        row = (await connection.execute(text(
            "SELECT verification_state::text, verified_at, verified_by_user_id, verified_by_api_key_id FROM pg_demo_pages WHERE id = :id"
        ), {"id": source})).one()
        assert tuple(row) == ("not_verified", None, None, None)
        # The constraint refuses a verified page without its verifier.
        with pytest.raises(Exception, match="ck_pg_demo_pages_verification"):
            async with connection.begin_nested():
                await connection.execute(text("UPDATE pg_demo_pages SET verification_state = 'verified' WHERE id = :id"), {"id": source})
        await connection.run_sync(validate_schema)


@pytest.mark.asyncio
async def test_page_verification_api_scopes_and_key_attribution(migrated_postgres, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from people_gator_api.routes.v1 import router
    from people_gator_api.services import database_service, auth_service
    from people_gator_api.schemas.api_keys import APIKeyCreateRequest
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(UserCreateRequest(display_name="Key reviewer", is_active=True, external_subject="key-reviewer", external_issuer="issue149"))
        key = await db.api_keys.get_or_create(APIKeyCreateRequest(identifier="page-reviewer", display_name="Page reviewer", user_id=user.user_id))
        actor = AuthContext(user_id=user.user_id, api_key_id=key.api_key_id, authentication_method="api_key", scopes={"people-gator:browse"})
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[database_service.get_database] = lambda: db

        async def authenticated_token(token):
            return actor
        monkeypatch.setattr(auth_service, "authenticate_bearer", authenticated_token)
        parent, [page] = await _document(db, "api-verify", pages=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer synthetic"}) as client:
            url = f"/api/v1/pages/{page.source_id}"
            assert (await client.patch(url, json={"verification_state": "verified"})).status_code == 403
            actor.scopes.add("people-gator:annotate")
            for invalid in (None, "partially_verified", 1):
                assert (await client.patch(url, json={"verification_state": invalid})).status_code == 422
            response = await client.patch(url, json={"verification_state": "verified"})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["verification_state"] == "verified"
            assert body["verified_by_user_id"] == str(user.user_id)
            assert body["verified_by_api_key_id"] == str(key.api_key_id)
            document = (await client.get(f"/api/v1/documents/{parent.source_id}")).json()
            assert (document["verification_state"], document["verified_page_count"]) == ("verified", 1)
            listed = await client.get("/api/v1/documents", params={"filter.library": "api-verify", "filter.verification_state": "verified"})
            assert [item["source_id"] for item in listed.json()["items"]] == [str(parent.source_id)]
            pages = await client.get("/api/v1/pages", params={"filter.library": "api-verify", "filter.verification_state": "not_verified"})
            assert pages.json()["items"] == []
            removed = (await client.patch(url, json={"verification_state": "not_verified"})).json()
            assert removed["verified_by_api_key_id"] is None and removed["verified_at"] is None
