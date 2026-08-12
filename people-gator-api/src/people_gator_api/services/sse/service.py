"""Backend-independent topic delivery for server-sent events.

The public broker contract is documented in ``docs/05-sse.md``. Topics are
slash-like tuples, and publishing to a leaf fans the event out to that topic
and each non-empty ancestor. ``LocalTopicBroker`` is process-local and does
not provide replay or durable delivery.
"""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Protocol
from fastapi import Depends
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel
import uuid

type JsonValue = (
    str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
)

type Topic = tuple[str | uuid.UUID | None, ...]
type _TopicStr = tuple[str, ...]


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
    """Transport contract shared by local and future distributed brokers.

    Implementations must preserve topic ancestor propagation and accept
    Pydantic payloads that can be serialized by ``ServerSentEvent``.
    """

    def subscribe(
        self, topic: Topic
    ) -> AbstractAsyncContextManager[AsyncIterator[ServerSentEvent]]: ...

    def stream(self, topic: Topic) -> AsyncIterator[ServerSentEvent]: ...

    async def publish(
        self,
        topic: Topic,
        event: SseEventType,
        data: BaseModel,
        id: str | None = None,
        retry: int | None = None,
        comment: str | None = None,
    ) -> None: ...

    async def publish_to_topics(
        self,
        *topics: Topic,
        event: SseEventType,
        data: BaseModel,
    ) -> None: ...

    def subscriber_counts(self) -> dict[tuple[str, ...], int]: ...


def _new_subscriptions() -> dict[_TopicStr, set[asyncio.Queue[ServerSentEvent]]]:
    return {}


@dataclass(slots=True)
class LocalTopicBroker:
    """In-process broker backed by one asynchronous queue per subscriber.

    Subscriptions are removed when their async context exits. Queues are
    intentionally unbounded in this initial implementation; durable or
    distributed delivery belongs in a future ``TopicBroker`` implementation.
    """

    _subscriptions: dict[_TopicStr, set[asyncio.Queue[ServerSentEvent]]] = field(
        default_factory=_new_subscriptions,
        init=False,
    )

    def subscriber_count(self, topic: Topic) -> int:
        return len(self._subscriptions.get(_topic_to_str(topic), ()))

    def subscriber_counts(self) -> dict[tuple[str, ...], int]:
        """Return active subscriber counts keyed by normalized topic path."""

        return {
            topic: len(subscribers)
            for topic, subscribers in self._subscriptions.items()
        }

    async def publish(
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
        for i in range(len(topic), 0, -1):
            ancestor: tuple[str | uuid.UUID | None, ...] = topic[:i]
            for queue in tuple(self._subscriptions.get(_topic_to_str(ancestor), ())):
                queue.put_nowait(ServerSentEvent(data=data, event=event, id=id, retry=retry, comment=comment))
        await asyncio.sleep(0)  # yield to allow consumers to run

    async def publish_to_topics(
        self,
        *topics: Topic,
        event: SseEventType,
        data: BaseModel,
    ) -> None:
        """Publish one typed event concurrently to each supplied topic."""

        await asyncio.gather(*(self.publish(topic, event, data) for topic in topics))

    async def stream(self, topic: Topic) -> AsyncIterator[ServerSentEvent]:
        """Yield events for a topic until the consumer disconnects."""

        async with self.subscribe(topic) as events:
            async for event in events:
                yield event

    @asynccontextmanager
    async def subscribe(
        self, topic: Topic
    ) -> AsyncGenerator[AsyncIterator[ServerSentEvent], None]:
        """Register a consumer and clean it up when the context exits."""
        queue: asyncio.Queue[ServerSentEvent] = asyncio.Queue()
        self._subscriptions.setdefault(_topic_to_str(topic), set()).add(queue)
        try:
            yield self._events(queue)
        finally:
            str_topic = _topic_to_str(topic)
            subscribers = self._subscriptions.get(str_topic)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    del self._subscriptions[str_topic]

    async def _events(self, queue: asyncio.Queue[ServerSentEvent]) -> AsyncIterator[ServerSentEvent]:
        while True:
            yield await queue.get()


_sse_broker: TopicBroker = LocalTopicBroker()


def get_sse_broker() -> TopicBroker:
    """Return the application-level broker dependency."""

    return _sse_broker

type BrokerDependency = Annotated[TopicBroker, Depends(get_sse_broker)]


