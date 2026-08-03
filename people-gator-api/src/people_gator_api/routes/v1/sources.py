"""Source endpoints (spec §2.7 simplified source model)."""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    status,
)
from weaviate import (
    WeaviateAsyncClient,
)

from people_gator_api.schemas.enums import (
    SourceKind,
)
from people_gator_api.services.auth_service import (
    AuthContext,
    require_scopes,
)
from people_gator_api.services.database_service import (
    get_session,
)
from people_gator_api.services.http_errors import (
    raise_api_error,
)
from people_gator_api.services.crud_services.source_service import (
    create_source,
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
    source_type: SourceKind | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SourceListResponse:
    return await list_sources(session, source_type, after_id, limit)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source_route(
    source_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SourceResponse:
    source = await get_source(session, source_id)
    if source is None:
        raise_api_error(404, "not_found", "Source not found")
    return source


@router.post("/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source_route(
    payload: SourceCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SourceResponse:
    created_by = auth.principal.principal_id if auth.principal is not None else None
    source, created = await create_source(session, payload, created_by)
    if not created:
        raise_api_error(409, "already_exists", "Source already registered")
    return source
