"""Authenticated immutable audit queries, including deleted objects."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Query, Path
from people_gator_api.schemas.audit import (
    AuditQuery,
    AuditListResponse,
    AuditRevision,
    ObjectKind,
)
from people_gator_api.services.auth_service import BrowseActorDependency
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=AuditListResponse)
async def list_audit_route(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    query: Annotated[AuditQuery, Query()],
) -> AuditListResponse:
    try:
        return await database.audit.list(query)
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))


@router.get(
    "/audit/{object_type}/{object_id}/versions/{version}", response_model=AuditRevision
)
async def get_audit_revision_route(
    object_type: ObjectKind,
    object_id: UUID,
    version: Annotated[int, Path(ge=1)],
    database: DatabaseDependency,
    user: BrowseActorDependency,
) -> AuditRevision:
    try:
        revision = await database.audit.get(object_type, object_id, version)
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))
    if revision is None:
        raise_api_error(404, "not_found", "Archived version not found")
    return revision
