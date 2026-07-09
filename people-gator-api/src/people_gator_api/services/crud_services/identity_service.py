"""Service for identity endpoints."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.models.annotation.description import Description
from people_gator_api.models.annotation.document_mention import DocumentMention
from people_gator_api.models.annotation.face import Face
from people_gator_api.models.annotation.name import Name
from people_gator_api.models.identity import Identity
from people_gator_api.schemas.identities import (
    IdentityCreateRequest,
    IdentityListResponse,
    IdentityResponse,
    IdentityViewResponse,
)


def _identity_out(item: Identity) -> IdentityResponse:
    return IdentityResponse(
        identity_id=item.identity_id,
        principal_id=item.principal_id,
    )


async def list_identities(
    session: AsyncSession,
    after_id: uuid.UUID | None,
    limit: int,
) -> IdentityListResponse:
    items = await Identity.list_page(session, after_id=after_id, limit=limit)
    responses = [_identity_out(item) for item in items]
    return IdentityListResponse(
        items=responses,
        total=len(responses),
        next_after_id=responses[-1].identity_id if len(responses) == limit and responses else None,
    )


async def get_identity(session: AsyncSession, identity_id: uuid.UUID) -> IdentityResponse | None:
    identity = await Identity.get(session, identity_id)
    if identity is None:
        return None
    return _identity_out(identity)


async def create_identity(
    session: AsyncSession,
    payload: IdentityCreateRequest,
    principal_id: uuid.UUID,
) -> IdentityResponse:
    _ = payload
    identity = await Identity.create(session, principal_id=principal_id)
    return _identity_out(identity)


async def get_identity_view(
    session: AsyncSession,
    identity_id: uuid.UUID,
) -> IdentityViewResponse | None:
    identity = await Identity.get(session, identity_id)
    if identity is None:
        return None

    document_mentions = await DocumentMention.list_page(
        session, identity_id=identity_id, limit=500
    )
    faces = await Face.list_page(session, identity_id=identity_id, limit=500)
    descriptions = await Description.list_page(
        session, identity_id=identity_id, limit=500
    )
    names = await Name.list_page(session, identity_id=identity_id, limit=500)

    return IdentityViewResponse(
        identity_id=identity_id,
        document_mention_ids=[item.document_mention_id for item in document_mentions],
        face_ids=[item.detection_id for item in faces],
        description_ids=[item.description_id for item in descriptions],
        name_ids=[item.name_id for item in names],
    )


async def delete_identity(session: AsyncSession, identity_id: uuid.UUID) -> bool:
    identity = await Identity.get(session, identity_id)
    if identity is None:
        return False
    await session.delete(identity)
    return True
