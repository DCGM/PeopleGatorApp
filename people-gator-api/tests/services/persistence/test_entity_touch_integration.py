"""Opt-in checks against an isolated PostgreSQL/pgvector database."""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.engine import make_url
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.persistence.postgres.models import APIKey, Entity
from people_gator_api.schemas.api_keys import APIKeyCreateRequest, APIKeyListRequest
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityPatchRequest,
    EntityPatchBatchItem,
    EntityListFilter,
    EntityListRequest,
)
from people_gator_api.schemas.enums import EntityType, FaceKeypointType
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FacePatchRequest,
    FacePatchBatchItem,
    BoundingBox,
    Keypoint,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionPatchRequest,
    TextMentionPatchBatchItem,
)
from people_gator_api.schemas.search import SearchEntitiesRequest, QueryBase
from people_gator_api.schemas.sources import DocumentCreateRequest, PageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext
from people_gator_api.services.database_service import (
    create_postgres_schema,
    make_postgres_engine,
    make_postgres_session_factory,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("PEOPLE_GATOR_POSTGRES_TEST_URL"),
        reason="requires isolated PostgreSQL",
    ),
]


@pytest_asyncio.fixture
async def records():
    engine = make_postgres_engine(
        make_url(os.environ["PEOPLE_GATOR_POSTGRES_TEST_URL"])
    )
    await create_postgres_schema(engine)
    sessions = make_postgres_session_factory(engine)
    async with sessions() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(
            UserCreateRequest(
                display_name="Tester",
                is_active=True,
                external_subject=uuid.uuid4().hex,
                external_issuer="issue2-tests",
            )
        )
        key = await db.api_keys.get_or_create(
            APIKeyCreateRequest(
                identifier=uuid.uuid4().hex,
                display_name="Importer",
                user_id=user.user_id,
            )
        )
        actor = AuthContext(
            user_id=user.user_id,
            user=user,
            api_key_id=key.api_key_id,
            authentication_method="api_key",
            scopes=set(),
        )
        entities = await db.entities.create_batch(
            [
                EntityCreateRequest(entity_type=EntityType.person, name="Ada Lovelace")
                for _ in range(3)
            ],
            actor,
        )
        document_id = uuid.uuid4()
        document, _ = await db.sources.get_or_create_document(
            DocumentCreateRequest(library="issue2", document_id=document_id)
        )
        other, _ = await db.sources.get_or_create_document(
            DocumentCreateRequest(library="other", document_id=document_id)
        )
        pages = []
        for library in ("issue2", "issue2", "other"):
            page, _ = await db.sources.get_or_create_page(
                PageCreateRequest(
                    library=library, document_id=document_id, page_id=uuid.uuid4()
                )
            )
            pages.append(page)
        yield SimpleNamespace(
            db=db,
            session=session,
            sessions=sessions,
            user=user,
            actor=actor,
            key=key,
            entities=entities,
            document=document,
            other=other,
            pages=pages,
        )
    await engine.dispose()


async def face(r, entity_id, page=0):
    return await r.db.faces.create(
        FaceCreateRequest(
            source_id=r.pages[page].source_id,
            entity_id=entity_id,
            confidence=0.9,
            bounding_box=BoundingBox(x=0, y=0, width=10, height=10),
            keypoints=[Keypoint(type=kind, x=1, y=1) for kind in FaceKeypointType],
        ),
        r.actor,
    )


async def mention(r, entity_id, page=0):
    return await r.db.text_mentions.create(
        TextMentionCreateRequest(
            source_id=r.pages[page].source_id,
            entity_id=entity_id,
            name="Ada",
            context="Ada Lovelace",
        ),
        r.actor,
    )


async def entity(r, index=0):
    return await r.db.entities.get(r.entities[index].entity_id)


async def test_touch_create_noops_patches_reassignment_and_deletion(records):
    r = records
    first, second, _ = r.entities
    assert first.last_touched_at.tzinfo is not None
    assert first.last_touched_by_user_id == r.user.user_id
    assert first.last_touched_by_api_key_id == r.key.api_key_id
    # Reads, empty patches, identical fields and alias-only reordering are no-ops.
    before = (await entity(r)).last_touched_at
    for patch in (
        EntityPatchRequest(),
        EntityPatchRequest(name=first.name, aliases=[]),
    ):
        after = await r.db.entities.patch(first.entity_id, patch, r.user)
        assert after.last_touched_at == before
        assert after.last_touched_by_api_key_id == r.key.api_key_id
    updated = await r.db.entities.patch(
        first.entity_id, EntityPatchRequest(aliases=["Ada", "Countess"]), r.actor
    )
    before = updated.last_touched_at
    after = await r.db.entities.patch(
        first.entity_id, EntityPatchRequest(aliases=["Countess", "Ada"]), r.user
    )
    assert after.last_touched_at == before
    # Reconcile overlapping alias sets without inserting duplicate alias rows.
    after = await r.db.entities.patch(
        first.entity_id, EntityPatchRequest(aliases=["Ada", "Lovelace"]), r.user
    )
    assert set(after.aliases) == {"Ada", "Lovelace"}
    assert after.last_touched_by_api_key_id is None
    f = await face(r, first.entity_id)
    assert (await entity(r)).last_touched_by_api_key_id == r.key.api_key_id
    before = (await entity(r)).last_touched_at
    await r.db.faces.patch(
        f.detection_id, FacePatchRequest(entity_id=first.entity_id), r.user
    )
    assert (await entity(r)).last_touched_at == before
    await r.db.faces.patch(
        f.detection_id, FacePatchRequest(entity_id=second.entity_id), r.user
    )
    assert (await entity(r)).last_touched_at > before
    assert (await entity(r)).last_touched_by_api_key_id is None
    assert (await entity(r, 1)).last_touched_by_api_key_id is None
    before = (await entity(r, 1)).last_touched_at
    await r.db.faces.delete(f.detection_id, context=r.actor)
    assert (await entity(r, 1)).last_touched_at > before
    before = (await entity(r, 1)).last_touched_at
    assert not await r.db.faces.delete(f.detection_id, context=r.user)
    assert (await entity(r, 1)).last_touched_at == before
    m = await mention(r, first.entity_id)
    before = (await entity(r)).last_touched_at
    await r.db.text_mentions.patch(
        m.mention_id, TextMentionPatchRequest(entity_id=first.entity_id), r.user
    )
    assert (await entity(r)).last_touched_at == before
    await r.db.text_mentions.patch(
        m.mention_id, TextMentionPatchRequest(entity_id=second.entity_id), r.user
    )
    assert (await entity(r)).last_touched_by_api_key_id is None
    before = (await entity(r, 1)).last_touched_at
    await r.db.text_mentions.delete(m.mention_id, context=r.actor)
    assert (await entity(r, 1)).last_touched_at > before


async def test_document_time_actor_filters_counts_search_and_cursors(records):
    r = records
    ids = [item.entity_id for item in r.entities]
    await face(r, ids[0], 0)
    await face(r, ids[0], 1)
    await mention(r, ids[0], 1)
    await mention(r, ids[1], 1)
    await face(r, ids[2], 2)  # same document UUID in another library must not match
    exact = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    await r.session.execute(
        update(Entity).where(Entity.id.in_(ids)).values(last_touched_at=exact)
    )
    await r.session.commit()
    combined = EntityListFilter(
        entity_id=ids,
        document_source_id=[r.document.source_id],
        last_touched_from=exact,
        last_touched_to=exact,
        last_touched_by_user_id=[r.user.user_id],
        last_touched_by_api_key_id=[r.key.api_key_id],
        has_mentions=True,
    )
    page = await r.db.entities.list(
        EntityListRequest(filter_=combined, limit=1, return_total_count=True)
    )
    assert page.total_count == 2
    assert page.cursor
    next_page = await r.db.entities.list(
        EntityListRequest(
            filter_=combined, limit=1, return_total_count=True, cursor=page.cursor
        )
    )
    assert next_page.total_count == 2
    assert {page.items[0].entity_id, next_page.items[0].entity_id} == set(ids[:2])
    assert next_page.cursor is None
    changed = combined.model_copy(update={"document_source_id": [r.other.source_id]})
    with pytest.raises(ValueError, match="different query"):
        await r.db.entities.list(
            EntityListRequest(
                filter_=changed, limit=1, return_total_count=True, cursor=page.cursor
            )
        )
    for filt, expected in [
        (
            EntityListFilter(
                entity_id=ids,
                document_source_id=[r.document.source_id, r.other.source_id],
            ),
            3,
        ),
        (EntityListFilter(entity_id=ids, last_touched_from=exact), 3),
        (
            EntityListFilter(
                entity_id=ids, last_touched_to=exact - timedelta(seconds=1)
            ),
            0,
        ),
        (
            EntityListFilter(
                entity_id=ids, last_touched_by_user_id=[uuid.uuid4(), r.user.user_id]
            ),
            3,
        ),
        (EntityListFilter(entity_id=ids, last_touched_by_api_key_id=[uuid.uuid4()]), 0),
    ]:
        result = await r.db.entities.list(
            EntityListRequest(filter_=filt, limit=10, return_total_count=True)
        )
        assert len(result.items) == result.total_count == expected
    search = await r.db.entities.search(
        SearchEntitiesRequest(
            query=QueryBase(text=["Ada"]),
            filter_=combined,
            limit=10,
            return_total_count=True,
        )
    )
    assert search.total_count == 2
    assert {item.entity_id for item in search.items} == set(ids[:2])
    await r.session.execute(
        update(Entity)
        .where(Entity.id == ids[2])
        .values(
            last_touched_at=None,
            last_touched_by_user_id=None,
            last_touched_by_api_key_id=None,
        )
    )
    await r.session.commit()
    assert (
        await r.db.entities.list(
            EntityListRequest(filter_=EntityListFilter(entity_id=ids), limit=10)
        )
    ).items
    assert (
        await r.db.entities.list(
            EntityListRequest(
                filter_=EntityListFilter(entity_id=ids, last_touched_from=exact),
                limit=10,
                return_total_count=True,
            )
        )
    ).total_count == 2


async def test_batch_merge_cascade_and_transaction_rollback(records, monkeypatch):
    r = records
    ids = [item.entity_id for item in r.entities]
    await r.db.entities.patch_batch(
        [EntityPatchBatchItem(entity_id=item, name="Updated") for item in ids], r.user
    )
    for item in ids:
        assert (await r.db.entities.get(item)).last_touched_by_api_key_id is None
    f = await face(r, ids[0])
    m = await mention(r, ids[0])
    await r.db.faces.patch_batch(
        [FacePatchBatchItem(detection_id=f.detection_id, entity_id=ids[1])], r.user
    )
    await r.db.text_mentions.patch_batch(
        [TextMentionPatchBatchItem(mention_id=m.mention_id, entity_id=ids[1])], r.user
    )
    before = (await entity(r, 1)).last_touched_at
    from people_gator_api.persistence.postgres import text_mention_repository

    original = text_mention_repository.commit

    async def fail(session, message):
        await session.rollback()
        raise RuntimeError("injected failure")

    monkeypatch.setattr(text_mention_repository, "commit", fail)
    with pytest.raises(RuntimeError, match="injected"):
        await r.db.text_mentions.patch(
            m.mention_id, TextMentionPatchRequest(entity_id=ids[2]), r.actor
        )
    monkeypatch.setattr(text_mention_repository, "commit", original)
    assert (await entity(r, 1)).last_touched_at == before
    assert (await r.db.text_mentions.get(m.mention_id)).entity_id == ids[1]
    result = await r.db.entities.merge_batch(ids[2], ids[:2], context=r.actor)
    assert result.merged_entity.last_touched_by_api_key_id == r.key.api_key_id
    assert result.faces_reassigned == result.text_mentions_reassigned == 1
    before = result.merged_entity.last_touched_at
    await r.db.sources.delete(r.pages[0].source_id, context=r.user)
    target = await entity(r, 2)
    assert target.last_touched_at > before
    assert target.last_touched_by_api_key_id is None


async def test_key_registration_concurrency_and_historical_listing(records):
    r = records
    identifier = uuid.uuid4().hex

    async def register():
        async with r.sessions() as session:
            return await postgres_database(session).api_keys.get_or_create(
                APIKeyCreateRequest(
                    identifier=identifier,
                    display_name="Concurrent importer",
                    user_id=r.user.user_id,
                )
            )

    keys = await asyncio.gather(*(register() for _ in range(8)))
    assert len({key.api_key_id for key in keys}) == 1
    assert (
        len(
            list(
                await r.session.scalars(
                    select(APIKey).where(APIKey.identifier == identifier)
                )
            )
        )
        == 1
    )
    listed = await r.db.api_keys.list(
        APIKeyListRequest(limit=1000, return_total_count=True)
    )
    assert keys[0].api_key_id in {key.api_key_id for key in listed.items}
    assert "hash" not in listed.model_dump_json()


async def test_filter_options_search_all_records_and_escape_wildcards(records):
    r = records
    marker = uuid.uuid4().hex
    for suffix in ("alpha", "beta"):
        await r.db.api_keys.get_or_create(
            APIKeyCreateRequest(
                identifier=f"{marker}-{suffix}",
                display_name=f"Importer {marker}",
                user_id=r.user.user_id,
            )
        )
    first = await r.db.api_keys.list(
        APIKeyListRequest(q=marker.upper(), limit=1, return_total_count=True)
    )
    assert first.total_count == 2 and first.cursor
    second = await r.db.api_keys.list(
        APIKeyListRequest(
            q=marker.upper(), limit=1, return_total_count=True, cursor=first.cursor
        )
    )
    assert (
        len(second.items) == 1
        and first.items[0].api_key_id != second.items[0].api_key_id
    )
    with pytest.raises(ValueError):
        await r.db.api_keys.list(
            APIKeyListRequest(
                q="other", limit=1, return_total_count=True, cursor=first.cursor
            )
        )
    escaped = await r.db.api_keys.list(
        APIKeyListRequest(q="%", limit=1, return_total_count=True)
    )
    assert escaped.total_count == 0
    from people_gator_api.schemas.users import UserListRequest, UserListFilter

    user = await r.db.users.get_or_create(
        UserCreateRequest(
            display_name=f"Searchable {marker}",
            is_active=True,
            external_subject=marker,
            external_issuer="option-tests",
        )
    )
    users = await r.db.users.list(
        UserListRequest(
            filter_=UserListFilter(search=marker.upper()),
            limit=10,
            return_total_count=True,
        )
    )
    assert users.total_count == 1 and users.items[0].user_id == user.user_id
    escaped = await r.db.users.list(
        UserListRequest(
            filter_=UserListFilter(search="%"), limit=1, return_total_count=True
        )
    )
    assert escaped.total_count == 0
