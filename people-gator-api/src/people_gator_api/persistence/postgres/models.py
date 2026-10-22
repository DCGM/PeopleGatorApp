"""Relational equivalent of the core Weaviate graph used by People Gator.

The demo deliberately uses joined-table inheritance for the two polymorphic
families. Embeddings use model-keyed rows with dimension-specific partial HNSW
indexes for each registered face model.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
import uuid
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    ARRAY,
    DDL,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    cast,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


from people_gator_api.schemas.enums import EntityLinkState

ENTITY_LINK_ENUM = Enum(EntityLinkState, name="pg_demo_entity_link_state", values_callable=lambda enum: [item.value for item in enum])

def link_constraints(table):
    return (
        CheckConstraint("(entity_id IS NULL) = (entity_link_state IS NULL)", name=f"ck_pg_demo_{table}_link"),
        CheckConstraint("(entity_link_state IS NOT DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NOT NULL AND entity_link_verified_at IS NOT NULL) OR (entity_link_state IS DISTINCT FROM 'verified' AND entity_link_verified_by_user_id IS NULL AND entity_link_verified_at IS NULL)", name=f"ck_pg_demo_{table}_verification"),
        Index(f"ix_pg_demo_{table}_source_state", "source_id", "entity_link_state"),
        Index(f"ix_pg_demo_{table}_entity_state", "entity_id", "entity_link_state"),
    )


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
event.listen(
    Base.metadata,
    "before_create",
    DDL("CREATE EXTENSION IF NOT EXISTS unaccent"),
)
event.listen(
    Base.metadata,
    "before_create",
    DDL(
        """CREATE OR REPLACE FUNCTION demo_unaccent(value text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        PARALLEL SAFE
        AS $$SELECT public.unaccent('public.unaccent'::pg_catalog.regdictionary, value)$$"""
    ),
)

IX = "ix_"
PG = "pg_"
PREFIX = "demo_"
TABLE_NAME_PREFIX = PG + PREFIX
INDEX_NAME_PREFIX = IX + PG + PREFIX
TABLE_NAME_FORMAT = TABLE_NAME_PREFIX + "{}"
INDEX_NAME_FORMAT = INDEX_NAME_PREFIX + "{}"

class User(Base):
    """Application user referenced by owner-aware records."""

    __tablename__ = TABLE_NAME_FORMAT.format("users")
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


class APIKey(Base):
    """Stable, historical key identity; no secret or verification hash."""

    __tablename__ = TABLE_NAME_FORMAT.format("api_keys")

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT"), nullable=False, index=True
    )


class RecordedCreation:
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT"))
    created_by_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("api_keys.id"), ondelete="RESTRICT"))


class AnnotationMetadata(RecordedCreation):
    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_touched_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT"), index=True)
    last_touched_by_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("api_keys.id"), ondelete="RESTRICT"), index=True)


class Entity(RecordedCreation, Base):
    """A canonical real-world entity."""

    __tablename__ = TABLE_NAME_FORMAT.format("entities")
    __table_args__ = (
        CheckConstraint("thumbnail_mode IN ('automatic', 'manual')", name="ck_pg_demo_entities_thumbnail_mode"),
        CheckConstraint("thumbnail_mode <> 'manual' OR thumbnail_face_id IS NOT NULL", name="ck_pg_demo_entities_manual_thumbnail"),
        CheckConstraint("kind = 'person' OR (thumbnail_face_id IS NULL AND thumbnail_mode = 'automatic')", name="ck_pg_demo_entities_person_thumbnail"),
        Index(
            INDEX_NAME_FORMAT.format("entities_name_trgm"),
            "name_normalized",
            postgresql_using="gin",
            postgresql_ops={"name_normalized": "gin_trgm_ops"},
        ),
        Index(
            INDEX_NAME_FORMAT.format("entities_search"), 
            "search_document", 
            postgresql_using="gin"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT"), nullable=False, index=True
    )
    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_touched_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT"), index=True
    )
    last_touched_by_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("api_keys.id"), ondelete="RESTRICT"), index=True
    )
    thumbnail_face_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("faces.id"), name="fk_pg_demo_entities_thumbnail_face",
                   ondelete="SET NULL", use_alter=True), index=True,
    )
    thumbnail_mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default="automatic")
    kind: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str | None] = mapped_column(Text)
    name_normalized: Mapped[str | None] = mapped_column(
        Text,
        Computed("lower(demo_unaccent(name))", persisted=True),
    )
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
    text_mentions: Mapped[list[TextMention]] = relationship(back_populates="entity")
    image_occurrences: Mapped[list[ImageOccurrence]] = relationship(
        back_populates="entity"
    )


class Alias(Base):
    """A separately searchable name that resolves to one entity."""

    __tablename__ = TABLE_NAME_FORMAT.format("aliases")
    __table_args__ = (
        UniqueConstraint(
            "entity_id", 
            "name", 
            name="uq_pg_demo_alias_entity_name"
        ),
        Index(
            INDEX_NAME_FORMAT.format("aliases_name_trgm"),
            "name_normalized",
            postgresql_using="gin",
            postgresql_ops={"name_normalized": "gin_trgm_ops"},
        ),
        Index(
            INDEX_NAME_FORMAT.format("aliases_search"), 
            "search_document", 
            postgresql_using="gin"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("entities.id"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_normalized: Mapped[str] = mapped_column(
        Text,
        Computed("lower(demo_unaccent(name))", persisted=True),
    )
    search_document: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, name)", persisted=True),
    )

    entity: Mapped[Entity] = relationship(back_populates="aliases")


class Source(Base):
    """URL-addressable evidence source and polymorphic source root."""

    __tablename__ = TABLE_NAME_FORMAT.format("sources")
    __table_args__ = (CheckConstraint(
        "(last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)",
        name="ck_pg_demo_sources_touch",
    ),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    last_touched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_touched_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT"), index=True
    )
    last_touched_by_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("api_keys.id"), ondelete="RESTRICT"), index=True
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

    __tablename__ = TABLE_NAME_FORMAT.format("documents")
    __table_args__ = (
        UniqueConstraint("library", "document_id", name="uq_pg_demo_document_identity"),
        Index("ix_pg_demo_documents_name_trgm", "name_normalized", postgresql_using="gin", postgresql_ops={"name_normalized": "gin_trgm_ops"}),
        Index("ix_pg_demo_documents_library", "library"),
        Index("ix_pg_demo_documents_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("sources.id"), ondelete="CASCADE"), primary_key=True
    )
    library: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    name_normalized: Mapped[str | None] = mapped_column(Text, Computed("lower(demo_unaccent(name))", persisted=True))

    __mapper_args__ = {"polymorphic_identity": "document"}  # noqa: RUF012


class Page(Source):
    """A page, identified independently while retaining its document identity."""

    __tablename__ = TABLE_NAME_FORMAT.format("pages")
    __table_args__ = (
        UniqueConstraint(
            "library",
            "document_id",
            "page_id",
            name="uq_pg_demo_page_identity",
        ),
        Index(
            INDEX_NAME_FORMAT.format("page_document"), 
            "library", 
            "document_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("sources.id"), ondelete="CASCADE"), primary_key=True
    )
    library: Mapped[str] = mapped_column(String(255), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __mapper_args__ = {"polymorphic_identity": "page"}  # noqa: RUF012


class Image(Source):
    """An arbitrary image URL source."""

    __tablename__ = TABLE_NAME_FORMAT.format("images")

    id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("sources.id"), ondelete="CASCADE"), primary_key=True
    )

    __mapper_args__ = {"polymorphic_identity": "image"}  # noqa: RUF012


class TextMention(AnnotationMetadata, Base):
    """A textual occurrence with mandatory provenance and optional resolution."""

    __tablename__ = TABLE_NAME_FORMAT.format("text_mentions")
    __table_args__ = (*link_constraints("text_mentions"), CheckConstraint(
        "(last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)", name="ck_pg_demo_text_mentions_touch"),
        Index(
            INDEX_NAME_FORMAT.format("text_mentions_mention_trgm"),
            "mention_normalized",
            postgresql_using="gin",
            postgresql_ops={"mention_normalized": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("sources.id"), ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("entities.id"), ondelete="SET NULL"), index=True
    )
    entity_link_state: Mapped[EntityLinkState | None] = mapped_column(ENTITY_LINK_ENUM)
    entity_link_verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT")
    )
    entity_link_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mention: Mapped[str] = mapped_column(Text, nullable=False)
    mention_normalized: Mapped[str] = mapped_column(
        Text,
        Computed("lower(demo_unaccent(mention))", persisted=True),
    )
    context: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship(back_populates="text_mentions")
    entity: Mapped[Entity | None] = relationship(back_populates="text_mentions")


class ImageOccurrence(AnnotationMetadata, Base):
    """An image-region occurrence and polymorphic root for face detections."""

    __tablename__ = TABLE_NAME_FORMAT.format("image_occurrences")
    __table_args__ = (*link_constraints("image_occurrences"), CheckConstraint(
        "(last_touched_at IS NULL AND last_touched_by_user_id IS NULL AND last_touched_by_api_key_id IS NULL) OR (last_touched_at IS NOT NULL AND last_touched_by_user_id IS NOT NULL)", name="ck_pg_demo_image_occurrences_touch"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("sources.id"), ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("entities.id"), ondelete="SET NULL"), index=True
    )
    entity_link_state: Mapped[EntityLinkState | None] = mapped_column(ENTITY_LINK_ENUM)
    entity_link_verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT")
    )
    entity_link_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurrence_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    roi: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source: Mapped[Source] = relationship(back_populates="image_occurrences")
    entity: Mapped[Entity | None] = relationship(back_populates="image_occurrences")

    __mapper_args__ = {  # noqa: RUF012
        "polymorphic_on": occurrence_type,
        "polymorphic_identity": "image_occurrence",
    }


class Face(ImageOccurrence):
    """A face occurrence with exactly five 2-D alignment keypoints."""

    __tablename__ = TABLE_NAME_FORMAT.format("faces")
    __table_args__ = (
        Index(
            "ix_pg_demo_faces_identifier_trgm",
            "identifier",
            postgresql_using="gin",
            postgresql_ops={"identifier": "gin_trgm_ops"},
        ),
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
        ForeignKey(TABLE_NAME_FORMAT.format("image_occurrences.id"), ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("users.id"), ondelete="RESTRICT"), nullable=False, index=True
    )
    identifier: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    keypoints: Mapped[list[list[float]]] = mapped_column(
        ARRAY(Float(), dimensions=2), nullable=False
    )
    keypoint_types: Mapped[list[str]] = mapped_column(ARRAY(String()), nullable=False)
    embeddings: Mapped[list[FaceEmbedding]] = relationship(
        back_populates="face",
        cascade="all, delete-orphan",
    )

    __mapper_args__ = {"polymorphic_identity": "face"}  # noqa: RUF012


class FaceModel(Base):
    """A registered face embedding model and its fixed vector dimension."""

    __tablename__ = TABLE_NAME_FORMAT.format("face_models")
    __table_args__ = (
        CheckConstraint(
            "embedding_dim > 0",
            name="ck_pg_demo_face_model_embedding_dim",
        ),
    )

    stub: Mapped[str] = mapped_column(String(255), primary_key=True)
    embedding_dim: Mapped[int] = mapped_column(nullable=False)

    embeddings: Mapped[list[FaceEmbedding]] = relationship(back_populates="model")


class FaceEmbedding(Base):
    """One vector for a face and a registered embedding model."""

    __tablename__ = TABLE_NAME_FORMAT.format("face_embeddings")
    __table_args__ = (
        CheckConstraint(
            "vector_dims(embedding) > 0",
            name="ck_pg_demo_face_embedding_nonempty",
        ),
    )

    face_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("faces.id"), ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[str] = mapped_column(
        ForeignKey(TABLE_NAME_FORMAT.format("face_models.stub"), ondelete="RESTRICT"),
        primary_key=True,
    )
    embedding: Mapped[list[float]] = mapped_column(VECTOR(), nullable=False)

    face: Mapped[Face] = relationship(back_populates="embeddings")
    model: Mapped[FaceModel] = relationship(back_populates="embeddings")



def face_embedding_hnsw_index(model_stub: str, embedding_dim: int) -> Index:
    """Build the stable partial HNSW index definition for one face model."""
    digest = hashlib.sha256(model_stub.encode()).hexdigest()[:16]
    index_name = INDEX_NAME_FORMAT.format(f"face_embedding_{digest}_{embedding_dim}dim_hnsw")
    expression = cast(FaceEmbedding.embedding, VECTOR(embedding_dim)).label("embedding")
    index = Index(
        index_name,
        expression,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=(FaceEmbedding.model_id == model_stub),
        postgresql_with={"m": 16, "ef_construction": 64},
    )
    return index

# FK SET NULL also runs this trigger, keeping raw SQL deletes consistent.
CLEAR_LINK_FUNCTION = """CREATE OR REPLACE FUNCTION pg_demo_clear_entity_link() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
IF NEW.entity_id IS NULL THEN
    NEW.entity_link_state := NULL;
    NEW.entity_link_verified_by_user_id := NULL;
    NEW.entity_link_verified_at := NULL;
END IF;
RETURN NEW;
END $$"""
event.listen(Base.metadata, "after_create", DDL(CLEAR_LINK_FUNCTION))
for table in (TextMention.__table__, ImageOccurrence.__table__):
    event.listen(Base.metadata, "after_create", DDL(
        f"CREATE OR REPLACE TRIGGER clear_entity_link BEFORE UPDATE OF entity_id ON {table.name} "
        "FOR EACH ROW EXECUTE FUNCTION pg_demo_clear_entity_link()"
    ))

# Bootstrap installs the same invariants as the thumbnail migration. Alembic
# carries its own frozen definitions so future changes cannot rewrite history.
from .thumbnail_ddl import THUMBNAIL_DDL


def _thumbnail_schema_present(ddl, target, connection, **kwargs):
    from sqlalchemy import inspect
    # create_all against a retained pre-migration store cannot add columns.
    # Leave that store untouched for the explicit migration/adoption command.
    return "thumbnail_face_id" in {
        column["name"] for column in inspect(connection).get_columns(Entity.__tablename__)
    }


for statement in THUMBNAIL_DDL:
    event.listen(Base.metadata, "after_create", DDL(statement).execute_if(callable_=_thumbnail_schema_present))
