import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.engine import get_session
from people_gator_api.schemas.sources import (
    SourceCreateRequest,
    SourceProcessingResponse,
    SourceResponse,
    SourceSchemaCreateRequest,
    SourceSchemaResponse,
)
from people_gator_api.services.authz import AuthContext, require_scopes
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.source_service import (
    create_source,
    create_source_schema,
    get_source,
    get_source_processing,
    get_source_schema,
    list_source_schemas,
    list_sources,
)

router = APIRouter(tags=["sources"])


@router.get("/source-schemas", response_model=list[SourceSchemaResponse])
async def list_source_schemas_route(
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> list[SourceSchemaResponse]:
    return await list_source_schemas(session)


@router.get("/source-schemas/{schema_name}", response_model=SourceSchemaResponse)
async def get_source_schema_route(
    schema_name: str,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> SourceSchemaResponse:
    item = await get_source_schema(session, schema_name)
    if item is None:
        raise_api_error(404, "not_found", "Source schema not found")
    return item


@router.post("/source-schemas", response_model=SourceSchemaResponse, status_code=status.HTTP_201_CREATED)
async def create_source_schema_route(
    payload: SourceSchemaCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:admin")),
    session: AsyncSession = Depends(get_session),
) -> SourceSchemaResponse:
    return await create_source_schema(session, payload)


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources_route(
    source_schema_name: str | None = None,
    provider: str | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> list[SourceResponse]:
    return await list_sources(session, source_schema_name, provider, after_id, limit)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source_route(
    source_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> SourceResponse:
    source = await get_source(session, source_id)
    if source is None:
        raise_api_error(404, "not_found", "Source not found")
    return source


@router.options("/sources/{source_id}")
async def options_source_route(
    source_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
) -> dict[str, object]:
    return {
        "source_id": str(source_id),
        "allowed_methods": ["GET", "HEAD", "OPTIONS"],
        "allowed_operations": [],
    }


@router.post("/sources", response_model=SourceResponse)
async def create_source_route(
    payload: SourceCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> SourceResponse:
    created_by = auth.principal.principal_id if auth.principal is not None else None
    source, created = await create_source(session, payload, created_by)
    _ = created
    return source


@router.get("/sources/{source_id}/processing", response_model=SourceProcessingResponse)
async def source_processing_route(
    source_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> SourceProcessingResponse:
    return await get_source_processing(session, source_id)
