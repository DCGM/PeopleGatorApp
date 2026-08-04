import logging
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from functools import lru_cache
from dataclasses import dataclass
import uuid
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import SecurityScopes
from typing import Annotated
from people_gator_api.utils.uuid_utils import new_uuid6
from people_gator_api.services.crud_services.principal_service import get_or_create_user
from people_gator_api.services.database_service import WeaviateSessionDependency
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

@dataclass
class Principal:
    """Represents an authenticated user or service principal."""
    principal_id: uuid.UUID
    username: str
    scopes: set[str]

security = HTTPBasic()

async def get_current_user(
    security_scopes: SecurityScopes, token: Annotated[HTTPBasicCredentials, Depends(security)], session: WeaviateSessionDependency
):
    """Get the current user from the request context."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )
    username = token.username
    password = token.password
    scopes = KNOWN_SCOPES
    
    ### DEBUG: ONLY TEST CREDENTIALS ARE ALLOWED FOR NOW
    if username != "test" or password != "test":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    user = get_or_create_user(
        session=session,
        external_subject=username,
        external_issuer="http://test.people-gator-api.local",
        display_name=username,
        email="test@test.people-gator-api.local",
    )
    
    for scope in security_scopes.scopes:
        if scope not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions for scope: {scope}",
            )
    return Principal(
        principal_id=user.principal_id,
        username=username,
        scopes=scopes,
    )


type DataIngestUserDependency = Annotated[Principal, Security(get_current_user, scopes=[INGEST_SCOPE])]
type AnnotatorUserDependency = Annotated[Principal, Security(get_current_user, scopes=[ANNOTATE_SCOPE])]
type AdminUserDependency = Annotated[Principal, Security(get_current_user, scopes=[ADMIN_SCOPE])]
type BrowseUserDependency = Annotated[Principal, Security(get_current_user, scopes=[BROWSE_SCOPE])]
