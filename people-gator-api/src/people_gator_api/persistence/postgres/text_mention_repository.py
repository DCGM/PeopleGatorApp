from __future__ import annotations

import uuid
from people_gator_api.persistence.entity_links import create_link_state, link_transition, apply_link
from people_gator_api.schemas.missing import is_missing
from collections.abc import Sequence

from sqlalchemy import (
    String,
    cast,
    case,
    and_,
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
    TextMentionGroup,
    TextMentionGroupListRequest,
    TextMentionGroupListResponse,
)
from people_gator_api.persistence.postgres.models import (
    Document,
    Page,
    Entity,
    Source,
    TextMention,
)


from people_gator_api.persistence.postgres.utils import (
    commit,
    ensure_ids,
    cursor_fingerprint,
    mention_response,
    mention_filters,
)

from people_gator_api.schemas.sorting import SortDirection
from .sorting import (
    Builders,
    SortKey,
    SortSpec,
    after_predicate,
    annotation_builders,
    build_spec,
    decode_keyset,
    keyset_page,
    order_by,
    sort_columns,
    with_sort_joins,
    text_keys,
)
from .touch import touch_entities, touch_sources, lock_annotation_graph, creation_values, touch_values, apply_touch

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
        rows = await self._session.scalars(statement.execution_options(populate_existing=True))
        return {row.id: row for row in rows.all()}

    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None:
        mention = (await self._load_many([mention_id])).get(mention_id)
        return mention_response(mention) if mention is not None else None

    @staticmethod
    def _sort_spec(field: str | None, direction: SortDirection) -> SortSpec:
        builders: Builders = {
            **annotation_builders(TextMention),
            "text": lambda desc: text_keys(TextMention.mention_normalized, TextMention.mention, desc),
        }
        return build_spec(field, direction, TextMention.id, builders, "mention_id")

    async def list(self, query: TextMentionListRequest) -> TextMentionListResponse:
        filters = mention_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        spec = self._sort_spec(*query.effective_sort())
        after = decode_keyset(query.cursor, spec, fingerprint)
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
        if after is not None:
            page_filters.append(after_predicate(spec, after))
        result = await self._session.execute(
            with_sort_joins(select(TextMention, *sort_columns(spec)), spec)
            .where(*page_filters)
            .order_by(*order_by(spec))
            .limit(query.limit + 1)
        )
        rows = [(row[0], tuple(row[1:])) for row in result.all()]
        page, cursor = keyset_page(rows, query.limit, spec, fingerprint)
        return TextMentionListResponse(
            items=[mention_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    async def list_groups(self, query: TextMentionGroupListRequest) -> TextMentionGroupListResponse:
        filters = mention_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        if query.group_by == "mention":
            grouped = (
                select(
                    TextMention.mention.label("name"),
                    func.min(TextMention.mention_normalized).label("name_normalized"),
                    func.count(TextMention.id).label("occurrence_count"),
                    func.max(TextMention.last_touched_at).label("last_touched_at"),
                ).where(*filters).group_by(TextMention.mention).subquery("mention_groups")
            )
            identity = grouped.c.name
        else:
            # Join subtype tables explicitly: repeated titles never identify a group.
            page = Page.__table__.alias("group_page")
            document = Document.__table__.alias("group_document")
            source_id = (func.coalesce(document.c.id, TextMention.source_id)
                         if query.group_by == "document" else TextMention.source_id)
            label = func.coalesce(document.c.name, cast(page.c.document_id, String), cast(TextMention.source_id, String))
            kind = (case((document.c.id.is_not(None), "document"), else_="source")
                    if query.group_by == "document"
                    else case((page.c.id.is_not(None), "page"), else_="source"))
            columns = [source_id.label("source_id"), label.label("name"),
                       kind.label("source_kind"), page.c.library.label("library"),
                       page.c.document_id.label("document_id")]
            if query.group_by == "page":
                columns.append(page.c.page_id.label("page_id"))
            grouped = (
                select(*columns, func.lower(label).label("name_normalized"),
                       func.count(TextMention.id).label("occurrence_count"),
                       func.max(TextMention.last_touched_at).label("last_touched_at"))
                .select_from(TextMention)
                .outerjoin(page, page.c.id == TextMention.source_id)
                .outerjoin(document, and_(document.c.library == page.c.library,
                                           document.c.document_id == page.c.document_id))
                .where(*filters).group_by(*columns).subquery("mention_groups")
            )
            identity = grouped.c.source_id
        field, direction = query.effective_sort()
        descending = direction == SortDirection.DESC
        builders: Builders = {
            "text": lambda desc: [SortKey(grouped.c.name_normalized.collate("C"), "text", desc)],
            "count": lambda desc: [SortKey(grouped.c.occurrence_count, "number", desc)],
            "last_touched_at": lambda desc: [SortKey(grouped.c.last_touched_at, "datetime", desc)],
        }
        keys = builders[field](descending) if field is not None else builders["text"](False)
        # Exact recorded text identifies a group and is its canonical tie-breaker.
        exact_descending = descending if field in (None, "text") else False
        spec = SortSpec(
            f"{field or 'default'}:{direction.value}",
            (*keys, SortKey(identity.collate("C") if query.group_by == "mention" else identity,
                               "text" if query.group_by == "mention" else "uuid", exact_descending)),
        )
        after = decode_keyset(query.cursor, spec, fingerprint)
        total = None
        if query.return_total_count:
            total = await self._session.scalar(select(func.count()).select_from(grouped)) or 0
        if query.limit == 0:
            return TextMentionGroupListResponse(items=[], limit=0, total_count=total)
        statement = select(grouped, *sort_columns(spec)).order_by(*order_by(spec)).limit(query.limit + 1)
        if after is not None:
            statement = statement.where(after_predicate(spec, after))
        result = await self._session.execute(statement)
        width = len(grouped.c)
        rows = [
            (
                TextMentionGroup(
                    **({key: getattr(row, key) for key in ("source_id", "source_kind", "library", "document_id")}
                       if query.group_by != "mention" else {}),
                    **({"page_id": row.page_id} if query.group_by == "page" else {}),
                    name=row.name,
                    occurrence_count=row.occurrence_count,
                    last_touched_at=row.last_touched_at,
                ),
                tuple(row[width:]),
            )
            for row in result.all()
        ]
        page, cursor = keyset_page(rows, query.limit, spec, fingerprint)
        return TextMentionGroupListResponse(
            items=page, limit=query.limit, total_count=total, cursor=cursor
        )

    @staticmethod
    def _new(payload: TextMentionCreateRequest, context: GenericActor) -> TextMention:
        return TextMention(
            **creation_values(context),
            **touch_values(context),
            mention=payload.name,
            context=payload.context,
            entity_id=payload.entity_id,
            entity_link_state=create_link_state(payload),
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
        await lock_annotation_graph(self._session)
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
        mentions = [self._new(payload, context) for payload in payloads]
        self._session.add_all(mentions)
        await touch_entities(self._session, [item.entity_id for item in payloads], context)
        await touch_sources(self._session, [item.source_id for item in payloads], context)
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
        await lock_annotation_graph(self._session)
        await ensure_ids(
            self._session,
            Entity,
            [
                command.entity_id
                for command in commands
                if not is_missing(command.entity_id) and command.entity_id is not None
            ],
            "mention entity",
        )
        mentions = await self._load_many(ids, lock=True)
        transitions = {c.mention_id: link_transition(mentions[c.mention_id], c, context) for c in commands if c.mention_id in mentions}
        touched: set[uuid.UUID | None] = set()
        sources: set[uuid.UUID] = set()
        for command in commands:
            mention = mentions.get(command.mention_id)
            if mention is not None:
                values = transitions[command.mention_id]
                if values != (mention.entity_id, mention.entity_link_state, mention.entity_link_verified_by_user_id, mention.entity_link_verified_at):
                    touched.update([mention.entity_id, values[0]])
                    sources.add(mention.source_id)
                    apply_link(mention, values)
                    apply_touch(mention, context)
        await touch_entities(self._session, touched, context)
        await touch_sources(self._session, sources, context)
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
        await lock_annotation_graph(self._session)
        removed = list(await self._session.execute(
            delete(TextMention).where(TextMention.id.in_(unique)).returning(TextMention.entity_id, TextMention.source_id)
        ))
        await touch_entities(self._session, [row.entity_id for row in removed], context)
        await touch_sources(self._session, [row.source_id for row in removed], context)
        await commit(self._session, "mention delete failed")
        return len(removed)
