"""Typed historical queries without joins to mutable live objects."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import TypeAdapter
from people_gator_api.persistence.contracts import AuditRepository
from people_gator_api.schemas.audit_history import (
    EntityAuditListRequest,
    EntityAuditListResponse,
    EntityAuditState,
    FaceAuditListRequest,
    FaceAuditListResponse,
    FaceAuditState,
    TextMentionAuditListRequest,
    TextMentionAuditListResponse,
    TextMentionAuditState,
    SourceAuditListRequest,
    SourceAuditListResponse,
    PageAuditState,
    DocumentAuditState,
    ImageAuditState,
)
from .models import (
    AuditChange,
    EntityHistory,
    FaceHistory,
    TextMentionHistory,
    SourceHistory,
    AliasHistory,
    FaceEmbeddingHistory,
)


class PostgresAuditRepository(AuditRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _list(self, query, model, identity, response, state):
        h, c = model.__table__, AuditChange
        filters = []
        for field in (
            identity,
            "entity_id",
            "source_id",
            "deleted",
            "source_type",
            "library",
            "document_id",
            "page_id",
        ):
            if field != identity and field not in type(query).model_fields:
                continue
            value = getattr(query, field, None)
            if value is not None:
                column = h.c.id if field == identity else h.c[field]
                filters.append(
                    column.in_(value) if isinstance(value, list) else column == value
                )
        if query.actor_user_id is not None:
            filters.append(c.actor_user_id.in_(query.actor_user_id))
        for value, predicate in (
            (query.since, c.changed_at.__ge__),
            (query.until, c.changed_at.__le__),
            (query.version_min, h.c.version.__ge__),
            (query.version_max, h.c.version.__le__),
        ):
            if value is not None:
                filters.append(predicate(value))
        base = select(h).join(c, h.c.change_id == c.id).where(*filters)
        count = await self._session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        column = c.changed_at if query.sort == "time" else h.c.version
        rows = (
            (
                await self._session.execute(
                    base.order_by(
                        column.asc() if query.direction == "asc" else column.desc(),
                        h.c.id,
                        h.c.version,
                    )
                    .limit(query.limit)
                    .offset(query.offset)
                )
            )
            .mappings()
            .all()
        )
        items = []
        for row in rows:
            data = dict(row)
            if model is EntityHistory:
                data["aliases"] = (
                    (
                        await self._session.execute(
                            select(AliasHistory.__table__)
                            .where(
                                AliasHistory.entity_id == row.id,
                                AliasHistory.version == row.version,
                            )
                            .order_by(AliasHistory.name)
                        )
                    )
                    .mappings()
                    .all()
                )
            if model is FaceHistory:
                embeddings = (
                    (
                        await self._session.execute(
                            select(FaceEmbeddingHistory.__table__)
                            .where(
                                FaceEmbeddingHistory.face_id == row.id,
                                FaceEmbeddingHistory.version == row.version,
                            )
                            .order_by(FaceEmbeddingHistory.model_id)
                        )
                    )
                    .mappings()
                    .all()
                )
                data["embeddings"] = [
                    dict(e) | {"embedding": list(e.embedding)} for e in embeddings
                ]
            items.append(TypeAdapter(state).validate_python(data))
        return response(items=items, total_count=count or 0, limit=query.limit)

    async def list_entities(
        self, query: EntityAuditListRequest
    ) -> EntityAuditListResponse:
        return await self._list(
            query, EntityHistory, "entity_id", EntityAuditListResponse, EntityAuditState
        )

    async def list_faces(self, query: FaceAuditListRequest) -> FaceAuditListResponse:
        return await self._list(
            query, FaceHistory, "detection_id", FaceAuditListResponse, FaceAuditState
        )

    async def list_text_mentions(
        self, query: TextMentionAuditListRequest
    ) -> TextMentionAuditListResponse:
        return await self._list(
            query,
            TextMentionHistory,
            "mention_id",
            TextMentionAuditListResponse,
            TextMentionAuditState,
        )

    async def list_sources(
        self, query: SourceAuditListRequest
    ) -> SourceAuditListResponse:
        return await self._list(
            query,
            SourceHistory,
            "source_id",
            SourceAuditListResponse,
            PageAuditState | DocumentAuditState | ImageAuditState,
        )
