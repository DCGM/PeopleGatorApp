"""ENTITY table model."""

import logging
import uuid
from collections import Counter

import sqlalchemy as sa
from sqlalchemy import ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class Entity(Base):
    """A distinct person entity."""

    __tablename__ = "entity"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.Index("ix_entity_principal_id", "principal_id"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> "Entity | None":
        result = await session.scalars(
            select(cls).where(cls.entity_id == entity_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Entity"]:
        stmt = select(cls).order_by(cls.entity_id.asc()).limit(limit)
        if after_id is not None:
            stmt = stmt.where(cls.entity_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        principal_id: uuid.UUID,
        entity_id: uuid.UUID | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> "Entity":
        new_id = entity_id or new_uuid6()
        entity = cls(
            entity_id=new_id,
            principal_id=principal_id,
            name=name,
            description=description,
        )
        session.add(entity)
        logger.info(
            "Created entity",
            extra={"entity_id": str(entity.entity_id)},
        )
        return entity

    @classmethod
    async def refresh_aggregates(
        cls,
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> None:
        """Refresh entity-level aggregated name/description from linked records."""
        entity = await cls.get(session, entity_id)
        if entity is None:
            return

        from people_gator_api.models.annotation.description import Description
        from people_gator_api.models.annotation.name import Name

        name_values = list(
            (
                await session.execute(
                    select(Name.name).where(Name.entity_id == entity_id)
                )
            )
            .scalars()
            .all()
        )
        description_values = list(
            (
                await session.execute(
                    select(Description.text).where(Description.entity_id == entity_id)
                )
            )
            .scalars()
            .all()
        )

        entity.name = _most_common_normalized(name_values)
        entity.description = _most_common_normalized(description_values)


def _most_common_normalized(values: list[str]) -> str | None:
    normalized_values = [" ".join(value.split()).strip().lower() for value in values]
    normalized_values = [value for value in normalized_values if value]
    if not normalized_values:
        return None
    counts = Counter(normalized_values)
    return counts.most_common(1)[0][0]


# Backward compatibility alias while API transitions from identity to entity.
Identity = Entity
