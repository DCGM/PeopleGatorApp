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

Text search uses PostgreSQL ``pg_trgm`` similarity. Face search uses pgvector
HNSW cosine search to generate a bounded candidate pool for each requested
reference embedding, then exactly rescores those candidates. Scores are
aggregated within each modality as requested by the schema, ranked with UUID
tie-breaking, and combined across modalities with reciprocal-rank fusion.

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
from collections.abc import Iterable, Sequence
from typing import Any, TypeVar, cast as type_cast

from pgvector.sqlalchemy import VECTOR
from pydantic import BaseModel
from sqlalchemy import (
    ColumnElement,
    cast,
    column,
    delete,
    exists,
    func,
    literal,
    or_,
    select,
    text,
    true,
    update,
    values,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload, with_polymorphic

from people_gator_api.persistence.contracts import (
    CreateResult,
    Database,
    EntityRepository,
    FaceModelRepository,
    FaceRepository,
    SourceRepository,
    TextMentionRepository,
    UserRepository,
)
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListFilter,
    EntityListRequest,
    EntityListResponse,
    EntityPatchBatchItem,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.schemas.enums import EntityType, ScoreAggregation, SourceKind
from people_gator_api.schemas.face_models import (
    FaceModelListResponse,
    FaceModelRegisterRequest,
    FaceModelResponse,
)
from people_gator_api.schemas.faces import (
    BoundingBox,
    FaceCreateRequest,
    FaceEmbedding as FaceEmbeddingInput,
    FaceListFilter,
    FaceListRequest,
    FaceListResponse,
    FacePatchBatchItem,
    FacePatchRequest,
    FaceResponse,
    Keypoint,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListFilter,
    TextMentionListRequest,
    TextMentionListResponse,
    TextMentionPatchBatchItem,
    TextMentionPatchRequest,
    TextMentionResponse,
)
from people_gator_api.schemas.missing import (
    MISSING,
    MissingType,
    is_missing,
    missing_to_none,
)
from people_gator_api.schemas.search import (
    RRF_K,
    FoundDocument,
    FoundEntity,
    FoundFace,
    FoundPage,
    SearchDocumentsRequest,
    SearchDocumentsResultListResponse,
    SearchEntitiesRequest,
    SearchEntitiesResultListResponse,
    SearchFacesRequest,
    SearchFacesResultListResponse,
    SearchPagesRequest,
    SearchPagesResultListResponse,
)
from people_gator_api.schemas.sources import (
    DocumentResponse,
    GenericSourceCreateRequest,
    GenericSourceListFilter,
    GenericSourceListRequest,
    GenericSourceListResponse,
    GenericSourceLookupRequest,
    GenericSourceResponse,
    PageResponse,
)
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListFilter,
    UserListRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.models import (
    Alias,
    Document,
    Entity,
    Face,
    FaceEmbedding as FaceEmbeddingRow,
    FaceModel,
    Image,
    ImageOccurrence,
    Page,
    Source,
    TextMention,
    User,
    face_embedding_hnsw_index,
)


ModelT = TypeVar("ModelT")

# HNSW returns a bounded face candidate pool for each reference vector. Exact
# per-entity/source/face scores are then recomputed within the union of those
# candidates so min/max/average aggregation keeps its existing meaning.
FACE_SEARCH_CANDIDATE_LIMIT = 200
HNSW_EF_SEARCH = 400


def _cosine_distance(embedding: object, query_vector: object) -> ColumnElement[float]:
    return type_cast(Any, embedding).cosine_distance(query_vector)


def _query_vectors_cte(vectors: dict[uuid.UUID, list[float]], embedding_dim: int):
    return (
        values(
            column("query_id", UUID(as_uuid=True)),
            column("embedding", VECTOR(embedding_dim)),
            name="query_vectors",
        )
        .data(list(vectors.items()))
        .cte("query_vectors")
    )


async def _configure_hnsw_search(session: AsyncSession) -> None:
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))


def _face_embedding_expression(embedding_dim: int) -> ColumnElement[list[float]]:
    return cast(FaceEmbeddingRow.embedding, VECTOR(embedding_dim))


def _face_model_predicate(model_stub: str) -> ColumnElement[bool]:
    return FaceEmbeddingRow.model_id == literal(model_stub, literal_execute=True)


def _strings(values: Iterable[object]) -> list[str]:
    return [str(value) for value in values]


async def _commit(session: AsyncSession, message: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError(message) from exc


async def _ensure_ids(
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


async def _validate_cursor(
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


def _cursor_fingerprint(query: BaseModel) -> str:
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


def _encode_cursor(item_id: uuid.UUID, fingerprint: str) -> str:
    payload = json.dumps(
        {"v": 1, "q": fingerprint, "id": str(item_id)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str | None, fingerprint: str) -> uuid.UUID | None:
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


def _next_cursor[T](
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
        _encode_cursor(getattr(page[-1], identifier.key), fingerprint)
        if has_more and page
        else None
    )
    return page, cursor


def _aggregate(values: Sequence[float], mode: ScoreAggregation) -> float:
    if not values:
        raise ValueError("cannot aggregate an empty score list")
    if mode == ScoreAggregation.min:
        return min(values)
    if mode == ScoreAggregation.max:
        return max(values)
    return sum(values) / len(values)


def _aggregate_scores(
    scores: dict[uuid.UUID, list[float]], mode: ScoreAggregation
) -> dict[uuid.UUID, float]:
    return {item_id: _aggregate(values, mode) for item_id, values in scores.items()}


def _fuse_scores(
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


def _search_page(
    ranked: list[tuple[uuid.UUID, float, float | None, float | None]],
    cursor: str | None,
    limit: int,
    fingerprint: str,
) -> tuple[list[tuple[uuid.UUID, float, float | None, float | None]], str | None]:
    start = 0
    cursor_id = _decode_cursor(cursor, fingerprint)
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
        _encode_cursor(page[-1][0], fingerprint) if has_more and page else None,
    )


def _entity_response(entity: Entity) -> EntityResponse:
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


def _source_response(source: Source) -> GenericSourceResponse:
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


def _face_response(face: Face) -> FaceResponse:
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
    )


def _mention_response(mention: TextMention) -> TextMentionResponse:
    return TextMentionResponse(
        mention_id=mention.id,
        name=mention.mention,
        context=mention.context,
        entity_id=mention.entity_id,
        source_id=mention.source_id,
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        display_name=user.display_name,
        is_active=user.is_active,
        external_subject=user.external_subject,
        external_issuer=user.external_issuer,
        email=user.email,
    )


def _entity_filters(
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
        filters.append(
            or_(
                exists().where(
                    ImageOccurrence.entity_id == Entity.id,
                    ImageOccurrence.source_id.in_(source_ids),
                ),
                exists().where(
                    TextMention.entity_id == Entity.id,
                    TextMention.source_id.in_(source_ids),
                ),
            )
        )
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


def _face_filters(
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


def _mention_filters(
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


def _user_filters(filter_: UserListFilter | MissingType) -> list[ColumnElement[bool]]:
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


def _source_filters(
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
        filters.append(Source.url.in_(_strings(urls)))
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


async def _registered_face_model(session: AsyncSession, model_stub: str) -> FaceModel:
    model = await session.get(FaceModel, model_stub)
    if model is None:
        raise ValueError(f"face embedding model is not registered: {model_stub}")
    return model


async def _validate_face_embeddings(
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


async def _reference_vectors(
    session: AsyncSession,
    face_ids: Sequence[uuid.UUID],
    model_stub: str,
) -> tuple[dict[uuid.UUID, list[float]], int]:
    model = await _registered_face_model(session, model_stub)
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


def _face_model_response(model: FaceModel) -> FaceModelResponse:
    return FaceModelResponse(
        model_stub=model.stub,
        embedding_dim=model.embedding_dim,
    )


class PostgresFaceModelRepository(FaceModelRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def register(self, payload: FaceModelRegisterRequest) -> FaceModelResponse:
        model = await self._session.get(FaceModel, payload.model_stub)
        if model is None:
            model = FaceModel(
                stub=payload.model_stub,
                embedding_dim=payload.embedding_dim,
            )
            self._session.add(model)
            try:
                await self._session.flush()
            except IntegrityError as exc:
                await self._session.rollback()
                model = await self._session.get(FaceModel, payload.model_stub)
                if model is None:
                    raise ValueError("face model registration conflict") from exc
                if model.embedding_dim != payload.embedding_dim:
                    message = f"face model '{payload.model_stub}' is already "
                    message += f"registered with dimension {model.embedding_dim}"
                    raise ValueError(message) from exc
        elif model.embedding_dim != payload.embedding_dim:
            message = f"face model '{payload.model_stub}' is already registered with "
            message += f"dimension {model.embedding_dim}"
            raise ValueError(message)

        index = face_embedding_hnsw_index(model.stub, model.embedding_dim)
        try:
            connection = await self._session.connection()
            await connection.run_sync(
                lambda sync_connection: index.create(
                    sync_connection,
                    checkfirst=True,
                )
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        return _face_model_response(model)

    async def list(self) -> FaceModelListResponse:
        models = await self._session.scalars(select(FaceModel).order_by(FaceModel.stub))
        return FaceModelListResponse(
            items=[_face_model_response(model) for model in models]
        )


class PostgresEntityRepository(EntityRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Entity]:
        if not ids:
            return {}
        rows = await self._session.scalars(
            select(Entity)
            .where(Entity.id.in_(ids))
            .options(selectinload(Entity.aliases))
        )
        return {row.id: row for row in rows.unique().all()}

    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        entity = (await self._load_many([entity_id])).get(entity_id)
        return _entity_response(entity) if entity is not None else None

    async def list(self, query: EntityListRequest) -> EntityListResponse:
        filters = _entity_filters(query.filter_)
        fingerprint = _cursor_fingerprint(query)
        cursor_id = _decode_cursor(query.cursor, fingerprint)
        await _validate_cursor(self._session, Entity, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(
                    select(func.count(Entity.id)).where(*filters)
                )
                or 0
            )
        if query.limit == 0:
            return EntityListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(Entity.id > cursor_id)
        rows = list(
            (
                await self._session.scalars(
                    select(Entity)
                    .where(*page_filters)
                    .options(selectinload(Entity.aliases))
                    .order_by(Entity.id)
                    .limit(query.limit + 1)
                )
            )
            .unique()
            .all()
        )
        page, cursor = _next_cursor(rows, query.limit, Entity.id, fingerprint)
        return EntityListResponse(
            items=[_entity_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(payload: EntityCreateRequest, user_id: uuid.UUID) -> Entity:
        entity = Entity(
            user_id=user_id,
            kind=payload.entity_type.value,
            name=payload.name,
            description=missing_to_none(payload.description),
            short_description=missing_to_none(payload.short_description),
            wikidata_id=missing_to_none(payload.wikidata_id),
            nlcr_authority_id=missing_to_none(payload.nlcr_authority_id),
        )
        entity.aliases = [
            Alias(name=value) for value in missing_to_none(payload.aliases) or []
        ]
        return entity

    async def create(
        self, payload: EntityCreateRequest, context: GenericActor
    ) -> EntityResponse:
        return (await self.create_batch([payload], context))[0]

    async def create_batch(
        self, payloads: Sequence[EntityCreateRequest], context: GenericActor
    ) -> list[EntityResponse]:
        if not payloads:
            return []
        await _ensure_ids(self._session, User, [context.user_id], "actor user")
        entities = [self._new(payload, context.user_id) for payload in payloads]
        self._session.add_all(entities)
        await _commit(self._session, "entity create violates a persistence constraint")
        return [_entity_response(entity) for entity in entities]

    @staticmethod
    def _apply(entity: Entity, payload: EntityPatchRequest) -> None:
        if not is_missing(payload.name):
            entity.name = payload.name
        if not is_missing(payload.description):
            entity.description = payload.description
        if not is_missing(payload.short_description):
            entity.short_description = payload.short_description
        if not is_missing(payload.wikidata_id):
            entity.wikidata_id = payload.wikidata_id
        if not is_missing(payload.nlcr_authority_id):
            entity.nlcr_authority_id = payload.nlcr_authority_id
        if not is_missing(payload.aliases):
            entity.aliases = [Alias(name=value) for value in payload.aliases]

    async def patch(
        self,
        entity_id: uuid.UUID,
        payload: EntityPatchRequest,
        context: GenericActor,
    ) -> EntityResponse | None:
        command = EntityPatchBatchItem(entity_id=entity_id, **payload.model_dump())
        return (await self.patch_batch([command], context))[0]

    async def patch_batch(
        self,
        commands: Sequence[EntityPatchBatchItem],
        context: GenericActor,
    ) -> list[EntityResponse | None]:
        ids = [command.entity_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("entity patch batch requires unique object IDs")
        if not commands:
            return []
        await _ensure_ids(self._session, User, [context.user_id], "actor user")
        entities = await self._load_many(ids)
        for command in commands:
            entity = entities.get(command.entity_id)
            if entity is not None:
                self._apply(entity, command)
        await _commit(self._session, "entity patch violates a persistence constraint")
        return [
            _entity_response(entity) if (entity := entities.get(item_id)) else None
            for item_id in ids
        ]

    async def delete(self, entity_id: uuid.UUID) -> bool:
        result = await self.delete_batch([entity_id])
        return result.deleted_count == 1

    async def delete_batch(
        self, entity_ids: Sequence[uuid.UUID]
    ) -> EntityDeleteManyResponse:
        unique = list(dict.fromkeys(entity_ids))
        if not unique:
            return EntityDeleteManyResponse(deleted_count=0)
        await self._session.execute(
            update(ImageOccurrence)
            .where(ImageOccurrence.entity_id.in_(unique))
            .values(entity_id=None)
        )
        await self._session.execute(
            update(TextMention)
            .where(TextMention.entity_id.in_(unique))
            .values(entity_id=None)
        )
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(Entity).where(Entity.id.in_(unique))),
        )
        await _commit(self._session, "entity delete failed")
        return EntityDeleteManyResponse(deleted_count=int(result.rowcount or 0))

    async def delete_many(
        self, selector: EntityDeleteManyRequest
    ) -> EntityDeleteManyResponse:
        filters = _entity_filters(selector.filter)
        ids = list(
            await self._session.scalars(
                select(Entity.id)
                .where(*filters)
                .order_by(Entity.id)
                .limit(selector.limit)
            )
        )
        return await self.delete_batch(ids)

    async def _text_scores(
        self, query: SearchEntitiesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        terms = missing_to_none(query.query.text)
        if terms is None:
            return {}
        collected: dict[uuid.UUID, list[float]] = {}
        for term in terms:
            score = func.greatest(
                func.similarity(func.coalesce(Entity.name, ""), term),
                func.similarity(func.coalesce(Entity.description, ""), term),
                func.similarity(func.coalesce(Entity.short_description, ""), term),
                func.coalesce(func.max(func.similarity(Alias.name, term)), 0.0),
            )
            rows = await self._session.execute(
                select(Entity.id, score.label("score"))
                .outerjoin(Alias, Alias.entity_id == Entity.id)
                .where(*filters)
                .group_by(Entity.id)
            )
            for item_id, raw_score in rows.all():
                value = float(raw_score)
                if value > 0:
                    collected.setdefault(item_id, []).append(value)
        return _aggregate_scores(collected, query.query.score_aggregation)

    async def _face_scores(
        self, query: SearchEntitiesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        face_ids = missing_to_none(query.query.face_id)
        if face_ids is None:
            return {}
        model_stub = query.query.face_embedding_model
        vectors, embedding_dim = await _reference_vectors(
            self._session, face_ids, model_stub
        )
        embedding = _face_embedding_expression(embedding_dim)
        model_filter = _face_model_predicate(model_stub)
        query_vectors = _query_vectors_cte(vectors, embedding_dim)
        candidate_distance = _cosine_distance(embedding, query_vectors.c.embedding)
        nearest_faces = (
            select(Entity.id.label("candidate_id"))
            .select_from(FaceEmbeddingRow)
            .join(Face, Face.id == FaceEmbeddingRow.face_id)
            .join(Entity, Entity.id == Face.entity_id)
            .where(*filters, model_filter)
            .order_by(candidate_distance)
            .limit(FACE_SEARCH_CANDIDATE_LIMIT)
        )
        if query.query.exclude_reference_face_id:
            nearest_faces = nearest_faces.where(Face.id.not_in(face_ids))
        nearest_faces = nearest_faces.lateral("nearest_faces")
        await _configure_hnsw_search(self._session)
        candidate_ids = list(
            dict.fromkeys(
                await self._session.scalars(
                    select(nearest_faces.c.candidate_id)
                    .select_from(query_vectors.join(nearest_faces, true()))
                    .distinct()
                )
            )
        )
        if not candidate_ids:
            return {}

        collected: dict[uuid.UUID, list[float]] = {}
        for vector in vectors.values():
            distance = _cosine_distance(embedding, vector)
            statement = (
                select(Entity.id, func.max(1.0 - distance).label("score"))
                .join(Face, Face.entity_id == Entity.id)
                .join(FaceEmbeddingRow, FaceEmbeddingRow.face_id == Face.id)
                .where(
                    *filters,
                    Entity.id.in_(candidate_ids),
                    model_filter,
                )
                .group_by(Entity.id)
            )
            if query.query.exclude_reference_face_id:
                statement = statement.where(Face.id.not_in(face_ids))
            for item_id, raw_score in (await self._session.execute(statement)).all():
                collected.setdefault(item_id, []).append(float(raw_score))
        return _aggregate_scores(collected, query.query.score_aggregation)

    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        filters = _entity_filters(query.filter_)
        ranked = _fuse_scores(
            await self._text_scores(query, filters),
            await self._face_scores(query, filters),
        )
        page, cursor = _search_page(
            ranked,
            query.cursor,
            query.limit,
            _cursor_fingerprint(query),
        )
        entities = await self._load_many([item[0] for item in page])
        items = [
            FoundEntity(
                **_entity_response(entities[item_id]).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchEntitiesResultListResponse(
            items=items,
            limit=query.limit,
            total_count=len(ranked) if query.return_total_count else None,
            cursor=cursor,
        )


class PostgresSourceRepository(SourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session
        self._source = with_polymorphic(Source, [Document, Page, Image])

    async def lookup(
        self, lookup: GenericSourceLookupRequest
    ) -> GenericSourceResponse | None:
        statement = select(self._source)
        source_id = missing_to_none(lookup.source_id)
        source_type = missing_to_none(lookup.source_type)
        if source_id is not None:
            statement = statement.where(Source.id == source_id)
        elif source_type == SourceKind.image:
            statement = statement.where(
                Source.source_type == SourceKind.image.value,
                Source.url == str(lookup.url),
            )
        elif source_type == SourceKind.document:
            statement = statement.where(
                Source.source_type == SourceKind.document.value,
                Document.library == lookup.library,
                Document.document_id == lookup.document_id,
            )
        elif source_type == SourceKind.page:
            statement = statement.where(
                Source.source_type == SourceKind.page.value,
                Page.library == lookup.library,
                Page.document_id == lookup.document_id,
                Page.page_id == lookup.page_id,
            )
        else:
            raise ValueError("invalid source lookup")
        source = await self._session.scalar(statement.limit(1))
        return _source_response(source) if source is not None else None

    async def list(self, query: GenericSourceListRequest) -> GenericSourceListResponse:
        filters = _source_filters(query.filter_)
        fingerprint = _cursor_fingerprint(query)
        cursor_id = _decode_cursor(query.cursor, fingerprint)
        await _validate_cursor(self._session, Source, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(
                    select(func.count(Source.id))
                    .select_from(self._source)
                    .where(*filters)
                )
                or 0
            )
        if query.limit == 0:
            return GenericSourceListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(Source.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(self._source)
                .where(*page_filters)
                .order_by(Source.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = _next_cursor(rows, query.limit, Source.id, fingerprint)
        return GenericSourceListResponse(
            items=[_source_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(spec: GenericSourceCreateRequest) -> Source:
        common = {"url": str(spec.url)}
        if spec.source_type == SourceKind.page:
            assert isinstance(spec.library, str)
            assert isinstance(spec.document_id, uuid.UUID)
            assert isinstance(spec.page_id, uuid.UUID)
            return Page(
                **common,
                library=spec.library,
                document_id=spec.document_id,
                page_id=spec.page_id,
            )
        if spec.source_type == SourceKind.document:
            assert isinstance(spec.library, str)
            assert isinstance(spec.document_id, uuid.UUID)
            return Document(
                **common,
                library=spec.library,
                document_id=spec.document_id,
            )
        return Image(**common)

    async def _by_url(self, url: str) -> Source | None:
        return await self._session.scalar(
            select(self._source).where(Source.url == url).limit(1)
        )

    async def get_or_create(
        self, spec: GenericSourceCreateRequest
    ) -> tuple[GenericSourceResponse, CreateResult]:
        key = str(spec.url)
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0)))
        )
        by_identity = await self.lookup(
            GenericSourceLookupRequest(
                source_type=spec.source_type,
                url=spec.url if spec.source_type == SourceKind.image else MISSING,
                library=spec.library,
                document_id=spec.document_id,
                page_id=spec.page_id,
            )
        )
        by_url = await self._by_url(key)
        if by_identity is not None:
            if str(by_identity.url) != key:
                raise ValueError(
                    "source identity is already registered with another URL"
                )
            if by_url is not None and by_url.id != by_identity.source_id:
                raise ValueError("source URL conflicts with another source identity")
            return by_identity, CreateResult.EXISTING
        if by_url is not None:
            raise ValueError("source URL is already registered with another identity")
        source = self._new(spec)
        self._session.add(source)
        await _commit(self._session, "source create violates a persistence constraint")
        return _source_response(source), CreateResult.CREATED

    async def get_or_create_batch(
        self, specs: Sequence[GenericSourceCreateRequest]
    ) -> list[tuple[GenericSourceResponse, CreateResult]]:
        results: list[tuple[GenericSourceResponse, CreateResult]] = []
        for spec in specs:
            results.append(await self.get_or_create(spec))
        return results

    async def delete(self, source_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([source_id]))

    async def delete_batch(self, source_ids: Sequence[uuid.UUID]) -> int:
        unique = list(dict.fromkeys(source_ids))
        if not unique:
            return 0
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(Source).where(Source.id.in_(unique))),
        )
        await _commit(self._session, "source delete failed")
        return int(result.rowcount or 0)

    async def _source_text_scores(
        self,
        model: type[Page] | type[Document],
        query: SearchPagesRequest | SearchDocumentsRequest,
        filters: Sequence[ColumnElement[bool]],
    ) -> dict[uuid.UUID, float]:
        terms = missing_to_none(query.query.text)
        if terms is None:
            return {}
        collected: dict[uuid.UUID, list[float]] = {}
        for term in terms:
            score = func.greatest(
                func.similarity(Source.url, term),
                func.similarity(model.library, term),
            )
            rows = await self._session.execute(
                select(model.id, score.label("score")).where(*filters)
            )
            for item_id, raw_score in rows.all():
                value = float(raw_score)
                if value > 0:
                    collected.setdefault(item_id, []).append(value)
        return _aggregate_scores(collected, query.query.score_aggregation)

    async def _source_face_scores(
        self,
        model: type[Page] | type[Document],
        query: SearchPagesRequest | SearchDocumentsRequest,
        filters: Sequence[ColumnElement[bool]],
    ) -> dict[uuid.UUID, float]:
        face_ids = missing_to_none(query.query.face_id)
        if face_ids is None:
            return {}
        model_stub = query.query.face_embedding_model
        vectors, embedding_dim = await _reference_vectors(
            self._session, face_ids, model_stub
        )
        embedding = _face_embedding_expression(embedding_dim)
        model_filter = _face_model_predicate(model_stub)
        query_vectors = _query_vectors_cte(vectors, embedding_dim)
        candidate_distance = _cosine_distance(embedding, query_vectors.c.embedding)
        nearest_faces = (
            select(model.id.label("candidate_id"))
            .select_from(FaceEmbeddingRow)
            .join(Face, Face.id == FaceEmbeddingRow.face_id)
            .join(model, Face.source_id == model.id)
            .where(*filters, model_filter)
            .order_by(candidate_distance)
            .limit(FACE_SEARCH_CANDIDATE_LIMIT)
        )
        if query.query.exclude_reference_face_id:
            nearest_faces = nearest_faces.where(Face.id.not_in(face_ids))
        nearest_faces = nearest_faces.lateral("nearest_faces")
        await _configure_hnsw_search(self._session)
        candidate_ids = list(
            dict.fromkeys(
                await self._session.scalars(
                    select(nearest_faces.c.candidate_id)
                    .select_from(query_vectors.join(nearest_faces, true()))
                    .distinct()
                )
            )
        )
        if not candidate_ids:
            return {}

        collected: dict[uuid.UUID, list[float]] = {}
        for vector in vectors.values():
            distance = _cosine_distance(embedding, vector)
            statement = (
                select(model.id, func.max(1.0 - distance).label("score"))
                .join(Face, Face.source_id == model.id)
                .join(FaceEmbeddingRow, FaceEmbeddingRow.face_id == Face.id)
                .where(
                    *filters,
                    model.id.in_(candidate_ids),
                    model_filter,
                )
                .group_by(model.id)
            )
            if query.query.exclude_reference_face_id:
                statement = statement.where(Face.id.not_in(face_ids))
            for item_id, raw_score in (await self._session.execute(statement)).all():
                collected.setdefault(item_id, []).append(float(raw_score))
        return _aggregate_scores(collected, query.query.score_aggregation)

    async def _search_sources(
        self,
        model: type[Page] | type[Document],
        query: SearchPagesRequest | SearchDocumentsRequest,
        filters: Sequence[ColumnElement[bool]],
    ) -> tuple[
        list[tuple[uuid.UUID, float, float | None, float | None]],
        str | None,
        int,
    ]:
        ranked = _fuse_scores(
            await self._source_text_scores(model, query, filters),
            await self._source_face_scores(model, query, filters),
        )
        page, cursor = _search_page(
            ranked,
            query.cursor,
            query.limit,
            _cursor_fingerprint(query),
        )
        return page, cursor, len(ranked)

    async def search_pages(
        self, query: SearchPagesRequest
    ) -> SearchPagesResultListResponse:
        generic_filter = (
            query.filter_.to_generic() if query.filter_ is not None else MISSING
        )
        filters = _source_filters(generic_filter)
        filters.append(Source.source_type == SourceKind.page.value)
        page, cursor, total = await self._search_sources(Page, query, filters)
        rows = await self._session.scalars(
            select(Page).where(Page.id.in_([x[0] for x in page]))
        )
        by_id = {row.id: row for row in rows.all()}
        items = [
            FoundPage(
                **PageResponse.from_generic(
                    _source_response(by_id[item_id])
                ).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchPagesResultListResponse(
            items=items,
            limit=query.limit,
            total_count=total if query.return_total_count else None,
            cursor=cursor,
        )

    async def search_documents(
        self, query: SearchDocumentsRequest
    ) -> SearchDocumentsResultListResponse:
        generic_filter = (
            query.filter_.to_generic() if query.filter_ is not None else MISSING
        )
        filters = _source_filters(generic_filter)
        filters.append(Source.source_type == SourceKind.document.value)
        page, cursor, total = await self._search_sources(Document, query, filters)
        rows = await self._session.scalars(
            select(Document).where(Document.id.in_([x[0] for x in page]))
        )
        by_id = {row.id: row for row in rows.all()}
        items = [
            FoundDocument(
                **DocumentResponse.from_generic(
                    _source_response(by_id[item_id])
                ).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchDocumentsResultListResponse(
            items=items,
            limit=query.limit,
            total_count=total if query.return_total_count else None,
            cursor=cursor,
        )


class PostgresFaceRepository(FaceRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Face]:
        if not ids:
            return {}
        rows = await self._session.scalars(
            select(Face).where(Face.id.in_(ids)).options(selectinload(Face.embeddings))
        )
        return {row.id: row for row in rows.unique().all()}

    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None:
        face = (await self._load_many([detection_id])).get(detection_id)
        return _face_response(face) if face is not None else None

    async def list(self, query: FaceListRequest) -> FaceListResponse:
        filters = _face_filters(query.filter_)
        fingerprint = _cursor_fingerprint(query)
        cursor_id = _decode_cursor(query.cursor, fingerprint)
        await _validate_cursor(self._session, Face, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(select(func.count(Face.id)).where(*filters))
                or 0
            )
        if query.limit == 0:
            return FaceListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(Face.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(Face)
                .where(*page_filters)
                .order_by(Face.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = _next_cursor(rows, query.limit, Face.id, fingerprint)
        return FaceListResponse(
            items=[_face_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(payload: FaceCreateRequest, context: GenericActor) -> Face:
        embeddings = missing_to_none(payload.embeddings)
        face = Face(
            source_id=payload.source_id,
            entity_id=missing_to_none(payload.entity_id),
            user_id=context.user_id,
            identifier=missing_to_none(payload.identifier),
            confidence=payload.confidence,
            roi=payload.bounding_box.model_dump(),
            keypoints=[[item.x, item.y] for item in payload.keypoints],
            keypoint_types=[item.type for item in payload.keypoints],
        )
        if embeddings:
            face.embeddings = [
                FaceEmbeddingRow(
                    model_id=value.model_identifier,
                    embedding=list(value.vector),
                )
                for value in embeddings
            ]
        return face

    async def create(
        self, payload: FaceCreateRequest, context: GenericActor
    ) -> FaceResponse:
        return (await self.create_batch([payload], context))[0]

    async def create_batch(
        self, payloads: Sequence[FaceCreateRequest], context: GenericActor
    ) -> list[FaceResponse]:
        if not payloads:
            return []
        await _ensure_ids(self._session, User, [context.user_id], "actor user")
        await _ensure_ids(
            self._session, Source, [item.source_id for item in payloads], "face source"
        )
        entity_ids = [
            entity_id
            for item in payloads
            if (entity_id := missing_to_none(item.entity_id)) is not None
        ]
        await _ensure_ids(
            self._session,
            Entity,
            entity_ids,
            "face entity",
        )
        await _validate_face_embeddings(
            self._session,
            (
                embedding
                for payload in payloads
                for embedding in (missing_to_none(payload.embeddings) or [])
            ),
        )
        faces = [self._new(payload, context) for payload in payloads]
        self._session.add_all(faces)
        await _commit(self._session, "face create violates a persistence constraint")
        return [_face_response(face) for face in faces]

    @staticmethod
    def _apply_embeddings(face: Face, payload: FacePatchRequest) -> None:
        embeddings = missing_to_none(payload.embeddings)
        if not embeddings:
            return
        existing = {embedding.model_id: embedding for embedding in face.embeddings}
        for value in embeddings:
            embedding = existing.get(value.model_identifier)
            if embedding is None:
                face.embeddings.append(
                    FaceEmbeddingRow(
                        model_id=value.model_identifier,
                        embedding=list(value.vector),
                    )
                )
            else:
                embedding.embedding = list(value.vector)

    async def patch(
        self,
        detection_id: uuid.UUID,
        payload: FacePatchRequest,
        context: GenericActor,
    ) -> FaceResponse | None:
        command = FacePatchBatchItem(detection_id=detection_id, **payload.model_dump())
        return (await self.patch_batch([command], context))[0]

    async def patch_batch(
        self,
        commands: Sequence[FacePatchBatchItem],
        context: GenericActor,
    ) -> list[FaceResponse | None]:
        ids = [command.detection_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("face patch batch requires unique object IDs")
        if not commands:
            return []
        await _ensure_ids(self._session, User, [context.user_id], "actor user")
        entity_ids = [
            entity_id
            for command in commands
            if not is_missing(command.entity_id)
            and (entity_id := command.entity_id) is not None
        ]
        await _ensure_ids(
            self._session,
            Entity,
            entity_ids,
            "face entity",
        )
        await _validate_face_embeddings(
            self._session,
            (
                embedding
                for command in commands
                for embedding in (missing_to_none(command.embeddings) or [])
            ),
        )
        faces = await self._load_many(ids)
        for command in commands:
            face = faces.get(command.detection_id)
            if face is None:
                continue
            if not is_missing(command.entity_id):
                face.entity_id = command.entity_id
            self._apply_embeddings(face, command)
        await _commit(self._session, "face patch violates a persistence constraint")
        return [
            _face_response(face) if (face := faces.get(item_id)) else None
            for item_id in ids
        ]

    async def delete(self, detection_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([detection_id]))

    async def delete_batch(self, detection_ids: Sequence[uuid.UUID]) -> int:
        unique = list(dict.fromkeys(detection_ids))
        if not unique:
            return 0
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(
                delete(ImageOccurrence).where(ImageOccurrence.id.in_(unique))
            ),
        )
        await _commit(self._session, "face delete failed")
        return int(result.rowcount or 0)

    async def _text_scores(
        self, query: SearchFacesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        terms = missing_to_none(query.query.text)
        if terms is None:
            return {}
        collected: dict[uuid.UUID, list[float]] = {}
        for term in terms:
            score = func.greatest(
                func.similarity(func.coalesce(Face.identifier, ""), term),
                func.similarity(func.coalesce(Entity.name, ""), term),
                func.coalesce(func.max(func.similarity(Alias.name, term)), 0.0),
            )
            rows = await self._session.execute(
                select(Face.id, score.label("score"))
                .outerjoin(Entity, Entity.id == Face.entity_id)
                .outerjoin(Alias, Alias.entity_id == Entity.id)
                .where(*filters)
                .group_by(Face.id, Entity.id)
            )
            for item_id, raw_score in rows.all():
                value = float(raw_score)
                if value > 0:
                    collected.setdefault(item_id, []).append(value)
        return _aggregate_scores(collected, query.query.score_aggregation)

    async def _face_scores(
        self, query: SearchFacesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        face_ids = missing_to_none(query.query.face_id)
        if face_ids is None:
            return {}
        model_stub = query.query.face_embedding_model
        vectors, embedding_dim = await _reference_vectors(
            self._session, face_ids, model_stub
        )
        embedding = _face_embedding_expression(embedding_dim)
        model_filter = _face_model_predicate(model_stub)
        query_vectors = _query_vectors_cte(vectors, embedding_dim)
        candidate_distance = _cosine_distance(embedding, query_vectors.c.embedding)
        nearest_faces = (
            select(Face.id.label("candidate_id"))
            .select_from(FaceEmbeddingRow)
            .join(Face, Face.id == FaceEmbeddingRow.face_id)
            .where(*filters, model_filter)
            .order_by(candidate_distance)
            .limit(FACE_SEARCH_CANDIDATE_LIMIT)
        )
        if query.query.exclude_reference_face_id:
            nearest_faces = nearest_faces.where(Face.id.not_in(face_ids))
        nearest_faces = nearest_faces.lateral("nearest_faces")
        await _configure_hnsw_search(self._session)
        candidate_ids = list(
            dict.fromkeys(
                await self._session.scalars(
                    select(nearest_faces.c.candidate_id)
                    .select_from(query_vectors.join(nearest_faces, true()))
                    .distinct()
                )
            )
        )
        if not candidate_ids:
            return {}

        collected: dict[uuid.UUID, list[float]] = {}
        for vector in vectors.values():
            distance = _cosine_distance(embedding, vector)
            statement = (
                select(Face.id, (1.0 - distance).label("score"))
                .join(FaceEmbeddingRow, FaceEmbeddingRow.face_id == Face.id)
                .where(
                    *filters,
                    Face.id.in_(candidate_ids),
                    model_filter,
                )
            )
            if query.query.exclude_reference_face_id:
                statement = statement.where(Face.id.not_in(face_ids))
            for item_id, raw_score in (await self._session.execute(statement)).all():
                collected.setdefault(item_id, []).append(float(raw_score))
        return _aggregate_scores(collected, query.query.score_aggregation)

    async def search(self, query: SearchFacesRequest) -> SearchFacesResultListResponse:
        filters = _face_filters(query.filter_)
        ranked = _fuse_scores(
            await self._text_scores(query, filters),
            await self._face_scores(query, filters),
        )
        page, cursor = _search_page(
            ranked,
            query.cursor,
            query.limit,
            _cursor_fingerprint(query),
        )
        faces = await self._load_many([item[0] for item in page])
        items = [
            FoundFace(
                **_face_response(faces[item_id]).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchFacesResultListResponse(
            items=items,
            limit=query.limit,
            total_count=len(ranked) if query.return_total_count else None,
            cursor=cursor,
        )


class PostgresTextMentionRepository(TextMentionRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(
        self, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, TextMention]:
        if not ids:
            return {}
        rows = await self._session.scalars(
            select(TextMention).where(TextMention.id.in_(ids))
        )
        return {row.id: row for row in rows.all()}

    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None:
        mention = (await self._load_many([mention_id])).get(mention_id)
        return _mention_response(mention) if mention is not None else None

    async def list(self, query: TextMentionListRequest) -> TextMentionListResponse:
        filters = _mention_filters(query.filter_)
        fingerprint = _cursor_fingerprint(query)
        cursor_id = _decode_cursor(query.cursor, fingerprint)
        await _validate_cursor(self._session, TextMention, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(
                    select(func.count(TextMention.id)).where(*filters)
                )
                or 0
            )
        if query.limit == 0:
            return TextMentionListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(TextMention.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(TextMention)
                .where(*page_filters)
                .order_by(TextMention.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = _next_cursor(
            rows,
            query.limit,
            TextMention.id,
            fingerprint,
        )
        return TextMentionListResponse(
            items=[_mention_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(payload: TextMentionCreateRequest) -> TextMention:
        return TextMention(
            mention=payload.name,
            context=payload.context,
            entity_id=payload.entity_id,
            source_id=payload.source_id,
        )

    async def create(
        self, payload: TextMentionCreateRequest, context: GenericActor
    ) -> TextMentionResponse:
        return (await self.create_batch([payload], context))[0]

    async def create_batch(
        self,
        payloads: Sequence[TextMentionCreateRequest],
        context: GenericActor,
    ) -> list[TextMentionResponse]:
        del context
        if not payloads:
            return []
        await _ensure_ids(
            self._session,
            Source,
            [item.source_id for item in payloads],
            "mention source",
        )
        await _ensure_ids(
            self._session,
            Entity,
            [item.entity_id for item in payloads],
            "mention entity",
        )
        mentions = [self._new(payload) for payload in payloads]
        self._session.add_all(mentions)
        await _commit(self._session, "mention create violates a persistence constraint")
        return [_mention_response(mention) for mention in mentions]

    async def patch(
        self,
        mention_id: uuid.UUID,
        payload: TextMentionPatchRequest,
        context: GenericActor,
    ) -> TextMentionResponse | None:
        return (
            await self.patch_batch(
                [
                    TextMentionPatchBatchItem(
                        mention_id=mention_id, **payload.model_dump()
                    )
                ],
                context,
            )
        )[0]

    async def patch_batch(
        self,
        commands: Sequence[TextMentionPatchBatchItem],
        context: GenericActor,
    ) -> list[TextMentionResponse | None]:
        del context
        ids = [command.mention_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("text mention patch batch requires unique object IDs")
        if not commands:
            return []
        await _ensure_ids(
            self._session,
            Entity,
            [
                command.entity_id
                for command in commands
                if command.entity_id is not None
            ],
            "mention entity",
        )
        mentions = await self._load_many(ids)
        for command in commands:
            mention = mentions.get(command.mention_id)
            if mention is not None:
                mention.entity_id = command.entity_id
        await _commit(self._session, "mention patch violates a persistence constraint")
        return [
            _mention_response(mention) if (mention := mentions.get(item_id)) else None
            for item_id in ids
        ]

    async def delete(self, mention_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([mention_id]))

    async def delete_batch(self, mention_ids: Sequence[uuid.UUID]) -> int:
        unique = list(dict.fromkeys(mention_ids))
        if not unique:
            return 0
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(
                delete(TextMention).where(TextMention.id.in_(unique))
            ),
        )
        await _commit(self._session, "mention delete failed")
        return int(result.rowcount or 0)


class PostgresUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def get(self, user_id: uuid.UUID) -> UserResponse | None:
        user = await self._session.get(User, user_id)
        return _user_response(user) if user is not None else None

    async def list(self, query: UserListRequest) -> UserListResponse:
        filters = _user_filters(query.filter_)
        fingerprint = _cursor_fingerprint(query)
        cursor_id = _decode_cursor(query.cursor, fingerprint)
        await _validate_cursor(self._session, User, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(select(func.count(User.id)).where(*filters))
                or 0
            )
        if query.limit == 0:
            return UserListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(User.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(User)
                .where(*page_filters)
                .order_by(User.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = _next_cursor(rows, query.limit, User.id, fingerprint)
        return UserListResponse(
            items=[_user_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        identity = json.dumps(
            [payload.external_issuer, payload.external_subject],
            separators=(",", ":"),
        )
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(identity, 0)))
        )
        user = await self._session.scalar(
            select(User).where(
                User.external_issuer == payload.external_issuer,
                User.external_subject == payload.external_subject,
            )
        )
        if user is not None:
            return _user_response(user)
        user = User(**payload.model_dump())
        self._session.add(user)
        await _commit(self._session, "user create violates a persistence constraint")
        return _user_response(user)

    async def patch(
        self, user_id: uuid.UUID, payload: UserPatchRequest
    ) -> UserResponse | None:
        user = await self._session.get(User, user_id)
        if user is None:
            return None
        if not is_missing(payload.display_name):
            user.display_name = payload.display_name
        if not is_missing(payload.is_active):
            user.is_active = payload.is_active
        if not is_missing(payload.external_subject):
            user.external_subject = payload.external_subject
        if not is_missing(payload.external_issuer):
            user.external_issuer = payload.external_issuer
        if not is_missing(payload.email):
            user.email = payload.email
        await _commit(self._session, "user patch violates a persistence constraint")
        return _user_response(user)

    async def delete(self, user_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([user_id]))

    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int:
        unique = list(dict.fromkeys(user_ids))
        if not unique:
            return 0
        referenced = await self._session.scalar(
            select(
                or_(
                    exists().where(Entity.user_id.in_(unique)),
                    exists().where(Face.user_id.in_(unique)),
                )
            )
        )
        if referenced:
            raise ValueError("cannot delete a user referenced by an entity or face")
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(User).where(User.id.in_(unique))),
        )
        await _commit(self._session, "user delete failed")
        return int(result.rowcount or 0)


def postgres_database(session: AsyncSession) -> Database:
    """Bind all repositories to one request-scoped SQLAlchemy session."""
    return Database(
        entities=PostgresEntityRepository(session),
        sources=PostgresSourceRepository(session),
        faces=PostgresFaceRepository(session),
        face_models=PostgresFaceModelRepository(session),
        text_mentions=PostgresTextMentionRepository(session),
        users=PostgresUserRepository(session),
    )


__all__ = [
    "PostgresEntityRepository",
    "PostgresFaceModelRepository",
    "PostgresSourceRepository",
    "PostgresFaceRepository",
    "PostgresTextMentionRepository",
    "PostgresUserRepository",
    "postgres_database",
]
