from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, cast as type_cast

from sqlalchemy import (
    ColumnElement,
    delete,
    func,
    select,
)
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
    GenericSourceCreateRequest,
    GenericSourceListRequest,
    GenericSourceListResponse,
    GenericSourceLookupRequest,
    GenericSourceResponse,
    PageResponse,
)
from people_gator_api.models import (
    Document,
    Image,
    Page,
    Source,
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
    search_page,
    source_response,
    source_filters,
)

class PostgresSourceRepository(SourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session
        self._source = with_polymorphic(Source, [Document, Page, Image])

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
        return source_response(source) if source is not None else None

    async def list(self, query: GenericSourceListRequest) -> GenericSourceListResponse:
        filters = source_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        cursor_id = decode_cursor(query.cursor, fingerprint)
        await validate_cursor(self._session, Source, cursor_id, filters)
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

    async def delete(self, source_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([source_id]))

    async def delete_batch(self, source_ids: Sequence[uuid.UUID]) -> int:
        unique = list(dict.fromkeys(source_ids))
        if not unique:
            return 0
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(Source).where(Source.id.in_(unique))),
        )
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
            score = func.greatest(
                func.similarity(Source.url, term),
                func.similarity(model.library, term),
            )
            rows = await self._session.execute(
                select(model.id, score.label("score")).where(*filters)
            )
            for item_id, raw_score in rows.all():
                value = float(raw_score)
                if value > 0:
                    collected.setdefault(item_id, []).append(value)
        return aggregate_scores(collected, query.query.score_aggregation)

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

    async def search_pages(
        self, query: SearchPagesRequest
    ) -> SearchPagesResultListResponse:
        generic_filter = (
            query.filter_.to_generic() if query.filter_ is not None else MISSING
        )
        filters = source_filters(generic_filter)
        filters.append(Source.source_type == SourceKind.page.value)
        page, cursor, total = await self._search_sources(Page, query, filters)
        rows = await self._session.scalars(
            select(Page).where(Page.id.in_([x[0] for x in page]))
        )
        by_id = {row.id: row for row in rows.all()}
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
        filters = source_filters(generic_filter)
        filters.append(Source.source_type == SourceKind.document.value)
        page, cursor, total = await self._search_sources(Document, query, filters)
        rows = await self._session.scalars(
            select(Document).where(Document.id.in_([x[0] for x in page]))
        )
        by_id = {row.id: row for row in rows.all()}
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
