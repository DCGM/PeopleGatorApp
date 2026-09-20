"""Typed search interface demonstrating relational filtering plus hybrid search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    Select,
    String,
    and_,
    bindparam,
    cast,
    func,
    literal_column,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.services.postgres_demo.models import (
    Alias,
    Document,
    Entity,
    EntityEmbedding,
    Face,
    ImageOccurrence,
    ImageOccurrenceEmbedding,
    Page,
    Source,
)


@dataclass(frozen=True, slots=True)
class DocumentRef:
    """The exact archive document scope used by the exclusion predicate."""

    library: str
    document_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class EntityAliasSearchHit:
    entity: Entity
    matched_alias: str
    score: float


@dataclass(frozen=True, slots=True)
class EntityVectorSearchHit:
    entity: Entity
    distance: float


@dataclass(frozen=True, slots=True)
class FaceVectorSearchHit:
    face: Face
    distance: float


def entity_alias_search_excluding_document_statement(
    query: str,
    excluded_document: DocumentRef,
    *,
    limit: int = 20,
    minimum_similarity: float = 0.15,
) -> Select[tuple[Entity, str, float]]:
    """Build the central demo query.

    It combines typo-tolerant pg_trgm similarity with a tsvector full-text hit,
    selects the best matching alias per entity, and excludes entities assigned
    to a Face whose mandatory Source is the exact requested document or one of
    its pages.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("query must contain non-whitespace text")
    if limit < 1:
        raise ValueError("limit must be positive")
    if not 0 <= minimum_similarity <= 1:
        raise ValueError("minimum_similarity must be between 0 and 1")

    query_parameter = bindparam("alias_query", value=cleaned_query, type_=String())
    ts_query = func.websearch_to_tsquery(
        literal_column("'simple'::regconfig"), query_parameter
    )
    trigram_score = func.similarity(Alias.name, query_parameter)
    fulltext_score = func.ts_rank_cd(Alias.search_document, ts_query)
    combined_score = func.greatest(trigram_score, fulltext_score)

    face_table = Face.__table__
    occurrence_table = ImageOccurrence.__table__
    source_table = Source.__table__
    page_table = Page.__table__
    document_table = Document.__table__
    face_sources = (
        face_table.join(occurrence_table, face_table.c.id == occurrence_table.c.id)
        .join(source_table, occurrence_table.c.source_id == source_table.c.id)
        .outerjoin(page_table, page_table.c.id == source_table.c.id)
        .outerjoin(document_table, document_table.c.id == source_table.c.id)
    )
    face_in_document = (
        select(face_table.c.id)
        .select_from(face_sources)
        .where(occurrence_table.c.entity_id == Entity.id)
        .where(
            or_(
                and_(
                    source_table.c.source_type == "page",
                    page_table.c.library == excluded_document.library,
                    page_table.c.document_id == excluded_document.document_id,
                ),
                and_(
                    source_table.c.source_type == "document",
                    document_table.c.library == excluded_document.library,
                    document_table.c.document_id == excluded_document.document_id,
                ),
            )
        )
        .correlate(Entity)
        .exists()
    )

    ranked_aliases = (
        select(
            Alias.entity_id.label("entity_id"),
            Alias.name.label("matched_alias"),
            combined_score.label("score"),
            func.row_number()
            .over(
                partition_by=Alias.entity_id,
                order_by=(combined_score.desc(), Alias.name.asc()),
            )
            .label("alias_rank"),
        )
        .join(Entity, Entity.id == Alias.entity_id)
        .where(
            or_(
                Alias.search_document.op("@@")(ts_query),
                trigram_score >= minimum_similarity,
            )
        )
        .where(~face_in_document)
        .cte("ranked_aliases")
    )

    return (
        select(
            Entity,
            ranked_aliases.c.matched_alias,
            ranked_aliases.c.score,
        )
        .join(ranked_aliases, ranked_aliases.c.entity_id == Entity.id)
        .where(ranked_aliases.c.alias_rank == 1)
        .order_by(ranked_aliases.c.score.desc(), Entity.id.asc())
        .limit(limit)
    )


async def search_entities_by_alias_excluding_document(
    session: AsyncSession,
    query: str,
    excluded_document: DocumentRef,
    *,
    limit: int = 20,
    minimum_similarity: float = 0.15,
) -> list[EntityAliasSearchHit]:
    """Execute the hybrid alias search and materialize typed hits."""
    statement = entity_alias_search_excluding_document_statement(
        query,
        excluded_document,
        limit=limit,
        minimum_similarity=minimum_similarity,
    )
    rows = (await session.execute(statement)).all()
    return [
        EntityAliasSearchHit(entity=row[0], matched_alias=row[1], score=float(row[2]))
        for row in rows
    ]


def entity_description_vector_search_statement(
    query_vector: list[float],
    *,
    model: str,
    field: Literal["description", "short_description"] = "description",
    limit: int = 20,
) -> Select[tuple[Entity, float]]:
    """Build a model-scoped cosine search over either entity description field."""
    _validate_vector_query(query_vector, model, limit)
    distance = cast(
        EntityEmbedding.embedding, VECTOR(len(query_vector))
    ).cosine_distance(query_vector)
    return (
        select(Entity, distance.label("distance"))
        .join(EntityEmbedding, EntityEmbedding.entity_id == Entity.id)
        .where(
            EntityEmbedding.model == model,
            EntityEmbedding.field == field,
            EntityEmbedding.dimensions == len(query_vector),
        )
        .order_by(distance.asc())
        .limit(limit)
    )


async def search_entities_by_description_vector(
    session: AsyncSession,
    query_vector: list[float],
    *,
    model: str,
    field: Literal["description", "short_description"] = "description",
    limit: int = 20,
) -> list[EntityVectorSearchHit]:
    rows = (
        await session.execute(
            entity_description_vector_search_statement(
                query_vector, model=model, field=field, limit=limit
            )
        )
    ).all()
    return [
        EntityVectorSearchHit(entity=row[0], distance=float(row[1])) for row in rows
    ]


def face_vector_search_statement(
    query_vector: list[float],
    *,
    model: str,
    limit: int = 20,
) -> Select[tuple[Face, float]]:
    """Build a model-scoped cosine search over Face occurrence embeddings."""
    _validate_vector_query(query_vector, model, limit)
    distance = cast(
        ImageOccurrenceEmbedding.embedding, VECTOR(len(query_vector))
    ).cosine_distance(query_vector)
    return (
        select(Face, distance.label("distance"))
        .join(
            ImageOccurrenceEmbedding,
            ImageOccurrenceEmbedding.occurrence_id == Face.id,
        )
        .where(
            ImageOccurrenceEmbedding.model == model,
            ImageOccurrenceEmbedding.dimensions == len(query_vector),
        )
        .order_by(distance.asc())
        .limit(limit)
    )


async def search_faces_by_vector(
    session: AsyncSession,
    query_vector: list[float],
    *,
    model: str,
    limit: int = 20,
) -> list[FaceVectorSearchHit]:
    rows = (
        await session.execute(
            face_vector_search_statement(query_vector, model=model, limit=limit)
        )
    ).all()
    return [FaceVectorSearchHit(face=row[0], distance=float(row[1])) for row in rows]


def _validate_vector_query(query_vector: list[float], model: str, limit: int) -> None:
    if not query_vector:
        raise ValueError("query_vector must not be empty")
    if not model.strip():
        raise ValueError("model must not be empty")
    if limit < 1:
        raise ValueError("limit must be positive")
