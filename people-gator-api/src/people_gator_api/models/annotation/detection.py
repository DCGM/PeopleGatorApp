"""DETECTION table — a face detection with keypoints and metadata (spec §2.3).

Stores the bounding box and facial keypoints as JSON, plus the MODEL_AGENT
that performed the detection and its confidence.  Immutable once created
(spec §4.1).
"""

import logging
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Float, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from people_gator_api.models.annotation.description import BaseAnnotation
from people_gator_api.models.enums import AnnotationType
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class Detection(BaseAnnotation):
    """A face detection produced by a MODEL_AGENT over a source image.

    ``bounding_box`` is ``{"x": int, "y": int, "width": int, "height": int}``
    in pixel coordinates.  ``keypoints`` is an array of
    ``{"type": str, "x": float, "y": float}`` facial landmarks (spec §2.3).
    """

    __tablename__ = "detection"
    bounding_box: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    keypoints: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (
        sa.Index("ix_detection_source_id", "source_id"),
        sa.Index("ix_detection_principal_id", "principal_id"),
        sa.Index("ix_detection_confidence", "confidence"),
    )
    __mapped_args__ = {
        "polymorphic_identity": AnnotationType.detection,
    }

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        detection_id: uuid.UUID,
    ) -> "Detection | None":
        result = await session.scalars(
            select(cls).where(cls.annotation_id == detection_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_page(
        cls,
        session: AsyncSession,
        source_id: uuid.UUID | None = None,
        after_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list["Detection"]:
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
        source_id: uuid.UUID,
        bounding_box: dict[str, Any],
        principal_id: uuid.UUID,
        confidence: float,
        keypoints: list[dict[str, Any]] | None = None,
    ) -> "Detection":
        new_id = new_uuid6()
        obj = cls(
            id=new_id,
            source_id=source_id,
            bounding_box=bounding_box,
            keypoints=keypoints,
            principal_id=principal_id,
            confidence=confidence,
            created_at=new_id,
        )
        session.add(obj)
        logger.info(
            "Created detection",
            extra={"detection_id": str(obj.annotation_id)},
        )
        return obj
