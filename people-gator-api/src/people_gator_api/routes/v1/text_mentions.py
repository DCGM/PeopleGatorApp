"""Text mention endpoints."""

import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Query, status

from people_gator_api.schemas.text_mentions import (
    TextMentionCreateRequest,
    TextMentionEntityPatchRequest,
    TextMentionListResponse,
    TextMentionResponse,
)
from people_gator_api.services.auth_service import (
    AnnotatorUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.crud_services.text_mention_service import (
    create_text_mention,
    create_text_mention_batch,
    get_text_mention,
    list_text_mentions,
    reassign_text_mention_entity,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error


router = APIRouter(tags=["text mentions"])


async def _iter_payloads[T](items: list[T]) -> AsyncGenerator[T, None]:
    for item in items:
        yield item


@router.get("/text-mentions", response_model=TextMentionListResponse)
async def list_text_mentions_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    source_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> TextMentionListResponse:
    del user
    return await list_text_mentions(
        session,
        source_id=source_id,
        entity_id=entity_id,
        after_id=after_id,
        limit=limit,
    )


@router.post(
    "/text-mentions",
    response_model=TextMentionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_text_mention_route(
    payload: TextMentionCreateRequest,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> TextMentionResponse:
    del user
    return await create_text_mention(session, payload)


@router.post(
    "/text-mentions:batch",
    response_model=list[TextMentionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_text_mention_batch_route(
    payload: list[TextMentionCreateRequest],
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> list[TextMentionResponse]:
    del user
    return await create_text_mention_batch(session, _iter_payloads(payload))


@router.get(
    "/text-mentions/{mention_id}",
    response_model=TextMentionResponse,
)
async def get_text_mention_route(
    mention_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> TextMentionResponse:
    del user
    mention = await get_text_mention(session, mention_id)
    if mention is None:
        raise_api_error(404, "not_found", "Text mention not found")
    return mention


@router.patch(
    "/text-mentions/{mention_id}",
    response_model=TextMentionResponse,
)
async def reassign_text_mention_entity_route(
    mention_id: uuid.UUID,
    payload: TextMentionEntityPatchRequest,
    session: WeaviateSessionDependency,
    user: AnnotatorUserDependency,
) -> TextMentionResponse:
    del user
    mention = await reassign_text_mention_entity(
        session,
        mention_id,
        payload.entity_id,
    )
    if mention is None:
        raise_api_error(404, "not_found", "Text mention not found")
    return mention
