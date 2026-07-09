"""Service for identity endpoints (spec §2.1).

Identities are the central entity representing distinct persons.  Each
identity is created by a principal and accrues annotations through the
consensus model.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.models.link import LinkConsensus
from people_gator_api.models.identity import Identity
from people_gator_api.schemas.identities import (
    IdentityAnnotationEntry,
    IdentityCreateRequest,
    IdentityListResponse,
    IdentityResponse,
    IdentityViewResponse,
)
from people_gator_api.utils.uuid_utils import uuid6_to_datetime


def _identity_out(item: Identity) -> IdentityResponse:
    return IdentityResponse(
        identity_id=item.identity_id,
        created_at=uuid6_to_datetime(item.created_at),
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
    identity = await Identity.create(session, principal_id=principal_id)
    return _identity_out(identity)


async def get_identity_view(
    session: AsyncSession,
    identity_id: uuid.UUID,
) -> IdentityViewResponse | None:
    """Return an identity's current view from consensus-linked annotations."""
    identity = await Identity.get(session, identity_id)
    if identity is None:
        return None
    included = await LinkConsensus.list_for_identity(session, identity_id)
    entries = [
        IdentityAnnotationEntry(
            annotation_id=row.annotation_id,
        )
        for row in included
    ]
    return IdentityViewResponse(identity_id=identity_id, included=entries)


async def delete_identity(session: AsyncSession, identity_id: uuid.UUID) -> bool:
    identity = await Identity.get(session, identity_id)
    if identity is None:
        return False
    await session.delete(identity)
    return True
