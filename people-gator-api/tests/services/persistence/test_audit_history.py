"""Audit contract checks against real transactions and migrated PostgreSQL."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from pydantic import ValidationError
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.audit import AuditQuery, VersionConflict
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityPatchRequest,
    EntityPatchBatchItem,
    EntityMergeTargetPatch,
)
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FacePatchRequest,
    BoundingBox,
    Keypoint,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionPatchRequest,
)
from people_gator_api.schemas.enums import FaceKeypointType
from people_gator_api.schemas.sources import PageCreateRequest, PagePatchRequest
from people_gator_api.schemas.users import UserCreateRequest


@pytest_asyncio.fixture
async def audit_graph(migrated_postgres):
    sessions = async_sessionmaker(migrated_postgres, expire_on_commit=False)
    async with sessions() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(
            UserCreateRequest(
                display_name="Reviewer",
                is_active=True,
                external_subject="audit",
                external_issuer="synthetic",
            )
        )
        actor = GenericActor(user_id=user.user_id)
        first, second = await db.entities.create_batch(
            [
                EntityCreateRequest(
                    entity_type="person", name="Ada", aliases=["Original alias"]
                ),
                EntityCreateRequest(entity_type="person", name="Bea"),
            ],
            actor,
        )
        page, _ = await db.sources.get_or_create_page(
            PageCreateRequest(
                library="audit",
                document_id=uuid.uuid4(),
                page_id=uuid.uuid4(),
                page_number=1,
            )
        )
        face = await db.faces.create(
            FaceCreateRequest(
                source_id=page.source_id,
                entity_id=first.entity_id,
                confidence=0.9,
                bounding_box=BoundingBox(x=0, y=0, width=100, height=100),
                keypoints=[
                    Keypoint(type=kind, x=20 + i * 10, y=20 + i * 10)
                    for i, kind in enumerate(FaceKeypointType)
                ],
            ),
            actor,
        )
        mention = await db.text_mentions.create(
            TextMentionCreateRequest(
                source_id=page.source_id,
                entity_id=first.entity_id,
                name="Ada",
                context="Synthetic Ada",
            ),
            actor,
        )
        yield SimpleNamespace(
            db=db,
            session=session,
            sessions=sessions,
            actor=actor,
            first=first,
            second=second,
            page=page,
            face=face,
            mention=mention,
        )


@pytest.mark.asyncio
async def test_profile_aliases_noops_and_stale_edits(audit_graph):
    r = audit_graph
    assert (await r.db.entities.get(r.first.entity_id)).version == 1
    with pytest.raises(ValidationError):
        EntityPatchRequest(name="Unconditional")
    changed = await r.db.entities.patch(
        r.first.entity_id,
        EntityPatchRequest(expected_version=1, name="Ada new", aliases=["New alias"]),
        r.actor,
    )
    assert changed.version == 2
    rows = await r.db.audit.list(AuditQuery(object_id=r.first.entity_id))
    assert rows.total_count == 1
    old = rows.items[0]
    assert old.version == 1 and old.state["name"] == "Ada"
    assert [a["name"] for a in old.state["aliases"]] == ["Original alias"]
    assert old.actor_user_id == r.actor.user_id and old.state[
        "created_by_user_id"
    ] == str(r.actor.user_id)
    assert (
        await r.db.entities.patch(
            r.first.entity_id,
            EntityPatchRequest(expected_version=2, name="Ada new"),
            r.actor,
        )
    ).version == 2
    with pytest.raises(VersionConflict):
        await r.db.entities.patch(
            r.first.entity_id,
            EntityPatchRequest(expected_version=1, name="Ada new"),
            r.actor,
        )
    assert (await r.db.audit.list(AuditQuery())).total_count == 1


@pytest.mark.asyncio
async def test_annotation_transitions_and_related_filters(audit_graph):
    r = audit_graph
    verified = await r.db.faces.patch(
        r.face.detection_id,
        FacePatchRequest(expected_version=1, entity_link_state="verified"),
        r.actor,
    )
    assert verified.version == 2
    moved = await r.db.faces.patch(
        r.face.detection_id,
        FacePatchRequest(expected_version=2, entity_id=r.second.entity_id),
        r.actor,
    )
    assert moved.version == 3
    unlinked = await r.db.faces.patch(
        r.face.detection_id,
        FacePatchRequest(expected_version=3, entity_id=None),
        r.actor,
    )
    assert unlinked.version == 4
    await r.db.text_mentions.patch(
        r.mention.mention_id,
        TextMentionPatchRequest(expected_version=1, entity_id=None),
        r.actor,
    )
    assert (await r.db.entities.get(r.first.entity_id)).version == 1
    history = await r.db.audit.list(
        AuditQuery(
            object_type="face",
            object_id=r.face.detection_id,
            sort="version",
            direction="asc",
        )
    )
    assert [row.version for row in history.items] == [1, 2, 3]
    assert history.items[1].state["entity_link_verified_by_user_id"] == str(
        r.actor.user_id
    )
    assert history.items[1].state["entity_link_verified_at"] is not None
    assert history.items[2].entity_id == r.second.entity_id
    filtered = await r.db.audit.list(
        AuditQuery(
            entity_id=r.first.entity_id,
            source_id=r.page.source_id,
            actor_user_id=r.actor.user_id,
        )
    )
    assert filtered.total_count == 3
    assert (
        await r.db.audit.list(
            AuditQuery(object_id=r.face.detection_id, version_min=2, version_max=2)
        )
    ).items[0].version == 2
    assert (await r.db.audit.list(AuditQuery(limit=1, offset=1))).total_count == 4


@pytest.mark.asyncio
async def test_source_changes_cascade_deletion_and_retained_ids(audit_graph):
    r = audit_graph
    updated = await r.db.sources.patch_page(
        r.page.source_id,
        PagePatchRequest(expected_version=1, page_number=2),
        context=r.actor,
    )
    assert updated.version == 2
    assert await r.db.sources.delete(
        r.page.source_id, context=r.actor, expected_version=2
    )
    assert await r.db.faces.get(r.face.detection_id) is None
    await r.db.entities.delete(r.first.entity_id, context=r.actor, expected_version=1)
    history = await r.db.audit.list(
        AuditQuery(source_id=r.page.source_id, deleted=True)
    )
    assert {row.object_type for row in history.items} == {"source", "face", "mention"}
    assert (
        next(row for row in history.items if row.object_type == "face").entity_id
        == r.first.entity_id
    )
    source = await r.db.audit.list(
        AuditQuery(object_id=r.page.source_id, sort="version", direction="asc")
    )
    assert [row.state["page_number"] for row in source.items] == [1, 2]
    assert [row.deleted for row in source.items] == [False, True]


@pytest.mark.asyncio
async def test_concurrent_writers_and_batch_conflict_rollback(audit_graph):
    r = audit_graph

    async def edit(name):
        async with r.sessions() as session:
            try:
                return await postgres_database(session).entities.patch(
                    r.first.entity_id,
                    EntityPatchRequest(expected_version=1, name=name),
                    r.actor,
                )
            except VersionConflict:
                return "conflict"

    outcomes = await asyncio.gather(edit("one"), edit("two"))
    assert sum(value == "conflict" for value in outcomes) == 1
    with pytest.raises(VersionConflict):
        await r.db.entities.patch_batch(
            [
                EntityPatchBatchItem(
                    entity_id=r.second.entity_id,
                    expected_version=1,
                    name="Must roll back",
                ),
                EntityPatchBatchItem(
                    entity_id=r.first.entity_id, expected_version=1, name="Stale"
                ),
            ],
            r.actor,
        )
    assert (await r.db.entities.get(r.second.entity_id)).name == "Bea"
    assert (await r.db.audit.list(AuditQuery())).total_count == 1


@pytest.mark.asyncio
async def test_merge_and_injected_failure_are_atomic(audit_graph):
    r = audit_graph
    versions = {r.first.entity_id: 1, r.second.entity_id: 1}
    with patch(
        "people_gator_api.persistence.postgres.audit.finish_audit",
        side_effect=RuntimeError("injected"),
    ):
        with pytest.raises(RuntimeError, match="injected"):
            await r.db.entities.merge_batch(
                r.second.entity_id,
                [r.first.entity_id],
                EntityMergeTargetPatch(expected_versions=versions),
                context=r.actor,
            )
    assert (await r.db.faces.get(r.face.detection_id)).entity_id == r.first.entity_id
    assert (await r.db.audit.list(AuditQuery())).total_count == 0
    merged = await r.db.entities.merge_batch(
        r.second.entity_id,
        [r.first.entity_id],
        EntityMergeTargetPatch(expected_versions=versions),
        context=r.actor,
    )
    assert merged.merged_entity.version == 2
    assert (await r.db.faces.get(r.face.detection_id)).version == 2
    assert (await r.db.text_mentions.get(r.mention.mention_id)).version == 2
    assert await r.db.entities.get(r.first.entity_id) is None
    assert (
        (await r.db.audit.list(AuditQuery(object_id=r.first.entity_id)))
        .items[0]
        .deleted
    )


@pytest.mark.asyncio
async def test_http_requires_versions_exposes_conflicts_and_filters(audit_graph):
    import httpx
    from people_gator_api.app import get_app
    from people_gator_api.services.auth_service import get_auth_context
    from people_gator_api.services.database_service import get_database

    r = audit_graph
    app = get_app()
    app.dependency_overrides[get_database] = lambda: r.db
    app.dependency_overrides[get_auth_context] = lambda: r.actor
    url = f"/api/v1/entities/{r.first.entity_id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (
            await client.patch(url, json={"name": "Unconditional"})
        ).status_code == 422
        changed = await client.patch(
            url, json={"expected_version": 1, "name": "Reviewed Ada"}
        )
        assert changed.status_code == 200 and changed.json()["version"] == 2
        stale = await client.patch(
            url, json={"expected_version": 1, "name": "Reviewed Ada"}
        )
        assert (
            stale.status_code == 409
            and stale.json()["detail"]["code"] == "version_conflict"
        )
        assert (await client.delete(url)).status_code == 422
        result = await client.get(
            "/api/v1/audit",
            params={
                "entity_id": str(r.first.entity_id),
                "sort": "version",
                "direction": "asc",
            },
        )
        assert result.status_code == 200 and result.json()["total_count"] == 1
        assert result.json()["items"][0]["state"]["name"] == "Ada"
        archived = await client.get(
            f"/api/v1/audit/entity/{r.first.entity_id}/versions/1"
        )
        assert archived.status_code == 200 and archived.json()["state"]["name"] == "Ada"
        assert (
            await client.get(f"/api/v1/audit/entity/{r.first.entity_id}/versions/2")
        ).status_code == 404
        for params in (
            {"sort": "name"},
            {"version_min": 0},
            {"limit": 501},
            {"version_min": 3, "version_max": 1},
        ):
            assert (await client.get("/api/v1/audit", params=params)).status_code == 422
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_migration_initializes_existing_rows_without_inventing_history(
    migrated_postgres,
):
    from alembic import command
    from people_gator_api.persistence.postgres.schema import (
        migration_config,
        validate_schema,
    )

    async with migrated_postgres.begin() as connection:

        def migrate(sync, target, downgrade=False):
            config = migration_config()
            config.attributes["connection"] = sync
            (command.downgrade if downgrade else command.upgrade)(config, target)

        await connection.run_sync(lambda sync: migrate(sync, "d34a021b0014", True))
        user_id, entity_id = uuid.uuid4(), uuid.uuid4()
        await connection.execute(
            text(
                "INSERT INTO pg_demo_users(id,display_name,is_active,external_subject,external_issuer) VALUES (:id,'Legacy',true,'legacy','audit')"
            ),
            {"id": user_id},
        )
        await connection.execute(
            text(
                "INSERT INTO pg_demo_entities(id,user_id,kind,name) VALUES (:id,:user,'person','Legacy Ada')"
            ),
            {"id": entity_id, "user": user_id},
        )
        await connection.run_sync(lambda sync: migrate(sync, "head"))
        await connection.run_sync(lambda sync: migrate(sync, "head"))
        row = (
            await connection.execute(
                text(
                    "SELECT version,created_at,last_touched_at FROM pg_demo_entities WHERE id=:id"
                ),
                {"id": entity_id},
            )
        ).one()
        assert tuple(row) == (1, None, None)
        assert (
            await connection.scalar(text("SELECT count(*) FROM pg_demo_object_history"))
            == 0
        )
        await connection.run_sync(validate_schema)


@pytest.mark.asyncio
async def test_face_vectors_and_api_key_actor_are_preserved(audit_graph):
    import json
    from people_gator_api.schemas.api_keys import APIKeyCreateRequest
    from people_gator_api.schemas.face_models import FaceModelRegisterRequest
    from people_gator_api.schemas.faces import FaceEmbedding
    from people_gator_api.services.auth_service import AuthContext

    r = audit_graph
    key = await r.db.api_keys.get_or_create(
        APIKeyCreateRequest(
            identifier="audit-review",
            display_name="Audit review",
            user_id=r.actor.user_id,
        )
    )
    actor = AuthContext(
        user_id=r.actor.user_id,
        api_key_id=key.api_key_id,
        authentication_method="api_key",
        scopes=set(),
    )
    await r.db.face_models.register(
        FaceModelRegisterRequest(model_stub="audit-2d", embedding_dim=2)
    )
    await r.db.faces.patch(
        r.face.detection_id,
        FacePatchRequest(
            expected_version=1,
            embeddings=[FaceEmbedding(model_identifier="audit-2d", vector=[0.1, 0.2])],
        ),
        actor,
    )
    changed = await r.db.faces.patch(
        r.face.detection_id,
        FacePatchRequest(
            expected_version=2,
            embeddings=[FaceEmbedding(model_identifier="audit-2d", vector=[0.3, 0.4])],
        ),
        actor,
    )
    assert changed.version == 3
    old = await r.db.audit.get("face", r.face.detection_id, 2)
    embedding = old.state["embeddings"][0]
    assert embedding["model_id"] == "audit-2d"
    vector = embedding["embedding"]
    assert (json.loads(vector) if isinstance(vector, str) else vector) == pytest.approx(
        [0.1, 0.2]
    )
    assert old.actor_api_key_id == key.api_key_id
    assert old.state["created_by_api_key_id"] is None
    assert (await r.db.entities.get(r.first.entity_id)).version == 1
