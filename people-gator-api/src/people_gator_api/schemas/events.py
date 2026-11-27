"""Live change notifications delivered over Server-Sent Events.

See ``docs/EVENTS.md`` for the session and topic contract.
"""

import uuid
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


MAX_SESSION_TOPICS = 1000


class TopicKind(StrEnum):
    """Kinds of objects that change live in the application."""

    ENTITY = "entity"
    SOURCE = "source"
    FACE = "face"
    MENTION = "mention"


class TopicScope(StrEnum):
    """Whether a topic follows the object itself or what is related to it."""

    SELF = "self"
    RELATED = "related"


class ChangeKind(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class ObjectRef(BaseModel, frozen=True):
    """Identity of one changed object. Clients refetch it; no snapshot is sent."""

    kind: TopicKind
    id: uuid.UUID


class Topic(BaseModel, frozen=True):
    """One subscribable topic.

    ``self`` follows the object with this ``id``; without an ``id`` it follows
    every object of the kind. ``related`` follows the faces and text mentions
    linked to an entity, or the faces, text mentions and pages of a source.
    """

    kind: TopicKind
    id: uuid.UUID | None = Field(
        default=None,
        description="Object UUID. Omit to follow every object of this kind.",
    )
    scope: TopicScope = TopicScope.SELF

    @model_validator(mode="after")
    def _related_needs_parent(self) -> Self:
        if self.scope is TopicScope.RELATED:
            if self.id is None:
                raise ValueError("A related topic needs the id of its entity or source")
            if self.kind not in (TopicKind.ENTITY, TopicKind.SOURCE):
                raise ValueError("Only entities and sources have related topics")
        return self


class SessionEvent(BaseModel):
    """First frame of every connection: the session's current subscriptions.

    Events published while no stream was connected are not replayed, so a
    client refetches what it shows and re-subscribes missing topics.
    """

    type: Literal["session"] = "session"
    session_id: uuid.UUID
    topics: list[Topic]


class ChangeEvent(BaseModel):
    """A subscribed topic changed."""

    type: Literal["change"] = "change"
    topic: Topic = Field(description="The subscribed topic this event belongs to.")
    change: ChangeKind = Field(description="What happened to the object.")
    object: ObjectRef | None = Field(
        description=(
            "The changed object. Null on a related or kind-wide topic when one "
            "request changed several objects."
        ),
    )


class SubscriptionUpdateRequest(BaseModel):
    """Topics to add to and remove from a session; unsubscribing is applied first."""

    subscribe: list[Topic] = Field(default_factory=list[Topic], max_length=MAX_SESSION_TOPICS)
    unsubscribe: list[Topic] = Field(default_factory=list[Topic], max_length=MAX_SESSION_TOPICS)


class SubscriptionsResponse(BaseModel):
    session_id: uuid.UUID
    connected: bool = Field(description="Whether a stream is currently attached.")
    topics: list[Topic]


__all__ = [
    "MAX_SESSION_TOPICS",
    "ChangeEvent",
    "ChangeKind",
    "ObjectRef",
    "SessionEvent",
    "SubscriptionUpdateRequest",
    "SubscriptionsResponse",
    "Topic",
    "TopicKind",
    "TopicScope",
]
