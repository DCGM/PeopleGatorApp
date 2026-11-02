"""Small snapshot repository; no action replay or historical joins to live data."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from people_gator_api.persistence.contracts import AuditRepository
from people_gator_api.schemas.audit import AuditQuery, AuditRevision, AuditListResponse
from .models import AuditChange, ObjectHistory


class PostgresAuditRepository(AuditRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list(self, query: AuditQuery) -> AuditListResponse:
        h, c = ObjectHistory, AuditChange
        filters = []
        for field in ("object_type", "object_id", "entity_id", "source_id", "deleted"):
            value = getattr(query, field)
            if value is not None:
                filters.append(getattr(h, field) == value)
        if query.actor_user_id is not None:
            filters.append(c.actor_user_id == query.actor_user_id)
        for value, predicate in (
            (query.since, c.changed_at.__ge__),
            (query.until, c.changed_at.__le__),
            (query.version_min, h.version.__ge__),
            (query.version_max, h.version.__le__),
        ):
            if value is not None:
                filters.append(predicate(value))
        base = select(h, c).join(c, h.change_id == c.id).where(*filters)
        count = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        column = c.changed_at if query.sort == "time" else h.version
        ordering = column.asc() if query.direction == "asc" else column.desc()
        rows = await self._session.execute(
            base.order_by(ordering, h.object_type, h.object_id, h.version)
            .limit(query.limit)
            .offset(query.offset)
        )
        return AuditListResponse(
            items=[
                AuditRevision(
                    object_type=history.object_type,
                    object_id=history.object_id,
                    version=history.version,
                    changed_at=change.changed_at,
                    actor_user_id=change.actor_user_id,
                    actor_api_key_id=change.actor_api_key_id,
                    deleted=history.deleted,
                    entity_id=history.entity_id,
                    source_id=history.source_id,
                    state=history.state,
                )
                for history, change in rows
            ],
            total_count=count or 0,
            limit=query.limit,
            offset=query.offset,
        )
