"""Live change notifications: one stream per session and its subscriptions."""

import uuid
from collections.abc import AsyncIterable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.sse import EventSourceResponse

from people_gator_api.schemas.events import (
    ChangeEvent,
    SessionEvent,
    SubscriptionsResponse,
    SubscriptionUpdateRequest,
)
from people_gator_api.services.auth_service import BrowseActorDependency
from people_gator_api.services.event_service import (
    EventHubDependency,
    SessionLimitError,
    SessionOwnershipError,
    TopicLimitError,
)
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(prefix="/events", tags=["events"])


def _resolve(
    session_id: uuid.UUID, user: BrowseActorDependency, hub: EventHubDependency, connecting: bool
) -> SubscriptionsResponse:
    try:
        return hub.subscriptions(session_id, user.user_id, connecting=connecting)
    except SessionOwnershipError:
        raise_api_error(404, "not_found", "Session not found")
    except SessionLimitError:
        raise_api_error(429, "too_many_sessions", "Too many open event sessions")


def _session(
    session_id: uuid.UUID, user: BrowseActorDependency, hub: EventHubDependency
) -> SubscriptionsResponse:
    """Resolve a session the caller may use."""
    return _resolve(session_id, user, hub, connecting=False)


def _stream_session(
    session_id: uuid.UUID, user: BrowseActorDependency, hub: EventHubDependency
) -> SubscriptionsResponse:
    """Refuse a stream the caller may not open before the response starts."""
    return _resolve(session_id, user, hub, connecting=True)


type OwnedSessionDependency = Annotated[SubscriptionsResponse, Depends(_session)]
type StreamSessionDependency = Annotated[SubscriptionsResponse, Depends(_stream_session)]


@router.get(
    "/{session_id}",
    response_class=EventSourceResponse,
    # Routers lose the stream item type on include (FastAPI 0.136), so the
    # frame payloads are documented here to reach OpenAPI and the client.
    responses={200: {"model": SessionEvent | ChangeEvent, "description": "JSON `data` of each frame."}},
    summary="Stream a session's events",
    description=(
        "Open the session's event stream; the client chooses the session UUID. "
        "The first frame lists the session's topics, each later frame reports one "
        "changed topic, starting with those queued while no stream was open. The "
        "session belongs to the stream's user until the stream closes."
    ),
)
async def stream_events_route(
    session: StreamSessionDependency,
    user: BrowseActorDependency,
    hub: EventHubDependency,
) -> AsyncIterable[SessionEvent | ChangeEvent]:
    with hub.connect(session.session_id, user.user_id) as connection:
        yield connection.hello
        async for event in connection.events():
            yield event


@router.get(
    "/{session_id}/topics",
    response_model=SubscriptionsResponse,
    summary="List a session's topics",
)
async def get_event_topics_route(session: OwnedSessionDependency) -> SubscriptionsResponse:
    return session


@router.patch(
    "/{session_id}/topics",
    response_model=SubscriptionsResponse,
    summary="Subscribe and unsubscribe a session",
    description=(
        "Add and remove topics while the stream stays open. Repeating a "
        "subscription or removing an unknown topic changes nothing. A session "
        "without a stream keeps queueing and is forgotten after a minute."
    ),
)
async def update_event_topics_route(
    payload: SubscriptionUpdateRequest,
    session: OwnedSessionDependency,
    user: BrowseActorDependency,
    hub: EventHubDependency,
) -> SubscriptionsResponse:
    try:
        return hub.update(
            session.session_id,
            user.user_id,
            subscribe=payload.subscribe,
            unsubscribe=payload.unsubscribe,
        )
    except TopicLimitError as exc:
        raise_api_error(422, "too_many_topics", str(exc))
