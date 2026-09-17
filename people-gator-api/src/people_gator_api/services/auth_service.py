import logging
import uuid
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import SecurityScopes
from typing import Annotated, TypedDict
import argon2
from people_gator_api.schemas.jwks import TokenResponse
from people_gator_api.schemas.users import UserResponse
from people_gator_api.services.crud_services.user_service import get_or_create_user
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.jwk_service import (
    issue_access_token,
    issue_refresh_token,
    verify_access_token,
    verify_refresh_token,
)


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


class RefreshSession(TypedDict):
    jti: str
    scopes: list[str]


class UserRecord(TypedDict):
    hash: str
    scopes: set[str]
    refresh_sessions: dict[str, RefreshSession]

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


user_db: dict[str, UserRecord] = {
    "test": {
        "hash": "$argon2id$v=19$m=65536,t=3,p=4$iTpODf7wIneTlqalyjALZA$1U6pPAHY87UZFYdK0R6wm6B403c9l42nnTw5K9ThuQc",
        "scopes": KNOWN_SCOPES,
        "refresh_sessions": {},  # Session UUID to refresh session (max 4)
    }
}

MAX_REFRESH_SESSIONS_PER_USER = 4



async def get_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """Get the raw access token and refresh token from the request context."""
    username = form_data.username
    password = form_data.password
    scopes = form_data.scopes
    user_record = user_db.get(username)
    # Check if the user exists and the password is correct
    if not user_record or not argon2.PasswordHasher().verify(str(user_record["hash"]), password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    for scope in scopes:
        if scope not in user_record["scopes"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions for scope: {scope}",
            )
    
    # Generate access token
    access_token = await issue_access_token(
        subject=username,
        scopes=scopes,
    )
    
    # Generate and persist both identifiers for this refresh session.
    jti = str(uuid.uuid4())
    refresh_token = await issue_refresh_token(
        subject=username,
        scopes=scopes,
        jti=jti,
    )
    
    # Store session by UUID (limit to 4 sessions per user).
    refresh_sessions = user_record["refresh_sessions"]
    refresh_sessions[jti] = {"jti": jti, "scopes": scopes}
    if len(refresh_sessions) > MAX_REFRESH_SESSIONS_PER_USER:
        oldest_session_id = next(iter(refresh_sessions))
        del refresh_sessions[oldest_session_id]
    user_record["refresh_sessions"] = refresh_sessions
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")
    

async def get_current_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(security)],
    session: WeaviateSessionDependency,
) -> UserResponse:
    """Get the current user from the request context."""
    claims = await verify_access_token(token)
    issuer = claims["iss"]
    subject = claims["sub"]
    scopes = claims["scopes"]
    user = await get_or_create_user(
        client=session,
        external_subject=subject,
        external_issuer=issuer,
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
    global user_db  # Use the in-memory user database for this example
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
    
    user_record = user_db.get(subject)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    # Verify that the session is valid and that its current token is being used.
    refresh_sessions = user_record["refresh_sessions"]
    session = refresh_sessions.get(jti)
    if session is None or session["jti"] != jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token session expired",
        )
    
    # Restore scopes from the persisted session because refresh tokens do not
    # carry access-token claims.
    scopes = session["scopes"]
    
    # Generate new access token with same scopes
    access_token = await issue_access_token(
        subject=subject,
        scopes=scopes,
    )
    
    # Rotate the refresh token identifier while keeping the session active.
    new_jti = str(uuid.uuid4())
    new_refresh_token = await issue_refresh_token(
        subject=subject,
        scopes=scopes,
        jti=new_jti,
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
