"""Annotation endpoints (spec §2.2–§2.5).

Annotations are the four evidence types: named entities, detections,
descriptions, and alternative names.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.schemas.identities import (
    AlternativeNameCreateRequest,
    AlternativeNameResponse,
    DescriptionCreateRequest,
    DescriptionResponse,
    DetectionCreateRequest,
    DetectionResponse,
    NamedEntityCreateRequest,
    NamedEntityResponse,
)
from people_gator_api.services.crud_services.annotation_service import (
    create_alternative_name,
    create_description,
    create_detection,
    create_named_entity,
    get_alternative_name,
    get_description,
    get_detection,
    get_named_entity,
    list_alternative_names,
    list_descriptions,
    list_detections,
    list_named_entities,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.database_service import get_session
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["annotations"])


# ---------------------------------------------------------------------------
# Named entities
# ---------------------------------------------------------------------------


@router.post("/named-entities", response_model=NamedEntityResponse, status_code=status.HTTP_201_CREATED)
async def create_named_entity_route(
    payload: NamedEntityCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> NamedEntityResponse:
    return await create_named_entity(session, payload)


@router.get("/named-entities", response_model=list[NamedEntityResponse])
async def list_named_entities_route(
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[NamedEntityResponse]:
    return await list_named_entities(session, source_id, after_id, limit)


@router.get("/named-entities/{entity_id}", response_model=NamedEntityResponse)
async def get_named_entity_route(
    entity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> NamedEntityResponse:
    entity = await get_named_entity(session, entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Named entity not found")
    return entity


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------


@router.post("/detections", response_model=DetectionResponse, status_code=status.HTTP_201_CREATED)
async def create_detection_route(
    payload: DetectionCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> DetectionResponse:
    return await create_detection(session, payload)


@router.get("/detections", response_model=list[DetectionResponse])
async def list_detections_route(
    source_id: uuid.UUID | None = None,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[DetectionResponse]:
    return await list_detections(session, source_id, after_id, limit)


@router.get("/detections/{detection_id}", response_model=DetectionResponse)
async def get_detection_route(
    detection_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> DetectionResponse:
    detection = await get_detection(session, detection_id)
    if detection is None:
        raise_api_error(404, "not_found", "Detection not found")
    return detection


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


@router.post("/descriptions", response_model=DescriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_description_route(
    payload: DescriptionCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> DescriptionResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    return await create_description(session, payload, auth.principal.principal_id)


@router.get("/descriptions", response_model=list[DescriptionResponse])
async def list_descriptions_route(
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[DescriptionResponse]:
    return await list_descriptions(session, after_id, limit)


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


# ---------------------------------------------------------------------------
# Alternative names
# ---------------------------------------------------------------------------


@router.post("/alternative-names", response_model=AlternativeNameResponse, status_code=status.HTTP_201_CREATED)
async def create_alternative_name_route(
    payload: AlternativeNameCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> AlternativeNameResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    return await create_alternative_name(session, payload, auth.principal.principal_id)


@router.get("/alternative-names", response_model=list[AlternativeNameResponse])
async def list_alternative_names_route(
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[AlternativeNameResponse]:
    return await list_alternative_names(session, after_id, limit)


@router.get("/alternative-names/{alt_name_id}", response_model=AlternativeNameResponse)
async def get_alternative_name_route(
    alt_name_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> AlternativeNameResponse:
    alt_name = await get_alternative_name(session, alt_name_id)
    if alt_name is None:
        raise_api_error(404, "not_found", "Alternative name not found")
    return alt_name
