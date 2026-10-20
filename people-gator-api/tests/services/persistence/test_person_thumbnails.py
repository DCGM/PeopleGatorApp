"""Portrait state must survive graph transitions without turning reads into edits."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.persistence.postgres.schema import migration_config, validate_postgres_schema
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.entities import (
    EntityCreateRequest, EntityListRequest, EntityPatchRequest, EntityPatchBatchItem,
)
from people_gator_api.schemas.enums import FaceKeypointType
from people_gator_api.schemas.faces import FaceCreateRequest, FacePatchRequest, BoundingBox, Keypoint
from people_gator_api.schemas.search import SearchEntitiesRequest, QueryBase
from people_gator_api.schemas.sources import PageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest


@pytest_asyncio.fixture
async def portraits(migrated_postgres):
    sessions = async_sessionmaker(migrated_postgres, expire_on_commit=False)
    async with sessions() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(UserCreateRequest(
            display_name="Portrait reviewer", is_active=True,
            external_subject=uuid.uuid4().hex, external_issuer="issue35",
        ))
        actor = GenericActor(user_id=user.user_id)
        entities = await db.entities.create_batch([
            EntityCreateRequest(entity_type=kind, name=name)
            for kind, name in (("person", "Ada Portrait"), ("person", "Other Person"))
        ], actor)
        # The API exposes only people; exercise historical non-person rows too.
        organization = SimpleNamespace(entity_id=uuid.uuid4())
        await session.execute(text("INSERT INTO pg_demo_entities (id, user_id, kind, name) VALUES (:id, :user, 'organization', 'Archive')"),
                              {"id": organization.entity_id, "user": user.user_id})
        await session.commit()
        page, _ = await db.sources.get_or_create_page(PageCreateRequest(
            library="issue35", document_id=uuid.uuid4(), page_id=uuid.uuid4(),
        ))
        yield SimpleNamespace(db=db, session=session, sessions=sessions, actor=actor,
                              person=entities[0], other=entities[1], organization=organization, page=page)


async def face(r, owner):
    return await r.db.faces.create(FaceCreateRequest(
        source_id=r.page.source_id, entity_id=owner, confidence=0.9,
        bounding_box=BoundingBox(x=0, y=0, width=100, height=100),
        keypoints=[Keypoint(type=kind, x=20 + i * 10, y=20 + i * 10)
                   for i, kind in enumerate(FaceKeypointType)],
    ), r.actor)


async def get(r, person=None):
    return await r.db.entities.get((person or r.person).entity_id)


async def choose(r, face_id, person=None):
    return await r.db.entities.patch((person or r.person).entity_id,
        EntityPatchRequest(thumbnail_face_id=face_id), r.actor)


@pytest.mark.asyncio
async def test_selection_reset_response_parity_noops_and_later_faces(portraits):
    r = portraits
    assert (await get(r)).thumbnail_face_id is None
    first = await face(r, r.person.entity_id)
    automatic = await get(r)
    assert automatic.thumbnail_mode == "automatic"
    assert automatic.thumbnail_face_id == first.detection_id
    second = await face(r, r.person.entity_id)
    assert (await get(r)).thumbnail_face_id == first.detection_id
    manual = await choose(r, second.detection_id)
    assert manual.thumbnail_face_id == second.detection_id
    assert manual.thumbnail_mode == "manual"
    assert manual.last_touched_by_user_id == r.actor.user_id
    for patch in (EntityPatchRequest(), EntityPatchRequest(thumbnail_face_id=second.detection_id)):
        unchanged = await r.db.entities.patch(r.person.entity_id, patch, r.actor)
        assert unchanged == manual
    assert await get(r) == manual  # reads preserve timestamp and mode
    from people_gator_api.schemas.entities import EntityListFilter
    listed = await r.db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(entity_type=["person"])))
    searched = await r.db.entities.search(SearchEntitiesRequest(query=QueryBase(text=["Ada"]), limit=100))
    for item in (next(x for x in listed.items if x.entity_id == r.person.entity_id), searched.items[0]):
        assert item.thumbnail_face_id == second.detection_id and item.thumbnail_mode == "manual"
    # Independent session models a reload/restart, with no face-list request.
    async with r.sessions() as session:
        assert await postgres_database(session).entities.get(r.person.entity_id) == manual
    reset = await choose(r, None)
    assert reset.thumbnail_mode == "automatic"
    assert reset.thumbnail_face_id == min(first.detection_id, second.detection_id)
    assert (await choose(r, None)).last_touched_at == reset.last_touched_at


@pytest.mark.asyncio
async def test_validation_and_batch_failure_are_atomic(portraits):
    r = portraits
    own = await face(r, r.person.entity_id)
    foreign = await face(r, r.other.entity_id)
    before = await get(r)
    for invalid in (uuid.uuid4(), foreign.detection_id):
        with pytest.raises(ValueError, match="linked to this person"):
            await r.db.entities.patch_batch([
                EntityPatchBatchItem(entity_id=r.other.entity_id, name="Must roll back"),
                EntityPatchBatchItem(entity_id=r.person.entity_id, thumbnail_face_id=invalid, name="Also rollback"),
            ], r.actor)
        assert await get(r) == before
        assert (await get(r, r.other)).name == "Other Person"
    for selection in (own.detection_id, None):
        with pytest.raises(ValueError, match="only for people"):
            await choose(r, selection, r.organization)
    # Database guard also rejects bypassing the repository's ownership check.
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await r.session.execute(text("UPDATE pg_demo_entities SET thumbnail_face_id=:face WHERE id=:id"),
                                {"face": foreign.detection_id, "id": r.person.entity_id})
    await r.session.rollback()
    assert await get(r) == before


@pytest.mark.asyncio
async def test_reassignment_unlink_face_and_source_deletion(portraits):
    r = portraits
    first = await face(r, r.person.entity_id)
    second = await face(r, r.person.entity_id)
    await choose(r, first.detection_id)
    await r.db.faces.patch(first.detection_id, FacePatchRequest(entity_id=r.other.entity_id), r.actor)
    repaired = await get(r)
    assert repaired.thumbnail_face_id == second.detection_id and repaired.thumbnail_mode == "automatic"
    assert (await get(r, r.other)).thumbnail_face_id == first.detection_id
    assert repaired.last_touched_by_user_id == r.actor.user_id
    await r.db.faces.patch(second.detection_id, FacePatchRequest(entity_id=None), r.actor)
    assert (await get(r)).thumbnail_face_id is None
    await r.db.faces.patch(second.detection_id, FacePatchRequest(entity_id=r.person.entity_id), r.actor)
    await choose(r, second.detection_id)
    await r.db.faces.delete(second.detection_id, context=r.actor)
    assert (await get(r)).thumbnail_face_id is None
    await choose(r, first.detection_id, r.other)
    await r.db.sources.delete(r.page.source_id, context=r.actor)
    other = await get(r, r.other)
    assert other.thumbnail_face_id is None and other.thumbnail_mode == "automatic"


@pytest.mark.asyncio
async def test_merge_preserves_target_manual_and_resolves_empty_target(portraits):
    r = portraits
    first = await face(r, r.person.entity_id)
    second = await face(r, r.other.entity_id)
    await choose(r, first.detection_id)
    result = await r.db.entities.merge(r.person.entity_id, r.other.entity_id, context=r.actor)
    assert result.merged_entity.thumbnail_face_id == first.detection_id
    assert result.merged_entity.thumbnail_mode == "manual"
    assert (await r.db.faces.get(second.detection_id)).entity_id == r.person.entity_id
    empty = await r.db.entities.create(EntityCreateRequest(entity_type="person", name="Empty target"), r.actor)
    result = await r.db.entities.merge(empty.entity_id, r.person.entity_id, context=r.actor)
    assert result.merged_entity.thumbnail_face_id == min(first.detection_id, second.detection_id)
    assert result.merged_entity.thumbnail_mode == "automatic"


@pytest.mark.asyncio
async def test_concurrent_selection_and_reassignment(portraits):
    r = portraits
    first = await face(r, r.person.entity_id)
    second = await face(r, r.person.entity_id)
    async def select():
        async with r.sessions() as session:
            try:
                await postgres_database(session).entities.patch(r.person.entity_id,
                    EntityPatchRequest(thumbnail_face_id=first.detection_id), r.actor)
            except ValueError:
                pass  # reassignment won; selection must be rejected
    async def reassign():
        async with r.sessions() as session:
            await postgres_database(session).faces.patch(first.detection_id,
                FacePatchRequest(entity_id=r.other.entity_id), r.actor)
    await asyncio.wait_for(asyncio.gather(select(), reassign()), timeout=10)
    assert (await get(r)).thumbnail_face_id == second.detection_id
    assert (await get(r)).thumbnail_mode == "automatic"


@pytest.mark.asyncio
async def test_populated_upgrade_preserves_history_and_is_repeatable(portraits, migrated_postgres):
    r = portraits
    first = await face(r, r.person.entity_id)
    before = await get(r)
    detection = await r.db.faces.get(first.detection_id)
    await r.session.rollback()
    def revision(connection, target, downgrade=False):
        config = migration_config()
        config.attributes['connection'] = connection
        (command.downgrade if downgrade else command.upgrade)(config, target)
    async with migrated_postgres.begin() as connection:
        await connection.run_sync(lambda c: revision(c, "d34a021b0008", True))
        await connection.run_sync(lambda c: revision(c, "head"))
        await connection.run_sync(lambda c: revision(c, "head"))
    await validate_postgres_schema(migrated_postgres)
    after = await get(r)
    assert after == before
    assert await r.db.faces.get(first.detection_id) == detection
