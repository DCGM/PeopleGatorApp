"""Entity endpoints (spec §2.1)."""

from collections.abc import AsyncGenerator
import uuid

from fastapi import (
    APIRouter,
    Query,
    status,
)

from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.crud_services.entity_service import (
    create_entity,
    create_entity_batch,
    delete_entities,
    delete_entity,
    get_entity,
    link_entity_to_source,
    list_entities,
    patch_entity,
    unlink_entity_from_source,
)
from people_gator_api.services.crud_services.source_service import SourceResolutionError
router = APIRouter(tags=["entities"])


@router.get("/entities", response_model=EntityListResponse)
async def list_entities_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    source_id: uuid.UUID | None = None,
    entity_type: EntityType | None = None,
    wikidata_id: str | None = None,
    nlcr_authority_id: str | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> EntityListResponse:
    try:
        return await list_entities(
            session,
            user.user_id,
            after_id,
            limit,
            entity_type=entity_type,
            wikidata_id=wikidata_id,
            nlcr_authority_id=nlcr_authority_id,
            owner_user_id=user_id,
            source_id=source_id,
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_filter", str(exc))


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> EntityResponse:
    entity = await get_entity(session, entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    return entity


@router.post(
    "/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED
)
async def create_entity_route(
    payload: EntityCreateRequest,
    session: WeaviateSessionDependency,
    user: AnnotatorUserDependency,
) -> EntityResponse:
    entity = await create_entity(session, payload, user.user_id)
    return entity


@router.post(
    "/entities:batch",
    response_model=list[EntityResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_entity_batch_route(
    payload: list[EntityCreateRequest],
    session: WeaviateSessionDependency,
    user: AnnotatorUserDependency,
) -> list[EntityResponse]:
    async def async_list(
        iterable: list[EntityCreateRequest],
    ) -> AsyncGenerator[EntityCreateRequest, None]:
        for item in iterable:
            yield item

    entities = await create_entity_batch(
        session, async_list(payload), user.user_id
    )
    return entities


@router.patch("/entities/{entity_id}", response_model=EntityResponse)
async def patch_entity_route(
    entity_id: uuid.UUID,
    payload: EntityPatchRequest,
    session: WeaviateSessionDependency,
    user: AnnotatorUserDependency,
) -> EntityResponse:
    del user
    entity = await patch_entity(session, entity_id, payload)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    return entity


@router.put(
    "/entities/{entity_id}/mentioned-in/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def link_entity_to_source_route(
    entity_id: uuid.UUID,
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> None:
    del user
    try:
        linked = await link_entity_to_source(session, entity_id, source_id)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    if not linked:
        raise_api_error(404, "not_found", "Entity not found")


@router.delete(
    "/entities/{entity_id}/mentioned-in/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_entity_from_source_route(
    entity_id: uuid.UUID,
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: AnnotatorUserDependency,
) -> None:
    del user
    try:
        unlinked = await unlink_entity_from_source(session, entity_id, source_id)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    if not unlinked:
        raise_api_error(404, "not_found", "Entity not found")


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: AdminUserDependency,
) -> None:
    del user
    entity = await get_entity(session, entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    deleted = await delete_entity(session, entity_id)
    if not deleted:
        raise_api_error(404, "not_found", "Entity not found")


@router.delete(
    "/entities",
    response_model=EntityDeleteManyResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_entities_route(
    payload: EntityDeleteManyRequest,
    session: WeaviateSessionDependency,
    user: AdminUserDependency,
) -> EntityDeleteManyResponse:
    del user
    response = await delete_entities(session, payload)
    return response
