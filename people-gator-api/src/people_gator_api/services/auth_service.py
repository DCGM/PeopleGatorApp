import asyncio
import logging
import uuid
from botocore.exceptions import ClientError
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from typing import Literal
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.services.api_key_service import verify_api_key
from fastapi.security import SecurityScopes
from typing import Annotated, TypedDict
import argon2
from pydantic import TypeAdapter
from people_gator_api.schemas.auth import TokenResponse
from people_gator_api.schemas.users import UserCreateRequest, UserResponse
from people_gator_api.persistence.contracts import Database
from people_gator_api.services.database_service import DatabaseContextDependency
from contextlib import AbstractAsyncContextManager
from people_gator_api.services.filesystem_service import get_filesystem
from people_gator_api.services.jwk_service import (
    issue_access_token,
    issue_refresh_token,
    verify_access_token,
    verify_refresh_token,
)
from people_gator_api.settings import settings


logger = logging.getLogger(__name__)


from people_gator_api.services.auth_scopes import (
    BROWSE_SCOPE as BROWSE_SCOPE, ANNOTATE_SCOPE as ANNOTATE_SCOPE,
    INGEST_SCOPE as INGEST_SCOPE, ADMIN_SCOPE as ADMIN_SCOPE, KNOWN_SCOPES as KNOWN_SCOPES,
)


security = OAuth2PasswordBearer(
    auto_error=False,
    tokenUrl="/token/login",
    refreshUrl="/token/refresh",
    scheme_name="PeopleGator API OAuth2PasswordBearer",
    scopes={
        BROWSE_SCOPE: "Browse data and metadata",
        ANNOTATE_SCOPE: "Annotate data",
        INGEST_SCOPE: "Ingest data",
        ADMIN_SCOPE: "Administer the system",
    },
    description="OAuth2 password flow for PeopleGator API. Use this to obtain an access token for authenticated requests.",
)


MAX_REFRESH_SESSIONS_PER_USER = 4


class RefreshSession(TypedDict):
    jti: str
    scopes: list[str]


class UserRecord(TypedDict):
    hash: str
    scopes: set[str]


_refresh_sessions: dict[str, dict[str, RefreshSession]] = {}
_refresh_session_locks: dict[str, asyncio.Lock] = {}
_users_adapter = TypeAdapter(dict[str, UserRecord])


async def get_users() -> dict[str, UserRecord]:
    """Load password hashes and allowed scopes from the configured filesystem."""
    filesystem = get_filesystem()
    path = settings.jwk.users_path
    try:
        data = await filesystem.read_bytes(path)
    except (FileNotFoundError, ClientError) as exc:
        if isinstance(exc, ClientError) and exc.response.get("Error", {}).get("Code") not in (
            "NoSuchKey", "404", "NotFound",
        ):
            raise
        data = b"{}"
        await filesystem.write_bytes(path, data)
    return _users_adapter.validate_json(data)


def _check_scopes(scopes: list[str], allowed_scopes: set[str]) -> None:
    for scope in scopes:
        if scope not in KNOWN_SCOPES or scope not in allowed_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions for scope: {scope}",
            )


async def resolve_active_user(
    database_context: AbstractAsyncContextManager[Database], username: str,
) -> UserResponse:
    """Resolve the persisted identity for token issuance and require it to be active.

    First login creates an active identity; existing records are never reactivated.
    """
    async with database_context as database:
        user = await database.users.get_or_create(UserCreateRequest(
            display_name=username, is_active=True,
            external_subject=username, external_issuer=settings.jwk.issuer,
        ))
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is inactive")
    return user



async def get_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    database_context: DatabaseContextDependency,
) -> TokenResponse:
    """Get the raw access token and refresh token from the request context."""
    username = form_data.username
    password = form_data.password
    scopes = form_data.scopes
    users = await get_users()
    user_record = users.get(username)
    valid_password = False
    if user_record is not None:
        try:
            valid_password = argon2.PasswordHasher().verify(user_record["hash"], password)
        except argon2.exceptions.VerifyMismatchError:
            pass
    if user_record is None or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    _check_scopes(scopes, user_record["scopes"])
    user = await resolve_active_user(database_context, username)

    access_token = await issue_access_token(subject=username, scopes=scopes, user_id=user.user_id)
    jti = str(uuid.uuid4())
    refresh_token = await issue_refresh_token(
        subject=username, scopes=scopes, jti=jti,
    )

    async with _refresh_session_locks.setdefault(username, asyncio.Lock()):
        refresh_sessions = _refresh_sessions.setdefault(username, {})
        refresh_sessions[jti] = {"jti": jti, "scopes": scopes}
        if len(refresh_sessions) > MAX_REFRESH_SESSIONS_PER_USER:
            oldest_session_id = next(iter(refresh_sessions))
            del refresh_sessions[oldest_session_id]
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")
    

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


async def authenticate_api_key(secret: str, database: Database, required_scopes: list[str]) -> AuthContext:
    identifier, record = await verify_api_key(secret)
    _check_scopes(required_scopes, record.scopes)
    user = await database.users.get_or_create(UserCreateRequest(
        display_name=record.username, is_active=True,
        external_subject=record.username, external_issuer=settings.jwk.issuer,
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
    database_context: DatabaseContextDependency,
    token: Annotated[str | None, Security(security)],
    api_key: Annotated[str | None, Security(api_key_security)],
) -> AuthContext:
    has_bearer = "authorization" in request.headers
    has_key = "x-api-key" in request.headers
    if has_bearer and has_key:
        raise HTTPException(400, "Use one authentication method")
    if has_bearer:
        if not token or not token.strip():
            raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"})
        context = await authenticate_bearer(token)
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


async def refresh_access_token(
    refresh_token: str, database_context: AbstractAsyncContextManager[Database],
) -> TokenResponse:
    """Exchange a refresh token for a new access token.

    Validates the refresh token, its session, current credential scopes and the
    persisted user's active state, then rotates the session with the same scopes.
    An inactive user's session is revoked and no tokens are issued.
    """
    try:
        claims = await verify_refresh_token(refresh_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}",
        )
    
    subject = claims.get("sub")
    jti = claims.get("jti")
    
    if not subject or not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token claims",
        )
    
    users = await get_users()
    user_record = users.get(subject)
    if user_record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    session = _refresh_sessions.get(subject, {}).get(jti)
    if session is None or session["jti"] != jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token session expired",
        )

    scopes = session["scopes"]
    _check_scopes(scopes, user_record["scopes"])
    try:
        user = await resolve_active_user(database_context, subject)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            async with _refresh_session_locks.setdefault(subject, asyncio.Lock()):
                _refresh_sessions.get(subject, {}).pop(jti, None)
        raise

    access_token = await issue_access_token(subject=subject, scopes=scopes, user_id=user.user_id)
    new_jti = str(uuid.uuid4())
    new_refresh_token = await issue_refresh_token(
        subject=subject, scopes=scopes, jti=new_jti,
    )

    async with _refresh_session_locks.setdefault(subject, asyncio.Lock()):
        refresh_sessions = _refresh_sessions.get(subject, {})
        # Signing awaits I/O; another request may have rotated or evicted the session.
        if refresh_sessions.get(jti) is not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token session expired",
            )
        del refresh_sessions[jti]
        refresh_sessions[new_jti] = {"jti": new_jti, "scopes": scopes}
    
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token, token_type="bearer")


type TokenDependency = Annotated[TokenResponse, Depends(get_token)]

type DataIngestActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[INGEST_SCOPE])]
type AnnotatorActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[ANNOTATE_SCOPE])]
type AdminActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[ADMIN_SCOPE])]
type BrowseActorDependency = Annotated[AuthContext, Security(get_auth_context, scopes=[BROWSE_SCOPE])]

# Retain import compatibility for consumers during the transition.
DataIngestUserDependency = DataIngestActorDependency
AnnotatorUserDependency = AnnotatorActorDependency
AdminUserDependency = AdminActorDependency
BrowseUserDependency = BrowseActorDependency
