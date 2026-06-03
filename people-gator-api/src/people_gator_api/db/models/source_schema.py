"""SOURCE_SCHEMA table — resolver configuration for a family of sources."""

import logging

import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base
from people_gator_api.db.models.enums import ResolverType

logger = logging.getLogger(__name__)


class SourceSchema(Base):
    """Defines how to resolve storage and access paths for a family of sources.

    ``schema_name`` is the globally-unique human-readable string PK, e.g.
    ``image-upload``, ``kramerius-iiif``.

    ``resolver_config`` is a JSONB document whose structure is determined by
    ``resolver_type`` and validated in the application layer via
    ``storage.resolver.ResolverConfig``.
    """

    __tablename__ = "source_schema"

    schema_name: Mapped[str] = mapped_column(String, primary_key=True)
    resolver_type: Mapped[ResolverType] = mapped_column(
        SAEnum(ResolverType, name="resolver_type_enum"), nullable=False
    )
    resolver_config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        sa.Index(
            "ix_source_schema_resolver_config_gin",
            "resolver_config",
            postgresql_using="gin",
        ),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        schema_name: str,
    ) -> "SourceSchema | None":
        result = await session.scalars(
            select(cls).where(cls.schema_name == schema_name)
        )
        return result.one_or_none()

    @classmethod
    async def list_all(
        cls,
        session: AsyncSession,
    ) -> list["SourceSchema"]:
        result = await session.execute(
            select(cls).order_by(cls.schema_name.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        schema_name: str,
        resolver_type: ResolverType,
        resolver_config: dict[str, object],
    ) -> "SourceSchema":
        schema = cls(
            schema_name=schema_name,
            resolver_type=resolver_type,
            resolver_config=resolver_config,
        )
        session.add(schema)
        logger.info(
            "Created source schema",
            extra={
                "schema_name": schema_name,
                "resolver_type": resolver_type.value,
            },
        )
        return schema
