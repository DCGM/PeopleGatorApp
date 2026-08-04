"""Search endpoints.

Cluster/version concepts have been removed; search returns entity and
annotation-level results.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from weaviate import (
    WeaviateAsyncClient,
)

from people_gator_api.schemas.enums import (
    AnnotationType,
)
from people_gator_api.schemas.search import (
    SearchQuery,
    SearchResponse,
)
from people_gator_api.settings import (
    settings,
)
from people_gator_api.services.auth_service import (
    BrowseUserDependency,
)
from people_gator_api.services.database_service import (
    get_session,
)
from people_gator_api.services.crud_services.search_service import (
    search,
)

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_get(
    _auth: BrowseUserDependency,
    name: str | None = Query(default=None, alias="query_name"),
    limit: int = 20,
    after_id: uuid.UUID | None = None,
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchResponse:
    return await search(session, SearchQuery(
        name=name,
        limit=limit,
        after_id=after_id,
    ))


@router.post("/search", response_model=SearchResponse)
async def search_post(
    request: SearchQuery,
    _auth: BrowseUserDependency,
    session: WeaviateAsyncClient = Depends(get_session),
) -> SearchResponse:
    return await search(session, request)
