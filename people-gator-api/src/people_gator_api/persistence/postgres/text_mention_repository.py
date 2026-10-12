from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import (
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.persistence.contracts import (
    TextMentionRepository,
)
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListRequest,
    TextMentionListResponse,
    TextMentionPatchBatchItem,
    TextMentionPatchRequest,
    TextMentionResponse,
)
from people_gator_api.persistence.postgres.models import (
    Entity,
    Source,
    TextMention,
)


from people_gator_api.persistence.postgres.utils import (
    commit,
    ensure_ids,
    validate_cursor,
    cursor_fingerprint,
    decode_cursor,
    next_cursor,
    mention_response,
    mention_filters,
)

from .touch import touch_entities

class PostgresTextMentionRepository(TextMentionRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(
        self, ids: Sequence[uuid.UUID], *, lock: bool = False
    ) -> dict[uuid.UUID, TextMention]:
        if not ids:
            return {}
        statement = select(TextMention).where(TextMention.id.in_(ids))
        if lock:
            statement = statement.order_by(TextMention.id).with_for_update()
        rows = await self._session.scalars(statement)
        return {row.id: row for row in rows.all()}

    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None:
        mention = (await self._load_many([mention_id])).get(mention_id)
        return mention_response(mention) if mention is not None else None

    async def list(self, query: TextMentionListRequest) -> TextMentionListResponse:
        filters = mention_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        cursor_id = decode_cursor(query.cursor, fingerprint)
        await validate_cursor(self._session, TextMention, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(
                    select(func.count(TextMention.id)).where(*filters)
                )
                or 0
            )
        if query.limit == 0:
            return TextMentionListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(TextMention.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(TextMention)
                .where(*page_filters)
                .order_by(TextMention.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = next_cursor(
            rows,
            query.limit,
            TextMention.id,
            fingerprint,
        )
        return TextMentionListResponse(
            items=[mention_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(payload: TextMentionCreateRequest) -> TextMention:
        return TextMention(
            mention=payload.name,
            context=payload.context,
            entity_id=payload.entity_id,
            source_id=payload.source_id,
        )

    async def create(
        self, payload: TextMentionCreateRequest, context: GenericActor
    ) -> TextMentionResponse:
        return (await self.create_batch([payload], context))[0]

    async def create_batch(
        self,
        payloads: Sequence[TextMentionCreateRequest],
        context: GenericActor,
    ) -> list[TextMentionResponse]:
        if not payloads:
            return []
        await ensure_ids(
            self._session,
            Source,
            [item.source_id for item in payloads],
            "mention source",
        )
        await ensure_ids(
            self._session,
            Entity,
            [item.entity_id for item in payloads],
            "mention entity",
        )
        mentions = [self._new(payload) for payload in payloads]
        self._session.add_all(mentions)
        await touch_entities(self._session, [item.entity_id for item in payloads], context)
        await commit(self._session, "mention create violates a persistence constraint")
        return [mention_response(mention) for mention in mentions]

    async def patch(
        self,
        mention_id: uuid.UUID,
        payload: TextMentionPatchRequest,
        context: GenericActor,
    ) -> TextMentionResponse | None:
        return (
            await self.patch_batch(
                [
                    TextMentionPatchBatchItem(
                        mention_id=mention_id, **payload.model_dump()
                    )
                ],
                context,
            )
        )[0]

    async def patch_batch(
        self,
        commands: Sequence[TextMentionPatchBatchItem],
        context: GenericActor,
    ) -> list[TextMentionResponse | None]:
        ids = [command.mention_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("text mention patch batch requires unique object IDs")
        if not commands:
            return []
        await ensure_ids(
            self._session,
            Entity,
            [
                command.entity_id
                for command in commands
                if command.entity_id is not None
            ],
            "mention entity",
        )
        mentions = await self._load_many(ids, lock=True)
        touched: set[uuid.UUID | None] = set()
        for command in commands:
            mention = mentions.get(command.mention_id)
            if mention is not None and mention.entity_id != command.entity_id:
                touched.update([mention.entity_id, command.entity_id])
                mention.entity_id = command.entity_id
        await touch_entities(self._session, touched, context)
        await commit(self._session, "mention patch violates a persistence constraint")
        return [
            mention_response(mention) if (mention := mentions.get(item_id)) else None
            for item_id in ids
        ]

    async def delete(self, mention_id: uuid.UUID, *, context: GenericActor) -> bool:
        return bool(await self.delete_batch([mention_id], context=context))

    async def delete_batch(self, mention_ids: Sequence[uuid.UUID], *, context: GenericActor) -> int:
        unique = list(dict.fromkeys(mention_ids))
        if not unique:
            return 0
        removed = list(await self._session.scalars(
            delete(TextMention).where(TextMention.id.in_(unique)).returning(TextMention.entity_id)
        ))
        await touch_entities(self._session, removed, context)
        await commit(self._session, "mention delete failed")
        return len(removed)
