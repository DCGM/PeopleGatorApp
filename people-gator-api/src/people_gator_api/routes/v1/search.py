"""Multimodal search endpoints backed only by persistence contracts."""

from fastapi import APIRouter

from people_gator_api.routes.v1.query_dependencies import (
    DocumentListFilterDependency,
    EntityListFilterDependency,
    FaceListFilterDependency,
    PageListFilterDependency,
    SearchListRequestDependency,
    SearchQueryDependency,
)
from people_gator_api.schemas.search import (
    SearchDocumentsRequest,
    SearchDocumentsResultListResponse,
    SearchEntitiesRequest,
    SearchEntitiesResultListResponse,
    SearchFacesRequest,
    SearchFacesResultListResponse,
    SearchPagesRequest,
    SearchPagesResultListResponse,
)
from people_gator_api.services.auth_service import BrowseActorDependency
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["search"])


@router.get("/search-entities", response_model=SearchEntitiesResultListResponse)
async def search_entities_get(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    query: SearchQueryDependency,
    filter: EntityListFilterDependency,
    list_request: SearchListRequestDependency,
) -> SearchEntitiesResultListResponse:
    del user
    try:
        request = SearchEntitiesRequest(
            query=query,
            filter_=filter,
            limit=list_request.limit,
            return_total_count=list_request.return_total_count,
            cursor=list_request.cursor,
        )
        return await database.entities.search(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))


@router.get("/search-faces", response_model=SearchFacesResultListResponse)
async def search_faces_get(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    query: SearchQueryDependency,
    filter: FaceListFilterDependency,
    list_request: SearchListRequestDependency,
) -> SearchFacesResultListResponse:
    del user
    try:
        request = SearchFacesRequest(
            query=query,
            filter_=filter,
            limit=list_request.limit,
            return_total_count=list_request.return_total_count,
            cursor=list_request.cursor,
        )
        return await database.faces.search(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))


@router.get("/search-pages", response_model=SearchPagesResultListResponse)
async def search_pages_get(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    query: SearchQueryDependency,
    filter: PageListFilterDependency,
    list_request: SearchListRequestDependency,
) -> SearchPagesResultListResponse:
    del user
    try:
        request = SearchPagesRequest(
            query=query,
            filter_=filter,
            limit=list_request.limit,
            return_total_count=list_request.return_total_count,
            cursor=list_request.cursor,
        )
        return await database.sources.search_pages(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))


@router.get("/search-documents", response_model=SearchDocumentsResultListResponse)
async def search_documents_get(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    query: SearchQueryDependency,
    filter: DocumentListFilterDependency,
    list_request: SearchListRequestDependency,
) -> SearchDocumentsResultListResponse:
    del user
    try:
        request = SearchDocumentsRequest(
            query=query,
            filter_=filter,
            limit=list_request.limit,
            return_total_count=list_request.return_total_count,
            cursor=list_request.cursor,
        )
        return await database.sources.search_documents(request)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))
