"""Explicit server-sent event endpoints."""

from collections.abc import AsyncIterator
import uuid

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from people_gator_api.schemas.sse import SseStatsResponse, SseTopicStatsResponse
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    BrowseUserDependency,
)
from people_gator_api.services.sse import BrokerDependency

router = APIRouter(prefix="/sse", tags=["sse"])


@router.get("/", response_model=SseStatsResponse)
async def get_sse_stats(
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> SseStatsResponse:
    del principal
    topics = broker.subscriber_counts()
    return SseStatsResponse(
        topics=[
            SseTopicStatsResponse(topic=topic, subscriber_count=count)
            for topic, count in topics.items()
        ],
        total_subscribers=sum(topics.values()),
    )


# Collection topics


@router.get("/entities/{entity_id}", response_class=EventSourceResponse)
def stream_entity(
    entity_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("entities", entity_id))


@router.get("/faces/{detection_id}", response_class=EventSourceResponse)
def stream_face(
    detection_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("faces", detection_id))


@router.get("/page-mentions/{page_mention_id}", response_class=EventSourceResponse)
def stream_page_mention(
    page_mention_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("page-mentions", page_mention_id))


@router.get("/document-mentions/{document_mention_id}", response_class=EventSourceResponse)
def stream_document_mention(
    document_mention_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("document-mentions", document_mention_id))


@router.get("/principals/{principal_id}", response_class=EventSourceResponse)
def stream_principal(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("principals", principal_id))


@router.get("/model-agents/{principal_id}", response_class=EventSourceResponse)
def stream_model_agent(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("model-agents", principal_id))


@router.get("/users/{principal_id}", response_class=EventSourceResponse)
def stream_user(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("users", principal_id))


@router.get("/sources/{source_id}", response_class=EventSourceResponse)
def stream_source(
    source_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("sources", source_id))


# Relationship topics


@router.get(
    "/entities/{entity_id}/faces", response_class=EventSourceResponse
)
def stream_entity_faces(
    entity_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("entities", entity_id, "faces"))

@router.get(
    "/entities/{entity_id}/document-mentions", response_class=EventSourceResponse
)
def stream_entity_document_mentions(
    entity_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("entities", entity_id, "document-mentions"))


@router.get(
    "/principals/{principal_id}/faces", response_class=EventSourceResponse
)
def stream_principal_faces(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("principals", principal_id, "faces"))


@router.get(
    "/principals/{principal_id}/entities", response_class=EventSourceResponse
)
def stream_principal_entities(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("principals", principal_id, "entities"))


@router.get(
    "/principals/{principal_id}/page-mentions", response_class=EventSourceResponse
)
def stream_principal_page_mentions(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("principals", principal_id, "page-mentions"))


@router.get(
    "/principals/{principal_id}/document-mentions",
    response_class=EventSourceResponse,
)
def stream_principal_document_mentions(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("principals", principal_id, "document-mentions"))


@router.get(
    "/principals/{principal_id}/sources", response_class=EventSourceResponse
)
def stream_principal_sources(
    principal_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("principals", principal_id, "sources"))


@router.get(
    "/sources/{source_id}/faces", response_class=EventSourceResponse
)
def stream_source_faces(
    source_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("sources", source_id, "faces"))


@router.get(
    "/sources/{source_id}/page-mentions", response_class=EventSourceResponse
)
def stream_source_page_mentions(
    source_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("sources", source_id, "page-mentions"))


@router.get(
    "/sources/{source_id}/document-mentions",
    response_class=EventSourceResponse,
)
def stream_source_document_mentions(
    source_id: uuid.UUID,
    principal: BrowseUserDependency,
    broker: BrokerDependency,
) -> AsyncIterator[ServerSentEvent]:
    del principal
    return broker.stream(("sources", source_id, "document-mentions"))
