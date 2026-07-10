"""Annotation endpoints for simplified ERD entities."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.schemas.entities import (
    DescriptionCreateRequest,
    DescriptionResponse,
    DocumentMentionCreateRequest,
    DocumentMentionResponse,
    FaceCreateRequest,
    FaceResponse,
    InformationCreateRequest,
    InformationResponse,
    MentionCreateRequest,
    MentionResponse,
    NameCreateRequest,
    NameResponse,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.crud_services.annotation_service import (
    create_description,
    create_document_mention,
    create_face,
    create_information,
    create_mention,
    create_name,
    get_description,
    get_document_mention,
    get_face,
    get_information,
    get_mention,
    get_name,
    list_descriptions,
    list_document_mentions,
    list_faces,
    list_information,
    list_mentions,
    list_names,
)
from people_gator_api.services.database_service import get_session
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["annotations"])


@router.post("/mentions", response_model=MentionResponse, status_code=status.HTTP_201_CREATED)
async def create_mention_route(
    payload: MentionCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> MentionResponse:
    return await create_mention(session, payload)


@router.get("/mentions", response_model=list[MentionResponse])
async def list_mentions_route(
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[MentionResponse]:
    return await list_mentions(session, source_id, after_id, limit)


@router.get("/mentions/{mention_id}", response_model=MentionResponse)
async def get_mention_route(
    mention_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> MentionResponse:
    mention = await get_mention(session, mention_id)
    if mention is None:
        raise_api_error(404, "not_found", "Mention not found")
    return mention


@router.post("/information", response_model=InformationResponse, status_code=status.HTTP_201_CREATED)
async def create_information_route(
    payload: InformationCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> InformationResponse:
    return await create_information(session, payload)


@router.get("/information", response_model=list[InformationResponse])
async def list_information_route(
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[InformationResponse]:
    return await list_information(session, source_id, after_id, limit)


@router.get("/information/{information_id}", response_model=InformationResponse)
async def get_information_route(
    information_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> InformationResponse:
    information = await get_information(session, information_id)
    if information is None:
        raise_api_error(404, "not_found", "Information not found")
    return information


@router.post("/document-mentions", response_model=DocumentMentionResponse, status_code=status.HTTP_201_CREATED)
async def create_document_mention_route(
    payload: DocumentMentionCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> DocumentMentionResponse:
    return await create_document_mention(session, payload)


@router.get("/document-mentions", response_model=list[DocumentMentionResponse])
async def list_document_mentions_route(
    entity_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentMentionResponse]:
    return await list_document_mentions(session, entity_id, source_id, after_id, limit)


@router.get("/document-mentions/{document_mention_id}", response_model=DocumentMentionResponse)
async def get_document_mention_route(
    document_mention_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> DocumentMentionResponse:
    item = await get_document_mention(session, document_mention_id)
    if item is None:
        raise_api_error(404, "not_found", "Document mention not found")
    return item


@router.post("/faces", response_model=FaceResponse, status_code=status.HTTP_201_CREATED)
async def create_face_route(
    payload: FaceCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> FaceResponse:
    return await create_face(session, payload)


@router.get("/faces", response_model=list[FaceResponse])
async def list_faces_route(
    source_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[FaceResponse]:
    return await list_faces(session, source_id, entity_id, after_id, limit)


@router.get("/faces/{detection_id}", response_model=FaceResponse)
async def get_face_route(
    detection_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> FaceResponse:
    face = await get_face(session, detection_id)
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face


@router.post("/descriptions", response_model=DescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_description_route(
    payload: DescriptionCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> DescriptionResponse:
    return await create_description(session, payload)


@router.get("/descriptions", response_model=list[DescriptionResponse])
async def list_descriptions_route(
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[DescriptionResponse]:
    return await list_descriptions(session, entity_id, after_id, limit)


@router.get("/descriptions/{description_id}", response_model=DescriptionResponse)
async def get_description_route(
    description_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> DescriptionResponse:
    description = await get_description(session, description_id)
    if description is None:
        raise_api_error(404, "not_found", "Description not found")
    return description


@router.post("/names", response_model=NameResponse, status_code=status.HTTP_201_CREATED)
async def create_name_route(
    payload: NameCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> NameResponse:
    return await create_name(session, payload)


@router.get("/names", response_model=list[NameResponse])
async def list_names_route(
    entity_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[NameResponse]:
    return await list_names(session, entity_id, after_id, limit)


@router.get("/names/{name_id}", response_model=NameResponse)
async def get_name_route(
    name_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> NameResponse:
    name = await get_name(session, name_id)
    if name is None:
        raise_api_error(404, "not_found", "Name not found")
    return name
