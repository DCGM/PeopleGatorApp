"""Event stream, subscription endpoint and publishing from mutation routes (#209)."""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from people_gator_api.persistence.contracts import CreateResult
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.routes.v1 import router as v1_router
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.entities import EntityCreateRequest, EntityMergeResponse
from people_gator_api.schemas.enums import EntityLinkState, EntityType
from people_gator_api.schemas.faces import FaceResponse
from people_gator_api.schemas.mentions import TextMentionCreateRequest, TextMentionResponse
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentResponse,
    PageCreateRequest,
    PageResponse,
)
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services import database_service
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database, get_database_context
from people_gator_api.services.event_service import EventHub, get_event_hub


USER = uuid.uuid4()


def _face(**fields: object) -> FaceResponse:
    return FaceResponse.model_validate({
        "detection_id": uuid.uuid4(),
        "source_id": uuid.uuid4(),
        "bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4},
        "keypoints": [
            {"type": name, "x": 1.0, "y": 1.0}
            for name in ("left_eye", "right_eye", "nose", "right_mouth_corner", "left_mouth_corner")
        ],
        "user_id": USER,
        "confidence": 0.9,
        **fields,
    })


def _mention(**fields: object) -> TextMentionResponse:
    return TextMentionResponse.model_validate({
        "mention_id": uuid.uuid4(), "name": "Jan Novak", "context": "Jan Novak signed.",
        "entity_id": None, "source_id": uuid.uuid4(), **fields,
    })


class Api:
    """The v1 API over a fake database, with one session stream to read back."""

    def __init__(self, client: httpx.AsyncClient, hub: EventHub, app: FastAPI) -> None:
        super().__init__()
        self.client, self.hub, self.app = client, hub, app
        self.session = uuid.uuid4()

    async def subscribe(self, *topics: dict[str, str]) -> httpx.Response:
        return await self.client.patch(
            f"/api/v1/events/{self.session}/topics", json={"subscribe": list(topics)}
        )

    async def frames(self, act: Callable[[], Awaitable[Any]]) -> list[dict[str, Any]]:
        """Open the stream, run ``act`` and return every frame it produced."""
        stream = asyncio.create_task(self.client.get(f"/api/v1/events/{self.session}"))
        while not self.hub.subscriptions(self.session, USER).connected:
            await asyncio.sleep(0)
        await act()
        queue = self.hub._sessions[self.session].queue  # pyright: ignore[reportPrivateUsage]
        while queue is not None and not queue.empty():  # let the stream send what was published
            await asyncio.sleep(0)
        with self.hub.connect(self.session, USER):  # a newer stream ends the request
            response = await stream
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines() if line.startswith("data: ")
        ]

    async def changes(self, act: Callable[[], Awaitable[Any]]) -> set[tuple[str, str, str, str, str | None]]:
        """Changes as (topic kind, topic id, scope, change, object id)."""
        hello, *events = await self.frames(act)
        assert hello["type"] == "session"
        assert all(event["type"] == "change" for event in events)
        return {
            (
                event["topic"]["kind"], event["topic"]["id"], event["topic"]["scope"],
                event["change"], event["object"] and event["object"]["id"],
            )
            for event in events
        }


@asynccontextmanager
async def _api(user_id: uuid.UUID = USER, hub: EventHub | None = None, **repositories: Any) -> AsyncGenerator[Api]:
    app = FastAPI()
    app.include_router(v1_router)
    hub = hub or EventHub()
    database = SimpleNamespace(**repositories)

    @asynccontextmanager
    async def context() -> AsyncGenerator[SimpleNamespace]:
        yield database

    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_database_context] = context
    app.dependency_overrides[get_event_hub] = lambda: hub
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(user_id=user_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield Api(client, hub, app)


def _topic(kind: str, object_id: uuid.UUID | None = None, scope: str = "self") -> dict[str, Any]:
    return {"kind": kind, "id": object_id and str(object_id), "scope": scope}


def test_event_routes_are_documented() -> None:
    app = FastAPI()
    app.include_router(v1_router)
    schema = app.openapi()

    stream = schema["paths"]["/api/v1/events/{session_id}"]["get"]
    assert "text/event-stream" in stream["responses"]["200"]["content"]
    assert {"get", "patch"} <= schema["paths"]["/api/v1/events/{session_id}/topics"].keys()
    assert {"SessionEvent", "ChangeEvent", "Topic", "ObjectRef"} <= schema["components"]["schemas"].keys()


@pytest.mark.asyncio
async def test_subscriptions_are_configured_beside_the_stream() -> None:
    entity = uuid.uuid4()
    async with _api() as api:
        url = f"/api/v1/events/{api.session}/topics"
        assert (await api.client.get(url)).json() == {
            "session_id": str(api.session), "connected": False, "topics": [],
        }

        response = await api.subscribe(_topic("entity", entity), _topic("entity", entity, "related"))
        assert response.status_code == 200
        assert response.json()["topics"] == [_topic("entity", entity), _topic("entity", entity, "related")]

        response = await api.client.patch(url, json={"unsubscribe": [{"kind": "entity", "id": str(entity)}]})
        assert response.json()["topics"] == [_topic("entity", entity, "related")]

        rejected = await api.client.patch(url, json={"subscribe": [_topic("face", uuid.uuid4(), "related")]})
        assert rejected.status_code == 422
        assert (await api.client.get(url)).json()["topics"] == [_topic("entity", entity, "related")]


@pytest.mark.asyncio
async def test_another_users_session_is_not_found() -> None:
    hub = EventHub()
    async with _api(hub=hub) as owner, _api(user_id=uuid.uuid4(), hub=hub) as intruder:
        await owner.subscribe(_topic("face"))
        url = f"/api/v1/events/{owner.session}"

        assert (await intruder.client.get(url)).status_code == 404
        assert (await intruder.client.get(url + "/topics")).status_code == 404
        assert (await intruder.client.patch(url + "/topics", json={})).status_code == 404
        assert hub.subscriptions(owner.session, USER).topics


@pytest.mark.asyncio
async def test_the_stream_starts_with_the_sessions_topics() -> None:
    async with _api() as api:
        await api.subscribe(_topic("mention"))

        async def nothing() -> None:
            assert (await api.client.get(f"/api/v1/events/{api.session}/topics")).json()["connected"]

        assert await api.frames(nothing) == [
            {"type": "session", "session_id": str(api.session), "topics": [_topic("mention")]},
        ]


@pytest.mark.asyncio
async def test_reassigning_a_face_notifies_the_face_source_and_both_entities() -> None:
    old, new = uuid.uuid4(), uuid.uuid4()
    before = _face(entity_id=old)
    after = before.model_copy(update={"entity_id": new})
    face, source = str(before.detection_id), str(before.source_id)
    faces = SimpleNamespace(get=AsyncMock(return_value=before), patch=AsyncMock(return_value=after))

    async with _api(faces=faces) as api:
        await api.subscribe(
            _topic("face", before.detection_id), _topic("face"),
            _topic("source", before.source_id, "related"), _topic("source", before.source_id),
            _topic("entity", old, "related"), _topic("entity", new, "related"),
            _topic("entity", uuid.uuid4(), "related"),
        )
        changes = await api.changes(lambda: api.client.patch(
            f"/api/v1/faces/{face}", json={"entity_id": str(new)},
        ))

    assert changes == {
        ("face", face, "self", "updated", face),
        ("face", None, "self", "updated", face),
        ("source", source, "related", "updated", face),
        ("entity", str(old), "related", "updated", face),
        ("entity", str(new), "related", "updated", face),
    }


@pytest.mark.asyncio
async def test_mention_create_and_delete_notify_source_and_entity() -> None:
    entity = uuid.uuid4()
    mention = _mention(entity_id=entity)
    mention_id, source = str(mention.mention_id), str(mention.source_id)
    mentions = SimpleNamespace(
        create=AsyncMock(return_value=mention),
        get=AsyncMock(return_value=mention),
        delete=AsyncMock(return_value=True),
    )

    async with _api(text_mentions=mentions) as api:
        await api.subscribe(_topic("source", mention.source_id, "related"), _topic("entity", entity, "related"))

        async def act() -> None:
            created = await api.client.post("/api/v1/text-mentions", json={
                "name": "Jan Novak", "source_id": source, "entity_id": str(entity), "entity_link_state": "manual",
            })
            assert created.status_code == 201
            assert (await api.client.delete(f"/api/v1/text-mentions/{mention_id}")).status_code == 204

        changes = await api.changes(act)

    assert changes == {
        ("source", source, "related", change, mention_id) for change in ("created", "deleted")
    } | {
        ("entity", str(entity), "related", change, mention_id) for change in ("created", "deleted")
    }


@pytest.mark.asyncio
async def test_failed_writes_publish_nothing() -> None:
    face = _face()
    faces = SimpleNamespace(
        get=AsyncMock(return_value=None),
        patch=AsyncMock(return_value=None),
        delete=AsyncMock(return_value=False),
        create=AsyncMock(side_effect=ValueError("unknown source")),
    )

    async with _api(faces=faces) as api:
        await api.subscribe(_topic("face"))

        async def act() -> None:
            url = f"/api/v1/faces/{face.detection_id}"
            assert (await api.client.patch(url, json={"entity_id": None})).status_code == 404
            assert (await api.client.delete(url)).status_code == 404
            created = await api.client.post("/api/v1/faces", json=face.model_dump(mode="json"))
            assert created.status_code == 422

        assert await api.changes(act) == set()


@pytest.mark.asyncio
async def test_writes_read_nothing_extra_while_nobody_is_subscribed() -> None:
    face = _face()
    faces = SimpleNamespace(
        get=AsyncMock(return_value=face),
        patch=AsyncMock(return_value=face),
        delete=AsyncMock(return_value=True),
    )

    async with _api(faces=faces) as api:
        url = f"/api/v1/faces/{face.detection_id}"
        assert (await api.client.patch(url, json={"entity_id": None})).status_code == 200
        assert (await api.client.delete(url)).status_code == 204

    faces.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_merge_and_delete_notify_entity_topics() -> None:
    target, merged, deleted = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entity = {"entity_id": str(target), "entity_type": "person", "name": "Ada Novak", "user_id": str(USER)}
    entities = SimpleNamespace(
        merge=AsyncMock(return_value=EntityMergeResponse.model_validate({
            "source_entity_id": merged, "target_entity_id": target,
            "faces_reassigned": 1, "text_mentions_reassigned": 0, "merged_entity": entity,
        })),
        delete=AsyncMock(return_value=True),
    )

    async with _api(entities=entities) as api:
        await api.subscribe(
            _topic("entity", target), _topic("entity", target, "related"),
            _topic("entity", merged), _topic("entity", deleted, "related"),
        )

        async def act() -> None:
            response = await api.client.post(
                f"/api/v1/entities/{target}:merge", json={"source_entity_id": str(merged)},
            )
            assert response.status_code == 200, response.text
            assert (await api.client.delete(f"/api/v1/entities/{deleted}")).status_code == 204

        changes = await api.changes(act)

    assert changes == {
        ("entity", str(target), "self", "updated", str(target)),
        ("entity", str(target), "related", "updated", None),
        ("entity", str(merged), "self", "deleted", str(merged)),
        ("entity", str(deleted), "related", "deleted", str(deleted)),
    }


@pytest.mark.asyncio
async def test_new_pages_notify_their_document_once_per_request() -> None:
    document_id = uuid.uuid4()
    document = DocumentResponse.model_validate({
        "source_id": uuid.uuid4(), "source_type": "document", "url": "https://example.test/d",
        "library": "mzk", "document_id": document_id,
    })
    pages = [
        PageResponse.model_validate({
            "source_id": uuid.uuid4(), "source_type": "page", "url": f"https://example.test/p{index}",
            "library": "mzk", "document_id": document_id, "page_id": uuid.uuid4(),
        })
        for index in range(3)
    ]
    results = [(pages[0], CreateResult.CREATED), (pages[1], CreateResult.EXISTING), (pages[2], CreateResult.CREATED)]
    sources = SimpleNamespace(
        get_or_create_page_batch=AsyncMock(return_value=results),
        lookup_document=AsyncMock(return_value=document),
    )

    async with _api(sources=sources) as api:
        await api.subscribe(
            _topic("source", document.source_id, "related"),
            *(_topic("source", page.source_id) for page in pages),
        )
        changes = await api.changes(lambda: api.client.post("/api/v1/pages:batch", json=[
            {"library": "mzk", "document_id": str(document_id), "page_id": str(page.page_id)} for page in pages
        ]))

    assert changes == {
        ("source", str(document.source_id), "related", "created", None),
        ("source", str(pages[0].source_id), "self", "created", str(pages[0].source_id)),
        ("source", str(pages[2].source_id), "self", "created", str(pages[2].source_id)),
    }
    sources.lookup_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_reassignment_and_delete_reach_subscribers(
    migrated_postgres: AsyncEngine, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading the prior link in the request's own session must not disturb the write."""
    sessions = database_service.make_postgres_session_factory(migrated_postgres)
    async with sessions() as session:
        database = postgres_database(session)
        user = await database.users.get_or_create(UserCreateRequest(
            display_name="Event reviewer", is_active=True,
            external_subject="event-reviewer", external_issuer="urn:people-gator:tests",
        ))
        actor = GenericActor(user_id=user.user_id)
        old, new = [
            (await database.entities.create(EntityCreateRequest(entity_type=EntityType.person, name=name), actor)).entity_id
            for name in ("Ada Events", "Bea Events")
        ]
        library, document_id = "events", uuid.uuid4()
        document, _ = await database.sources.get_or_create_document(
            DocumentCreateRequest(library=library, document_id=document_id, name="Events"), context=actor,
        )
        page, _ = await database.sources.get_or_create_page(
            PageCreateRequest(library=library, document_id=document_id, page_id=uuid.uuid4()), context=actor,
        )
        mention = await database.text_mentions.create(TextMentionCreateRequest(
            name="Ada Events", source_id=page.source_id, entity_id=old, entity_link_state=EntityLinkState.manual,
        ), actor)
    monkeypatch.setattr(database_service, "_postgres_engine", migrated_postgres)
    monkeypatch.setattr(database_service, "_postgres_sessions", sessions)
    mention_id, source = str(mention.mention_id), str(page.source_id)

    async with _api(user_id=user.user_id) as api:
        api.app.dependency_overrides.pop(get_database)
        api.app.dependency_overrides.pop(get_database_context)
        url = f"/api/v1/text-mentions/{mention_id}"
        await api.subscribe(
            _topic("mention", mention.mention_id), _topic("source", page.source_id, "related"),
            _topic("entity", old, "related"), _topic("entity", new, "related"),
            _topic("source", document.source_id, "related"), _topic("source", page.source_id),
        )
        stream = asyncio.create_task(api.client.get(f"/api/v1/events/{api.session}"))
        while not api.hub.subscriptions(api.session, user.user_id).connected:
            await asyncio.sleep(0)

        patched = await api.client.patch(url, json={"entity_id": str(new), "entity_link_state": "manual"})
        assert patched.status_code == 200, patched.text
        assert patched.json()["entity_id"] == str(new)
        verified = await api.client.patch(f"/api/v1/pages/{source}", json={"verification_state": "verified"})
        assert verified.status_code == 200, verified.text
        assert (await api.client.delete(url)).status_code == 204
        assert (await api.client.get(url)).status_code == 404

        queue = api.hub._sessions[api.session].queue  # pyright: ignore[reportPrivateUsage]
        while queue is not None and not queue.empty():
            await asyncio.sleep(0)
        with api.hub.connect(api.session, user.user_id):
            response = await stream

    events = [
        (event["topic"]["kind"], event["topic"]["id"], event["topic"]["scope"], event["change"], event["object"]["id"])
        for event in (json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: "))
        if event["type"] == "change"
    ]
    assert sorted(events[:4]) == sorted([
        ("mention", mention_id, "self", "updated", mention_id),
        ("source", source, "related", "updated", mention_id),
        ("entity", str(old), "related", "updated", mention_id),
        ("entity", str(new), "related", "updated", mention_id),
    ])
    assert sorted(events[4:6]) == sorted([
        ("source", source, "self", "updated", source),
        ("source", str(document.source_id), "related", "updated", source),
    ])
    # After the move only the new entity hears about the deletion.
    assert sorted(events[6:]) == sorted([
        ("mention", mention_id, "self", "deleted", mention_id),
        ("source", source, "related", "deleted", mention_id),
        ("entity", str(new), "related", "deleted", mention_id),
    ])
