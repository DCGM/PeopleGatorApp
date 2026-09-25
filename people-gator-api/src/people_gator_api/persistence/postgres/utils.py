"""PostgreSQL implementation of the backend-neutral persistence contracts.

The adapter binds every repository in :class:`Database` to one request-scoped
``AsyncSession``. API schemas are translated explicitly to the joined-table
SQLAlchemy source hierarchy and the entity, face, mention, alias, embedding,
and user tables; no ORM type crosses the persistence boundary.

Ordinary lists use deterministic UUID keyset pagination. Their opaque cursor is
a URL-safe base64 JSON token containing the last UUID and a fingerprint of the
request without its cursor, which rejects malformed tokens and reuse with
different filters or options. Search cursors use the same envelope and point to
an item in the deterministic score/UUID ranking.

Text search uses PostgreSQL ``pg_trgm`` similarity. Face search reduces large
reference sets to a fixed number of weighted k-means representatives,
uses pgvector HNSW cosine search to generate candidates, then rescores those
candidates in one query. Scores are aggregated within each modality as
requested by the schema, ranked with UUID tie-breaking, and combined across
modalities with reciprocal-rank fusion.

Writes validate referenced rows before mutation and translate integrity errors
to ``ValueError`` as required by the contracts. Entity deletion unassigns faces
and mentions, source deletion relies on relational cascades, and referenced
users cannot be deleted. Each mutating operation commits its unit of work;
batch methods preserve input order but intentionally expose no stronger
atomicity guarantee than the backend-neutral contract.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import uuid
from asyncio import to_thread
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast as type_cast

import numpy as np
from numpy.typing import NDArray
from pgvector.sqlalchemy import VECTOR
from pydantic import BaseModel
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize
from sqlalchemy import (
    ColumnElement,
    cast,
    column,
    exists,
    func,
    literal,
    or_,
    select,
    text,
    true,
    union_all,
    values,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from people_gator_api.schemas.entities import (
    EntityListFilter,
    EntityResponse,
)
from people_gator_api.schemas.enums import EntityType, ScoreAggregation, SourceKind
from people_gator_api.schemas.face_models import (
    FaceModelResponse,
)
from people_gator_api.schemas.faces import (
    BoundingBox,
    FaceEmbedding as FaceEmbeddingInput,
    FaceListFilter,
    FaceResponse,
    Keypoint,
)
from people_gator_api.schemas.mentions import (
    TextMentionListFilter,
    TextMentionResponse,
)
from people_gator_api.schemas.missing import (
    MissingType,
    missing_to_none,
)
from people_gator_api.schemas.search import (
    RRF_K,
)
from people_gator_api.schemas.sources import (
    GenericSourceListFilter,
    GenericSourceResponse,
)
from people_gator_api.schemas.users import (
    UserListFilter,
    UserResponse,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.models import (
    Alias,
    Document,
    Entity,
    Face,
    FaceEmbedding as FaceEmbeddingRow,
    FaceModel,
    ImageOccurrence,
    Page,
    Source,
    TextMention,
    User,
)


ModelT = TypeVar("ModelT")
FloatArray = NDArray[np.float64]

# HNSW returns a bounded face candidate pool for each representative query
# vector. Large query sets are reduced with deterministic k-means over
# normalized embeddings so database work is bounded rather than growing with
# every reference face.
FACE_SEARCH_CANDIDATE_LIMIT = 200
FACE_SEARCH_REPRESENTATIVE_LIMIT = 8
HNSW_EF_SEARCH = 400

# Text search has the same two-stage shape as vector search: use indexes to
# retrieve a small pool per signal, then calculate the existing exact score on
# the union.  Without this bound, the alias join and similarity calls scan the
# entire entity catalogue for every query term.
TEXT_SEARCH_CANDIDATE_LIMIT = 200


def cosine_distance(embedding: object, query_vector: object) -> ColumnElement[float]:
    return type_cast(Any, embedding).cosine_distance(query_vector)


@dataclass(frozen=True)
class FaceQueryRepresentative:
    query_id: uuid.UUID
    embedding: list[float]
    weight: int


@trace("representative_face_vectors")
async def representative_face_vectors(
    vectors: dict[uuid.UUID, list[float]],
) -> list[FaceQueryRepresentative]:
    """Bound a face-query set using deterministic k-means.

    Embeddings are L2-normalized for clustering because downstream search uses
    cosine distance. The original embedding nearest each learned center is
    returned, so every representative remains an actual query face. Small
    searches remain exact, and cluster weights preserve the original query
    distribution for average aggregation.
    """
    items = list(vectors.items())
    if len(items) <= FACE_SEARCH_REPRESENTATIVE_LIMIT:
        return [
            FaceQueryRepresentative(query_id, vector, 1) for query_id, vector in items
        ]

    points = type_cast(
        FloatArray,
        normalize(
            np.asarray([vector for _, vector in items], dtype=np.float64),
            norm="l2",
        ),
    )
    cluster_count = min(
        FACE_SEARCH_REPRESENTATIVE_LIMIT,
        len(np.unique(points, axis=0)),
    )
    kmeans = KMeans(n_clusters=cluster_count, random_state=0)
    assignments = type_cast(
        NDArray[np.int32],
        await to_thread(kmeans.fit_predict, points),
    )
    representatives: list[FaceQueryRepresentative] = []
    for cluster_index in range(cluster_count):
        member_indices = np.flatnonzero(assignments == cluster_index)
        if not len(member_indices):
            continue
        member_points = points[member_indices]
        center = type_cast(FloatArray, kmeans.cluster_centers_)[cluster_index]
        squared_distances = type_cast(
            FloatArray,
            np.sum(np.square(member_points - center), axis=1),
        )
        representative_index = int(member_indices[np.argmin(squared_distances)])
        query_id, embedding = items[representative_index]
        representatives.append(
            FaceQueryRepresentative(
                query_id=query_id,
                embedding=embedding,
                weight=len(member_indices),
            )
        )
    return representatives


def query_vectors_cte(
    representatives: Sequence[FaceQueryRepresentative], embedding_dim: int
):
    vector_type = VECTOR(embedding_dim)
    rows = [
        (
            representative.query_id,
            # A pgvector bind processor serializes the value as text. VALUES has
            # no typed column context in PostgreSQL, so asyncpg otherwise leaves
            # this parameter as text and the cosine operator becomes
            # ``vector <=> text``.
            cast(literal(representative.embedding, type_=vector_type), vector_type),
            representative.weight,
        )
        for representative in representatives
    ]
    return (
        values(
            column("query_id", UUID(as_uuid=True)),
            column("embedding", vector_type),
            column("weight"),
            name="query_vectors",
        )
        .data(rows)
        .cte("query_vectors")
    )


def entity_text_candidates(
    normalized_term: ColumnElement[str],
    filters: Sequence[ColumnElement[bool]],
):
    """Return index-backed entity candidates for one text query.

    Keep the branches separate so PostgreSQL can use the trigram GIN index on
    each name column. Combining these predicates around the alias join causes
    a catalogue-wide aggregate.
    """
    entity_name_score = func.word_similarity(
        normalized_term,
        Entity.name_normalized,
    )
    entity_names = (
        select(Entity.id.label("candidate_id"))
        .where(
            *filters,
            Entity.name_normalized.op("%>")(normalized_term),
        )
        .order_by(entity_name_score.desc())
        .limit(TEXT_SEARCH_CANDIDATE_LIMIT)
    )

    alias_name_score = func.word_similarity(
        normalized_term,
        Alias.name_normalized,
    )
    alias_names = select(Alias.entity_id.label("candidate_id"))
    if filters:
        alias_names = alias_names.join(Entity, Entity.id == Alias.entity_id)
    alias_names = (
        alias_names.where(
            *filters,
            Alias.name_normalized.op("%>")(normalized_term),
        )
        .order_by(alias_name_score.desc())
        .limit(TEXT_SEARCH_CANDIDATE_LIMIT)
    )

    candidates = union_all(entity_names, alias_names).subquery("entity_text_candidates")
    return select(candidates.c.candidate_id).distinct()


@trace("postgres.hnsw.configure")
async def configure_hnsw_search(session: AsyncSession) -> None:
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))


def face_embedding_expression(embedding_dim: int) -> ColumnElement[list[float]]:
    return cast(FaceEmbeddingRow.embedding, VECTOR(embedding_dim))


def face_model_predicate(model_stub: str) -> ColumnElement[bool]:
    return FaceEmbeddingRow.model_id == literal(model_stub, literal_execute=True)


def face_target_select(
    target: type[Face] | type[Entity] | type[Page] | type[Document],
    *columns: ColumnElement[Any],
):
    """Create the common embedding-to-result join for a face search target."""
    statement = (
        select(*columns)
        .select_from(FaceEmbeddingRow)
        .join(Face, Face.id == FaceEmbeddingRow.face_id)
    )
    if target is Entity:
        return statement.join(Entity, Entity.id == Face.entity_id)
    if target is Page or target is Document:
        return statement.join(target, target.id == Face.source_id)
    if target is Face:
        return statement
    raise TypeError(f"unsupported face-search target: {target!r}")


def face_score_query(
    target: type[Face] | type[Entity] | type[Page] | type[Document],
    representatives: Sequence[FaceQueryRepresentative],
    embedding_dim: int,
    model_stub: str,
    filters: Sequence[ColumnElement[bool]],
    excluded_face_ids: Sequence[uuid.UUID],
    aggregation: ScoreAggregation,
):
    """Generate a filtered HNSW candidate query plus bounded exact rescoring."""
    target_id = target.id
    embedding = face_embedding_expression(embedding_dim)
    model_filter = face_model_predicate(model_stub)
    query_vectors = query_vectors_cte(representatives, embedding_dim)
    candidate_distance = cosine_distance(embedding, query_vectors.c.embedding)

    nearest = face_target_select(
        target,
        target_id.label("candidate_id"),
    ).where(*filters, model_filter)
    if excluded_face_ids:
        nearest = nearest.where(Face.id.not_in(excluded_face_ids))
    nearest = (
        nearest.order_by(candidate_distance)
        .limit(FACE_SEARCH_CANDIDATE_LIMIT)
        .lateral("nearest_faces")
    )
    candidates = (
        select(nearest.c.candidate_id)
        .select_from(query_vectors.join(nearest, true()))
        .distinct()
        .cte("face_candidates")
    )

    distance = cosine_distance(embedding, query_vectors.c.embedding)
    per_representative = face_target_select(
        target,
        target_id.label("candidate_id"),
        query_vectors.c.query_id,
        query_vectors.c.weight,
        func.max(1.0 - distance).label("score"),
    ).join(query_vectors, true())
    per_representative = per_representative.where(
        *filters,
        model_filter,
        target_id.in_(select(candidates.c.candidate_id)),
    )
    if excluded_face_ids:
        per_representative = per_representative.where(Face.id.not_in(excluded_face_ids))
    per_representative = per_representative.group_by(
        target_id,
        query_vectors.c.query_id,
        query_vectors.c.weight,
    ).cte("face_scores_by_representative")

    if aggregation == ScoreAggregation.min:
        aggregate_score = func.min(per_representative.c.score)
    elif aggregation == ScoreAggregation.max:
        aggregate_score = func.max(per_representative.c.score)
    else:
        aggregate_score = func.sum(
            per_representative.c.score * per_representative.c.weight
        ) / func.sum(per_representative.c.weight)
    return select(
        per_representative.c.candidate_id,
        aggregate_score.label("score"),
    ).group_by(per_representative.c.candidate_id)


@trace("postgres.face_search.scores")
async def search_face_scores(
    session: AsyncSession,
    target: type[Face] | type[Entity] | type[Page] | type[Document],
    face_ids: Sequence[uuid.UUID],
    model_stub: str,
    filters: Sequence[ColumnElement[bool]],
    exclude_reference_faces: bool,
    aggregation: ScoreAggregation,
) -> dict[uuid.UUID, float]:
    vectors, embedding_dim = await reference_vectors(session, face_ids, model_stub)
    representatives = await representative_face_vectors(vectors)
    statement = face_score_query(
        target=target,
        representatives=representatives,
        embedding_dim=embedding_dim,
        model_stub=model_stub,
        filters=filters,
        excluded_face_ids=face_ids if exclude_reference_faces else [],
        aggregation=aggregation,
    )
    await configure_hnsw_search(session)
    rows = await session.execute(statement)
    return {item_id: float(score) for item_id, score in rows.all()}


def strings(values: Iterable[object]) -> list[str]:
    return [str(value) for value in values]


@trace("postgres.commit")
async def commit(session: AsyncSession, message: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError(message) from exc


@trace("postgres.validate_ids")
async def ensure_ids(
    session: AsyncSession,
    model: type[ModelT],
    ids: Iterable[uuid.UUID],
    label: str,
) -> None:
    requested = set(ids)
    if not requested:
        return
    found = set(
        type_cast(
            Iterable[uuid.UUID],
            await session.scalars(
                select(model.id).where(model.id.in_(requested))  # type: ignore[attr-defined]
            ),
        )
    )
    missing = sorted(requested - found, key=lambda item: item.int)
    if missing:
        raise ValueError(f"{label} does not exist: {missing[0]}")


@trace("postgres.validate_cursor")
async def validate_cursor(
    session: AsyncSession,
    model: type[ModelT],
    cursor: uuid.UUID | None,
    filters: Sequence[ColumnElement[bool]],
) -> None:
    if cursor is None:
        return
    valid = await session.scalar(
        select(
            exists().where(
                model.id == cursor,  # type: ignore[attr-defined]
                *filters,
            )
        )
    )
    if not valid:
        raise ValueError("cursor is not valid for this query")


def cursor_fingerprint(query: BaseModel) -> str:
    payload = query.model_dump(mode="json", exclude={"cursor"})
    serialized = json.dumps(
        {
            "type": f"{type(query).__module__}.{type(query).__qualname__}",
            "query": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode()).hexdigest()[:24]


def encode_cursor(item_id: uuid.UUID, fingerprint: str) -> str:
    payload = json.dumps(
        {"v": 1, "q": fingerprint, "id": str(item_id)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_cursor(cursor: str | None, fingerprint: str) -> uuid.UUID | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded: object = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(decoded, dict):
            raise ValueError
        payload = type_cast(dict[str, object], decoded)
        item_id = payload.get("id")
        if (
            payload.get("v") != 1
            or payload.get("q") != fingerprint
            or not isinstance(item_id, str)
        ):
            raise ValueError
        return uuid.UUID(item_id)
    except (TypeError, ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("cursor is malformed or belongs to a different query") from exc


def next_cursor[T](
    rows: list[T],
    limit: int,
    identifier: InstrumentedAttribute[uuid.UUID],
    fingerprint: str,
) -> tuple[list[T], str | None]:
    if limit == 0:
        return [], None
    has_more = len(rows) > limit
    page = rows[:limit]
    cursor = (
        encode_cursor(getattr(page[-1], identifier.key), fingerprint)
        if has_more and page
        else None
    )
    return page, cursor


def aggregate(values: Sequence[float], mode: ScoreAggregation) -> float:
    if not values:
        raise ValueError("cannot aggregate an empty score list")
    if mode == ScoreAggregation.min:
        return min(values)
    if mode == ScoreAggregation.max:
        return max(values)
    return sum(values) / len(values)


def aggregate_scores(
    scores: dict[uuid.UUID, list[float]], mode: ScoreAggregation
) -> dict[uuid.UUID, float]:
    return {item_id: aggregate(values, mode) for item_id, values in scores.items()}


def fuse_scores(
    text_scores: dict[uuid.UUID, float],
    face_scores: dict[uuid.UUID, float],
) -> list[tuple[uuid.UUID, float, float | None, float | None]]:
    text_rank = {
        item_id: rank
        for rank, (item_id, _) in enumerate(
            sorted(text_scores.items(), key=lambda item: (-item[1], item[0].int)),
            start=1,
        )
    }
    face_rank = {
        item_id: rank
        for rank, (item_id, _) in enumerate(
            sorted(face_scores.items(), key=lambda item: (-item[1], item[0].int)),
            start=1,
        )
    }
    fused: list[tuple[uuid.UUID, float, float | None, float | None]] = []
    for item_id in text_scores.keys() | face_scores.keys():
        score = 0.0
        if item_id in text_rank:
            score += 1.0 / (RRF_K + text_rank[item_id])
        if item_id in face_rank:
            score += 1.0 / (RRF_K + face_rank[item_id])
        fused.append(
            (item_id, score, text_scores.get(item_id), face_scores.get(item_id))
        )
    return sorted(fused, key=lambda item: (-item[1], item[0].int))


def search_page(
    ranked: list[tuple[uuid.UUID, float, float | None, float | None]],
    cursor: str | None,
    limit: int,
    fingerprint: str,
) -> tuple[list[tuple[uuid.UUID, float, float | None, float | None]], str | None]:
    start = 0
    cursor_id = decode_cursor(cursor, fingerprint)
    if cursor_id is not None:
        try:
            start = next(i for i, item in enumerate(ranked) if item[0] == cursor_id) + 1
        except StopIteration as exc:
            raise ValueError("cursor is not valid for this search") from exc
    if limit == 0:
        return [], None
    page = ranked[start : start + limit]
    has_more = start + len(page) < len(ranked)
    return (
        page,
        encode_cursor(page[-1][0], fingerprint) if has_more and page else None,
    )


def entity_response(entity: Entity) -> EntityResponse:
    if entity.kind is None or entity.name is None:
        raise ValueError(
            f"entity {entity.id} does not satisfy the persistence contract"
        )
    return EntityResponse(
        entity_id=entity.id,
        user_id=entity.user_id,
        entity_type=EntityType(entity.kind),
        name=entity.name,
        description=entity.description,
        short_description=entity.short_description,
        aliases=[alias.name for alias in entity.aliases],
        wikidata_id=entity.wikidata_id,
        nlcr_authority_id=entity.nlcr_authority_id,
    )


def source_response(source: Source) -> GenericSourceResponse:
    common: dict[str, Any] = {
        "source_id": source.id,
        "source_type": SourceKind(source.source_type),
        "url": source.url,
    }
    if isinstance(source, Page):
        common.update(
            library=source.library,
            document_id=source.document_id,
            page_id=source.page_id,
        )
    elif isinstance(source, Document):
        common.update(library=source.library, document_id=source.document_id)
    return GenericSourceResponse(**common)


def face_response(face: Face) -> FaceResponse:
    box = face.roi
    return FaceResponse(
        detection_id=face.id,
        identifier=face.identifier,
        source_id=face.source_id,
        entity_id=face.entity_id,
        user_id=face.user_id,
        confidence=face.confidence,
        bounding_box=BoundingBox(
            x=int(box["x"]),
            y=int(box["y"]),
            width=int(box["width"]),
            height=int(box["height"]),
        ),
        keypoints=[
            Keypoint(type=kind, x=point[0], y=point[1])
            for kind, point in zip(face.keypoint_types, face.keypoints, strict=True)
        ],
        embeddings=sorted(embedding.model_id for embedding in face.embeddings),
    )


def mention_response(mention: TextMention) -> TextMentionResponse:
    return TextMentionResponse(
        mention_id=mention.id,
        name=mention.mention,
        context=mention.context,
        entity_id=mention.entity_id,
        source_id=mention.source_id,
    )


def user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        display_name=user.display_name,
        is_active=user.is_active,
        external_subject=user.external_subject,
        external_issuer=user.external_issuer,
        email=user.email,
    )


def entity_filters(
    filter_: EntityListFilter | MissingType | None,
) -> list[ColumnElement[bool]]:
    filter_values = missing_to_none(filter_)
    if filter_values is None:
        return []
    filters: list[ColumnElement[bool]] = []
    entity_ids = missing_to_none(filter_values.entity_id)
    if entity_ids is not None:
        filters.append(Entity.id.in_(entity_ids))
    entity_types = missing_to_none(filter_values.entity_type)
    if entity_types is not None:
        filters.append(Entity.kind.in_([item.value for item in entity_types]))
    wikidata_ids = missing_to_none(filter_values.wikidata_id)
    if wikidata_ids is not None:
        filters.append(Entity.wikidata_id.in_(wikidata_ids))
    authority_ids = missing_to_none(filter_values.nlcr_authority_id)
    if authority_ids is not None:
        filters.append(Entity.nlcr_authority_id.in_(authority_ids))
    source_ids = missing_to_none(filter_values.source_id)
    if source_ids is not None:
        # Resolve the usually small set of linked entity IDs from the source
        # indexes first.  Expressing this as two OR-ed correlated EXISTS
        # predicates makes PostgreSQL scan entities in UUID order to satisfy
        # list pagination; a source with no linked entities consequently scans
        # the entire entity table before it can return an empty page.
        linked_entity_ids = union_all(
            select(ImageOccurrence.entity_id).where(
                ImageOccurrence.source_id.in_(source_ids),
                ImageOccurrence.entity_id.is_not(None),
            ),
            select(TextMention.entity_id).where(
                TextMention.source_id.in_(source_ids),
                TextMention.entity_id.is_not(None),
            ),
        )
        filters.append(Entity.id.in_(linked_entity_ids))
    detection_ids = missing_to_none(filter_values.detection_id)
    if detection_ids is not None:
        filters.append(
            exists().where(
                ImageOccurrence.entity_id == Entity.id,
                ImageOccurrence.id.in_(detection_ids),
            )
        )
    mention_ids = missing_to_none(filter_values.mention_id)
    if mention_ids is not None:
        filters.append(
            exists().where(
                TextMention.entity_id == Entity.id,
                TextMention.id.in_(mention_ids),
            )
        )
    has_mentions = missing_to_none(filter_values.has_mentions)
    if has_mentions is not None:
        predicate = exists().where(TextMention.entity_id == Entity.id)
        filters.append(predicate if has_mentions else ~predicate)
    has_detections = missing_to_none(filter_values.has_detections)
    if has_detections is not None:
        predicate = exists().where(ImageOccurrence.entity_id == Entity.id)
        filters.append(predicate if has_detections else ~predicate)
    return filters


def face_filters(
    filter_: FaceListFilter | None | MissingType,
) -> list[ColumnElement[bool]]:
    filter_values = missing_to_none(filter_)
    if filter_values is None:
        return []
    filters: list[ColumnElement[bool]] = []
    entity_ids = missing_to_none(filter_values.entity_id)
    if entity_ids is not None:
        filters.append(Face.entity_id.in_(entity_ids))
    source_ids = missing_to_none(filter_values.source_id)
    if source_ids is not None:
        filters.append(Face.source_id.in_(source_ids))
    detection_ids = missing_to_none(filter_values.detection_id)
    if detection_ids is not None:
        filters.append(Face.id.in_(detection_ids))
    return filters


def mention_filters(
    filter_: TextMentionListFilter | MissingType,
) -> list[ColumnElement[bool]]:
    filter_values = missing_to_none(filter_)
    if filter_values is None:
        return []
    filters: list[ColumnElement[bool]] = []
    entity_ids = missing_to_none(filter_values.entity_id)
    if entity_ids is not None:
        filters.append(TextMention.entity_id.in_(entity_ids))
    source_ids = missing_to_none(filter_values.source_id)
    if source_ids is not None:
        filters.append(TextMention.source_id.in_(source_ids))
    return filters


def user_filters(filter_: UserListFilter | MissingType) -> list[ColumnElement[bool]]:
    filter_values = missing_to_none(filter_)
    if filter_values is None:
        return []
    filters: list[ColumnElement[bool]] = []
    display_names = missing_to_none(filter_values.display_name)
    if display_names is not None:
        filters.append(User.display_name.in_(display_names))
    active_values = missing_to_none(filter_values.is_active)
    if active_values is not None:
        filters.append(User.is_active.in_(active_values))
    external_subjects = missing_to_none(filter_values.external_subject)
    if external_subjects is not None:
        filters.append(User.external_subject.in_(external_subjects))
    external_issuers = missing_to_none(filter_values.external_issuer)
    if external_issuers is not None:
        filters.append(User.external_issuer.in_(external_issuers))
    emails = missing_to_none(filter_values.email)
    if emails is not None:
        filters.append(User.email.in_(emails))
    return filters


def source_filters(
    filter_: GenericSourceListFilter | MissingType,
) -> list[ColumnElement[bool]]:
    filter_values = missing_to_none(filter_)
    if filter_values is None:
        return []
    filters: list[ColumnElement[bool]] = []
    source_types = missing_to_none(filter_values.source_type)
    if source_types is not None:
        filters.append(Source.source_type.in_([item.value for item in source_types]))
    urls = missing_to_none(filter_values.url)
    if urls is not None:
        filters.append(Source.url.in_(strings(urls)))
    source_ids = missing_to_none(filter_values.source_id)
    if source_ids is not None:
        filters.append(Source.id.in_(source_ids))
    libraries = missing_to_none(filter_values.library)
    if libraries is not None:
        filters.append(
            or_(Page.library.in_(libraries), Document.library.in_(libraries))
        )
    document_ids = missing_to_none(filter_values.document_id)
    if document_ids is not None:
        filters.append(
            or_(
                Page.document_id.in_(document_ids),
                Document.document_id.in_(document_ids),
            )
        )
    page_ids = missing_to_none(filter_values.page_id)
    if page_ids is not None:
        filters.append(Page.page_id.in_(page_ids))
    entity_ids = missing_to_none(filter_values.entity_id)
    if entity_ids is not None:
        filters.append(
            or_(
                exists().where(
                    ImageOccurrence.source_id == Source.id,
                    ImageOccurrence.entity_id.in_(entity_ids),
                ),
                exists().where(
                    TextMention.source_id == Source.id,
                    TextMention.entity_id.in_(entity_ids),
                ),
            )
        )
    detection_ids = missing_to_none(filter_values.detection_id)
    if detection_ids is not None:
        filters.append(
            exists().where(
                ImageOccurrence.source_id == Source.id,
                ImageOccurrence.id.in_(detection_ids),
            )
        )
    mention_ids = missing_to_none(filter_values.mention_id)
    if mention_ids is not None:
        filters.append(
            exists().where(
                TextMention.source_id == Source.id,
                TextMention.id.in_(mention_ids),
            )
        )
    return filters


@trace("postgres.face_model.load")
async def registered_face_model(session: AsyncSession, model_stub: str) -> FaceModel:
    model = await session.get(FaceModel, model_stub)
    if model is None:
        raise ValueError(f"face embedding model is not registered: {model_stub}")
    return model


@trace("postgres.face_embeddings.validate")
async def validate_face_embeddings(
    session: AsyncSession, embeddings: Iterable[FaceEmbeddingInput]
) -> None:
    items = list(embeddings)
    if not items:
        return
    stubs = {item.model_identifier for item in items}
    rows = await session.scalars(select(FaceModel).where(FaceModel.stub.in_(stubs)))
    registered = {model.stub: model for model in rows}
    missing = sorted(stubs - registered.keys())
    if missing:
        raise ValueError(f"face embedding model is not registered: {missing[0]}")
    for item in items:
        expected = registered[item.model_identifier].embedding_dim
        actual = len(item.vector)
        if actual != expected:
            message = f"face embedding model '{item.model_identifier}' requires "
            message += f"{expected} dimensions, got {actual}"
            raise ValueError(message)


@trace("postgres.face_search.load_reference_vectors")
async def reference_vectors(
    session: AsyncSession,
    face_ids: Sequence[uuid.UUID],
    model_stub: str,
) -> tuple[dict[uuid.UUID, list[float]], int]:
    model = await registered_face_model(session, model_stub)
    rows = await session.execute(
        select(
            FaceEmbeddingRow.face_id,
            FaceEmbeddingRow.embedding,
        ).where(
            FaceEmbeddingRow.face_id.in_(face_ids),
            FaceEmbeddingRow.model_id == model_stub,
        )
    )
    vectors = {row[0]: list(row[1]) for row in rows.all()}
    missing = [face_id for face_id in face_ids if face_id not in vectors]
    if missing:
        message = f"reference face does not exist or lacks embedding '{model_stub}': "
        message += str(missing[0])
        raise ValueError(message)
    return vectors, model.embedding_dim


def face_model_response(model: FaceModel) -> FaceModelResponse:
    return FaceModelResponse(
        model_stub=model.stub,
        embedding_dim=model.embedding_dim,
    )


__all__ = [
    "cosine_distance",
    "FaceQueryRepresentative",
    "representative_face_vectors",
    "query_vectors_cte",
    "entity_text_candidates",
    "configure_hnsw_search",
    "face_embedding_expression",
    "face_model_predicate",
    "face_target_select",
    "face_score_query",
    "search_face_scores",
    "strings",
    "commit",
    "ensure_ids",
    "validate_cursor",
    "cursor_fingerprint",
    "encode_cursor",
    "decode_cursor",
    "next_cursor",
    "aggregate",
    "fuse_scores",
    "search_page",
    "entity_response",
    "source_response",
    "face_response",
    "mention_response",
    "user_response",
    "entity_filters",
    "face_filters",
    "mention_filters",
    "user_filters",
    "source_filters",
    "registered_face_model",
    "validate_face_embeddings",
    "reference_vectors",
    "face_model_response",
]
