import logging
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from functools import lru_cache
from dataclasses import dataclass
import uuid
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import SecurityScopes
from typing import Annotated
from people_gator_api.utils.uuid_utils import new_uuid6

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

@lru_cache(maxsize=1)
def single_uuid() -> uuid.UUID:
    """Return a single UUID for testing purposes."""
    return new_uuid6()

@dataclass
class Principal:
    """Represents an authenticated user or service principal."""
    principal_id: uuid.UUID
    username: str
    scopes: set[str]

security = HTTPBasic()

async def get_current_user(
    security_scopes: SecurityScopes, token: Annotated[HTTPBasicCredentials, Depends(security)]
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
    
    for scope in security_scopes.scopes:
        if scope not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not enough permissions for scope: {scope}",
            )
    return Principal(principal_id=single_uuid(), username=username, scopes=scopes)


type DataIngestUserDependency = Annotated[Principal, Security(get_current_user, scopes=[INGEST_SCOPE])]
type AnnotatorUserDependency = Annotated[Principal, Security(get_current_user, scopes=[ANNOTATE_SCOPE])]
type AdminUserDependency = Annotated[Principal, Security(get_current_user, scopes=[ADMIN_SCOPE])]
type BrowseUserDependency = Annotated[Principal, Security(get_current_user, scopes=[BROWSE_SCOPE])]
