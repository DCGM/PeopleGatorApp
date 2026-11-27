"""Process-local hub for live change notifications.

A client owns a session, subscribes it to topics and reads its events from one
stream. Mutation routes describe what they changed in a :class:`ChangeSet` and
publish it after their transaction committed. Delivery is best effort: nothing
is stored or replayed, and other processes do not see each other's changes.
The public contract is documented in ``docs/EVENTS.md``.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends

from people_gator_api.schemas.events import (
    MAX_SESSION_TOPICS,
    ChangeEvent,
    ChangeKind,
    ObjectRef,
    SessionEvent,
    SubscriptionsResponse,
    Topic,
    TopicKind,
    TopicScope,
)


type _Hit = tuple[ChangeKind, ObjectRef | None]


class SessionOwnershipError(Exception):
    """The session ID belongs to another user."""


class SessionLimitError(Exception):
    """The user already has the maximum number of connected sessions."""


class TopicLimitError(ValueError):
    """The session would exceed its topic limit."""


class ChangeSet:
    """What one request changed, grouped by the topics it concerns."""

    def __init__(self) -> None:
        super().__init__()
        self.hits: dict[Topic, list[_Hit]] = {}

    def changed(self, kind: TopicKind, object_id: uuid.UUID, change: ChangeKind) -> ObjectRef:
        """Record a change of the object itself."""
        ref = ObjectRef(kind=kind, id=object_id)
        self.hits.setdefault(Topic(kind=kind, id=object_id), []).append((change, ref))
        self.hits.setdefault(Topic(kind=kind), []).append((change, ref))
        return ref

    def several(self, kind: TopicKind, change: ChangeKind) -> None:
        """Record a bulk change whose objects are not known individually."""
        self.hits.setdefault(Topic(kind=kind), []).append((change, None))

    def related(
        self,
        kind: TopicKind,
        parent_id: uuid.UUID,
        change: ChangeKind,
        ref: ObjectRef | None,
    ) -> None:
        """Record that something related to an entity or source changed."""
        topic = Topic(kind=kind, id=parent_id, scope=TopicScope.RELATED)
        self.hits.setdefault(topic, []).append((change, ref))

    def link(
        self,
        kind: TopicKind,
        change: ChangeKind,
        object_id: uuid.UUID,
        source_id: uuid.UUID,
        *entity_ids: uuid.UUID | None,
    ) -> None:
        """Record a face or mention change for its source and its old/new entity."""
        ref = self.changed(kind, object_id, change)
        self.related(TopicKind.SOURCE, source_id, change, ref)
        for entity_id in dict.fromkeys(entity_ids):
            if entity_id is not None:
                self.related(TopicKind.ENTITY, entity_id, change, ref)

    def entity(self, change: ChangeKind, entity_id: uuid.UUID) -> None:
        ref = self.changed(TopicKind.ENTITY, entity_id, change)
        if change is ChangeKind.DELETED:
            self.related(TopicKind.ENTITY, entity_id, change, ref)

    def merge(self, target_id: uuid.UUID, merged_ids: Iterable[uuid.UUID]) -> None:
        """Record a merge: the target changed and gained links, the others are gone."""
        self.entity(ChangeKind.UPDATED, target_id)
        self.related(TopicKind.ENTITY, target_id, ChangeKind.UPDATED, None)
        for merged_id in merged_ids:
            self.entity(ChangeKind.DELETED, merged_id)

    def source(
        self,
        change: ChangeKind,
        source_id: uuid.UUID,
        parent_id: uuid.UUID | None = None,
    ) -> None:
        """Record a source change; a page also concerns its document (the parent)."""
        ref = self.changed(TopicKind.SOURCE, source_id, change)
        if change is ChangeKind.DELETED:
            self.related(TopicKind.SOURCE, source_id, change, ref)
        if parent_id is not None:
            self.related(TopicKind.SOURCE, parent_id, change, ref)


def _event(topic: Topic, hits: list[_Hit]) -> ChangeEvent:
    """One event per topic and request; several objects collapse to ``object: null``."""
    distinct = list(dict.fromkeys(hits))
    if len(distinct) == 1:
        change, ref = distinct[0]
        return ChangeEvent(topic=topic, change=change, object=ref)
    changes = {change for change, _ in distinct}
    change = changes.pop() if len(changes) == 1 else ChangeKind.UPDATED
    return ChangeEvent(topic=topic, change=change, object=None)


@dataclass(slots=True)
class _Session:
    user_id: uuid.UUID
    idle_deadline: float | None
    topics: dict[Topic, None] = field(default_factory=dict[Topic, None])
    queue: asyncio.Queue[ChangeEvent | None] | None = None


@dataclass(frozen=True, slots=True)
class Connection:
    """An attached stream: the hello frame, then events until the stream is ended."""

    hello: SessionEvent
    _queue: asyncio.Queue[ChangeEvent | None]

    async def events(self) -> AsyncIterator[ChangeEvent]:
        while (event := await self._queue.get()) is not None:
            yield event


class EventHub:
    """Sessions, their topic subscriptions and best-effort fan-out."""

    def __init__(
        self,
        *,
        idle_seconds: float = 60.0,
        queue_size: int = 1000,
        max_user_sessions: int = 16,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self._idle_seconds = idle_seconds
        self._queue_size = queue_size
        self._max_user_sessions = max_user_sessions
        self._clock = clock
        self._sessions: dict[uuid.UUID, _Session] = {}
        self._subscribers: dict[Topic, set[uuid.UUID]] = {}

    @property
    def active(self) -> bool:
        """Whether any session is subscribed; publishers skip their work otherwise."""
        self._purge()
        return bool(self._subscribers)

    def subscriptions(self, session_id: uuid.UUID, user_id: uuid.UUID) -> SubscriptionsResponse:
        """Return the session, creating it for this user when it does not exist."""
        return self._response(session_id, self._session(session_id, user_id))

    def update(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        subscribe: Iterable[Topic] = (),
        unsubscribe: Iterable[Topic] = (),
    ) -> SubscriptionsResponse:
        session = self._session(session_id, user_id)
        topics = dict(session.topics)
        for topic in unsubscribe:
            topics.pop(topic, None)
        topics.update(dict.fromkeys(subscribe))
        if len(topics) > MAX_SESSION_TOPICS:
            raise TopicLimitError(f"A session can follow at most {MAX_SESSION_TOPICS} topics")
        for topic in session.topics.keys() - topics.keys():
            self._unsubscribe(session_id, topic)
        for topic in topics.keys() - session.topics.keys():
            self._subscribers.setdefault(topic, set()).add(session_id)
        session.topics = topics
        return self._response(session_id, session)

    @contextmanager
    def connect(self, session_id: uuid.UUID, user_id: uuid.UUID) -> Generator[Connection]:
        """Attach the session's single stream; a newer connection ends the older one."""
        session = self._session(session_id, user_id)
        self._end(session)
        queue = asyncio.Queue[ChangeEvent | None](maxsize=self._queue_size)
        session.queue = queue
        session.idle_deadline = None
        try:
            yield Connection(
                SessionEvent(session_id=session_id, topics=list(session.topics)), queue
            )
        finally:
            if session.queue is queue:
                self._detach(session)

    def publish(self, changes: ChangeSet) -> None:
        """Queue one event per subscribed topic. Never blocks or raises for a slow client."""
        self._purge()
        for topic, hits in changes.hits.items():
            subscribers = self._subscribers.get(topic)
            if not subscribers:
                continue
            event = _event(topic, hits)
            for session_id in subscribers:
                session = self._sessions[session_id]
                if session.queue is None:
                    continue
                try:
                    session.queue.put_nowait(event)
                except asyncio.QueueFull:
                    # The client fell behind. End its stream so that it
                    # reconnects and refetches instead of acting on a gap.
                    self._end(session)

    def _session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> _Session:
        self._purge()
        session = self._sessions.get(session_id)
        if session is not None:
            if session.user_id != user_id:
                raise SessionOwnershipError
            return session
        owned = [(key, value) for key, value in self._sessions.items() if value.user_id == user_id]
        if len(owned) >= self._max_user_sessions:
            idle = [(value.idle_deadline, key) for key, value in owned if value.idle_deadline is not None]
            if not idle:
                raise SessionLimitError
            self._remove(min(idle, key=lambda item: item[0])[1])
        session = _Session(user_id=user_id, idle_deadline=self._clock() + self._idle_seconds)
        self._sessions[session_id] = session
        return session

    def _response(self, session_id: uuid.UUID, session: _Session) -> SubscriptionsResponse:
        return SubscriptionsResponse(
            session_id=session_id,
            connected=session.queue is not None,
            topics=list(session.topics),
        )

    def _unsubscribe(self, session_id: uuid.UUID, topic: Topic) -> None:
        subscribers = self._subscribers[topic]
        subscribers.discard(session_id)
        if not subscribers:
            del self._subscribers[topic]

    def _detach(self, session: _Session) -> None:
        session.queue = None
        session.idle_deadline = self._clock() + self._idle_seconds

    def _end(self, session: _Session) -> None:
        """End the attached stream, dropping what it had not read yet."""
        queue = session.queue
        if queue is None:
            return
        self._detach(session)
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait(None)

    def _remove(self, session_id: uuid.UUID) -> None:
        session = self._sessions.pop(session_id)
        for topic in session.topics:
            self._unsubscribe(session_id, topic)

    def _purge(self) -> None:
        """Forget sessions that stayed without a stream for the idle period."""
        now = self._clock()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.idle_deadline is not None and session.idle_deadline <= now
        ]
        for session_id in expired:
            self._remove(session_id)


_event_hub = EventHub()


def get_event_hub() -> EventHub:
    """Return the application-wide hub."""
    return _event_hub


type EventHubDependency = Annotated[EventHub, Depends(get_event_hub)]


__all__ = [
    "ChangeSet",
    "Connection",
    "EventHub",
    "EventHubDependency",
    "SessionLimitError",
    "SessionOwnershipError",
    "TopicLimitError",
    "get_event_hub",
]
