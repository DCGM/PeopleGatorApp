import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, Enum as SAEnum, Float, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from people_gator_api.db.models.base import Base, new_uuid6
from people_gator_api.db.models.enums import RecordType


class SearchProfile(Base):
    """Named, reusable search configuration.

    Per-modality weights and model pin selections are stored in the join table
    ``SearchProfileModality``.  System profiles (``is_system=True``) are
    provisioned at deployment and are read-only.  Any profile can be cloned,
    which produces a fully independent copy owned by the requesting user.
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


class SearchProfileModality(Base):
    """Per-modality configuration row for a SearchProfile.

    Composite primary key on ``(profile_id, record_type)`` enforces the
    one-row-per-modality-per-profile constraint at the database level.

    ``model_id`` is a nullable FK to ``ModalityModel``.  When null the
    highest-priority active model for the ``record_type`` is resolved at query
    time.  When set the query is pinned to that specific model's vector slot.
    """

    __tablename__ = "search_profile_modality"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("search_profile.profile_id", ondelete="CASCADE"),
        primary_key=True,
    )
    record_type: Mapped[RecordType] = mapped_column(
        SAEnum(RecordType, name="record_type_enum"), primary_key=True
    )
    # Nullable — null means "use best active model at query time".
    model_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("modality_model.model_id"),
        nullable=True,
    )
    # Relative contribution to the combined score; normalised to sum=1 at
    # query time across all enabled modalities.
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Allows toggling a modality off without deleting the row.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Records below this confidence are excluded before scoring; null = no filter.
    min_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    profile: Mapped["SearchProfile"] = relationship(
        "SearchProfile", back_populates="modalities"
    )

    __table_args__ = (
        sa.Index("ix_search_profile_modality_model", "model_id"),
    )
