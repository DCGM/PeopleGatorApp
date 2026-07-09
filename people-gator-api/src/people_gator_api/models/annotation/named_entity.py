"""NAMED_ENTITY table — a named entity mention found in text (spec §2.2).

Stores the actual text, its character offsets within the source, the entity
type, and the model metadata that detected it.  Immutable once created
(spec §4.1).
"""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, Float, Integer, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.annotation.base_annotation import BaseAnnotation
from people_gator_api.models.enums import AnnotationType, EntityType
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class NamedEntity(BaseAnnotation):
    """A named entity mention found in a source document.

    ``offset_start``/``offset_end`` are character offsets into the source
    text; ``principal_id`` links the detection to the PRINCIPAL that
    produced it for staleness detection.
    """

    __tablename__ = "named_entity"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    offset_start: Mapped[int] = mapped_column(Integer, nullable=False)
    offset_end: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, name="entity_type_enum"), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (
        sa.Index("ix_named_entity_source_id", "source_id"),
        sa.Index("ix_named_entity_entity_type", "entity_type"),
        sa.Index("ix_named_entity_principal_id", "principal_id"),
        sa.Index("ix_named_entity_text", "text"),
    )
    __mapped_args__ = {
        "polymorphic_identity": AnnotationType.named_entity,
    }

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> "NamedEntity | None":
        result = await session.scalars(
            select(cls).where(cls.annotation_id == entity_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["NamedEntity"]:
        stmt = select(cls).order_by(cls.annotation_id.asc()).limit(limit)
        if source_id is not None:
            stmt = stmt.where(cls.source_id == source_id)
        if after_id is not None:
            stmt = stmt.where(cls.annotation_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        text: str,
        source_id: uuid.UUID,
        offset_start: int,
        offset_end: int,
        entity_type: EntityType,
        principal_id: uuid.UUID,
        confidence: float,
    ) -> "NamedEntity":
        new_id = new_uuid6()
        obj = cls(
            id=new_id,
            text=text,
            source_id=source_id,
            offset_start=offset_start,
            offset_end=offset_end,
            entity_type=entity_type,
            principal_id=principal_id,
            confidence=confidence,
            created_at=new_id,
        )
        session.add(obj)
        logger.info(
            "Created named entity",
            extra={"entity_id": str(obj.annotation_id)},
        )
        return obj
