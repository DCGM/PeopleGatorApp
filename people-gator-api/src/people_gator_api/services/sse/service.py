"""Backend-independent topic delivery for server-sent events.

The public broker contract is documented in ``docs/05-sse.md``. Topics are
slash-like tuples, and publishing to a leaf fans the event out to that topic
and each non-empty ancestor. ``LocalTopicBroker`` is process-local and does
not provide replay or durable delivery.

Internal queues carry plain ``dict`` snapshots produced by ``model_dump``.
``stream[T]`` and ``subscribe[T]`` accept the target Pydantic model class and
reconstruct typed instances via ``model_validate`` before yielding them.
FastAPI serialises ``AsyncIterator[BaseModel]`` directly into SSE frames, so
endpoints can declare ``-> AsyncIterator[SomeModel]`` without extra plumbing.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Protocol, TypeVar, NamedTuple
from fastapi import Depends
from pydantic import BaseModel
import uuid

type Topic = tuple[str | uuid.UUID | None, ...]
type _TopicStr = tuple[str, ...]
# Internal queue item: a plain dict produced by model_dump, or None to
# signal subscriber stream termination.

class _Event(NamedTuple):
    event: str
    data: dict[str, object]
type _QueuedEvent = _Event | None

T = TypeVar("T", bound=BaseModel)


class DeletedResourceEvent(BaseModel):
    """Minimal payload emitted after a single resource has been deleted."""

    resource_id: uuid.UUID


def _topic_to_str(topic: Topic) -> _TopicStr:
    return tuple(str(part) for part in topic)


class SseEventType(StrEnum):
    """Wire-level event names published through the SSE broker."""

    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    MODEL_AGENT_CREATED = "model_agent_created"
    MODEL_AGENT_UPDATED = "model_agent_updated"
    MODEL_AGENT_DELETED = "model_agent_deleted"

    ENTITY_CREATED = "entity_created"
    ENTITY_UPDATED = "entity_updated"
    ENTITY_DELETED = "entity_deleted"

    DOCUMENT_MENTION_CREATED = "document_mention_created"
    DOCUMENT_MENTION_UPDATED = "document_mention_updated"

    PAGE_MENTION_CREATED = "page_mention_created"

    FACE_CREATED = "face_created"
    FACE_UPDATED = "face_updated"

    SOURCE_CREATED = "source_created"
    SOURCE_UPDATED = "source_updated"
    SOURCE_DELETED = "source_deleted"


class TopicBroker(Protocol):
    """Transport contract shared by local and future distributed brokers."""

    def subscribe[T: BaseModel](
        self, model: type[T], topic: Topic
    ) -> AbstractAsyncContextManager[AsyncIterator[T]]: ...

    def stream[T: BaseModel](
        self, model: type[T], topic: Topic
    ) -> AsyncIterator[T]: ...

    def close_topic(self, topic: Topic) -> None: ...

    async def publish_single(
        self,
        topic: Topic,
        event: SseEventType,
        data: BaseModel,
        id: str | None = None,
        retry: int | None = None,
        comment: str | None = None,
    ) -> None: ...

    async def publish(
        self,
        *topics: Topic,
        event: SseEventType,
        data: BaseModel,
    ) -> None: ...

    async def publish_batch(
        self,
        batch: Iterable[tuple[Topic, SseEventType, BaseModel]],
    ) -> None: ...

    def publish_batch_task(
        self,
        batch: Iterable[tuple[Topic, SseEventType, BaseModel]],
    ) -> asyncio.Task[None]: ...

    def publish_task(
        self,
        *topics: Topic,
        event: SseEventType,
        data: BaseModel,
    ) -> asyncio.Task[None]: ...

    def subscriber_counts(self) -> dict[tuple[str, ...], int]: ...


def _new_subscriptions() -> dict[_TopicStr, set[asyncio.Queue[_QueuedEvent]]]:
    return {}


@dataclass(slots=True)
class LocalTopicBroker:
    """In-process broker backed by one asynchronous queue per subscriber.

    Subscriptions are removed when their async context exits. Queues are
    intentionally unbounded in this initial implementation; durable or
    distributed delivery belongs in a future ``TopicBroker`` implementation.
    """

    _max_notification_depth: int = 1
    _subscriptions: dict[_TopicStr, set[asyncio.Queue[_QueuedEvent]]] = field(
        default_factory=_new_subscriptions,
        init=False,
    )


    def subscriber_count(self, topic: Topic) -> int:
        return len(self._subscriptions.get(_topic_to_str(topic), ()))


    def subscriber_counts(self) -> dict[tuple[str, ...], int]:
        """Return active subscriber counts keyed by normalised topic path."""

        return {
            topic: len(subscribers)
            for topic, subscribers in self._subscriptions.items()
        }


    def close_topic(self, topic: Topic) -> None:
        """Gracefully terminate current subscribers of an exact topic."""

        for queue in tuple(self._subscriptions.get(_topic_to_str(topic), ())):
            queue.put_nowait(None)


    async def publish_single(
        self,
        topic: Topic,
        event: SseEventType,
        data: BaseModel,
        id: str | None = None,
        retry: int | None = None,
        comment: str | None = None,
    ) -> None:
        """Fan one event out to the exact topic and all of its ancestors."""
        if None in topic:
            await asyncio.sleep(0)  # yield to allow consumers to run
            return  # don't publish to topics with None in them
        _topic_str = _topic_to_str(topic)
        _queued: _QueuedEvent = _Event(
            event=event, data=data.model_dump(mode="json")
        )
        for i in range(0, min(len(topic), self._max_notification_depth)):
            ancestor: tuple[str, ...] = _topic_str[:-i] if i > 0 else _topic_str
            queues = self._subscriptions.get(ancestor)
            if queues is None:
                continue
            for queue in queues:
                queue.put_nowait(_queued)
        await asyncio.sleep(0)  # yield to allow consumers to run


    async def publish(
        self,
        *topics: Topic,
        event: SseEventType,
        data: BaseModel,
    ) -> None:
        """Publish one typed event concurrently to each supplied topic."""

        await asyncio.gather(*(self.publish_single(topic, event, data) for topic in topics))


    def publish_task(
        self,
        *topics: Topic,
        event: SseEventType,
        data: BaseModel,
    ) -> asyncio.Task[None]:
        """Schedule publish as a fire-and-forget task."""

        return asyncio.ensure_future(
            self.publish(*topics, event=event, data=data)
        )


    async def publish_batch(
        self,
        batch: Iterable[tuple[Topic, SseEventType, BaseModel]],
    ) -> None:
        """Publish each (topic, event, data) triple in the batch."""
        pipelined_batch: Iterable[tuple[Topic, SseEventType, BaseModel]] = filter(
            lambda tpl: None not in tpl[0],
            batch,
        )  # filter out topics with None in them
        str_batch: Iterable[tuple[_TopicStr, SseEventType, BaseModel]] = map(
            lambda tpl: (_topic_to_str(tpl[0]), tpl[1], tpl[2]),
            pipelined_batch,
        )  # convert topics to strings
        expanded_batch: Iterable[tuple[_TopicStr, SseEventType, BaseModel]] = (
            (topic[:-i] if i > 0 else topic, event, data)
            for topic, event, data in str_batch
            for i in range(0, min(len(topic), self._max_notification_depth))
        )  # expand ancestor topics up to max_notification_depth
        filtered_batch = filter(
            lambda tpl: tpl[0] in self._subscriptions,
            expanded_batch,
        )  # filter out topics that have no subscribers
        for ancestor, event, data in filtered_batch:
            queued: _QueuedEvent = _Event(
                event=event, data=data.model_dump(mode="json")
            )
            queues = self._subscriptions[ancestor]
            for queue in queues:
                queue.put_nowait(queued)
        await asyncio.sleep(0)  # yield to allow consumers to run


    def publish_batch_task(
        self,
        batch: Iterable[tuple[Topic, SseEventType, BaseModel]],
    ) -> asyncio.Task[None]:
        """Schedule publish_batch as a fire-and-forget task.

        The batch iterable is consumed eagerly before the task is scheduled so
        that a generator passed by the caller is not exhausted at an unexpected
        time.
        """

        return asyncio.ensure_future(self.publish_batch(list(batch)))


    def stream[T: BaseModel](
        self, model: type[T], topic: Topic
    ) -> AsyncIterator[T]:
        """Yield model_validate'd ``T`` instances for a topic until disconnected."""

        return self._stream(model, topic)


    async def _stream[T: BaseModel](
        self, model: type[T], topic: Topic
    ) -> AsyncIterator[T]:
        async with self.subscribe(model, topic) as events:
            async for event in events:
                yield event


    def subscribe[T: BaseModel](
        self, model: type[T], topic: Topic
    ) -> AbstractAsyncContextManager[AsyncIterator[T]]:
        """Return an async context manager that yields a ``model_validate``'d stream."""

        return self._subscribe(model, topic)


    @asynccontextmanager
    async def _subscribe[T: BaseModel](
        self, model: type[T], topic: Topic
    ) -> AsyncGenerator[AsyncIterator[T], None]:
        """Register a consumer and clean it up when the context exits."""
        queue: asyncio.Queue[_QueuedEvent] = asyncio.Queue()
        self._subscriptions.setdefault(_topic_to_str(topic), set()).add(queue)
        try:
            yield self._events(model, queue)
        finally:
            str_topic = _topic_to_str(topic)
            subscribers = self._subscriptions.get(str_topic)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    del self._subscriptions[str_topic]


    async def _events[T: BaseModel](
        self, model: type[T], queue: asyncio.Queue[_QueuedEvent]
    ) -> AsyncIterator[T]:
        while True:
            raw = await queue.get()
            if raw is None:
                return
            yield model.model_validate(raw)


_sse_broker: TopicBroker | None = None


def get_sse_broker() -> TopicBroker:
    """Return the application-level broker dependency."""
    global _sse_broker
    if _sse_broker is None:
        _sse_broker = LocalTopicBroker()
    return _sse_broker


type BrokerDependency = Annotated[TopicBroker, Depends(get_sse_broker)]
