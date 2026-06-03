import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.enums import ProcessingStatus
from people_gator_api.db.models.source import Source
from people_gator_api.db.models.source_processing import SourceProcessing
from people_gator_api.db.models.source_schema import SourceSchema
from people_gator_api.schemas.sources import (
    SourceCreateRequest,
    SourceProcessingEntry,
    SourceProcessingResponse,
    SourceResponse,
    SourceSchemaCreateRequest,
    SourceSchemaResponse,
)


def _schema_out(item: SourceSchema) -> SourceSchemaResponse:
    return SourceSchemaResponse(
        schema_name=item.schema_name,
        resolver_type=item.resolver_type,
        resolver_config=item.resolver_config,
    )


def _source_out(item: Source) -> SourceResponse:
    return SourceResponse(
        source_id=item.source_id,
        source_schema_name=item.source_schema_name,
        source=item.source,
        provider=item.provider,
        content_hash=item.content_hash,
        metadata=item.metadata_,
    )


async def list_source_schemas(session: AsyncSession) -> list[SourceSchemaResponse]:
    items = await SourceSchema.list_all(session)
    return [_schema_out(item) for item in items]


async def get_source_schema(session: AsyncSession, schema_name: str) -> SourceSchemaResponse | None:
    item = await SourceSchema.get(session, schema_name)
    if item is None:
        return None
    return _schema_out(item)


async def create_source_schema(session: AsyncSession, payload: SourceSchemaCreateRequest) -> SourceSchemaResponse:
    item = await SourceSchema.create(
        session=session,
        schema_name=payload.schema_name,
        resolver_type=payload.resolver_type,
        resolver_config=payload.resolver_config,
    )
    return _schema_out(item)


async def list_sources(
    session: AsyncSession,
    source_schema_name: str | None,
    provider: str | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[SourceResponse]:
    stmt = sa.select(Source).order_by(Source.source_id.asc()).limit(limit)
    if source_schema_name is not None:
        stmt = stmt.where(Source.source_schema_name == source_schema_name)
    if provider is not None:
        stmt = stmt.where(Source.provider == provider)
    if after_id is not None:
        stmt = stmt.where(Source.source_id > after_id)

    result = await session.execute(stmt)
    return [_source_out(item) for item in result.scalars().all()]


async def get_source(session: AsyncSession, source_id: uuid.UUID) -> SourceResponse | None:
    source = await Source.get(session, source_id)
    if source is None:
        return None
    return _source_out(source)


async def create_source(
    session: AsyncSession,
    payload: SourceCreateRequest,
    created_by: uuid.UUID | None,
) -> tuple[SourceResponse, bool]:
    existing = await Source.get_by_content_hash(session, payload.content_hash)
    if existing is not None:
        return _source_out(existing), False

    source = await Source.create(
        session=session,
        source=payload.source,
        source_schema_name=payload.source_schema_name,
        provider=payload.provider,
        metadata=payload.metadata,
        content_hash=payload.content_hash,
        created_by=created_by,
    )
    return _source_out(source), True


async def get_source_processing(session: AsyncSession, source_id: uuid.UUID) -> SourceProcessingResponse:
    rows = await SourceProcessing.list_for_source(session, source_id)
    return SourceProcessingResponse(
        source_id=source_id,
        processing=[
            SourceProcessingEntry(
                producer_id=row.producer_id,
                processing_status=row.processing_status,
                started_at=row.started_at.isoformat() if row.started_at else None,
                completed_at=row.completed_at.isoformat() if row.completed_at else None,
                error_message=row.error_message,
            )
            for row in rows
        ],
    )


async def upsert_source_processing(
    session: AsyncSession,
    source_id: uuid.UUID,
    producer_id: uuid.UUID,
    processing_status: ProcessingStatus,
    error_message: str | None,
) -> SourceProcessing:
    row = await SourceProcessing.get(session, source_id, producer_id)
    if row is None:
        row = await SourceProcessing.create(session, source_id, producer_id)
    row.processing_status = processing_status
    row.error_message = error_message
    if processing_status == ProcessingStatus.in_progress:
        row.started_at = sa.func.now()
    if processing_status in {ProcessingStatus.complete, ProcessingStatus.failed}:
        row.completed_at = sa.func.now()
    session.add(row)
    return row
