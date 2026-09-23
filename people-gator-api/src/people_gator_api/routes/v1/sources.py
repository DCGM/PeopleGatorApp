"""Generic source endpoints backed only by persistence contracts."""

import uuid

from fastapi import APIRouter, status
from pydantic import AnyUrl

from people_gator_api.routes.v1.query_dependencies import (
    ListRequestDependency,
    SourceListFilterDependency,
)
from people_gator_api.schemas.sources import (
    SourceListFilter,
    SourceListRequest,
    SourceListResponse,
    SourceResponseBase,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=SourceListResponse)
async def list_sources_route(
    database: DatabaseDependency,
    user: DataIngestUserDependency,
    filter: SourceListFilterDependency,
    list_request: ListRequestDependency,
) -> SourceListResponse:
    del user
    try:
        return await database.sources.list_sources(
            SourceListRequest(
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
            )
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.get("/sources/lookup", response_model=SourceResponseBase)
async def lookup_source_route(
    url: AnyUrl,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> SourceResponseBase:
    """Fetch one source by its globally unique URL."""
    del user
    result = await database.sources.list_sources(
        SourceListRequest(
            filter_=SourceListFilter(url=[url]),
            limit=2,
            return_total_count=False,
        )
    )
    if not result.items:
        raise_api_error(404, "not_found", "Source not found")
    if len(result.items) != 1:
        raise_api_error(409, "identity_conflict", "Source URL is not unique")
    return result.items[0]


@router.get("/sources/{source_id:uuid}", response_model=SourceResponseBase)
async def get_source_route(
    source_id: uuid.UUID,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> SourceResponseBase:
    del user
    source = await database.sources.get_source(source_id)
    if source is None:
        raise_api_error(404, "not_found", "Source not found")
    return source


@router.delete("/sources/{source_id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_route(
    source_id: uuid.UUID,
    database: DatabaseDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if not await database.sources.delete(source_id):
        raise_api_error(404, "not_found", "Source not found")
