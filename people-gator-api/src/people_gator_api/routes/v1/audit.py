"""Typed, auditor-only historical object lists, independent of live objects."""

from typing import Annotated
from fastapi import APIRouter, Query
from people_gator_api.schemas.audit_history import (
    EntityAuditListRequest,
    EntityAuditListResponse,
    FaceAuditListRequest,
    FaceAuditListResponse,
    TextMentionAuditListRequest,
    TextMentionAuditListResponse,
    SourceAuditListRequest,
    SourceAuditListResponse,
)
from people_gator_api.services.auth_service import AuditorActorDependency
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error

router = APIRouter(tags=["audit"])


@router.get("/entities/audit", response_model=EntityAuditListResponse)
async def list_entity_audit_route(
    database: DatabaseDependency,
    user: AuditorActorDependency,
    query: Annotated[EntityAuditListRequest, Query()],
) -> EntityAuditListResponse:
    try:
        return await database.audit.list_entities(query)
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))


@router.get("/faces/audit", response_model=FaceAuditListResponse)
async def list_face_audit_route(
    database: DatabaseDependency,
    user: AuditorActorDependency,
    query: Annotated[FaceAuditListRequest, Query()],
) -> FaceAuditListResponse:
    try:
        return await database.audit.list_faces(query)
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))


@router.get("/text-mentions/audit", response_model=TextMentionAuditListResponse)
async def list_text_mention_audit_route(
    database: DatabaseDependency,
    user: AuditorActorDependency,
    query: Annotated[TextMentionAuditListRequest, Query()],
) -> TextMentionAuditListResponse:
    try:
        return await database.audit.list_text_mentions(query)
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))


@router.get("/sources/audit", response_model=SourceAuditListResponse)
async def list_source_audit_route(
    database: DatabaseDependency,
    user: AuditorActorDependency,
    query: Annotated[SourceAuditListRequest, Query()],
) -> SourceAuditListResponse:
    try:
        return await database.audit.list_sources(query)
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))
