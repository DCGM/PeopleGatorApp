"""Resource authentication: public token validation and isolated API-key access."""
import uuid
from contextlib import AbstractAsyncContextManager
from typing import Annotated, Literal, Protocol
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPBearer, SecurityScopes
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.persistence.contracts import APIKeyRepository, UserRepository
from people_gator_api.services.api_key_service import verify_api_key
from people_gator_api.services.database_service import get_database_context
from people_gator_api.services.jwk_service import verify_access_token
from people_gator_api.settings import settings
from people_gator_api.services.auth_scopes import (
    BROWSE_SCOPE as BROWSE_SCOPE, ANNOTATE_SCOPE as ANNOTATE_SCOPE,
    INGEST_SCOPE as INGEST_SCOPE, ADMIN_SCOPE as ADMIN_SCOPE, KNOWN_SCOPES as KNOWN_SCOPES,
)
from fastapi.security import HTTPAuthorizationCredentials
security = HTTPBearer(
    auto_error=False,
    scheme_name="PeopleGatorBearer",
    description="Use [Sign in](/login.html?return=%2Fdocs) to reuse your app session, or enter an access token.",
)

class IdentityRepositories(Protocol):
    @property
    def users(self) -> UserRepository: ...
    @property
    def api_keys(self) -> APIKeyRepository | None: ...

type IdentityContext = AbstractAsyncContextManager[IdentityRepositories]
type IdentityContextDependency = Annotated[IdentityContext, Depends(get_database_context, use_cache=False)]

def _check_scopes(scopes: list[str], allowed_scopes: set[str]) -> None:
    for scope in scopes:
        if scope not in KNOWN_SCOPES or scope not in allowed_scopes:
            raise HTTPException(403, f"Not enough permissions for scope: {scope}")

api_key_security = APIKeyHeader(name="X-API-Key", scheme_name="PeopleGatorAPIKey", auto_error=False)


class AuthContext(GenericActor):
    """Authenticated actor for authorization and attribution.

    Bearer contexts come from signed claims alone. Endpoints needing persisted
    profile data load it explicitly with ``database.users.get(user_id)``.
    """

    api_key_id: uuid.UUID | None = None
    authentication_method: Literal["bearer", "api_key"]
    scopes: set[str]


async def authenticate_bearer(token: str) -> AuthContext:
    """Authorize from the signed access token; never touches persistence."""
    try:
        claims = await verify_access_token(token)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"}) from exc
        raise
    return AuthContext(user_id=claims["uid"], authentication_method="bearer", scopes=set(claims["scopes"]))


async def authenticate_api_key(
    secret: str, database: IdentityRepositories, required_scopes: list[str],
) -> AuthContext:
    identifier, record = await verify_api_key(secret)
    _check_scopes(required_scopes, record.scopes)
    user = await database.users.get_or_create(UserCreateRequest(
        display_name=record.username, is_active=True,
        external_subject=record.username, external_issuer=settings.api_keys.identity_issuer,
    ))
    # API keys have no token exchange, so their persisted user is checked per request.
    if not user.is_active:
        raise HTTPException(403, "User is inactive")
    if database.api_keys is None:
        raise RuntimeError("API-key registry is unavailable for this persistence backend")
    key = await database.api_keys.get_or_create(APIKeyCreateRequest(
        identifier=identifier, display_name=record.display_name, user_id=user.user_id,
    ))
    return AuthContext(user_id=user.user_id, api_key_id=key.api_key_id,
                       authentication_method="api_key", scopes=record.scopes)


async def get_auth_context(
    security_scopes: SecurityScopes,
    request: Request,
    database_context: IdentityContextDependency,
    token: Annotated[HTTPAuthorizationCredentials | None, Security(security)],
    api_key: Annotated[str | None, Security(api_key_security)],
) -> AuthContext:
    has_bearer = "authorization" in request.headers
    has_key = "x-api-key" in request.headers
    if has_bearer and has_key:
        raise HTTPException(400, "Use one authentication method")
    if has_bearer:
        if not token or not token.credentials.strip():
            raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"})
        context = await authenticate_bearer(token.credentials)
    elif has_key:
        if not api_key or not api_key.strip():
            raise HTTPException(401, "Invalid API key", headers={"WWW-Authenticate": "APIKey"})
        # Authentication returns detached schemas. Release its connection and
        # user-identity advisory lock before the handler waits on external I/O.
        async with database_context as database:
            context = await authenticate_api_key(api_key, database, security_scopes.scopes)
    else:
        raise HTTPException(401, "Missing credentials", headers={"WWW-Authenticate": "Bearer, APIKey"})
    _check_scopes(security_scopes.scopes, context.scopes)
    return context


# Compatibility for code importing the previous dependency function.
get_current_user = get_auth_context


type DataIngestActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[INGEST_SCOPE])]
type AnnotatorActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[ANNOTATE_SCOPE])]
type AdminActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[ADMIN_SCOPE])]
type BrowseActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[BROWSE_SCOPE])]

# Retain import compatibility for consumers during the transition.
DataIngestUserDependency = DataIngestActorDependency
AnnotatorUserDependency = AnnotatorActorDependency
AdminUserDependency = AdminActorDependency
BrowseUserDependency = BrowseActorDependency
