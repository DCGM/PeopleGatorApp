"""Entity endpoints (spec §2.1)."""

import uuid

from fastapi import APIRouter, Depends, status
from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListResponse,
    EntityResponse,
    EntityViewResponse,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.database_service import get_session
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.crud_services.entity_service import (
    create_entity,
    delete_entity,
    get_entity,
    get_entity_view,
    list_entities,
)

router = APIRouter(tags=["entities"])


@router.get("/entities", response_model=EntityListResponse)
async def list_entities_route(
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> EntityListResponse:
    return await list_entities(session, after_id, limit)


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity_route(
    entity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> EntityResponse:
    entity = await get_entity(session, entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    return entity


@router.get("/entities/{entity_id}/view", response_model=EntityViewResponse)
async def get_entity_view_route(
    entity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> EntityViewResponse:
    view = await get_entity_view(session, entity_id)
    if view is None:
        raise_api_error(404, "not_found", "Entity not found")
    return view


@router.post("/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity_route(
    payload: EntityCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> EntityResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    return await create_entity(session, payload, auth.principal.principal_id)


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity_route(
    entity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:admin")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> None:
    deleted = await delete_entity(session, entity_id)
    if not deleted:
        raise_api_error(404, "not_found", "Entity not found")
