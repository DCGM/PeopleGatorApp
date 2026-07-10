"""CRUD service for simplified annotation entities."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.models.annotation.description import Description
from people_gator_api.models.annotation.document_mention import DocumentMention
from people_gator_api.models.annotation.face import (
    BoundingBox as FaceBoundingBox,
    Face,
    FaceKeypoint as FaceModelKeypoint,
)
from people_gator_api.models.annotation.information import Information
from people_gator_api.models.annotation.mention import Mention, Polygon as MentionModelPolygon
from people_gator_api.models.annotation.name import Name
from people_gator_api.models.entities import Entity
from people_gator_api.schemas.entities import (
    BoundingBox,
    DescriptionCreateRequest,
    DescriptionResponse,
    DocumentMentionCreateRequest,
    DocumentMentionResponse,
    FaceCreateRequest,
    FaceKeypoint,
    FaceResponse,
    InformationCreateRequest,
    InformationResponse,
    MentionCreateRequest,
    MentionPolygon,
    MentionPolygonPoint,
    MentionResponse,
    NameCreateRequest,
    NameResponse,
)


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------


def _mention_out(item: Mention) -> MentionResponse:
    polygons = None
    if item.polygons is not None:
        polygons = [
            MentionPolygon(
                points=[
                    MentionPolygonPoint(x=point["x"], y=point["y"])
                    for point in polygon["points"]
                ]
            )
            for polygon in item.polygons
        ]

    return MentionResponse(
        mention_id=item.mention_id,
        text=item.text,
        document_mention_id=item.document_mention_id,
        source_id=item.source_id,
        offset_start=item.offset_start,
        offset_end=item.offset_end,
        polygons=polygons,
        model_agent_id=item.model_agent_id,
        confidence=item.confidence,
        embedding=item.embedding,
        model_identifier=item.model_identifier,
    )

async def create_mention(
    session: AsyncSession,
    payload: MentionCreateRequest,
) -> MentionResponse:
    polygons: list[MentionModelPolygon] | None = None
    if payload.polygons is not None:
        polygons = [
            {
                "points": [
                    {"x": point.x, "y": point.y}
                    for point in polygon.points
                ]
            }
            for polygon in payload.polygons
        ]

    item = await Mention.create(
        session=session,
        text=payload.text,
        document_mention_id=payload.document_mention_id,
        source_id=payload.source_id,
        offset_start=payload.offset_start,
        offset_end=payload.offset_end,
        polygons=polygons,
        model_agent_id=payload.model_agent_id,
        confidence=payload.confidence,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )
    return _mention_out(item)


async def get_mention(
    session: AsyncSession,
    mention_id: uuid.UUID,
) -> MentionResponse | None:
    item = await Mention.get(session, mention_id)
    if item is None:
        return None
    return _mention_out(item)


async def list_mentions(
    session: AsyncSession,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[MentionResponse]:
    items = await Mention.list_page(
        session,
        source_id=source_id,
        after_id=after_id,
        limit=limit,
    )
    return [_mention_out(item) for item in items]



# ---------------------------------------------------------------------------
# Information
# ---------------------------------------------------------------------------


def _information_out(item: Information) -> InformationResponse:
    return InformationResponse(
        information_id=item.information_id,
        text=item.text,
        document_mention_id=item.document_mention_id,
        source_id=item.source_id,
        model_agent_id=item.model_agent_id,
        embedding=item.embedding,
        model_identifier=item.model_identifier,
    )


async def create_information(
    session: AsyncSession,
    payload: InformationCreateRequest,
) -> InformationResponse:
    item = await Information.create(
        session=session,
        text=payload.text,
        document_mention_id=payload.document_mention_id,
        source_id=payload.source_id,
        model_agent_id=payload.model_agent_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )
    return _information_out(item)


async def get_information(
    session: AsyncSession,
    information_id: uuid.UUID,
) -> InformationResponse | None:
    item = await Information.get(session, information_id)
    if item is None:
        return None
    return _information_out(item)


async def list_information(
    session: AsyncSession,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[InformationResponse]:
    items = await Information.list_page(
        session,
        source_id=source_id,
        after_id=after_id,
        limit=limit,
    )
    return [_information_out(item) for item in items]


# ---------------------------------------------------------------------------
# Document Mentions
# ---------------------------------------------------------------------------


def _document_mention_out(item: DocumentMention) -> DocumentMentionResponse:
    return DocumentMentionResponse(
        document_mention_id=item.document_mention_id,
        name=item.name,
        information=item.information,
        model_agent_id=item.model_agent_id,
        source_id=item.source_id,
        entity_id=item.entity_id,
        embedding=item.embedding,
        model_identifier=item.model_identifier,
    )


async def create_document_mention(
    session: AsyncSession,
    payload: DocumentMentionCreateRequest,
) -> DocumentMentionResponse:
    item = await DocumentMention.create(
        session=session,
        name=payload.name,
        information=payload.information,
        model_agent_id=payload.model_agent_id,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )
    return _document_mention_out(item)


async def get_document_mention(
    session: AsyncSession,
    document_mention_id: uuid.UUID,
) -> DocumentMentionResponse | None:
    item = await DocumentMention.get(session, document_mention_id)
    if item is None:
        return None
    return _document_mention_out(item)


async def list_document_mentions(
    session: AsyncSession,
    entity_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DocumentMentionResponse]:
    items = await DocumentMention.list_page(
        session,
        entity_id=entity_id,
        source_id=source_id,
        after_id=after_id,
        limit=limit,
    )
    return [_document_mention_out(item) for item in items]


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------


def _face_out(item: Face) -> FaceResponse:
    bounding_box = BoundingBox(
        x=item.bounding_box["x"],
        y=item.bounding_box["y"],
        width=item.bounding_box["width"],
        height=item.bounding_box["height"],
    )
    keypoints = [
        FaceKeypoint(type=keypoint["type"], x=keypoint["x"], y=keypoint["y"])
        for keypoint in item.keypoints
    ]
    return FaceResponse(
        detection_id=item.detection_id,
        source_id=item.source_id,
        bounding_box=bounding_box,
        keypoints=keypoints,
        model_agent_id=item.model_agent_id,
        entity_id=item.entity_id,
        confidence=item.confidence,
        embedding=item.embedding,
        model_identifier=item.model_identifier,
    )


async def create_face(
    session: AsyncSession,
    payload: FaceCreateRequest,
) -> FaceResponse:
    bounding_box: FaceBoundingBox = {
        "x": payload.bounding_box.x,
        "y": payload.bounding_box.y,
        "width": payload.bounding_box.width,
        "height": payload.bounding_box.height,
    }
    keypoints: list[FaceModelKeypoint] = [
        {"type": keypoint.type, "x": keypoint.x, "y": keypoint.y}
        for keypoint in payload.keypoints
    ]
    item = await Face.create(
        session=session,
        source_id=payload.source_id,
        bounding_box=bounding_box,
        keypoints=keypoints,
        model_agent_id=payload.model_agent_id,
        entity_id=payload.entity_id,
        confidence=payload.confidence,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )
    return _face_out(item)


async def get_face(
    session: AsyncSession,
    detection_id: uuid.UUID,
) -> FaceResponse | None:
    item = await Face.get(session, detection_id)
    if item is None:
        return None
    return _face_out(item)


async def list_faces(
    session: AsyncSession,
    source_id: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[FaceResponse]:
    items = await Face.list_page(
        session,
        source_id=source_id,
        entity_id=entity_id,
        after_id=after_id,
        limit=limit,
    )
    return [_face_out(item) for item in items]


# ---------------------------------------------------------------------------
# Descriptions
# ---------------------------------------------------------------------------


def _description_out(item: Description) -> DescriptionResponse:
    return DescriptionResponse(
        description_id=item.description_id,
        text=item.text,
        language=item.language,
        source_id=item.source_id,
        entity_id=item.entity_id,
        embedding=item.embedding,
        model_identifier=item.model_identifier,
    )


async def create_description(
    session: AsyncSession,
    payload: DescriptionCreateRequest,
) -> DescriptionResponse:
    item = await Description.create(
        session=session,
        text=payload.text,
        language=payload.language,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )
    await Entity.refresh_aggregates(session, payload.entity_id)
    return _description_out(item)


async def get_description(
    session: AsyncSession,
    description_id: uuid.UUID,
) -> DescriptionResponse | None:
    item = await Description.get(session, description_id)
    if item is None:
        return None
    return _description_out(item)


async def list_descriptions(
    session: AsyncSession,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DescriptionResponse]:
    items = await Description.list_page(
        session,
        entity_id=entity_id,
        after_id=after_id,
        limit=limit,
    )
    return [_description_out(item) for item in items]


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------


def _name_out(item: Name) -> NameResponse:
    return NameResponse(
        name_id=item.name_id,
        name=item.name,
        source_id=item.source_id,
        entity_id=item.entity_id,
        embedding=item.embedding,
        model_identifier=item.model_identifier,
    )


async def create_name(
    session: AsyncSession,
    payload: NameCreateRequest,
) -> NameResponse:
    item = await Name.create(
        session=session,
        name=payload.name,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )
    await Entity.refresh_aggregates(session, payload.entity_id)
    return _name_out(item)


async def get_name(
    session: AsyncSession,
    name_id: uuid.UUID,
) -> NameResponse | None:
    item = await Name.get(session, name_id)
    if item is None:
        return None
    return _name_out(item)


async def list_names(
    session: AsyncSession,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[NameResponse]:
    items = await Name.list_page(
        session,
        entity_id=entity_id,
        after_id=after_id,
        limit=limit,
    )
    return [_name_out(item) for item in items]
