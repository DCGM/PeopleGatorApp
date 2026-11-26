"""Text mention endpoints backed only by persistence contracts."""

import uuid
from typing import Literal

from fastapi import APIRouter, status

from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionGroupListRequest,
    TextMentionGroupListResponse,
    TextMentionListRequest,
    TextMentionListResponse,
    TextMentionPatchRequest,
    TextMentionResponse,
    TextMentionsBatchCreateRequest,
    TextMentionsBatchPatchRequest,
)
from people_gator_api.routes.v1.query_dependencies import (
    DEFAULT_SORT,
    ListRequestDependency,
    TextMentionGroupSortDependency,
    TextMentionListFilterDependency,
    TextMentionSortDependency,
)
from people_gator_api.services.auth_service import (
    AdminActorDependency,
    AnnotatorActorDependency,
    BrowseActorDependency,
    DataIngestActorDependency,
)
from people_gator_api.media.text_mention_spans import check_text_mention_contexts
from people_gator_api.schemas.missing import is_missing
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["text mentions"])


async def _require_unique_contexts(database, mentions) -> None:
    """A mention's context locates it at most once on its page, with one exact name (#176)."""
    if error := await check_text_mention_contexts(database, mentions):
        raise_api_error(422, "ambiguous_context", error)


async def _require_unique_patched_contexts(database, commands) -> None:
    """Check the text a PATCH leaves, merging omitted fields from the stored mention."""
    checks = []
    for command in commands:
        mention_id, payload = command if isinstance(command, tuple) else (command.mention_id, command)
        if is_missing(payload.name) and is_missing(payload.context):
            continue
        stored = await database.text_mentions.get(mention_id)
        if stored is None:
            continue
        checks.append((
            stored.source_id,
            stored.name if is_missing(payload.name) else payload.name,
            stored.context if is_missing(payload.context) else payload.context,
        ))
    await _require_unique_contexts(database, checks)


@router.get("/text-mentions", response_model=TextMentionListResponse)
async def list_text_mentions_route(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    filter: TextMentionListFilterDependency,
    list_request: ListRequestDependency,
    sort: TextMentionSortDependency = DEFAULT_SORT,
) -> TextMentionListResponse:
    del user
    try:
        return await database.text_mentions.list(
            TextMentionListRequest(
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
                sort=sort.sort,
                sort_direction=sort.sort_direction,
            )
        )
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.get("/text-mention-groups", response_model=TextMentionGroupListResponse)
async def list_text_mention_groups_route(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    filter: TextMentionListFilterDependency,
    list_request: ListRequestDependency,
    sort: TextMentionGroupSortDependency = DEFAULT_SORT,
    group_by: Literal["mention", "document", "page"] = "mention",
) -> TextMentionGroupListResponse:
    """Group the complete filtered mention set by text, document or page."""
    del user
    try:
        return await database.text_mentions.list_groups(
            TextMentionGroupListRequest(
                group_by=group_by,
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
                sort=sort.sort,
                sort_direction=sort.sort_direction,
            )
        )
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))
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
    user: DataIngestActorDependency,
) -> TextMentionResponse:
    await _require_unique_contexts(database, [(payload.source_id, payload.name, payload.context)])
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
    user: DataIngestActorDependency,
) -> list[TextMentionResponse]:
    await _require_unique_contexts(
        database, [(item.source_id, item.name, item.context) for item in payload]
    )
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
    user: AnnotatorActorDependency,
) -> list[TextMentionResponse | None]:
    await _require_unique_patched_contexts(database, list(payload))
    try:
        return await database.text_mentions.patch_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))


@router.delete("/text-mentions:batch", response_model=int)
async def delete_text_mention_batch_route(
    mention_id: list[uuid.UUID],
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> int:
    return await database.text_mentions.delete_batch(mention_id, context=user)


@router.get(
    "/text-mentions/{mention_id}",
    response_model=TextMentionResponse,
)
async def get_text_mention_route(
    mention_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseActorDependency,
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
    user: AnnotatorActorDependency,
) -> TextMentionResponse:
    await _require_unique_patched_contexts(database, [(mention_id, payload)])
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
    user: AdminActorDependency,
) -> None:
    if not await database.text_mentions.delete(mention_id, context=user):
        raise_api_error(404, "not_found", "Text mention not found")
