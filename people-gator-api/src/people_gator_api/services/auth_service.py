import asyncio
import logging
import uuid
from botocore.exceptions import ClientError
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import SecurityScopes
from typing import Annotated, TypedDict
import argon2
from pydantic import TypeAdapter
from people_gator_api.schemas.auth import TokenResponse
from people_gator_api.schemas.users import UserCreateRequest, UserResponse
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.services.filesystem_service import get_filesystem
from people_gator_api.services.jwk_service import (
    issue_access_token,
    issue_refresh_token,
    verify_access_token,
    verify_refresh_token,
)
from people_gator_api.settings import settings


logger = logging.getLogger(__name__)


BROWSE_SCOPE = "people-gator:browse"
ANNOTATE_SCOPE = "people-gator:annotate"
INGEST_SCOPE = "people-gator:ingest"
ADMIN_SCOPE = "people-gator:admin"

KNOWN_SCOPES = {
    BROWSE_SCOPE,
    ANNOTATE_SCOPE,
    INGEST_SCOPE,
    ADMIN_SCOPE,
}


security = OAuth2PasswordBearer(
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



async def get_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
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

    access_token = await issue_access_token(subject=username, scopes=scopes)
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
    

async def get_current_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(security)],
    database: DatabaseDependency,
) -> UserResponse:
    """Get the current user from the request context."""
    claims = await verify_access_token(token)
    issuer = claims["iss"]
    subject = claims["sub"]
    scopes = claims["scopes"]
    user = await database.users.get_or_create(
        UserCreateRequest(
            display_name=subject,
            is_active=True,
            external_subject=subject,
            external_issuer=issuer,
        )
    )
    for scope in security_scopes.scopes:
        if scope not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions for scope: {scope}",
            )
    return user


async def refresh_access_token(refresh_token: str) -> TokenResponse:
    """Exchange a refresh token for a new access token.
    
    Validates that the refresh token is valid and that the session exists,
    then generates a new access token with the same scopes.
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

    access_token = await issue_access_token(subject=subject, scopes=scopes)
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

type DataIngestUserDependency = Annotated[
    UserResponse, Security(get_current_user, scopes=[INGEST_SCOPE])
]
type AnnotatorUserDependency = Annotated[
    UserResponse, Security(get_current_user, scopes=[ANNOTATE_SCOPE])
]
type AdminUserDependency = Annotated[
    UserResponse, Security(get_current_user, scopes=[ADMIN_SCOPE])
]
type BrowseUserDependency = Annotated[
    UserResponse, Security(get_current_user, scopes=[BROWSE_SCOPE])
]
