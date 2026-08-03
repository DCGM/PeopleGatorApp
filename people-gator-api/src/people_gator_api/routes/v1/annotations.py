"""Annotation endpoints for the current collection model."""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    status,
)
from weaviate import (
    WeaviateAsyncClient,
)

from people_gator_api.schemas.entities import (
    DescriptionCreateRequest,
    DescriptionResponse,
    DocumentMentionCreateRequest,
    DocumentMentionResponse,
    EntityNameCreateRequest,
    EntityNameResponse,
    FaceCreateRequest,
    FaceResponse,
    PageMentionCreateRequest,
    PageMentionResponse,
    SpanCreateRequest,
    SpanResponse,
)
from people_gator_api.services.auth_service import (
    AuthContext,
    require_scopes,
)
from people_gator_api.services.crud_services.annotation_service import (
    create_description,
    create_document_mention,
    create_entity_name,
    create_face,
    create_page_mention,
    create_span,
    get_description,
    get_document_mention,
    get_entity_name,
    get_face,
    get_page_mention,
    get_span,
    list_descriptions,
    list_document_mentions,
    list_entity_names,
    list_faces,
    list_page_mentions,
    list_spans,
)
from people_gator_api.services.database_service import (
    get_session,
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
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> PageMentionResponse:
    return await create_page_mention(session, payload)


@router.get("/page-mentions", response_model=list[PageMentionResponse])
async def list_page_mentions_route(
    document_mention_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
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
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> PageMentionResponse:
    page_mention = await get_page_mention(session, page_mention_id)
    if page_mention is None:
        raise_api_error(404, "not_found", "Page mention not found")
    return page_mention


@router.post("/spans", response_model=SpanResponse, status_code=status.HTTP_201_CREATED)
async def create_span_route(
    payload: SpanCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SpanResponse:
    return await create_span(session, payload)


@router.get("/spans", response_model=list[SpanResponse])
async def list_spans_route(
    page_mention_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> list[SpanResponse]:
    return await list_spans(session, page_mention_id, source_id, after_id, limit)


@router.get("/spans/{span_id}", response_model=SpanResponse)
async def get_span_route(
    span_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> SpanResponse:
    span = await get_span(session, span_id)
    if span is None:
        raise_api_error(404, "not_found", "Span not found")
    return span


@router.post(
    "/document-mentions",
    response_model=DocumentMentionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_document_mention_route(
    payload: DocumentMentionCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> DocumentMentionResponse:
    return await create_document_mention(session, payload)


@router.get("/document-mentions", response_model=list[DocumentMentionResponse])
async def list_document_mentions_route(
    entity_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> list[DocumentMentionResponse]:
    return await list_document_mentions(session, entity_id, source_id, after_id, limit)


@router.get(
    "/document-mentions/{document_mention_id}",
    response_model=DocumentMentionResponse,
)
async def get_document_mention_route(
    document_mention_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> DocumentMentionResponse:
    item = await get_document_mention(session, document_mention_id)
    if item is None:
        raise_api_error(404, "not_found", "Document mention not found")
    return item


@router.post("/faces", response_model=FaceResponse, status_code=status.HTTP_201_CREATED)
async def create_face_route(
    payload: FaceCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> FaceResponse:
    return await create_face(session, payload)


@router.get("/faces", response_model=list[FaceResponse])
async def list_faces_route(
    source_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> list[FaceResponse]:
    return await list_faces(session, source_id, entity_id, after_id, limit)


@router.get("/faces/{detection_id}", response_model=FaceResponse)
async def get_face_route(
    detection_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> FaceResponse:
    face = await get_face(session, detection_id)
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face


@router.post(
    "/descriptions",
    response_model=DescriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_description_route(
    payload: DescriptionCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> DescriptionResponse:
    return await create_description(session, payload)


@router.get("/descriptions", response_model=list[DescriptionResponse])
async def list_descriptions_route(
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> list[DescriptionResponse]:
    return await list_descriptions(session, entity_id, after_id, limit)


@router.get("/descriptions/{description_id}", response_model=DescriptionResponse)
async def get_description_route(
    description_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> DescriptionResponse:
    description = await get_description(session, description_id)
    if description is None:
        raise_api_error(404, "not_found", "Description not found")
    return description


@router.post(
    "/entity-names",
    response_model=EntityNameResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_entity_name_route(
    payload: EntityNameCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> EntityNameResponse:
    return await create_entity_name(session, payload)


@router.get("/entity-names", response_model=list[EntityNameResponse])
async def list_entity_names_route(
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> list[EntityNameResponse]:
    return await list_entity_names(session, entity_id, after_id, limit)


@router.get("/entity-names/{entity_name_id}", response_model=EntityNameResponse)
async def get_entity_name_route(
    entity_name_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: WeaviateAsyncClient = Depends(get_session),
) -> EntityNameResponse:
    entity_name = await get_entity_name(session, entity_name_id)
    if entity_name is None:
        raise_api_error(404, "not_found", "Entity name not found")
    return entity_name
