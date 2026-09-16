"""Annotation endpoints for the current collection model."""

import uuid
from collections.abc import AsyncGenerator

from fastapi import (
    APIRouter,
    Query,
    status,
)

from people_gator_api.schemas.entities import (
    DocumentMentionCreateRequest,
    DocumentMentionEntityPatchRequest,
    DocumentMentionListResponse,
    DocumentMentionResponse,
    FaceCreateRequest,
    FaceEntityPatchRequest,
    FaceListResponse,
    FaceResponse,
    PageMentionCreateRequest,
    PageMentionListResponse,
    PageMentionResponse,
)
from people_gator_api.services.auth_service import (
    AnnotatorUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.crud_services.annotation_service import (
    create_document_mention,
    create_document_mention_batch,
    create_face,
    create_face_batch,
    create_page_mention,
    get_document_mention,
    get_face,
    get_page_mention,
    list_document_mentions,
    list_faces,
    list_page_mentions,
    patch_document_mention_entity,
    patch_face_entity,
)
from people_gator_api.services.crud_services.source_service import SourceResolutionError
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.routes.v1.source_filters import SourceFilterDependency

router = APIRouter(tags=["annotations"])


async def _iter_payloads[T](items: list[T]) -> AsyncGenerator[T, None]:
    for item in items:
        yield item


@router.get("/page-mentions", response_model=PageMentionListResponse)
async def list_page_mentions_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    resolved_source_id: SourceFilterDependency,
    document_mention_id: uuid.UUID | None = None,
    principal_id: uuid.UUID | None = None,
    name: str | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> PageMentionListResponse:
    return await list_page_mentions(
        session,
        principal.principal_id,
        document_mention_id,
        resolved_source_id,
        after_id,
        limit,
        owner_principal_id=principal_id,
        name=name,
    )


@router.post(
    "/page-mentions",
    response_model=PageMentionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_page_mention_route(
    payload: PageMentionCreateRequest,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> PageMentionResponse:
    try:
        page_mention = await create_page_mention(session, payload, principal.principal_id)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return page_mention


@router.get("/page-mentions/{page_mention_id}", response_model=PageMentionResponse)
async def get_page_mention_route(
    page_mention_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> PageMentionResponse:
    page_mention = await get_page_mention(
        session, principal.principal_id, page_mention_id
    )
    if page_mention is None:
        raise_api_error(404, "not_found", "Page mention not found")
    return page_mention


@router.get("/document-mentions", response_model=DocumentMentionListResponse)
async def list_document_mentions_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    resolved_source_id: SourceFilterDependency,
    entity_id: uuid.UUID | None = None,
    principal_id: uuid.UUID | None = None,
    name: str | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> DocumentMentionListResponse:
    return await list_document_mentions(
        session,
        principal.principal_id,
        entity_id,
        resolved_source_id,
        after_id,
        limit,
        owner_principal_id=principal_id,
        name=name,
    )


@router.post(
    "/document-mentions",
    response_model=DocumentMentionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_mention_route(
    payload: DocumentMentionCreateRequest,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> DocumentMentionResponse:
    try:
        document_mention = await create_document_mention(
            session, payload, principal.principal_id
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return document_mention


@router.post(
    "/document-mentions:batch",
    response_model=list[DocumentMentionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_document_mention_batch_route(
    payload: list[DocumentMentionCreateRequest],
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> list[DocumentMentionResponse]:
    try:
        document_mentions = await create_document_mention_batch(
            session,
            _iter_payloads(payload),
            principal.principal_id,
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return document_mentions


@router.get(
    "/document-mentions/{document_mention_id}",
    response_model=DocumentMentionResponse,
)
async def get_document_mention_route(
    document_mention_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> DocumentMentionResponse:
    item = await get_document_mention(
        session, principal.principal_id, document_mention_id
    )
    if item is None:
        raise_api_error(404, "not_found", "Document mention not found")
    return item


@router.patch(
    "/document-mentions/{document_mention_id}",
    response_model=DocumentMentionResponse,
)
async def patch_document_mention_entity_route(
    document_mention_id: uuid.UUID,
    payload: DocumentMentionEntityPatchRequest,
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
) -> DocumentMentionResponse:
    item = await patch_document_mention_entity(
        session,
        principal.principal_id,
        document_mention_id,
        payload.entity_id,
    )
    if item is None:
        raise_api_error(404, "not_found", "Document mention not found")
    return item


@router.get("/faces", response_model=FaceListResponse)
async def list_faces_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    resolved_source_id: SourceFilterDependency,
    entity_id: uuid.UUID | None = None,
    principal_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> FaceListResponse:
    return await list_faces(
        session,
        principal.principal_id,
        resolved_source_id,
        entity_id,
        after_id,
        limit,
        owner_principal_id=principal_id,
    )


@router.post("/faces", response_model=FaceResponse, status_code=status.HTTP_201_CREATED)
async def create_face_route(
    payload: FaceCreateRequest,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> FaceResponse:
    try:
        face = await create_face(session, payload, principal.principal_id)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return face


@router.post(
    "/faces:batch",
    response_model=list[FaceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_face_batch_route(
    payload: list[FaceCreateRequest],
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> list[FaceResponse]:
    try:
        faces = await create_face_batch(
            session,
            _iter_payloads(payload),
            principal.principal_id,
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return faces


@router.get("/faces/{detection_id}", response_model=FaceResponse)
async def get_face_route(
    detection_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> FaceResponse:
    face = await get_face(session, principal.principal_id, detection_id)
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face


@router.patch("/faces/{detection_id}", response_model=FaceResponse)
async def patch_face_entity_route(
    detection_id: uuid.UUID,
    payload: FaceEntityPatchRequest,
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
) -> FaceResponse:
    face = await patch_face_entity(
        session,
        principal.principal_id,
        detection_id,
        payload.entity_id,
    )
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face
