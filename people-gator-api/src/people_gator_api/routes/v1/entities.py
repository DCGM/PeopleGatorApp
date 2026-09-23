"""Entity endpoints backed only by the persistence contracts."""

import uuid

from fastapi import APIRouter, Query, status

from people_gator_api.schemas.entities import (
    EntityBatchCreateRequest,
    EntityBatchPatchRequest,
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListFilter,
    EntityListRequest,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.missing import MISSING, MissingType
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
    BrowseUserDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.services.http_errors import raise_api_error


router = APIRouter(tags=["entities"])


def _entity_filter(**values: object) -> EntityListFilter | MissingType:
    supplied = {name: value for name, value in values.items() if value is not None}
    return EntityListFilter.model_validate(supplied) if supplied else MISSING


@router.get("/entities", response_model=EntityListResponse)
async def list_entities_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    entity_id: list[uuid.UUID] | None = Query(default=None),
    entity_type: list[EntityType] | None = Query(default=None),
    wikidata_id: list[str] | None = Query(default=None),
    nlcr_authority_id: list[str] | None = Query(default=None),
    source_id: list[uuid.UUID] | None = Query(default=None),
    detection_id: list[uuid.UUID] | None = Query(default=None),
    mention_id: list[uuid.UUID] | None = Query(default=None),
    has_mentions: bool | None = None,
    has_detections: bool | None = None,
    limit: int = Query(default=50, ge=0),
    return_total_count: bool = False,
    cursor: str | None = None,
) -> EntityListResponse:
    del user
    filter_ = _entity_filter(
        entity_id=entity_id,
        entity_type=entity_type,
        wikidata_id=wikidata_id,
        nlcr_authority_id=nlcr_authority_id,
        source_id=source_id,
        detection_id=detection_id,
        mention_id=mention_id,
        has_mentions=has_mentions,
        has_detections=has_detections,
    )
    try:
        return await database.entities.list(
            EntityListRequest(
                filter=filter_,
                limit=limit,
                return_total_count=return_total_count,
                cursor=cursor,
            )
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity_route(
    entity_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseUserDependency,
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
    user: AnnotatorUserDependency,
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
    user: AnnotatorUserDependency,
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
    user: AnnotatorUserDependency,
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
    user: AnnotatorUserDependency,
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
    user: AdminUserDependency,
) -> None:
    del user
    if not await database.entities.delete(entity_id):
        raise_api_error(404, "not_found", "Entity not found")


@router.delete(
    "/entities",
    response_model=EntityDeleteManyResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_entities_route(
    payload: EntityDeleteManyRequest,
    database: DatabaseDependency,
    user: AdminUserDependency,
) -> EntityDeleteManyResponse:
    del user
    try:
        return await database.entities.delete_many(payload)
    except ValueError as exc:
        raise_api_error(422, "invalid_selector", str(exc))
