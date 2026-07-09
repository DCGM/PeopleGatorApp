"""ALTERNATIVE_NAME table — variant names from authorities (spec §2.5).

Stores name variants (birth name, pseudonym, transliteration, abbreviation)
from Wikidata, authority records, or manual curation.  Immutable once
created (spec §4.1).
"""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.annotation.base_annotation import BaseAnnotation
from people_gator_api.models.enums import AnnotationType, NameType
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class AlternativeName(BaseAnnotation):
    """A variant name for a person attributed to an external source.

    ``name_type`` classifies the variant (birth name, pseudonym, etc.) and
    ``source_type``/``source_ref`` record provenance (spec §2.5).
    """

    __tablename__ = "alternative_name"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_type: Mapped[NameType] = mapped_column(
        SAEnum(NameType, name="name_type_enum"), nullable=False
    )
    language: Mapped[str] = mapped_column(String, nullable=False)
    __table_args__ = (
        sa.Index("ix_alternative_name_name", "name"),
        sa.Index("ix_alternative_name_name_type", "name_type"),
        sa.Index("ix_alternative_name_source_type", "source_type"),
        sa.Index("ix_alternative_name_source_ref", "source_ref"),
        sa.Index("ix_alternative_name_language", "language"),
        sa.Index("ix_alternative_name_principal_id", "principal_id"),
    )
    __mapped_args__ = {
        "polymorphic_identity": AnnotationType.alternative_name,
    }

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        alt_name_id: uuid.UUID,
    ) -> "AlternativeName | None":
        result = await session.scalars(
            select(cls).where(cls.annotation_id == alt_name_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        name_type: NameType | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["AlternativeName"]:
        stmt = select(cls).order_by(cls.annotation_id.asc()).limit(limit)
        if name_type is not None:
            stmt = stmt.where(cls.name_type == name_type)
        if after_id is not None:
            stmt = stmt.where(cls.annotation_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        name: str,
        name_type: NameType,
        source_id: uuid.UUID,
        language: str,
        principal_id: uuid.UUID,
    ) -> "AlternativeName":
        new_id = new_uuid6()
        obj = cls(
            id=new_id,
            name=name,
            name_type=name_type,
            source_id=source_id,
            language=language,
            principal_id=principal_id,
            created_at=new_id,
        )
        session.add(obj)
        logger.info(
            "Created alternative name",
            extra={"alt_name_id": str(obj.annotation_id)},
        )
        return obj
