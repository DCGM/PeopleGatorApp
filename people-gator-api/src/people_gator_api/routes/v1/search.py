"""Search endpoints.

Cluster/version concepts have been removed; search returns entity and
annotation-level results.
"""

import uuid

from fastapi import (
    APIRouter,
    Query,
)
from people_gator_api.schemas.search import (
    SearchQuery,
    SearchResultListResponse,
)
from people_gator_api.services.auth_service import BrowseUserDependency
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.crud_services.search_service import search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResultListResponse)
async def search_get(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    name: str | None = Query(default=None, alias="query_name"),
    limit: int = 20,
    after_id: uuid.UUID | None = None,
) -> SearchResultListResponse:
    return await search(
        session,
        SearchQuery(
            name=name,
            limit=limit,
            after_id=after_id,
        ),
    )


@router.post("/search", response_model=SearchResultListResponse)
async def search_post(
    request: SearchQuery,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> SearchResultListResponse:
    return await search(session, request)
