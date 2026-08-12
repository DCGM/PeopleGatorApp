"""Backend-independent topic delivery for server-sent events."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Protocol
from fastapi import Depends
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel

type JsonValue = (
    str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
)

type Topic = tuple[str, ...]


class SseEventType(StrEnum):
    """Event names published through the SSE broker."""

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
    """The transport contract shared by local and future distributed brokers."""

    def subscribe(
        self, topic: Topic
    ) -> AbstractAsyncContextManager[AsyncIterator[ServerSentEvent]]: ...

    async def publish(
        self,
        topic: Topic,
        event: SseEventType,
        data: BaseModel,
        id: str | None = None,
        retry: int | None = None,
        comment: str | None = None,
    ) -> None: ...


def _new_subscriptions() -> dict[Topic, set[asyncio.Queue[ServerSentEvent]]]:
    return {}


@dataclass(slots=True)
class LocalTopicBroker:
    """In-process broker that fans events out to exact and ancestor topics."""

    _subscriptions: dict[Topic, set[asyncio.Queue[ServerSentEvent]]] = field(
        default_factory=_new_subscriptions,
        init=False,
    )

    def subscriber_count(self, topic: Topic) -> int:
        return len(self._subscriptions.get(topic, ()))

    async def publish(
        self,
        topic: Topic,
        event: SseEventType,
        data: BaseModel,
        id: str | None = None,
        retry: int | None = None,
        comment: str | None = None,
    ) -> None:
        for i in range(len(topic), 0, -1):
            ancestor = topic[:i]
            for queue in tuple(self._subscriptions.get(ancestor, ())):
                queue.put_nowait(ServerSentEvent(data=data, event=event, id=id, retry=retry, comment=comment))
        await asyncio.sleep(0)  # yield to allow consumers to run

    @asynccontextmanager
    async def subscribe(
        self, topic: Topic
    ) -> AsyncGenerator[AsyncIterator[ServerSentEvent], None]:
        queue: asyncio.Queue[ServerSentEvent] = asyncio.Queue()
        self._subscriptions.setdefault(topic, set()).add(queue)
        try:
            yield self._events(queue)
        finally:
            subscribers = self._subscriptions.get(topic)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    del self._subscriptions[topic]

    async def _events(self, queue: asyncio.Queue[ServerSentEvent]) -> AsyncIterator[ServerSentEvent]:
        while True:
            yield await queue.get()


_sse_broker: TopicBroker = LocalTopicBroker()


def get_sse_broker() -> TopicBroker:
    return _sse_broker

type BrokerDependency = Annotated[TopicBroker, Depends(get_sse_broker)]


