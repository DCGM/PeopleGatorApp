"""Relational equivalent of the core Weaviate graph used by People Gator.

The demo deliberately uses joined-table inheritance for the two polymorphic
families. Embeddings live in model-keyed child tables, which allows a new model
(and even a new vector dimension) to be added without adding a column.
"""

from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    ARRAY,
    DDL,
    CheckConstraint,
    Computed,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative root for the isolated PostgreSQL demo schema."""


# VECTOR columns require pgvector before CREATE TABLE. pg_trgm backs fuzzy name
# matching; PostgreSQL's built-in tsvector/tsquery machinery supplies full text.
event.listen(
    Base.metadata,
    "before_create",
    DDL("CREATE EXTENSION IF NOT EXISTS vector"),
)
event.listen(
    Base.metadata,
    "before_create",
    DDL("CREATE EXTENSION IF NOT EXISTS pg_trgm"),
)


class User(Base):
    """Application user referenced by owner-aware records."""

    __tablename__ = "pg_demo_users"
    __table_args__ = (
        UniqueConstraint(
            "external_issuer",
            "external_subject",
            name="uq_pg_demo_user_external_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, index=True)
    external_subject: Mapped[str] = mapped_column(Text, nullable=False)
    external_issuer: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)


class Entity(Base):
    """A canonical real-world entity."""

    __tablename__ = "pg_demo_entities"
    __table_args__ = (
        Index(
            "ix_pg_demo_entities_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index("ix_pg_demo_entities_search", "search_document", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    short_description: Mapped[str | None] = mapped_column(Text)
    wikidata_id: Mapped[str | None] = mapped_column(String(64), index=True)
    nlcr_authority_id: Mapped[str | None] = mapped_column(String(128), index=True)
    search_document: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            """to_tsvector('simple'::regconfig,
            coalesce(name, '') || ' ' || coalesce(description, '') || ' ' ||
            coalesce(short_description, ''))""",
            persisted=True,
        ),
    )

    aliases: Mapped[list[Alias]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list[EntityEmbedding]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    text_mentions: Mapped[list[TextMention]] = relationship(back_populates="entity")
    image_occurrences: Mapped[list[ImageOccurrence]] = relationship(
        back_populates="entity"
    )


class Alias(Base):
    """A separately searchable name that resolves to one entity."""

    __tablename__ = "pg_demo_aliases"
    __table_args__ = (
        UniqueConstraint("entity_id", "name", name="uq_pg_demo_alias_entity_name"),
        Index(
            "ix_pg_demo_aliases_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index("ix_pg_demo_aliases_search", "search_document", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    search_document: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, name)", persisted=True),
    )

    entity: Mapped[Entity] = relationship(back_populates="aliases")


class EntityEmbedding(Base):
    """One semantic vector for an entity field and embedding model.

    VECTOR intentionally has no fixed dimension. Queries cast it to the selected
    model's dimension, allowing per-model partial HNSW indexes (see README.md).
    """

    __tablename__ = "pg_demo_entity_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "field",
            "model",
            name="uq_pg_demo_entity_embedding_model",
        ),
        CheckConstraint(
            "field IN ('name', 'description', 'short_description', 'fulltext')",
            name="ck_pg_demo_entity_embedding_field",
        ),
        CheckConstraint(
            "dimensions > 0 AND vector_dims(embedding) = dimensions",
            name="ck_pg_demo_entity_embedding_dimensions",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(), nullable=False)

    entity: Mapped[Entity] = relationship(back_populates="embeddings")


class Source(Base):
    """URL-addressable evidence source and polymorphic source root."""

    __tablename__ = "pg_demo_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    text_mentions: Mapped[list[TextMention]] = relationship(back_populates="source")
    image_occurrences: Mapped[list[ImageOccurrence]] = relationship(
        back_populates="source"
    )

    __mapper_args__ = {  # noqa: RUF012
        "polymorphic_on": source_type,
        "polymorphic_identity": "source",
    }


class Document(Source):
    """A whole library document."""

    __tablename__ = "pg_demo_documents"
    __table_args__ = (
        UniqueConstraint("library", "document_id", name="uq_pg_demo_document_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_sources.id", ondelete="CASCADE"), primary_key=True
    )
    library: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __mapper_args__ = {"polymorphic_identity": "document"}  # noqa: RUF012


class Page(Source):
    """A page, identified independently while retaining its document identity."""

    __tablename__ = "pg_demo_pages"
    __table_args__ = (
        UniqueConstraint(
            "library",
            "document_id",
            "page_id",
            name="uq_pg_demo_page_identity",
        ),
        Index("ix_pg_demo_page_document", "library", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_sources.id", ondelete="CASCADE"), primary_key=True
    )
    library: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __mapper_args__ = {"polymorphic_identity": "page"}  # noqa: RUF012


class Image(Source):
    """An arbitrary image URL source."""

    __tablename__ = "pg_demo_images"

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_sources.id", ondelete="CASCADE"), primary_key=True
    )

    __mapper_args__ = {"polymorphic_identity": "image"}  # noqa: RUF012


class TextMention(Base):
    """A textual occurrence with mandatory provenance and optional resolution."""

    __tablename__ = "pg_demo_text_mentions"
    __table_args__ = (
        Index(
            "ix_pg_demo_text_mentions_mention_trgm",
            "mention",
            postgresql_using="gin",
            postgresql_ops={"mention": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pg_demo_entities.id", ondelete="SET NULL"), index=True
    )
    mention: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship(back_populates="text_mentions")
    entity: Mapped[Entity | None] = relationship(back_populates="text_mentions")


class ImageOccurrence(Base):
    """An image-region occurrence and polymorphic root for face detections."""

    __tablename__ = "pg_demo_image_occurrences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pg_demo_entities.id", ondelete="SET NULL"), index=True
    )
    occurrence_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    roi: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source: Mapped[Source] = relationship(back_populates="image_occurrences")
    entity: Mapped[Entity | None] = relationship(back_populates="image_occurrences")
    embeddings: Mapped[list[ImageOccurrenceEmbedding]] = relationship(
        back_populates="occurrence", cascade="all, delete-orphan"
    )

    __mapper_args__ = {  # noqa: RUF012
        "polymorphic_on": occurrence_type,
        "polymorphic_identity": "image_occurrence",
    }


class Face(ImageOccurrence):
    """A face occurrence with exactly five 2-D alignment keypoints."""

    __tablename__ = "pg_demo_faces"
    __table_args__ = (
        CheckConstraint(
            """array_ndims(keypoints) = 2
            AND array_length(keypoints, 1) = 5
            AND array_length(keypoints, 2) = 2""",
            name="ck_pg_demo_face_five_2d_keypoints",
        ),
        CheckConstraint(
            "cardinality(keypoint_types) = 5",
            name="ck_pg_demo_face_five_keypoint_types",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_image_occurrences.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    identifier: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    keypoints: Mapped[list[list[float]]] = mapped_column(
        ARRAY(Float(), dimensions=2), nullable=False
    )
    keypoint_types: Mapped[list[str]] = mapped_column(ARRAY(String()), nullable=False)

    __mapper_args__ = {"polymorphic_identity": "face"}  # noqa: RUF012


class ImageOccurrenceEmbedding(Base):
    """A model-keyed visual embedding for an image occurrence."""

    __tablename__ = "pg_demo_image_occurrence_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "occurrence_id", "model", name="uq_pg_demo_occurrence_embedding_model"
        ),
        CheckConstraint(
            "dimensions > 0 AND vector_dims(embedding) = dimensions",
            name="ck_pg_demo_occurrence_embedding_dimensions",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pg_demo_image_occurrences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(), nullable=False)

    occurrence: Mapped[ImageOccurrence] = relationship(back_populates="embeddings")
