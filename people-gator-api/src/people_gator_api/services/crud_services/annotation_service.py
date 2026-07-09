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
from people_gator_api.models.annotation.mention import Mention
from people_gator_api.models.annotation.name import Name
from people_gator_api.schemas.identities import (
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
    MentionResponse,
    NameCreateRequest,
    NameResponse,
)


# ---------------------------------------------------------------------------
# Mentions
# ---------------------------------------------------------------------------


def _mention_out(item: Mention) -> MentionResponse:
    return MentionResponse(
        mention_id=item.mention_id,
        text=item.text,
        document_mention_id=item.document_mention_id,
        source_id=item.source_id,
        offset_start=item.offset_start,
        offset_end=item.offset_end,
        model_agent_id=item.model_agent_id,
        confidence=item.confidence,
    )

async def create_mention(
    session: AsyncSession,
    payload: MentionCreateRequest,
) -> MentionResponse:
    item = await Mention.create(
        session=session,
        text=payload.text,
        document_mention_id=payload.document_mention_id,
        source_id=payload.source_id,
        offset_start=payload.offset_start,
        offset_end=payload.offset_end,
        model_agent_id=payload.model_agent_id,
        confidence=payload.confidence,
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
        identity_id=item.identity_id,
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
        identity_id=payload.identity_id,
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
    identity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DocumentMentionResponse]:
    items = await DocumentMention.list_page(
        session,
        identity_id=identity_id,
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
        identity_id=item.identity_id,
        confidence=item.confidence,
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
        identity_id=payload.identity_id,
        confidence=payload.confidence,
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
    identity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[FaceResponse]:
    items = await Face.list_page(
        session,
        source_id=source_id,
        identity_id=identity_id,
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
        identity_id=item.identity_id,
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
        identity_id=payload.identity_id,
    )
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
    identity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DescriptionResponse]:
    items = await Description.list_page(
        session,
        identity_id=identity_id,
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
        identity_id=item.identity_id,
    )


async def create_name(
    session: AsyncSession,
    payload: NameCreateRequest,
) -> NameResponse:
    item = await Name.create(
        session=session,
        name=payload.name,
        source_id=payload.source_id,
        identity_id=payload.identity_id,
    )
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
    identity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[NameResponse]:
    items = await Name.list_page(
        session,
        identity_id=identity_id,
        after_id=after_id,
        limit=limit,
    )
    return [_name_out(item) for item in items]
