import logging
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base
from people_gator_api.db.models.enums import ProcessingStatus

logger = logging.getLogger(__name__)


class SourceProcessing(Base):
    """Tracks the processing status of a SOURCE by a specific MODEL_AGENT.

    Composite primary key ``(source_id, producer_id)``.  ``producer_id`` is a
    FK to ``model_agent.principal_id`` — the MODEL_AGENT (inference pipeline)
    that is processing this source.  Each model gets its own row, enabling
    multiple concurrent ingestion pipelines per source.
    """

    __tablename__ = "source_processing"

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source.source_id", ondelete="CASCADE"),
        primary_key=True,
    )
    # FK → model_agent.principal_id (replaces old modality_model FK).
    producer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("model_agent.principal_id", ondelete="CASCADE"),
        primary_key=True,
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        SAEnum(ProcessingStatus, name="processing_status_enum"),
        nullable=False,
        default=ProcessingStatus.queued,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Populated on failure; null when status != failed.
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        sa.Index("ix_source_processing_source_id", "source_id"),
        sa.Index("ix_source_processing_producer_id", "producer_id"),
        sa.Index("ix_source_processing_status", "processing_status"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID,
        producer_id: uuid.UUID,
    ) -> "SourceProcessing | None":
        result = await session.scalars(
            select(cls).where(
                cls.source_id == source_id,
                cls.producer_id == producer_id,
            )
        )
        return result.one_or_none()

    @classmethod
    async def list_for_source(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID,
    ) -> list["SourceProcessing"]:
        result = await session.execute(
            select(cls).where(cls.source_id == source_id)
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID,
        producer_id: uuid.UUID,
    ) -> "SourceProcessing":
        sp = cls(
            source_id=source_id,
            producer_id=producer_id,
            processing_status=ProcessingStatus.queued,
        )
        session.add(sp)
        logger.info(
            "Created source processing entry",
            extra={
                "source_id": str(source_id),
                "producer_id": str(producer_id),
            },
        )
        return sp

