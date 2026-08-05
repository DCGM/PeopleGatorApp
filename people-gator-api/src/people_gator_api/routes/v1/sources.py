"""Source endpoints (spec §2.7 simplified source model)."""

import uuid

from fastapi import (
    APIRouter,
    status,
)

from people_gator_api.schemas.enums import (
    SourceKind,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.database_service import (
    WeaviateSessionDependency,
)
from people_gator_api.services.http_errors import (
    raise_api_error,
)
from people_gator_api.services.crud_services.source_service import (
    create_source,
    delete_source,
    get_source,
    list_sources,
)
from people_gator_api.schemas.sources import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
)

router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=SourceListResponse)
async def list_sources_route(
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
    source_type: SourceKind | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> SourceListResponse:
    return await list_sources(session, source_type, after_id, limit)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source_route(
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> SourceResponse:
    source = await get_source(session, source_id)
    if source is None:
        raise_api_error(404, "not_found", "Source not found")
    return source


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source_route(
    payload: SourceCreateRequest,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> SourceResponse:
    source, created = await create_source(session, payload, principal.principal_id)
    if not created:
        raise_api_error(409, "already_exists", "Source already registered")
    return source


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_route(
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
) -> None:
    deleted = await delete_source(session, source_id)
    if not deleted:
        raise_api_error(404, "not_found", "Source not found")
