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
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.services.auth_service import AuthContext
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
        key = await db.api_keys.get_or_create(APIKeyCreateRequest(
            identifier="portrait-reviewer-" + uuid.uuid4().hex,
            display_name="Portrait review key", user_id=user.user_id,
        ))
        actor = AuthContext(user_id=user.user_id, user=user, api_key_id=key.api_key_id,
                            authentication_method="api_key", scopes=set())
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


async def face(r, owner, detection_id=None):
    from unittest.mock import patch
    from people_gator_api.persistence.postgres.face_repository import PostgresFaceRepository
    original = PostgresFaceRepository._new
    def build(payload, context):
        result = original(payload, context)
        if detection_id is not None:
            result.id = detection_id
        return result
    with patch.object(PostgresFaceRepository, "_new", side_effect=build):
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
    manual_id = max(first.detection_id, second.detection_id)
    manual = await choose(r, manual_id)
    assert manual.thumbnail_face_id == manual_id
    assert manual.thumbnail_mode == "manual"
    assert manual.last_touched_by_user_id == r.actor.user_id
    assert manual.last_touched_by_api_key_id == r.actor.api_key_id
    for patch in (EntityPatchRequest(), EntityPatchRequest(thumbnail_face_id=manual_id)):
        unchanged = await r.db.entities.patch(r.person.entity_id, patch, r.actor)
        assert unchanged == manual
    assert await get(r) == manual  # reads preserve timestamp and mode
    from people_gator_api.schemas.entities import EntityListFilter
    listed = await r.db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(entity_type=["person"])))
    searched = await r.db.entities.search(SearchEntitiesRequest(query=QueryBase(text=["Ada"]), limit=100))
    for item in (next(x for x in listed.items if x.entity_id == r.person.entity_id), searched.items[0]):
        assert item.thumbnail_face_id == manual_id and item.thumbnail_mode == "manual"
    from people_gator_api.schemas.faces import FaceListRequest, FaceListFilter
    first_page = await r.db.faces.list(FaceListRequest(limit=1,
        filter_=FaceListFilter(entity_id=[r.person.entity_id])))
    assert manual_id not in {f.detection_id for f in first_page.items}
    filtered = await r.db.faces.list(FaceListRequest(limit=100,
        filter_=FaceListFilter(entity_id=[r.person.entity_id], entity_link_state=["verified"])))
    assert not filtered.items
    assert await get(r) == manual
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


@pytest.mark.asyncio
async def test_first_assignment_survives_lower_ids_identity_edits_and_merge(portraits):
    r = portraits
    first = await face(r, r.person.entity_id, uuid.UUID(int=100))
    later = await face(r, r.person.entity_id, uuid.UUID(int=50))
    source = await face(r, r.other.entity_id, uuid.UUID(int=1))
    assert (await get(r)).thumbnail_face_id == first.detection_id
    renamed = await r.db.entities.patch(r.person.entity_id, EntityPatchRequest(name="Renamed"), r.actor)
    assert renamed.thumbnail_face_id == first.detection_id
    assert (await choose(r, None)) == renamed
    merged = await r.db.entities.merge(r.person.entity_id, r.other.entity_id, context=r.actor)
    assert merged.merged_entity.thumbnail_face_id == first.detection_id
    assert merged.merged_entity.thumbnail_mode == "automatic"
    # Only losing the saved face permits automatic replacement. The fallback
    # is persisted and survives independent sessions and another automatic reset.
    await r.db.faces.delete(first.detection_id, context=r.actor)
    recovered = await get(r)
    assert recovered.thumbnail_face_id == source.detection_id
    assert recovered.thumbnail_face_id != later.detection_id
    assert await choose(r, None) == recovered
    async with r.sessions() as session:
        assert await postgres_database(session).entities.get(r.person.entity_id) == recovered


@pytest.mark.asyncio
async def test_batch_reset_returns_database_resolved_choices(portraits):
    r = portraits
    own = [await face(r, r.person.entity_id) for _ in range(2)]
    other = [await face(r, r.other.entity_id) for _ in range(2)]
    await choose(r, max(f.detection_id for f in own))
    await choose(r, max(f.detection_id for f in other), r.other)
    result = await r.db.entities.patch_batch([
        EntityPatchBatchItem(entity_id=person.entity_id, thumbnail_face_id=None)
        for person in (r.person, r.other)
    ], r.actor)
    for person, faces in zip(result, (own, other)):
        assert person.thumbnail_mode == "automatic"
        assert person.thumbnail_face_id == min(f.detection_id for f in faces)
        assert person == await r.db.entities.get(person.entity_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("constraint", [
    "ck_pg_demo_entities_thumbnail_mode", "ck_pg_demo_entities_manual_thumbnail",
    "ck_pg_demo_entities_person_thumbnail",
])
async def test_schema_validation_rejects_weakened_thumbnail_checks(migrated_postgres, constraint):
    from people_gator_api.persistence.postgres.schema import SchemaValidationError
    async with migrated_postgres.begin() as connection:
        await connection.execute(text(f"ALTER TABLE pg_demo_entities DROP CONSTRAINT {constraint}"))
        await connection.execute(text(f"ALTER TABLE pg_demo_entities ADD CONSTRAINT {constraint} CHECK (true)"))
    with pytest.raises(SchemaValidationError, match="thumbnail consistency constraint"):
        await validate_postgres_schema(migrated_postgres)


@pytest.mark.asyncio
async def test_bulk_face_insert_repairs_each_owner_once(portraits):
    from people_gator_api.persistence.postgres.face_repository import PostgresFaceRepository
    r = portraits
    original = await face(r, r.person.entity_id)
    await r.db.faces.patch(original.detection_id, FacePatchRequest(entity_id=None), r.actor)
    # Count entity UPDATE attempts separately from actual row modifications.
    # Row triggers would invoke repair once per face, even for valid choices.
    await r.session.execute(text("CREATE TEMP TABLE repair_calls (id integer)"))
    await r.session.execute(text("""CREATE FUNCTION count_portrait_updates() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN INSERT INTO repair_calls VALUES (1); RETURN NULL; END $$"""))
    await r.session.execute(text("""CREATE TRIGGER count_portrait_updates AFTER UPDATE ON pg_demo_entities
        FOR EACH STATEMENT EXECUTE FUNCTION count_portrait_updates()"""))
    request = FaceCreateRequest(source_id=original.source_id, confidence=original.confidence,
        bounding_box=original.bounding_box, keypoints=original.keypoints)
    payloads = [request.model_copy(update={"entity_id": owner.entity_id})
                for owner in (r.person, r.other) for _ in range(10)]
    # Exercise the actual ORM insertion strategy without unrelated touch UPDATEs.
    # Some drivers use executemany: owners already filled by an earlier statement
    # must be skipped too, rather than paying another repair UPDATE per face.
    rows = [PostgresFaceRepository._new(payload, r.actor) for payload in payloads]
    r.session.add_all(rows)
    await r.session.flush()
    assert await r.session.scalar(text("SELECT count(*) FROM repair_calls")) == 2
    await r.session.commit()
    for owner in (r.person, r.other):
        selected = (await get(r, owner)).thumbnail_face_id
        assert selected is not None
        assert (await r.db.faces.get(selected)).entity_id == owner.entity_id


@pytest.mark.asyncio
async def test_merge_preserves_manual_choice_made_after_session_cached_target(portraits):
    from people_gator_api.persistence.postgres.models import Entity
    r = portraits
    # Keep a strong reference: the identity map retains this portrait-less state.
    stale = await r.session.get(Entity, r.person.entity_id)
    assert stale is not None and stale.thumbnail_face_id is None
    await r.session.commit()
    async with r.sessions() as session:
        other = SimpleNamespace(**{**vars(r), "db": postgres_database(session)})
        await face(other, r.person.entity_id, uuid.UUID(int=10))
        chosen = await face(other, r.person.entity_id, uuid.UUID(int=20))
        await face(other, r.other.entity_id, uuid.UUID(int=5))
        await choose(other, chosen.detection_id)
    result = await r.db.entities.merge(r.person.entity_id, r.other.entity_id, context=r.actor)
    assert result.merged_entity.thumbnail_face_id == chosen.detection_id
    assert result.merged_entity.thumbnail_mode == "manual"


@pytest.mark.asyncio
async def test_bulk_reassignment_rewrites_emptied_owner_once(portraits):
    r = portraits
    target = await face(r, r.person.entity_id)
    await choose(r, target.detection_id)
    for _ in range(5):
        await face(r, r.other.entity_id)
    await r.session.execute(text("CREATE TEMP TABLE portrait_writes (id uuid)"))
    await r.session.execute(text("""CREATE FUNCTION count_portrait_writes() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN INSERT INTO portrait_writes VALUES (OLD.id); RETURN NULL; END $$"""))
    await r.session.execute(text("""CREATE TRIGGER count_portrait_writes AFTER UPDATE ON pg_demo_entities
        FOR EACH ROW EXECUTE FUNCTION count_portrait_writes()"""))
    # The merge moves every source face in one UPDATE; row triggers repair both
    # owners per face. The emptied source is written once, the valid target never.
    await r.db.entities.merge(r.person.entity_id, r.other.entity_id, context=r.actor)
    writes = dict((await r.session.execute(text(
        "SELECT id, count(*) FROM portrait_writes GROUP BY id"))).all())
    assert writes.get(r.other.entity_id) == 1
