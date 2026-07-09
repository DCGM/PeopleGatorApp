"""SEARCH_PROFILE tables — reusable multi-modality search configuration.

A search profile stores per-modality weights and optional model pins via
SEARCH_PROFILE_MODALITY rows.  Profiles are owned by a user, can be marked
public, or can be system-provisioned read-only defaults.  When no
``profile_id`` is supplied to a search endpoint the system-default profile
is used automatically.

Modalities are keyed by ``AnnotationType`` — each annotation type maps to
one or more named vector slots in the vector store.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, Enum as SAEnum, Float, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from people_gator_api.models.base import Base
from people_gator_api.models.enums import AnnotationType
from people_gator_api.utils.uuid_utils import new_uuid6


class SearchProfile(Base):
    """Named, reusable search configuration.

    Per-modality weights and model pin selections are stored in the join
    table ``SearchProfileModality``.  System profiles (``is_system=True``)
    are provisioned at deployment and are read-only.  Any profile can be
    cloned, which produces a fully independent copy owned by the requesting
    user.
    """

    __tablename__ = "search_profile"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    profile_name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Null for system profiles.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("principal.principal_id"),
        nullable=True,
    )
    # Visible and cloneable by all authenticated users.
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Read-only system default; cannot be modified or deleted.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    modalities: Mapped[list["SearchProfileModality"]] = relationship(
        "SearchProfileModality",
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        sa.Index("ix_search_profile_owner", "owner_id"),
        sa.Index("ix_search_profile_public", "is_public"),
    )

    # -------------------------------------------------------------------------
    # Class-level queries
    # -------------------------------------------------------------------------

    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        profile_id: uuid.UUID,
    ) -> "SearchProfile | None":
        result = await session.scalars(
            select(cls).where(cls.profile_id == profile_id)
        )
        return result.one_or_none()

    @classmethod
    async def list_all(
        cls,
        session: AsyncSession,
    ) -> list["SearchProfile"]:
        result = await session.execute(
            select(cls).order_by(cls.profile_name.asc())
        )
        return list(result.scalars().all())
    
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        profile_name: str,
        description: str | None = None,
        owner_id: uuid.UUID | None = None,
        is_public: bool = False,
        is_system: bool = False,
    ) -> "SearchProfile":
        obj = cls(
            profile_name=profile_name,
            description=description,
            owner_id=owner_id,
            is_public=is_public,
            is_system=is_system,
        )
        session.add(obj)
        await session.flush()
        return obj


class SearchProfileModality(Base):
    """Per-modality configuration row for a SearchProfile.

    Composite primary key on ``(profile_id, annotation_type)`` enforces the
    one-row-per-modality-per-profile constraint at the database level.

    ``model_id`` is a nullable FK to ``ModelAgent.principal_id``.  When null
    the highest-priority active MODEL_AGENT for the ``annotation_type`` is
    resolved at query time.  When set the query is pinned to that specific
    agent's vector slot.
    """

    __tablename__ = "search_profile_modality"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("search_profile.profile_id", ondelete="CASCADE"),
        primary_key=True,
    )
    annotation_type: Mapped[AnnotationType] = mapped_column(
        SAEnum(AnnotationType, name="annotation_type_enum"),
        primary_key=True
    )
    # Nullable — null means "use best active model at query time".
    # FK → model_agent.principal_id (MODEL_AGENT subtype table).
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("model_agent.principal_id"),
        nullable=True,
    )
    # Relative contribution to the combined score; normalised to sum=1 at
    # query time across all enabled modalities.
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Annotations below this confidence are excluded before scoring; null = no filter.
    min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    profile: Mapped["SearchProfile"] = relationship(
        "SearchProfile", back_populates="modalities"
    )
    __table_args__ = (
        sa.Index("ix_search_profile_modality_model", "model_id"),
    )


    @classmethod
    async def get(
        cls,
        session: AsyncSession,
        profile_id: uuid.UUID,
        annotation_type: AnnotationType,
    ) -> "SearchProfileModality | None":
        result = await session.scalars(
            select(cls).where(
                cls.profile_id == profile_id,
                cls.annotation_type == annotation_type,
            )
        )
        return result.one_or_none()
    
    @classmethod
    async def list_for_profile(
        cls,
        session: AsyncSession,
        profile_id: uuid.UUID,
    ) -> list["SearchProfileModality"]:
        result = await session.execute(
            select(cls).where(cls.profile_id == profile_id).order_by(cls.annotation_type.asc())
        )
        return list(result.scalars().all())
    
    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        profile_id: uuid.UUID,
        annotation_type: AnnotationType,
        weight: float = 1.0,
        model_id: uuid.UUID | None = None,
        min_confidence: float | None = None,
    ) -> "SearchProfileModality":
        obj = cls(
            profile_id=profile_id,
            annotation_type=annotation_type,
            weight=weight,
            model_id=model_id,
            min_confidence=min_confidence,
        )
        session.add(obj)
        await session.flush()
        return obj
    