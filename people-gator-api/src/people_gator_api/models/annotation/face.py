"""FACE table model."""

import uuid
from typing import TypedDict

import sqlalchemy as sa
from sqlalchemy import Float, ForeignKey, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.base import Base
from people_gator_api.utils.uuid_utils import new_uuid6


class BoundingBox(TypedDict):
    x: int
    y: int
    width: int
    height: int


class FaceKeypoint(TypedDict):
    type: str
    x: float
    y: float


class Face(Base):
    """Face detection linked to identity and source."""

    __tablename__ = "face"

    detection_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    bounding_box: Mapped[BoundingBox] = mapped_column(JSONB, nullable=False)
    keypoints: Mapped[list[FaceKeypoint]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source.source_id"), nullable=False
    )
    model_agent_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("principal.principal_id"), nullable=False
    )
    identity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("identity.identity_id"), nullable=False
    )

    __table_args__ = (
        sa.Index("ix_face_source_id", "source_id"),
        sa.Index("ix_face_model_agent_id", "model_agent_id"),
        sa.Index("ix_face_identity_id", "identity_id"),
    )

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        detection_id: uuid.UUID,
    ) -> "Face | None":
        result = await session.scalars(select(cls).where(cls.detection_id == detection_id))
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
        identity_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Face"]:
        stmt = select(cls).order_by(cls.detection_id.asc()).limit(limit)
        if source_id is not None:
            stmt = stmt.where(cls.source_id == source_id)
        if identity_id is not None:
            stmt = stmt.where(cls.identity_id == identity_id)
        if after_id is not None:
            stmt = stmt.where(cls.detection_id > after_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID,
        bounding_box: BoundingBox,
        keypoints: list[FaceKeypoint],
        model_agent_id: uuid.UUID,
        identity_id: uuid.UUID,
        confidence: float,
    ) -> "Face":
        item = cls(
            detection_id=new_uuid6(),
            source_id=source_id,
            bounding_box=bounding_box,
            keypoints=keypoints,
            model_agent_id=model_agent_id,
            identity_id=identity_id,
            confidence=confidence,
        )
        session.add(item)
        return item
