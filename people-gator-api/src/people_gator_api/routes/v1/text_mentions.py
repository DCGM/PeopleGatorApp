"""Text mention endpoints backed only by persistence contracts."""

import uuid

from fastapi import APIRouter, Query, status

from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListFilter,
    TextMentionListRequest,
    TextMentionListResponse,
    TextMentionPatchRequest,
    TextMentionResponse,
    TextMentionsBatchCreateRequest,
    TextMentionsBatchPatchRequest,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.services.http_errors import raise_api_error


router = APIRouter(tags=["text mentions"])


@router.get("/text-mentions", response_model=TextMentionListResponse)
async def list_text_mentions_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    source_id: list[uuid.UUID] | None = Query(default=None),
    entity_id: list[uuid.UUID] | None = Query(default=None),
    limit: int = Query(default=50, ge=0),
    return_total_count: bool = False,
    cursor: str | None = None,
) -> TextMentionListResponse:
    del user
    values = {
        name: value
        for name, value in {
            "source_id": source_id,
            "entity_id": entity_id,
        }.items()
        if value is not None
    }
    try:
        return await database.text_mentions.list(
            TextMentionListRequest(
                filter=TextMentionListFilter(**values),
                limit=limit,
                return_total_count=return_total_count,
                cursor=cursor,
            )
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.post(
    "/text-mentions",
    response_model=TextMentionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_text_mention_route(
    payload: TextMentionCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> TextMentionResponse:
    try:
        return await database.text_mentions.create(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.post(
    "/text-mentions:batch",
    response_model=list[TextMentionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_text_mention_batch_route(
    payload: TextMentionsBatchCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> list[TextMentionResponse]:
    try:
        return await database.text_mentions.create_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.patch(
    "/text-mentions:batch",
    response_model=list[TextMentionResponse | None],
)
async def patch_text_mention_batch_route(
    payload: TextMentionsBatchPatchRequest,
    database: DatabaseDependency,
    user: AnnotatorUserDependency,
) -> list[TextMentionResponse | None]:
    try:
        return await database.text_mentions.patch_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))


@router.delete("/text-mentions:batch", response_model=int)
async def delete_text_mention_batch_route(
    mention_id: list[uuid.UUID],
    database: DatabaseDependency,
    user: AdminUserDependency,
) -> int:
    del user
    return await database.text_mentions.delete_batch(mention_id)


@router.get(
    "/text-mentions/{mention_id}",
    response_model=TextMentionResponse,
)
async def get_text_mention_route(
    mention_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseUserDependency,
) -> TextMentionResponse:
    del user
    mention = await database.text_mentions.get(mention_id)
    if mention is None:
        raise_api_error(404, "not_found", "Text mention not found")
    return mention


@router.patch(
    "/text-mentions/{mention_id}",
    response_model=TextMentionResponse,
)
async def patch_text_mention_route(
    mention_id: uuid.UUID,
    payload: TextMentionPatchRequest,
    database: DatabaseDependency,
    user: AnnotatorUserDependency,
) -> TextMentionResponse:
    try:
        mention = await database.text_mentions.patch(mention_id, payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))
    if mention is None:
        raise_api_error(404, "not_found", "Text mention not found")
    return mention


@router.delete(
    "/text-mentions/{mention_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_text_mention_route(
    mention_id: uuid.UUID,
    database: DatabaseDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if not await database.text_mentions.delete(mention_id):
        raise_api_error(404, "not_found", "Text mention not found")
