"""Source endpoints (spec §2.7 simplified source model)."""

import uuid

from fastapi import (
    APIRouter,
    Query,
    status,
)
from pydantic import AnyUrl

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.crud_services.source_service import (
    create_source,
    delete_source,
    get_source,
    list_sources,
)
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    PageSourceMetadata,
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
)

router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=SourceListResponse)
async def list_sources_route(
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
    source_type: SourceKind | None = None,
    uri: str | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> SourceListResponse:
    del user
    return await list_sources(
        session,
        source_type,
        after_id,
        limit,
        url=uri,
        library=library,
        document_id=document,
        page_id=page,
    )


@router.get("/sources/object", response_model=SourceResponse)
async def get_source_object_route(
    url: AnyUrl,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> SourceResponse:
    """Fetch one source by its ``url``."""
    del user
    source = await get_source(session, url=str(url))
    if source is None:
        raise_api_error(404, "not_found", "Source not found")
    return source


@router.get("/sources/{source_id:uuid}", response_model=SourceResponse)
async def get_source_route(
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> SourceResponse:
    del user
    source = await get_source(session, source_id)
    if source is None:
        raise_api_error(404, "not_found", "Source not found")
    return source


@router.post(
    "/sources", response_model=SourceResponse, status_code=status.HTTP_201_CREATED
)
async def create_source_route(
    payload: SourceCreateRequest,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> SourceResponse:
    del user
    metadata = payload.metadata
    if isinstance(metadata, PageSourceMetadata):
        source, created = await create_source(
            session,
            payload.source_type,
            library=metadata.library,
            document_id=metadata.document,
            page_id=metadata.page,
        )
    elif isinstance(metadata, DocumentSourceMetadata):
        source, created = await create_source(
            session,
            payload.source_type,
            library=metadata.library,
            document_id=metadata.document,
        )
    else:
        source, created = await create_source(
            session,
            payload.source_type,
            url=payload.uri,
        )
    if not created:
        raise_api_error(409, "already_exists", "Source already registered")
    return source


@router.delete("/sources/{source_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_route(
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: AdminUserDependency,
) -> None:
    del user
    deleted = await delete_source(session, source_id)
    if not deleted:
        raise_api_error(404, "not_found", "Source not found")
