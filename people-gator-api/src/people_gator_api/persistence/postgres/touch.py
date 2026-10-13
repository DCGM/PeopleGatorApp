"""Touch metadata belongs to the same unit of work as its actual mutation."""

import uuid
from datetime import datetime, timezone
from collections.abc import Iterable
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from people_gator_api.schemas.common import GenericActor
from people_gator_api.persistence.postgres.models import Entity


def touch_values(context: GenericActor) -> dict[str, datetime | uuid.UUID | None]:
    return {
        "last_touched_at": datetime.now(timezone.utc),
        "last_touched_by_user_id": context.user_id,
        "last_touched_by_api_key_id": getattr(context, "api_key_id", None),
    }


async def touch_entities(
    session: AsyncSession, ids: Iterable[uuid.UUID | None], context: GenericActor
) -> None:
    unique = sorted({item for item in ids if item is not None})
    if not unique:
        return
    # Stable row-lock order serializes concurrent touches and avoids assigning a
    # timestamp before waiting on another transaction's entity update.
    await session.execute(
        select(Entity.id)
        .where(Entity.id.in_(unique))
        .order_by(Entity.id)
        .with_for_update()
    )
    await session.execute(
        update(Entity).where(Entity.id.in_(unique)).values(**touch_values(context))
    )
