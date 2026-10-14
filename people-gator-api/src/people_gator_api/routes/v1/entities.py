"""Entity endpoints backed only by the persistence contracts."""

import uuid

from fastapi import APIRouter, status

from people_gator_api.schemas.entities import (
    EntityBatchCreateRequest,
    EntityBatchPatchRequest,
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListRequest,
    EntityListResponse,
    EntityMergeFromRequest,
    EntityMergeResponse,
    EntityMergeBatchRequest,
    EntityMergeBatchResponse,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.routes.v1.query_dependencies import (
    EntityListFilterDependency,
    ListRequestDependency,
)
from people_gator_api.services.auth_service import (
    AdminActorDependency,
    AnnotatorActorDependency,
    BrowseActorDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["entities"])


@router.get("/entities", response_model=EntityListResponse)
async def list_entities_route(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    filter: EntityListFilterDependency,
    list_request: ListRequestDependency,
) -> EntityListResponse:
    del user
    try:
        return await database.entities.list(
            EntityListRequest(
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
            )
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity_route(
    entity_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseActorDependency,
) -> EntityResponse:
    del user
    entity = await database.entities.get(entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    return entity


@router.post(
    "/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED
)
async def create_entity_route(
    payload: EntityCreateRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> EntityResponse:
    try:
        return await database.entities.create(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.post(
    "/entities:batch",
    response_model=list[EntityResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_entity_batch_route(
    payload: EntityBatchCreateRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> list[EntityResponse]:
    try:
        return await database.entities.create_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.patch(
    "/entities:batch",
    response_model=list[EntityResponse | None],
)
async def patch_entity_batch_route(
    payload: EntityBatchPatchRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> list[EntityResponse | None]:
    try:
        return await database.entities.patch_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))


@router.patch("/entities/{entity_id}", response_model=EntityResponse)
async def patch_entity_route(
    entity_id: uuid.UUID,
    payload: EntityPatchRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> EntityResponse:
    try:
        entity = await database.entities.patch(entity_id, payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    return entity


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity_route(
    entity_id: uuid.UUID,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> None:
    if not await database.entities.delete(entity_id, context=user):
        raise_api_error(404, "not_found", "Entity not found")


@router.post(
    "/entities/{target_entity_id}:merge",
    response_model=EntityMergeResponse,
    summary="Merge one entity into this target",
    description="Reassign the source entity's faces and text mentions to the target in the URL, add its aliases without duplicates, then delete the source. Optional description fields update the target; null clears them and omission preserves them.",
)
async def merge_entity_route(
    target_entity_id: uuid.UUID,
    payload: EntityMergeFromRequest,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> EntityMergeResponse:
    try:
        result = await database.entities.merge(
            target_entity_id, payload.source_entity_id, target_patch=payload, context=user
        )
    except ValueError as exc:
        raise_api_error(409, "invalid_merge", str(exc))
    if result is None:
        raise_api_error(404, "not_found", "Source or target entity not found")
    return result


@router.post(
    "/entities/{target_entity_id}:merge-batch",
    response_model=EntityMergeBatchResponse,
    summary="Merge multiple entities into this target",
    description="Atomically reassign every source entity's faces and text mentions to the target in the URL, add their aliases without duplicates, then delete all sources. Optional description fields update the target; null clears them and omission preserves them.",
)
async def merge_entity_batch_route(
    target_entity_id: uuid.UUID,
    payload: EntityMergeBatchRequest,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> EntityMergeBatchResponse:
    try:
        result = await database.entities.merge_batch(
            target_entity_id, payload.source_entity_ids, target_patch=payload, context=user
        )
    except ValueError as exc:
        raise_api_error(409, "invalid_merge", str(exc))
    if result is None:
        raise_api_error(404, "not_found", "Target or source entity not found")
    return result


@router.delete(
    "/entities",
    response_model=EntityDeleteManyResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_entities_route(
    payload: EntityDeleteManyRequest,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> EntityDeleteManyResponse:
    try:
        return await database.entities.delete_many(payload, context=user)
    except ValueError as exc:
        raise_api_error(422, "invalid_selector", str(exc))
