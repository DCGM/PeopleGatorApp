import logging
import uuid

from sqlalchemy import Enum as SAEnum, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import ResolverType

logger = logging.getLogger(__name__)


class SourceSchema(Base):
    """Defines how to resolve storage and access paths for a family of sources.

    ``resolver_config`` is a JSONB document whose structure is determined by
    ``resolver_type``.  Template variables (e.g. ``{provider_id}``,
    ``{page}``) are interpolated from ``SOURCE.provider_id`` and
    ``RECORD.source_path`` values at resolution time.

    Example resolver_config shapes:

    - ``local-filesystem``:
      ``{"base_path": "/data/scans", "path_template": "{provider_id}.tif"}``
    - ``s3``:
      ``{"bucket": "scan-archive", "key_template": "{provider}/{provider_id}.jpg"}``
    - ``iiif``:
      ``{"base_url": "https://kramerius.example.org/iiif/3",
         "manifest_template": "{provider_id}/manifest"}``
    - ``http``:
      ``{"base_url": "https://cdn.example.org/scans",
         "path_template": "{provider_id}"}``
    """

    __tablename__ = "source_schema"

    schema_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    schema_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    resolver_type: Mapped[ResolverType] = mapped_column(
        SAEnum(ResolverType, name="resolver_type_enum"), nullable=False
    )
    resolver_config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        schema_id: uuid.UUID,
    ) -> "SourceSchema | None":
        result = await session.scalars(
            select(cls).where(cls.schema_id == schema_id)
        )
        return result.one_or_none()

    @classmethod
    async def get_by_name(
        cls,
        session: AsyncSession,
        schema_name: str,
    ) -> "SourceSchema | None":
        result = await session.scalars(
            select(cls).where(cls.schema_name == schema_name)
        )
        return result.one_or_none()

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        schema_name: str,
        resolver_type: ResolverType,
        resolver_config: dict[str, object],
    ) -> "SourceSchema":
        schema = cls(
            schema_id=new_uuid6(),
            schema_name=schema_name,
            resolver_type=resolver_type,
            resolver_config=resolver_config,
        )
        session.add(schema)
        logger.info(
            "Created source schema",
            extra={
                "schema_id": str(schema.schema_id),
                "schema_name": schema_name,
                "resolver_type": resolver_type.value,
            },
        )
        return schema
