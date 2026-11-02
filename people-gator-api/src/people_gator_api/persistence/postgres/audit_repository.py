"""Small snapshot repository; no action replay or historical joins to live data."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from people_gator_api.persistence.contracts import AuditRepository
from people_gator_api.schemas.audit import AuditQuery, AuditRevision, AuditListResponse
from .models import AuditChange, ObjectHistory
from people_gator_api.schemas.audit import ObjectKind
from people_gator_api.schemas.audit_history import (
    AuditListOptions,
    AuditItemMetadata,
    TypedAuditListResponse,
    EntityAuditListRequest,
    EntityAuditListResponse,
    EntityAuditItem,
    FaceAuditListRequest,
    FaceAuditListResponse,
    FaceAuditItem,
    TextMentionAuditListRequest,
    TextMentionAuditListResponse,
    TextMentionAuditItem,
    SourceAuditListRequest,
    SourceAuditListResponse,
    SourceAuditItem,
)


class PostgresAuditRepository(AuditRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list(self, query: AuditQuery) -> AuditListResponse:
        h, c = ObjectHistory, AuditChange
        filters = []
        for field in ("object_type", "object_id", "entity_id", "source_id", "deleted"):
            value = getattr(query, field)
            if value is not None:
                filters.append(
                    getattr(h, field).in_(value)
                    if isinstance(value, list)
                    else getattr(h, field) == value
                )
        for field in ("source_type", "library", "document_id", "page_id"):
            values = getattr(query, field)
            if values is not None:
                filters.append(
                    h.state[field].astext.in_([str(value) for value in values])
                )
        if query.actor_user_id is not None:
            filters.append(
                c.actor_user_id.in_(query.actor_user_id)
                if isinstance(query.actor_user_id, list)
                else c.actor_user_id == query.actor_user_id
            )
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

    async def _list_typed[T: AuditItemMetadata, R: TypedAuditListResponse](
        self,
        query: AuditListOptions,
        kind: ObjectKind,
        identity: str,
        item_type: type[T],
        response_type: type[R],
    ) -> R:
        values = query.model_dump()
        own_ids = values.pop(identity, None)
        result = await self.list(
            AuditQuery(object_type=kind, object_id=own_ids, **values)
        )
        items = []
        for row in result.items:
            data = row.model_dump(
                include={
                    "version",
                    "changed_at",
                    "actor_user_id",
                    "actor_api_key_id",
                    "deleted",
                    "state",
                }
            )
            data[identity] = row.object_id
            items.append(item_type.model_validate(data))
        return response_type(
            items=items,
            total_count=result.total_count,
            limit=result.limit,
            offset=result.offset,
        )

    async def list_entities(
        self, query: EntityAuditListRequest
    ) -> EntityAuditListResponse:
        return await self._list_typed(
            query,
            ObjectKind.entity,
            "entity_id",
            EntityAuditItem,
            EntityAuditListResponse,
        )

    async def list_faces(self, query: FaceAuditListRequest) -> FaceAuditListResponse:
        return await self._list_typed(
            query, ObjectKind.face, "detection_id", FaceAuditItem, FaceAuditListResponse
        )

    async def list_text_mentions(
        self, query: TextMentionAuditListRequest
    ) -> TextMentionAuditListResponse:
        return await self._list_typed(
            query,
            ObjectKind.mention,
            "mention_id",
            TextMentionAuditItem,
            TextMentionAuditListResponse,
        )

    async def list_sources(
        self, query: SourceAuditListRequest
    ) -> SourceAuditListResponse:
        return await self._list_typed(
            query,
            ObjectKind.source,
            "source_id",
            SourceAuditItem,
            SourceAuditListResponse,
        )
