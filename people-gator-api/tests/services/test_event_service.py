"""Session/topic hub for live change notifications (#209)."""

import asyncio
import uuid

import pytest
from pydantic import ValidationError

from people_gator_api.schemas.events import (
    MAX_SESSION_TOPICS,
    ChangeEvent,
    ChangeKind,
    ObjectRef,
    Topic,
    TopicKind,
    TopicScope,
)
from people_gator_api.services.event_service import (
    ChangeSet,
    Connection,
    EventHub,
    SessionLimitError,
    SessionOwnershipError,
    TopicLimitError,
)


USER = uuid.uuid4()


def _topic(kind: TopicKind, object_id: uuid.UUID | None = None, scope: TopicScope = TopicScope.SELF) -> Topic:
    return Topic(kind=kind, id=object_id, scope=scope)


async def _drain(connection: Connection) -> list[ChangeEvent]:
    """Return what is queued now without waiting for further events."""
    events: list[ChangeEvent] = []
    iterator = connection.events()
    while True:
        try:
            events.append(await asyncio.wait_for(anext(iterator), 0.01))
        except (TimeoutError, StopAsyncIteration):
            return events


def _link_change(kind: TopicKind, change: ChangeKind, *ids: uuid.UUID | None) -> ChangeSet:
    object_id, source_id, *entity_ids = ids
    assert object_id is not None and source_id is not None
    changes = ChangeSet()
    changes.link(kind, change, object_id, source_id, *entity_ids)
    return changes


@pytest.mark.parametrize("fields", [
    {"kind": "face", "id": str(uuid.uuid4()), "scope": "related"},
    {"kind": "mention", "id": str(uuid.uuid4()), "scope": "related"},
    {"kind": "entity", "scope": "related"},
])
def test_related_topics_need_an_entity_or_source_id(fields: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Topic.model_validate(fields)


@pytest.mark.asyncio
async def test_a_session_receives_only_its_subscribed_topics() -> None:
    hub = EventHub()
    session, other = uuid.uuid4(), uuid.uuid4()
    face, source, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    hub.update(session, USER, subscribe=[_topic(TopicKind.FACE, face)])
    hub.update(other, USER, subscribe=[_topic(TopicKind.MENTION)])

    with hub.connect(session, USER) as mine, hub.connect(other, USER) as theirs:
        assert mine.hello.topics == [_topic(TopicKind.FACE, face)]
        hub.publish(_link_change(TopicKind.FACE, ChangeKind.UPDATED, face, source, entity))
        hub.publish(_link_change(TopicKind.FACE, ChangeKind.UPDATED, uuid.uuid4(), source, entity))

        assert await _drain(mine) == [ChangeEvent(
            topic=_topic(TopicKind.FACE, face),
            change=ChangeKind.UPDATED,
            object=ObjectRef(kind=TopicKind.FACE, id=face),
        )]
        assert await _drain(theirs) == []


@pytest.mark.asyncio
async def test_reassignment_notifies_the_source_and_both_entities() -> None:
    hub = EventHub()
    session = uuid.uuid4()
    mention, source, old, new = (uuid.uuid4() for _ in range(4))
    topics = [
        _topic(TopicKind.SOURCE, source, TopicScope.RELATED),
        _topic(TopicKind.ENTITY, old, TopicScope.RELATED),
        _topic(TopicKind.ENTITY, new, TopicScope.RELATED),
        _topic(TopicKind.ENTITY, new),  # the entity itself did not change
    ]
    hub.update(session, USER, subscribe=topics)

    with hub.connect(session, USER) as connection:
        hub.publish(_link_change(TopicKind.MENTION, ChangeKind.UPDATED, mention, source, new, old))
        events = await _drain(connection)

    assert len(events) == 3 and {event.topic for event in events} == set(topics[:3])
    assert {event.object for event in events} == {ObjectRef(kind=TopicKind.MENTION, id=mention)}


@pytest.mark.asyncio
async def test_unsubscribing_stops_events_while_the_stream_stays_open() -> None:
    hub = EventHub()
    session, entity = uuid.uuid4(), uuid.uuid4()
    topic = _topic(TopicKind.ENTITY, entity)
    hub.update(session, USER, subscribe=[topic])
    changes = ChangeSet()
    changes.entity(ChangeKind.UPDATED, entity)

    with hub.connect(session, USER) as connection:
        hub.publish(changes)
        assert len(await _drain(connection)) == 1

        assert hub.update(session, USER, unsubscribe=[topic]).topics == []
        assert not hub.active
        hub.publish(changes)
        assert await _drain(connection) == []

        hub.update(session, USER, subscribe=[topic, topic])
        hub.publish(changes)
        assert len(await _drain(connection)) == 1


@pytest.mark.asyncio
async def test_one_request_sends_one_event_per_topic() -> None:
    hub = EventHub()
    session, source = uuid.uuid4(), uuid.uuid4()
    related = _topic(TopicKind.SOURCE, source, TopicScope.RELATED)
    hub.update(session, USER, subscribe=[related, _topic(TopicKind.FACE)])
    changes = ChangeSet()
    for _ in range(3):
        changes.link(TopicKind.FACE, ChangeKind.CREATED, uuid.uuid4(), source, None)

    with hub.connect(session, USER) as connection:
        hub.publish(changes)
        events = await _drain(connection)

    assert events == [
        ChangeEvent(topic=_topic(TopicKind.FACE), change=ChangeKind.CREATED, object=None),
        ChangeEvent(topic=related, change=ChangeKind.CREATED, object=None),
    ]


@pytest.mark.asyncio
async def test_deleting_and_merging_entities_notify_their_related_topics() -> None:
    hub = EventHub()
    session, target, merged = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    hub.update(session, USER, subscribe=[
        _topic(TopicKind.ENTITY, target, TopicScope.RELATED),
        _topic(TopicKind.ENTITY, merged, TopicScope.RELATED),
        _topic(TopicKind.ENTITY, merged),
    ])
    changes = ChangeSet()
    changes.merge(target, [merged])

    with hub.connect(session, USER) as connection:
        hub.publish(changes)
        events = {(event.topic.id, event.topic.scope): event for event in await _drain(connection)}

    gone = ObjectRef(kind=TopicKind.ENTITY, id=merged)
    assert events[target, TopicScope.RELATED].object is None
    assert events[target, TopicScope.RELATED].change is ChangeKind.UPDATED
    assert events[merged, TopicScope.RELATED] == ChangeEvent(
        topic=_topic(TopicKind.ENTITY, merged, TopicScope.RELATED), change=ChangeKind.DELETED, object=gone,
    )
    assert events[merged, TopicScope.SELF].change is ChangeKind.DELETED


@pytest.mark.asyncio
async def test_a_page_change_notifies_its_document() -> None:
    hub = EventHub()
    session, page, document = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    hub.update(session, USER, subscribe=[_topic(TopicKind.SOURCE, document, TopicScope.RELATED)])
    changes = ChangeSet()
    changes.source(ChangeKind.UPDATED, page, document)

    with hub.connect(session, USER) as connection:
        hub.publish(changes)
        (event,) = await _drain(connection)

    assert event.object == ObjectRef(kind=TopicKind.SOURCE, id=page)


def test_a_session_belongs_to_its_first_user() -> None:
    hub = EventHub()
    session = uuid.uuid4()
    hub.subscriptions(session, USER)

    with pytest.raises(SessionOwnershipError):
        hub.update(session, uuid.uuid4(), subscribe=[_topic(TopicKind.FACE)])
    with pytest.raises(SessionOwnershipError), hub.connect(session, uuid.uuid4()):
        pass


def test_topic_and_session_limits() -> None:
    hub = EventHub(max_user_sessions=2)
    session = uuid.uuid4()
    topics = [_topic(TopicKind.FACE, uuid.uuid4()) for _ in range(MAX_SESSION_TOPICS)]
    hub.update(session, USER, subscribe=topics)
    with pytest.raises(TopicLimitError):
        hub.update(session, USER, subscribe=[_topic(TopicKind.FACE)])
    # Swapping within the limit works, and a rejected update changed nothing.
    assert len(hub.update(session, USER, subscribe=[_topic(TopicKind.FACE)], unsubscribe=topics[:1]).topics) == MAX_SESSION_TOPICS

    with hub.connect(session, USER), hub.connect(uuid.uuid4(), USER):
        with pytest.raises(SessionLimitError):
            hub.subscriptions(uuid.uuid4(), USER)
        hub.subscriptions(uuid.uuid4(), uuid.uuid4())  # another user is unaffected
    # A detached session makes room for a new one.
    hub.subscriptions(uuid.uuid4(), USER)


def test_sessions_without_a_stream_expire() -> None:
    now = [0.0]
    hub = EventHub(idle_seconds=60, clock=lambda: now[0])
    session = uuid.uuid4()
    hub.update(session, USER, subscribe=[_topic(TopicKind.FACE)])

    with hub.connect(session, USER):
        now[0] = 1000
        assert hub.active  # a connected session never expires
    now[0] += 59
    assert hub.subscriptions(session, USER).topics
    now[0] += 1
    assert not hub.active
    assert hub.subscriptions(session, USER).topics == []


@pytest.mark.asyncio
async def test_a_newer_stream_ends_the_older_one() -> None:
    hub = EventHub()
    session = uuid.uuid4()
    hub.update(session, USER, subscribe=[_topic(TopicKind.FACE)])
    changes = ChangeSet()
    changes.changed(TopicKind.FACE, uuid.uuid4(), ChangeKind.CREATED)

    with hub.connect(session, USER) as older:
        with hub.connect(session, USER) as newer:
            hub.publish(changes)
            assert [event async for event in older.events()] == []
            assert len(await _drain(newer)) == 1
        assert not hub.subscriptions(session, USER).connected
    # The older stream's late cleanup must not disturb the session.
    assert hub.subscriptions(session, USER).topics


@pytest.mark.asyncio
async def test_a_client_that_falls_behind_is_disconnected() -> None:
    hub = EventHub(queue_size=2)
    session = uuid.uuid4()
    hub.update(session, USER, subscribe=[_topic(TopicKind.FACE)])

    with hub.connect(session, USER) as connection:
        for _ in range(3):
            changes = ChangeSet()
            changes.changed(TopicKind.FACE, uuid.uuid4(), ChangeKind.CREATED)
            hub.publish(changes)

        assert [event async for event in connection.events()] == []
        assert not hub.subscriptions(session, USER).connected
