"""Annotation endpoints for the current collection model."""

import uuid

from fastapi import (
    APIRouter,
    status,
)

from people_gator_api.schemas.entities import (
    DocumentMentionCreateRequest,
    DocumentMentionEntityPatchRequest,
    DocumentMentionResponse,
    FaceCreateRequest,
    FaceEntityPatchRequest,
    FaceResponse,
    PageMentionCreateRequest,
    PageMentionResponse,
)
from people_gator_api.services.auth_service import (
    AnnotatorUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.crud_services.annotation_service import (
    create_document_mention,
    create_face,
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
from people_gator_api.services.database_service import (
    WeaviateSessionDependency,
)
from people_gator_api.services.http_errors import (
    raise_api_error,
)

router = APIRouter(tags=["annotations"])


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
    return await create_page_mention(session, payload)


@router.get("/page-mentions", response_model=list[PageMentionResponse])
async def list_page_mentions_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    document_mention_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> list[PageMentionResponse]:
    return await list_page_mentions(
        session,
        document_mention_id,
        source_id,
        after_id,
        limit,
    )


@router.get("/page-mentions/{page_mention_id}", response_model=PageMentionResponse)
async def get_page_mention_route(
    page_mention_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> PageMentionResponse:
    page_mention = await get_page_mention(session, page_mention_id)
    if page_mention is None:
        raise_api_error(404, "not_found", "Page mention not found")
    return page_mention

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
    return await create_document_mention(session, payload)


@router.get("/document-mentions", response_model=list[DocumentMentionResponse])
async def list_document_mentions_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    entity_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> list[DocumentMentionResponse]:
    return await list_document_mentions(session, entity_id, source_id, after_id, limit)


@router.get(
    "/document-mentions/{document_mention_id}",
    response_model=DocumentMentionResponse,
)
async def get_document_mention_route(
    document_mention_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> DocumentMentionResponse:
    item = await get_document_mention(session, document_mention_id)
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
    item = await patch_document_mention_entity(session, document_mention_id, payload.entity_id)
    if item is None:
        raise_api_error(404, "not_found", "Document mention not found")
    return item

@router.get(
    "/document-mentions/{document_mention_id}/page-mentions",
    response_model=list[PageMentionResponse],
)
async def list_document_mention_page_mentions_route(
    document_mention_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> list[PageMentionResponse]:
    items = await list_page_mentions(session, document_mention_id=document_mention_id, source_id=None, after_id=after_id, limit=limit)
    return items


@router.post("/faces", response_model=FaceResponse, status_code=status.HTTP_201_CREATED)
async def create_face_route(
    payload: FaceCreateRequest,
    session: WeaviateSessionDependency,
    principal: DataIngestUserDependency,
) -> FaceResponse:
    return await create_face(session, payload)


@router.get("/faces", response_model=list[FaceResponse])
async def list_faces_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    source_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> list[FaceResponse]:
    return await list_faces(session, source_id, entity_id, after_id, limit)


@router.get("/faces/{detection_id}", response_model=FaceResponse)
async def get_face_route(
    detection_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> FaceResponse:
    face = await get_face(session, detection_id)
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
    face = await patch_face_entity(session, detection_id, payload.entity_id)
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face
