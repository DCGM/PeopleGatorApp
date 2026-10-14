from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, cast as type_cast

from sqlalchemy import (
    ColumnElement,
    Float,
    column,
    delete,
    exists,
    func,
    or_,
    select,
    union_all,
    values,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import with_polymorphic

from people_gator_api.persistence.contracts import (
    CreateResult,
    SourceRepository,
)
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.missing import (
    MISSING,
    MissingType,
    missing_to_none,
)
from people_gator_api.schemas.search import (
    FoundDocument,
    FoundPage,
    SearchDocumentsRequest,
    SearchDocumentsResultListResponse,
    SearchPagesRequest,
    SearchPagesResultListResponse,
)
from people_gator_api.schemas.sources import (
    DocumentResponse,
    GenericSourceListFilter,
    GenericSourceCreateRequest,
    GenericSourceListRequest,
    GenericSourceListResponse,
    GenericSourceLookupRequest,
    GenericSourceResponse,
    PageResponse,
    DocumentLibraryOptionsRequest, DocumentLibraryOptionsResponse, DocumentLibraryOption,
)
from people_gator_api.persistence.postgres.models import (
    Alias,
    Document,
    Entity,
    Face,
    Image,
    ImageOccurrence,
    Page,
    Source,
    TextMention,
)
from people_gator_api.persistence.postgres.utils import (
    aggregate_scores,
    search_face_scores,
    commit,
    validate_cursor,
    cursor_fingerprint,
    decode_cursor,
    next_cursor,
    fuse_scores,
    entity_text_candidates,
    search_page,
    source_response,
    load_link_stats,
    source_filters,
)

SOURCE_TEXT_CANDIDATE_LIMIT = 200


from .touch import touch_entities, touch_sources, source_touch_ids, lock_annotation_graph
from people_gator_api.schemas.common import GenericActor

class PostgresSourceRepository(SourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session
        self._source = with_polymorphic(Source, [Document, Page, Image])

    async def document_library_filter_options(self, query: DocumentLibraryOptionsRequest) -> DocumentLibraryOptionsResponse:
        import base64
        import json
        fingerprint = cursor_fingerprint(query)
        cursor_library = None
        if query.cursor:
            try:
                saved, cursor_library = json.loads(base64.urlsafe_b64decode(query.cursor.encode()))
                if saved != fingerprint or not isinstance(cursor_library, str):
                    raise ValueError("cursor does not match the library options query")
            except Exception as exc:
                raise ValueError("invalid library options cursor") from exc
        filters = [Document.library.icontains(query.q, autoescape=True)] if query.q else []
        choices = select(Document.library).where(*filters).distinct().subquery()
        total = await self._session.scalar(select(func.count()).select_from(choices)) if query.return_total_count else None
        if query.limit == 0:
            return DocumentLibraryOptionsResponse(items=[], limit=0, total_count=total)
        statement = select(choices.c.library).order_by(choices.c.library).limit(query.limit + 1)
        if cursor_library is not None:
            if not await self._session.scalar(select(exists(select(1).select_from(choices).where(choices.c.library == cursor_library)))):
                raise ValueError("library options cursor no longer exists")
            statement = statement.where(choices.c.library > cursor_library)
        rows = list(await self._session.scalars(statement))
        page = rows[:query.limit]
        cursor = base64.urlsafe_b64encode(json.dumps([fingerprint, page[-1]]).encode()).decode() if len(rows) > query.limit else None
        return DocumentLibraryOptionsResponse(items=[DocumentLibraryOption(library=value) for value in page], limit=query.limit, total_count=total, cursor=cursor)

    async def lookup(
        self, lookup: GenericSourceLookupRequest
    ) -> GenericSourceResponse | None:
        statement = select(self._source)
        source_id = missing_to_none(lookup.source_id)
        source_type = missing_to_none(lookup.source_type)
        if source_id is not None:
            statement = statement.where(Source.id == source_id)
        elif source_type == SourceKind.image:
            statement = statement.where(
                Source.source_type == SourceKind.image.value,
                Source.url == str(lookup.url),
            )
        elif source_type == SourceKind.document:
            statement = statement.where(
                Source.source_type == SourceKind.document.value,
                Document.library == lookup.library,
                Document.document_id == lookup.document_id,
            )
        elif source_type == SourceKind.page:
            statement = statement.where(
                Source.source_type == SourceKind.page.value,
                Page.library == lookup.library,
                Page.document_id == lookup.document_id,
                Page.page_id == lookup.page_id,
            )
        else:
            raise ValueError("invalid source lookup")
        source = await self._session.scalar(statement.limit(1))
        await load_link_stats(self._session, [source] if source is not None else [])
        return source_response(source) if source is not None else None

    async def list(self, query: GenericSourceListRequest) -> GenericSourceListResponse:
        filters = source_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        cursor_id = decode_cursor(query.cursor, fingerprint)
        if cursor_id is not None:
            valid = await self._session.scalar(select(exists().select_from(self._source).where(
                Source.id == cursor_id, *filters,
            )))
            if not valid:
                raise ValueError("cursor is not valid for this query")
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(
                    select(func.count(Source.id))
                    .select_from(self._source)
                    .where(*filters)
                )
                or 0
            )
        if query.limit == 0:
            return GenericSourceListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(Source.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(self._source)
                .where(*page_filters)
                .order_by(Source.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = next_cursor(rows, query.limit, Source.id, fingerprint)
        await load_link_stats(self._session, page)
        return GenericSourceListResponse(
            items=[source_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(spec: GenericSourceCreateRequest) -> Source:
        common = {"url": str(spec.url)}
        if spec.source_type == SourceKind.page:
            assert isinstance(spec.library, str)
            assert isinstance(spec.document_id, uuid.UUID)
            assert isinstance(spec.page_id, uuid.UUID)
            return Page(
                **common,
                library=spec.library,
                document_id=spec.document_id,
                page_id=spec.page_id,
            )
        if spec.source_type == SourceKind.document:
            assert isinstance(spec.library, str)
            assert isinstance(spec.document_id, uuid.UUID)
            return Document(
                **common,
                library=spec.library,
                document_id=spec.document_id,
                name=spec.name,
            )
        return Image(**common)

    async def _by_url(self, url: str) -> Source | None:
        return await self._session.scalar(
            select(self._source).where(Source.url == url).limit(1)
        )

    async def get_or_create(
        self, spec: GenericSourceCreateRequest
    ) -> tuple[GenericSourceResponse, CreateResult]:
        key = str(spec.url)
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0)))
        )
        by_identity = await self.lookup(
            GenericSourceLookupRequest(
                source_type=spec.source_type,
                url=spec.url if spec.source_type == SourceKind.image else MISSING,
                library=spec.library,
                document_id=spec.document_id,
                page_id=spec.page_id,
            )
        )
        by_url = await self._by_url(key)
        if by_identity is not None:
            if str(by_identity.url) != key:
                raise ValueError(
                    "source identity is already registered with another URL"
                )
            if by_url is not None and by_url.id != by_identity.source_id:
                raise ValueError("source URL conflicts with another source identity")
            return by_identity, CreateResult.EXISTING
        if by_url is not None:
            raise ValueError("source URL is already registered with another identity")
        source = self._new(spec)
        self._session.add(source)
        await commit(self._session, "source create violates a persistence constraint")
        return source_response(source), CreateResult.CREATED

    async def get_or_create_batch(
        self, specs: Sequence[GenericSourceCreateRequest]
    ) -> list[tuple[GenericSourceResponse, CreateResult]]:
        results: list[tuple[GenericSourceResponse, CreateResult]] = []
        for spec in specs:
            results.append(await self.get_or_create(spec))
        return results

    async def delete(self, source_id: uuid.UUID, *, context: GenericActor) -> bool:
        return bool(await self.delete_batch([source_id], context=context))

    async def delete_batch(self, source_ids: Sequence[uuid.UUID], *, context: GenericActor) -> int:
        unique = list(dict.fromkeys(source_ids))
        if not unique:
            return 0
        await lock_annotation_graph(self._session)
        survivors = set(await source_touch_ids(self._session, unique)) - set(unique)
        touched: set[uuid.UUID | None] = set()
        for evidence in (ImageOccurrence, TextMention):
            touched.update(await self._session.scalars(select(evidence.entity_id).where(evidence.source_id.in_(unique))))
        await touch_entities(self._session, touched, context)
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(Source).where(Source.id.in_(unique))),
        )
        await touch_sources(self._session, survivors, context)
        await commit(self._session, "source delete failed")
        return int(result.rowcount or 0)

    async def _source_text_scores(
        self,
        model: type[Page] | type[Document],
        query: SearchPagesRequest | SearchDocumentsRequest,
        filters: Sequence[ColumnElement[bool]],
    ) -> dict[uuid.UUID, float]:
        terms = missing_to_none(query.query.text)
        if terms is None:
            return {}
        collected: dict[uuid.UUID, list[float]] = {}
        for term in terms:
            # Exact archive identifiers remain useful alongside entity names.
            # These predicates use the URL and library btree indexes instead of
            # calculating trigram similarity for every source in the library.
            identities = [Source.url == term, model.library == term]
            if model is Document:
                try:
                    identities.append(Document.document_id == uuid.UUID(term))
                except ValueError:
                    pass
            direct = await self._session.scalars(
                select(model.id)
                .where(*filters, or_(*identities))
                .order_by(model.id)
                .limit(SOURCE_TEXT_CANDIDATE_LIMIT)
            )
            term_scores = {source_id: 1.0 for source_id in direct.all()}

            normalized_term = func.lower(func.unaccent(term))
            if model is Document:
                # Stored normalization and a trigram GIN index make substring
                # matching case/accent insensitive without scanning every name.
                escaped = func.replace(func.replace(func.replace(normalized_term, "\\", "\\\\"), "%", "\\%"), "_", "\\_")
                name_score = func.word_similarity(normalized_term, Document.name_normalized)
                names = await self._session.execute(select(Document.id, name_score.label("score")).where(
                    *filters, Document.name_normalized.like("%" + escaped + "%", escape="\\"),
                ).order_by(name_score.desc(), Document.id).limit(SOURCE_TEXT_CANDIDATE_LIMIT))
                for source_id, score in names:
                    term_scores[source_id] = max(term_scores.get(source_id, 0.0), float(score))
            candidate_ids = entity_text_candidates(normalized_term, [])
            entity_score = func.greatest(
                func.word_similarity(
                    normalized_term, func.coalesce(Entity.name_normalized, "")
                ),
                func.coalesce(
                    func.max(
                        func.word_similarity(normalized_term, Alias.name_normalized)
                    ),
                    0.0,
                ),
            )
            entity_rows = await self._session.execute(
                select(Entity.id, entity_score.label("score"))
                .outerjoin(Alias, Alias.entity_id == Entity.id)
                .where(Entity.id.in_(candidate_ids))
                .group_by(Entity.id)
            )
            matched_entities = [
                (entity_id, float(score))
                for entity_id, score in entity_rows.all()
                if float(score) > 0
            ]
            if matched_entities:
                for source_id, score in await self._entity_source_scores(
                    model, matched_entities, filters
                ):
                    term_scores[source_id] = max(term_scores.get(source_id, 0.0), score)
            for source_id, score in term_scores.items():
                collected.setdefault(source_id, []).append(score)
        return aggregate_scores(collected, query.query.score_aggregation)

    async def _entity_source_scores(
        self,
        model: type[Page] | type[Document],
        matched_entities: list[tuple[uuid.UUID, float]],
        filters: Sequence[ColumnElement[bool]],
    ) -> list[tuple[uuid.UUID, float]]:
        """Resolve bounded entity matches to sources through their occurrences."""
        entity_scores = (
            values(
                column("entity_id", UUID(as_uuid=True)),
                column("score", Float),
                name="matched_entity_scores",
            )
            .data(matched_entities)
            .cte("matched_entity_scores")
        )
        mentions = select(
            TextMention.source_id.label("source_id"), entity_scores.c.score
        ).join(entity_scores, entity_scores.c.entity_id == TextMention.entity_id)
        faces = (
            select(ImageOccurrence.source_id.label("source_id"), entity_scores.c.score)
            .select_from(ImageOccurrence)
            .join(Face.__table__, Face.__table__.c.id == ImageOccurrence.id)
            .join(entity_scores, entity_scores.c.entity_id == ImageOccurrence.entity_id)
        )
        if model is Document:
            # Mentions and faces live on pages; surface their parent document too.
            pages = Page.__table__
            documents = Document.__table__
            mention_pages = (
                select(documents.c.id.label("source_id"), entity_scores.c.score)
                .select_from(entity_scores)
                .join(TextMention, TextMention.entity_id == entity_scores.c.entity_id)
                .join(pages, pages.c.id == TextMention.source_id)
                .join(
                    documents,
                    (documents.c.library == pages.c.library)
                    & (documents.c.document_id == pages.c.document_id),
                )
            )
            face_pages = (
                select(documents.c.id.label("source_id"), entity_scores.c.score)
                .select_from(entity_scores)
                .join(
                    ImageOccurrence,
                    ImageOccurrence.entity_id == entity_scores.c.entity_id,
                )
                .join(Face.__table__, Face.__table__.c.id == ImageOccurrence.id)
                .join(pages, pages.c.id == ImageOccurrence.source_id)
                .join(
                    documents,
                    (documents.c.library == pages.c.library)
                    & (documents.c.document_id == pages.c.document_id),
                )
            )
            links = union_all(mentions, faces, mention_pages, face_pages).subquery(
                "entity_source_links"
            )
        else:
            links = union_all(mentions, faces).subquery("entity_source_links")
        score = func.max(links.c.score)
        rows = await self._session.execute(
            select(model.id, score.label("score"))
            .join(links, links.c.source_id == model.id)
            .where(*filters)
            .group_by(model.id)
            .order_by(score.desc(), model.id)
            .limit(SOURCE_TEXT_CANDIDATE_LIMIT)
        )
        return [(source_id, float(raw_score)) for source_id, raw_score in rows.all()]

    async def _source_face_scores(
        self,
        model: type[Page] | type[Document],
        query: SearchPagesRequest | SearchDocumentsRequest,
        filters: Sequence[ColumnElement[bool]],
    ) -> dict[uuid.UUID, float]:
        face_ids = missing_to_none(query.query.face_id)
        if face_ids is None:
            return {}
        return await search_face_scores(
            session=self._session,
            target=model,
            face_ids=face_ids,
            model_stub=query.query.face_embedding_model,
            filters=filters,
            exclude_reference_faces=query.query.exclude_reference_face_id,
            aggregation=query.query.score_aggregation,
        )

    async def _search_sources(
        self,
        model: type[Page] | type[Document],
        query: SearchPagesRequest | SearchDocumentsRequest,
        filters: Sequence[ColumnElement[bool]],
    ) -> tuple[
        list[tuple[uuid.UUID, float, float | None, float | None]],
        str | None,
        int,
    ]:
        ranked = fuse_scores(
            await self._source_text_scores(model, query, filters),
            await self._source_face_scores(model, query, filters),
        )
        page, cursor = search_page(
            ranked,
            query.cursor,
            query.limit,
            cursor_fingerprint(query),
        )
        return page, cursor, len(ranked)

    @staticmethod
    def _search_filters(
        model: type[Page] | type[Document],
        generic_filter: GenericSourceListFilter | MissingType,
    ) -> list[ColumnElement[bool]]:
        filter_values = missing_to_none(generic_filter)
        source_kind = SourceKind.page if model is Page else SourceKind.document
        if filter_values is None:
            return [Source.source_type == source_kind.value]
        base = filter_values.model_copy(
            update={"library": MISSING, "document_id": MISSING, "page_id": MISSING}
        )
        filters = source_filters(base)
        libraries = missing_to_none(filter_values.library)
        if libraries is not None:
            filters.append(model.library.in_(libraries))
        document_ids = missing_to_none(filter_values.document_id)
        if document_ids is not None:
            filters.append(model.document_id.in_(document_ids))
        if model is Page:
            page_ids = missing_to_none(filter_values.page_id)
            if page_ids is not None:
                filters.append(Page.page_id.in_(page_ids))
        filters.append(Source.source_type == source_kind.value)
        return filters

    async def search_pages(
        self, query: SearchPagesRequest
    ) -> SearchPagesResultListResponse:
        generic_filter = (
            query.filter_.to_generic() if query.filter_ is not None else MISSING
        )
        filters = self._search_filters(Page, generic_filter)
        page, cursor, total = await self._search_sources(Page, query, filters)
        rows = await self._session.scalars(
            select(Page).where(Page.id.in_([x[0] for x in page]))
        )
        by_id = {row.id: row for row in rows.all()}
        await load_link_stats(self._session, by_id.values())
        items = [
            FoundPage(
                **PageResponse.from_generic(
                    source_response(by_id[item_id])
                ).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchPagesResultListResponse(
            items=items,
            limit=query.limit,
            total_count=total if query.return_total_count else None,
            cursor=cursor,
        )

    async def search_documents(
        self, query: SearchDocumentsRequest
    ) -> SearchDocumentsResultListResponse:
        generic_filter = (
            query.filter_.to_generic() if query.filter_ is not None else MISSING
        )
        filters = self._search_filters(Document, generic_filter)
        page, cursor, total = await self._search_sources(Document, query, filters)
        rows = await self._session.scalars(
            select(Document).where(Document.id.in_([x[0] for x in page]))
        )
        by_id = {row.id: row for row in rows.all()}
        await load_link_stats(self._session, by_id.values())
        items = [
            FoundDocument(
                **DocumentResponse.from_generic(
                    source_response(by_id[item_id])
                ).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchDocumentsResultListResponse(
            items=items,
            limit=query.limit,
            total_count=total if query.return_total_count else None,
            cursor=cursor,
        )
