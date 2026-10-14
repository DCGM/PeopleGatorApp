"""Touch metadata belongs to the same unit of work as its actual mutation."""

import uuid
from datetime import datetime, timezone
from collections.abc import Iterable
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from people_gator_api.schemas.common import GenericActor
from people_gator_api.persistence.postgres.models import Entity, Source, Document, Page


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


async def lock_annotation_graph(session: AsyncSession) -> None:
    """Acquire before annotation locks, entity locks and source locks.

    Merge/delete traverse the graph in a different order from individual edits.
    A transaction advisory lock gives every graph mutation the same outer lock;
    reads and unrelated entity metadata edits remain concurrent.
    """
    await session.execute(select(func.pg_advisory_xact_lock(817308, 8)))


async def source_touch_ids(session: AsyncSession, ids: Iterable[uuid.UUID]) -> list[uuid.UUID]:
    unique = sorted(set(ids))
    if not unique:
        return []
    parents = await session.scalars(
        select(Document.__table__.c.id).select_from(Document.__table__.join(
            Page.__table__,
            (Document.__table__.c.library == Page.__table__.c.library)
            & (Document.__table__.c.document_id == Page.__table__.c.document_id),
        )).where(Page.__table__.c.id.in_(unique))
    )
    return sorted(set(unique).union(parents))


async def touch_sources(
    session: AsyncSession, source_ids: Iterable[uuid.UUID], context: GenericActor,
) -> None:
    targets = await source_touch_ids(session, source_ids)
    if not targets:
        return
    # Lock the entire surviving set before generating a single server timestamp.
    surviving = list(await session.scalars(
        select(Source.id).where(Source.id.in_(targets)).order_by(Source.id).with_for_update()
    ))
    if surviving:
        await session.execute(update(Source).where(Source.id.in_(surviving)).values(**touch_values(context)))
