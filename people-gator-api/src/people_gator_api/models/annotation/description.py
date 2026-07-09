"""DESCRIPTION table — biographical text from authorities (spec §2.4).

Stores descriptive text from Wikidata, authority records, or manual
curation, with an external source reference and language.  Immutable once
created (spec §4.1).
"""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.annotation.base_annotation import BaseAnnotation
from people_gator_api.models.enums import AnnotationType
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class Description(BaseAnnotation):
    """Biographical or descriptive text attributed to an external source.
    or authority ID) for provenance (spec §2.4).
    """

    __tablename__ = "description"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    __table_args__ = (
        sa.Index("ix_description_source_type", "source_type"),
        sa.Index("ix_description_source_ref", "source_ref"),
        sa.Index("ix_description_language", "language"),
        sa.Index("ix_description_principal_id", "principal_id"),
    )
    __mapped_args__ = {
        "polymorphic_identity": AnnotationType.description,
    }

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        description_id: uuid.UUID,
    ) -> "Description | None":
        result = await session.scalars(
            select(cls).where(cls.annotation_id == description_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Description"]:
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
        principal_id: uuid.UUID,
        language: str | None = None,
    ) -> "Description":
        new_id = new_uuid6()
        obj = cls(
            id=new_id,
            text=text,
            source_id=source_id,
            language=language,
            principal_id=principal_id,
            created_at=new_id,
        )
        session.add(obj)
        logger.info(
            "Created description",
            extra={"description_id": str(obj.annotation_id)},
        )
        return obj
