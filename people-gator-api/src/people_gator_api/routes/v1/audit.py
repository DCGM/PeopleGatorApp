"""Authenticated immutable audit queries, including deleted objects."""
from typing import Annotated
from fastapi import APIRouter, Query
from people_gator_api.schemas.audit import AuditQuery, AuditListResponse
from people_gator_api.services.auth_service import BrowseActorDependency
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=AuditListResponse)
async def list_audit_route(
    database: DatabaseDependency, user: BrowseActorDependency,
    query: Annotated[AuditQuery, Query()],
) -> AuditListResponse:
    try:
        return await database.audit.list(query)
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))
