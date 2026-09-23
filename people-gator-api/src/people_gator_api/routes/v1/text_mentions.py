"""Text mention endpoints backed only by persistence contracts."""

import uuid

from fastapi import APIRouter, status

from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListRequest,
    TextMentionListResponse,
    TextMentionPatchRequest,
    TextMentionResponse,
    TextMentionsBatchCreateRequest,
    TextMentionsBatchPatchRequest,
)
from people_gator_api.routes.v1.query_dependencies import (
    ListRequestDependency,
    TextMentionListFilterDependency,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["text mentions"])


@router.get("/text-mentions", response_model=TextMentionListResponse)
async def list_text_mentions_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    filter: TextMentionListFilterDependency,
    list_request: ListRequestDependency,
) -> TextMentionListResponse:
    del user
    try:
        return await database.text_mentions.list(
            TextMentionListRequest(
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
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
