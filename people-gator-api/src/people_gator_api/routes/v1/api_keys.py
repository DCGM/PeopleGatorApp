"""Browse historical API-key identities without exposing credentials."""

from fastapi import APIRouter
from people_gator_api.routes.v1.query_dependencies import ListRequestDependency
from people_gator_api.schemas.api_keys import APIKeyListResponse
from people_gator_api.services.auth_service import BrowseActorDependency
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error

router = APIRouter(tags=["api keys"])


@router.get("/api-keys", response_model=APIKeyListResponse)
async def list_api_keys_route(database: DatabaseDependency, actor: BrowseActorDependency,
                              list_request: ListRequestDependency) -> APIKeyListResponse:
    if database.api_keys is None:
        raise_api_error(501, "unsupported_backend", "API-key registry is unavailable")
    try:
        return await database.api_keys.list(list_request)
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))
