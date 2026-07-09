"""Service for annotation endpoints (spec §2.2–§2.5).

Annotations are the four evidence types: named entities, detections,
descriptions, and alternative names.  Each is a flat table with a FK to
SOURCE.  This service provides create + list operations for each type.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.models.annotation.alternative_name import AlternativeName
from people_gator_api.models.annotation.description import Description
from people_gator_api.models.annotation.detection import Detection
from people_gator_api.models.annotation.named_entity import NamedEntity
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
from people_gator_api.utils.uuid_utils import uuid6_to_datetime




# ---------------------------------------------------------------------------
# Named entities
# ---------------------------------------------------------------------------


def _named_entity_out(item: NamedEntity) -> NamedEntityResponse:
    return NamedEntityResponse(
        annotation_id=item.annotation_id,
        text=item.text,
        source_id=item.source_id,
        offset_start=item.offset_start,
        offset_end=item.offset_end,
        entity_type=item.entity_type,
        principal_id=item.principal_id,
        confidence=item.confidence,
        created_at=uuid6_to_datetime(item.created_at),
    )


async def create_named_entity(
    session: AsyncSession,
    payload: NamedEntityCreateRequest,
) -> NamedEntityResponse:
    entity = await NamedEntity.create(
        session=session,
        text=payload.text,
        source_id=payload.source_id,
        offset_start=payload.offset_start,
        offset_end=payload.offset_end,
        entity_type=payload.entity_type,
        principal_id=payload.principal_id,
        confidence=payload.confidence,
    )
    return _named_entity_out(entity)


async def get_named_entity(
    session: AsyncSession,
    entity_id: uuid.UUID,
) -> NamedEntityResponse | None:
    entity = await NamedEntity.get(session, entity_id)
    if entity is None:
        return None
    return _named_entity_out(entity)


async def list_named_entities(
    session: AsyncSession,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[NamedEntityResponse]:
    items = await NamedEntity.list_page(
        session,
        source_id=source_id,
        after_id=after_id,
        limit=limit,
    )
    return [_named_entity_out(item) for item in items]


# ---------------------------------------------------------------------------
# Detections
# ---------------------------------------------------------------------------


def _detection_out(item: Detection) -> DetectionResponse:
    return DetectionResponse(
        annotation_id=item.annotation_id,
        source_id=item.source_id,
        bounding_box=item.bounding_box,
        keypoints=item.keypoints,
        principal_id=item.principal_id,
        confidence=item.confidence,
        created_at=uuid6_to_datetime(item.created_at),
    )


async def create_detection(
    session: AsyncSession,
    payload: DetectionCreateRequest,
) -> DetectionResponse:
    detection = await Detection.create(
        session=session,
        source_id=payload.source_id,
        bounding_box=payload.bounding_box,
        keypoints=payload.keypoints,
        principal_id=payload.principal_id,
        confidence=payload.confidence,
    )
    return _detection_out(detection)


async def get_detection(
    session: AsyncSession,
    detection_id: uuid.UUID,
) -> DetectionResponse | None:
    detection = await Detection.get(session, detection_id)
    if detection is None:
        return None
    return _detection_out(detection)


async def list_detections(
    session: AsyncSession,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DetectionResponse]:
    items = await Detection.list_page(
        session,
        source_id=source_id,
        after_id=after_id,
        limit=limit,
    )
    return [_detection_out(item) for item in items]


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


def _description_out(item: Description) -> DescriptionResponse:
    return DescriptionResponse(
        annotation_id=item.annotation_id,
        text=item.text,
        source_id=item.source_id,
        language=item.language,
        principal_id=item.principal_id,
        created_at=uuid6_to_datetime(item.created_at),
    )


async def create_description(
    session: AsyncSession,
    payload: DescriptionCreateRequest,
    principal_id: uuid.UUID,
) -> DescriptionResponse:
    description = await Description.create(
        session=session,
        text=payload.text,
        source_id=payload.source_id,
        language=payload.language,
        principal_id=principal_id,
    )
    return _description_out(description)


async def get_description(
    session: AsyncSession,
    description_id: uuid.UUID,
) -> DescriptionResponse | None:
    description = await Description.get(session, description_id)
    if description is None:
        return None
    return _description_out(description)


async def list_descriptions(
    session: AsyncSession,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DescriptionResponse]:
    items = await Description.list_page(session, after_id=after_id, limit=limit)
    return [_description_out(item) for item in items]


# ---------------------------------------------------------------------------
# Alternative names
# ---------------------------------------------------------------------------


def _alt_name_out(item: AlternativeName) -> AlternativeNameResponse:
    return AlternativeNameResponse(
        annotation_id=item.annotation_id,
        name=item.name,
        name_type=item.name_type,
        source_id=item.source_id,
        language=item.language,
        principal_id=item.principal_id,
        created_at=uuid6_to_datetime(item.created_at),
    )


async def create_alternative_name(
    session: AsyncSession,
    payload: AlternativeNameCreateRequest,
    principal_id: uuid.UUID,
) -> AlternativeNameResponse:
    alt_name = await AlternativeName.create(
        session=session,
        name=payload.name,
        name_type=payload.name_type,
        source_id=payload.source_id,
        language=payload.language,
        principal_id=principal_id,
    )
    return _alt_name_out(alt_name)


async def get_alternative_name(
    session: AsyncSession,
    alt_name_id: uuid.UUID,
) -> AlternativeNameResponse | None:
    alt_name = await AlternativeName.get(session, alt_name_id)
    if alt_name is None:
        return None
    return _alt_name_out(alt_name)


async def list_alternative_names(
    session: AsyncSession,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[AlternativeNameResponse]:
    items = await AlternativeName.list_page(session, after_id=after_id, limit=limit)
    return [_alt_name_out(item) for item in items]
