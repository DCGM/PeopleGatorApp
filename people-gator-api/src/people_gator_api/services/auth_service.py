import logging
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import SecurityScopes
from typing import Annotated
import argon2
from people_gator_api.schemas.jwks import TokenResponse
from people_gator_api.schemas.principals import UserResponse
from people_gator_api.services.crud_services.principal_service import get_or_create_user
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.jwk_service import issue_key, verify_key


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
    tokenUrl="/api/v1/token/login",
    scheme_name="PeopleGator API OAuth2PasswordBearer",
    scopes={
        BROWSE_SCOPE: "Browse data and metadata",
        ANNOTATE_SCOPE: "Annotate data",
        INGEST_SCOPE: "Ingest data",
        ADMIN_SCOPE: "Administer the system",
    },
    description="OAuth2 password flow for PeopleGator API. Use this to obtain an access token for authenticated requests.",
)


user_db = {
    "test": {
        "hash": "$argon2id$v=19$m=65536,t=3,p=4$iTpODf7wIneTlqalyjALZA$1U6pPAHY87UZFYdK0R6wm6B403c9l42nnTw5K9ThuQc",
        "scopes": KNOWN_SCOPES,
    }
}



async def get_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """Get the raw access token from the request context."""
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
    token = await issue_key(
        subject=username,
        scopes=scopes,
    )
    return TokenResponse(access_token=token, token_type="bearer")
    

async def get_current_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(security)],
    session: WeaviateSessionDependency,
) -> UserResponse:
    """Get the current user from the request context."""
    claims = await verify_key(token)
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
