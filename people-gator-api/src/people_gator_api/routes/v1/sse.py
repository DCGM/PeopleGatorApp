"""Server-sent event endpoints."""

from collections.abc import AsyncIterable

from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent

from people_gator_api.services.auth_service import BrowseUserDependency
from people_gator_api.services.sse import BrokerDependency, Topic

router = APIRouter(prefix="/sse", tags=["sse"])


@router.get("/{topic_path:path}", response_class=EventSourceResponse)
async def stream_topic_events(
    topic_path: str,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterable[ServerSentEvent]:
    del principal
    try:
        topic: Topic = tuple(topic_path.strip("/").split("/"))
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid SSE topic") from error
    async with broker.subscribe(topic) as events:
        async for event in events:
            yield event
