"""Source endpoints (spec §2.7 simplified source model)."""

import asyncio
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
    get_source_by_uri,
    list_sources,
)
from people_gator_api.schemas.sources import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
)
from people_gator_api.services.sse import (
    BrokerDependency,
    DeletedResourceEvent,
    SseEventType,
)

router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=SourceListResponse)
async def list_sources_route(
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
    source_type: SourceKind | None = None,
    uri: str | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> SourceListResponse:
    del principal
    return await list_sources(
        session,
        source_type,
        after_id,
        limit,
        uri=uri,
        library=library,
        document=document,
        page=page,
    )


@router.get("/sources/object", response_model=SourceResponse)
async def get_source_object_route(
    url: AnyUrl,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> SourceResponse:
    """Fetch one source by its ``url``."""
    del principal
    source = await get_source_by_uri(
        session,
        str(url),
    )
    if source is None:
        raise_api_error(404, "not_found", "Source not found")
    return source


@router.get("/sources/{source_id:uuid}", response_model=SourceResponse)
async def get_source_route(
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> SourceResponse:
    del principal
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
    principal: DataIngestUserDependency,
    broker: BrokerDependency,
) -> SourceResponse:
    del principal
    source, created = await create_source(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Source already registered")
    asyncio.create_task(broker.publish(
        ("sources", source.source_id),
        event=SseEventType.SOURCE_CREATED,
        data=source,
    ))
    return source


@router.delete("/sources/{source_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_route(
    source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> None:
    del principal
    deleted = await delete_source(session, source_id)
    if not deleted:
        raise_api_error(404, "not_found", "Source not found")
    asyncio.create_task(broker.publish(
        ("sources", source_id),
        event=SseEventType.SOURCE_DELETED,
        data=DeletedResourceEvent(resource_id=source_id),
    ))
