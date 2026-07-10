"""Service for entity endpoints."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.models.annotation.description import Description
from people_gator_api.models.annotation.document_mention import DocumentMention
from people_gator_api.models.annotation.face import Face
from people_gator_api.models.annotation.name import Name
from people_gator_api.models.entities import Entity
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListResponse,
    EntityResponse,
    EntityViewResponse,
)


def _entity_out(item: Entity) -> EntityResponse:
    return EntityResponse(
        entity_id=item.entity_id,
        principal_id=item.principal_id,
        name=item.name,
        description=item.description,
    )


async def list_entities(
    session: AsyncSession,
    after_id: uuid.UUID | None,
    limit: int,
) -> EntityListResponse:
    items = await Entity.list_page(session, after_id=after_id, limit=limit)
    responses = [_entity_out(item) for item in items]
    return EntityListResponse(
        items=responses,
        total=len(responses),
        next_after_id=responses[-1].entity_id if len(responses) == limit and responses else None,
    )


async def get_entity(session: AsyncSession, entity_id: uuid.UUID) -> EntityResponse | None:
    entity = await Entity.get(session, entity_id)
    if entity is None:
        return None
    return _entity_out(entity)


async def create_entity(
    session: AsyncSession,
    payload: EntityCreateRequest,
    principal_id: uuid.UUID,
) -> EntityResponse:
    entity = await Entity.create(
        session,
        principal_id=principal_id,
        name=payload.name,
        description=payload.description,
    )
    return _entity_out(entity)


async def get_entity_view(
    session: AsyncSession,
    entity_id: uuid.UUID,
) -> EntityViewResponse | None:
    entity = await Entity.get(session, entity_id)
    if entity is None:
        return None

    document_mentions = await DocumentMention.list_page(
        session, entity_id=entity_id, limit=500
    )
    faces = await Face.list_page(session, entity_id=entity_id, limit=500)
    descriptions = await Description.list_page(
        session, entity_id=entity_id, limit=500
    )
    names = await Name.list_page(session, entity_id=entity_id, limit=500)

    return EntityViewResponse(
        entity_id=entity_id,
        document_mention_ids=[item.document_mention_id for item in document_mentions],
        face_ids=[item.detection_id for item in faces],
        description_ids=[item.description_id for item in descriptions],
        name_ids=[item.name_id for item in names],
    )


async def delete_entity(session: AsyncSession, entity_id: uuid.UUID) -> bool:
    entity = await Entity.get(session, entity_id)
    if entity is None:
        return False
    await session.delete(entity)
    return True


# Backward-compatible identity aliases.
list_identities = list_entities
get_identity = get_entity
create_identity = create_entity
get_identity_view = get_entity_view
delete_identity = delete_entity
