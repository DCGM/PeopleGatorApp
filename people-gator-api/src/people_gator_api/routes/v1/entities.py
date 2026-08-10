"""Entity endpoints (spec §2.1)."""

import uuid

from fastapi import (
    APIRouter,
    status,
)

from people_gator_api.schemas.entities import (
    DocumentMentionListResponse,
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListResponse,
    EntityResponse,
    FaceListResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
    BrowseUserDependency,
)
from people_gator_api.services.crud_services.annotation_service import (
    list_document_mentions,
    list_faces,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.crud_services.entity_service import (
    create_entity,
    delete_entities,
    delete_entity,
    get_entity,
    list_entities,
)

router = APIRouter(tags=["entities"])


@router.get("/entities", response_model=EntityListResponse)
async def list_entities_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> EntityListResponse:
    return await list_entities(session, principal.principal_id, after_id, limit)


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> EntityResponse:
    entity = await get_entity(session, entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    return entity


@router.get(
    "/entities/{entity_id}/document-mentions",
    response_model=DocumentMentionListResponse,
)
async def list_entity_document_mentions_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> DocumentMentionListResponse:
    return await list_document_mentions(
        session,
        principal.principal_id,
        entity_id,
        None,
        after_id,
        limit,
    )


@router.get("/entities/{entity_id}/faces", response_model=FaceListResponse)
async def list_entity_faces_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> FaceListResponse:
    return await list_faces(
        session,
        principal.principal_id,
        None,
        entity_id,
        after_id,
        limit,
    )


@router.post(
    "/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED
)
async def create_entity_route(
    payload: EntityCreateRequest,
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
) -> EntityResponse:
    return await create_entity(session, payload, principal.principal_id)


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
) -> None:
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
    principal: AdminUserDependency,
) -> EntityDeleteManyResponse:
    return await delete_entities(session, payload)
