"""Search-profile endpoint.

Allow a retrieval of current search profile configuration.
"""

from fastapi import (
    APIRouter,
    Depends,
)

from people_gator_api.services.auth_service import (
    AuthContext,
    require_scopes,
)
from people_gator_api.settings import (
    settings,
    SearchProfileSettings,
)


router = APIRouter(tags=["search-profile"])

@router.get("/search-profile", response_model=SearchProfileSettings)
async def get_search_profile(
    auth_context: "AuthContext" = Depends(require_scopes("people-gator:browse")),
) -> SearchProfileSettings:
    """Get the current search profile configuration."""
    return settings.search.profile
