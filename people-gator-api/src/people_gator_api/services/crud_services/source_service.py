"""Service for source endpoints (spec §2.7 simplified source model)."""

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.models.enums import SourceKind
from people_gator_api.models.source import Source
from people_gator_api.schemas.sources import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
)


def _source_out(item: Source) -> SourceResponse:
    return SourceResponse(
        source_id=item.source_id,
        source_type=item.source_type,
        uri=item.uri,
        metadata=item.metadata_,
    )


async def list_sources(
    session: AsyncSession,
    source_type: SourceKind | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> SourceListResponse:
    stmt = sa.select(Source).order_by(Source.source_id.asc()).limit(limit)
    if source_type is not None:
        stmt = stmt.where(Source.source_type == source_type)
    if after_id is not None:
        stmt = stmt.where(Source.source_id > after_id)

    result = await session.execute(stmt)
    items = [_source_out(item) for item in result.scalars().all()]
    return SourceListResponse(
        items=items,
        total=len(items),
        next_after_id=items[-1].source_id if len(items) == limit and items else None,
    )


async def get_source(session: AsyncSession, source_id: uuid.UUID) -> SourceResponse | None:
    source = await Source.get(session, source_id)
    if source is None:
        return None
    return _source_out(source)


async def create_source(
    session: AsyncSession,
    payload: SourceCreateRequest,
    _created_by: uuid.UUID | None,
) -> tuple[SourceResponse, bool]:
    """Create a source, returning (response, created).

    If a source with the same ``(source_type, uri)`` already exists, return it
    with ``created=False`` (idempotent ingest).
    """
    existing = await Source.get_by_type_uri(session, payload.source_type, payload.uri)
    if existing is not None:
        return _source_out(existing), False

    source = await Source.create(
        session=session,
        source_type=payload.source_type,
        uri=payload.uri,
        metadata=payload.metadata,
    )
    return _source_out(source), True
