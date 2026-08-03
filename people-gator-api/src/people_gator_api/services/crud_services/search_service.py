"""Service for vector-backed search endpoints."""

from __future__ import annotations

import asyncio
import uuid
from collections import (
    defaultdict,
)
from collections.abc import (
    Iterable,
    Sequence,
)
from dataclasses import (
    dataclass,
)

from weaviate import (
    WeaviateAsyncClient,
)
from weaviate.classes.query import (
    Filter,
)
from weaviate.collections.classes.filters import (
    FilterReturn,
)

from people_gator_api.schemas.enums import (
    AnnotationType,
)
from people_gator_api.schemas.search import (
    SearchAnnotationResult,
    SearchEntityResult,
    SearchFacetsResponse,
    SearchFilters,
    SearchQuery,
    SearchRequest,
    SearchResponse,
    SearchSignalContribution,
)
from people_gator_api.settings import (
    SearchEntityAggregationMode,
    SearchModalitySettings,
    SearchProfileSettings,
)
from people_gator_api.services.vector_service.schema import (
    ANNOTATION_COLLECTION_BY_TYPE,
    ENTITY_COLLECTION,
)
from people_gator_api.services.vector_service.schemas import (
    AnnotationSearchResult,
)
from people_gator_api.services.vector_service.search import (
    extract_named_vectors,
    fetch_collection_objects,
    flatten_annotation_search_batches,
    group_annotation_results_by_annotation,
    group_annotation_results_by_entity,
    search_by_vectors,
)
from people_gator_api.services.weaviate_utils import (
    query_objects,
)

_DIRECT_ENTITY_ANNOTATION_TYPES = frozenset(
    {
        AnnotationType.entity,
        AnnotationType.entity_name,
        AnnotationType.description,
        AnnotationType.face,
        AnnotationType.document_mention,
        AnnotationType.span,
    }
)
_CONFIDENCE_FILTER_ANNOTATION_TYPES = frozenset(
    {
        AnnotationType.face,
        AnnotationType.page_mention,
    }
)

type AnnotationHitKey = tuple[AnnotationType, uuid.UUID]


@dataclass(slots=True, frozen=True)
class ModalityScoreSet:
    raw_scores: dict[uuid.UUID, float]
    normalized_scores: dict[uuid.UUID, float]


@dataclass(slots=True, frozen=True)
class AggregatedAnnotationHit:
    hit: AnnotationSearchResult
    score: float


async def search(
    session: WeaviateAsyncClient,
    request: SearchRequest,
    profile: SearchProfileSettings,
) -> SearchResponse:
    modalities = list(profile.modalities)
    modality_vectors = await _resolve_query_vectors(session, request.query, modalities)
    resolved_modalities = [
        modality
        for modality in modalities
        if modality_vectors.get(modality.annotation_type)
    ]

    entity_results = await _search_entities(
        session=session,
        request=request,
        modality_vectors=modality_vectors,
        modalities=resolved_modalities,
        profile=profile,
    )
    annotation_results = await _search_annotations(
        session=session,
        request=request,
        modality_vectors=modality_vectors,
        modalities=resolved_modalities,
        profile=profile,
    )

    merged_results = _merge_results(entity_results, annotation_results, request.limit)
    facets = _compute_facets(merged_results)

    return SearchResponse(
        total=len(merged_results),
        limit=request.limit,
        next_after_id=None,
        results=merged_results,
        facets={
            "annotation_types": facets.annotation_types,
            "source_kinds": facets.source_kinds,
            "result_types": facets.result_types,
            "has_face": facets.has_face,
            "has_authority_link": facets.has_authority_link,
        },
        query=request.query,
        filters=request.filters,
    )


async def search_facets(
    session: WeaviateAsyncClient,
    query: SearchQuery,
    filters: SearchFilters,
    profile: SearchProfileSettings,
) -> SearchFacetsResponse:
    probe_request = SearchRequest(
        query=query,
        filters=filters,
        result_types=["entity", "annotation"],
        limit=200,
    )
    probe_response = await search(session, probe_request, profile)
    return _compute_facets(probe_response.results)


async def _resolve_query_vectors(
    session: WeaviateAsyncClient,
    query: SearchQuery,
    modalities: Sequence[SearchModalitySettings],
) -> dict[AnnotationType, list[list[float]]]:
    vectors: dict[AnnotationType, list[list[float]]] = {
        modality.annotation_type: [] for modality in modalities
    }
    modalities_by_collection = _group_modalities_by_collection(modalities)

    if query.annotation_ids:
        annotation_ids = list(dict.fromkeys(query.annotation_ids))
        annotation_jobs = [
            _fetch_query_vectors(
                client=session,
                collection_name=collection_name,
                modalities=collection_modalities,
                filters=Filter.by_id().contains_any(
                    [str(annotation_id) for annotation_id in annotation_ids]
                ),
                limit=len(annotation_ids),
            )
            for collection_name, collection_modalities in modalities_by_collection.items()
        ]
        for job_result in await asyncio.gather(*annotation_jobs):
            for annotation_type, resolved_vectors in job_result.items():
                vectors[annotation_type].extend(resolved_vectors)

    if query.reference_entity_id is not None:
        entity_jobs = [
            _fetch_query_vectors(
                client=session,
                collection_name=collection_name,
                modalities=collection_modalities,
                filters=Filter.by_property("entity_id").equal(str(query.reference_entity_id)),
                limit=500,
            )
            for collection_name, collection_modalities in modalities_by_collection.items()
            if any(
                modality.annotation_type in _DIRECT_ENTITY_ANNOTATION_TYPES
                for modality in collection_modalities
            )
        ]
        for job_result in await asyncio.gather(*entity_jobs):
            for annotation_type, resolved_vectors in job_result.items():
                vectors[annotation_type].extend(resolved_vectors)

    return {
        annotation_type: resolved_vectors
        for annotation_type, resolved_vectors in vectors.items()
        if resolved_vectors
    }


async def _fetch_query_vectors(
    *,
    client: WeaviateAsyncClient,
    collection_name: str,
    modalities: Sequence[SearchModalitySettings],
    filters: FilterReturn,
    limit: int,
) -> dict[AnnotationType, list[list[float]]]:
    objects = await fetch_collection_objects(
        client=client,
        collection_name=collection_name,
        filters=filters,
        include_vector=True,
        limit=limit,
    )
    vectors: dict[AnnotationType, list[list[float]]] = {}
    for modality in modalities:
        resolved_vectors = extract_named_vectors(objects, modality.vector_name)
        if resolved_vectors:
            vectors[modality.annotation_type] = resolved_vectors
    return vectors


async def _search_entities(
    *,
    session: WeaviateAsyncClient,
    request: SearchRequest,
    modality_vectors: dict[AnnotationType, list[list[float]]],
    modalities: Sequence[SearchModalitySettings],
    profile: SearchProfileSettings,
) -> list[SearchEntityResult]:
    if "entity" not in request.result_types:
        return []

    used_modalities = [
        modality for modality in modalities if modality_vectors.get(modality.annotation_type)
    ]
    if not used_modalities:
        return []

    candidate_limit = max(request.limit * profile.entity_candidate_multiplier, request.limit)
    modality_scores: dict[AnnotationType, ModalityScoreSet] = {}
    modality_score_jobs = [
        _entity_modality_scores(
            session=session,
            modality=modality,
            query_vectors=modality_vectors[modality.annotation_type],
            limit=candidate_limit,
        )
        for modality in used_modalities
    ]
    for modality, raw_scores in zip(
        used_modalities,
        await asyncio.gather(*modality_score_jobs),
        strict=False,
    ):
        if raw_scores:
            modality_scores[modality.annotation_type] = ModalityScoreSet(
                raw_scores=raw_scores,
                normalized_scores=_normalise_scores(raw_scores),
            )

    if not modality_scores:
        return []

    total_weight = sum(
        modality.weight
        for modality in used_modalities
        if modality.annotation_type in modality_scores
    )
    entity_ids = {
        entity_id
        for score_set in modality_scores.values()
        for entity_id in score_set.raw_scores
    }
    allowed_entity_ids = await _resolve_allowed_entity_ids(
        client=session,
        requested_entity_types=request.filters.entity_types,
        candidate_entity_ids=entity_ids,
    )
    results: list[SearchEntityResult] = []
    for entity_id in entity_ids:
        if allowed_entity_ids is not None and entity_id not in allowed_entity_ids:
            continue
        contributions: dict[AnnotationType, SearchSignalContribution] = {}
        weighted_score = 0.0
        for modality in used_modalities:
            score_set = modality_scores.get(modality.annotation_type)
            if score_set is None:
                continue
            raw_score = score_set.raw_scores.get(entity_id)
            normalized_score = score_set.normalized_scores.get(entity_id, 0.0)
            weighted_score += modality.weight * normalized_score
            if raw_score is None:
                continue
            contributions[modality.annotation_type] = SearchSignalContribution(
                score=raw_score,
                normalised_score=normalized_score,
                weight=modality.weight,
            )
        if not contributions:
            continue
        results.append(
            SearchEntityResult(
                entity_id=entity_id,
                score=weighted_score / total_weight if total_weight > 0 else 0.0,
                signal_contributions=contributions,
            )
        )

    return sorted(results, key=lambda item: item.score, reverse=True)[: request.limit]


async def _entity_modality_scores(
    *,
    session: WeaviateAsyncClient,
    modality: SearchModalitySettings,
    query_vectors: list[list[float]],
    limit: int,
) -> dict[uuid.UUID, float]:
    search_batches = await search_by_vectors(
        client=session,
        vectors=query_vectors,
        annotation_type=modality.annotation_type,
        target_named_vector=modality.vector_name,
        filters=_modality_query_filters(modality),
        limit=limit,
    )
    if not search_batches:
        return {}
    hits = flatten_annotation_search_batches(search_batches)
    return aggregate_entity_scores(hits, modality.aggregation)


async def _search_annotations(
    *,
    session: WeaviateAsyncClient,
    request: SearchRequest,
    modality_vectors: dict[AnnotationType, list[list[float]]],
    modalities: Sequence[SearchModalitySettings],
    profile: SearchProfileSettings,
) -> list[SearchAnnotationResult]:
    wants_annotation_results = (
        "annotation" in request.result_types
        or any(result_type != "entity" for result_type in request.result_types)
    )
    if not wants_annotation_results:
        return []

    selected_modalities = [
        modality
        for modality in modalities
        if modality_vectors.get(modality.annotation_type)
        and _annotation_result_requested(request, modality.annotation_type)
    ]
    if not selected_modalities:
        return []

    total_weight = sum(modality.weight for modality in selected_modalities)
    candidate_limit = max(request.limit * profile.annotation_candidate_multiplier, request.limit)
    accumulator: dict[AnnotationHitKey, SearchAnnotationResult] = {}
    modality_hit_jobs = [
        _annotation_modality_hits(
            session=session,
            modality=modality,
            query_vectors=modality_vectors[modality.annotation_type],
            limit=candidate_limit,
        )
        for modality in selected_modalities
    ]
    for modality, aggregated_hits in zip(
        selected_modalities,
        await asyncio.gather(*modality_hit_jobs),
        strict=False,
    ):
        if not aggregated_hits:
            continue
        raw_scores = {
            key: aggregated_hit.score for key, aggregated_hit in aggregated_hits.items()
        }
        normalized_scores = _normalise_scores(raw_scores)
        for key, aggregated_hit in aggregated_hits.items():
            raw_score = raw_scores[key]
            normalized_score = normalized_scores[key]
            weighted_score = (
                modality.weight * normalized_score / total_weight if total_weight > 0 else 0.0
            )
            contribution = SearchSignalContribution(
                score=raw_score,
                normalised_score=normalized_score,
                weight=modality.weight,
            )
            existing = accumulator.get(key)
            if existing is None:
                accumulator[key] = SearchAnnotationResult(
                    result_type=aggregated_hit.hit.annotation_type,
                    annotation_id=aggregated_hit.hit.annotation_id,
                    source_id=aggregated_hit.hit.source_id,
                    score=weighted_score,
                    signal_contributions={modality.annotation_type: contribution},
                )
                continue

            existing.score += weighted_score
            existing.signal_contributions[modality.annotation_type] = contribution

    return sorted(accumulator.values(), key=lambda item: item.score, reverse=True)[
        : request.limit
    ]


def _annotation_result_requested(
    request: SearchRequest,
    annotation_type: AnnotationType,
) -> bool:
    annotation_filters = set(request.filters.annotation_types)
    if annotation_filters and annotation_type not in annotation_filters:
        return False

    requested_annotation_types = {
        result_type
        for result_type in request.result_types
        if result_type not in {"entity", "annotation"}
    }
    if requested_annotation_types and annotation_type.value not in requested_annotation_types:
        return False
    return True


def _merge_results(
    entity_results: list[SearchEntityResult],
    annotation_results: list[SearchAnnotationResult],
    limit: int,
) -> list[SearchEntityResult | SearchAnnotationResult]:
    merged: list[SearchEntityResult | SearchAnnotationResult] = [
        *entity_results,
        *annotation_results,
    ]
    merged.sort(key=lambda item: item.score, reverse=True)
    return merged[:limit]


def _compute_facets(
    results: Iterable[SearchEntityResult | SearchAnnotationResult],
) -> SearchFacetsResponse:
    annotation_type_counts = {annotation_type.value: 0 for annotation_type in AnnotationType}
    result_type_counts = {"entity": 0, "annotation": 0}
    has_face_counts = {"true": 0, "false": 0}

    for result in results:
        if isinstance(result, SearchEntityResult):
            result_type_counts["entity"] += 1
            has_face = AnnotationType.face in result.signal_contributions
            has_face_counts["true" if has_face else "false"] += 1
            continue

        result_type_counts["annotation"] += 1
        annotation_type_counts[result.result_type.value] += 1

    return SearchFacetsResponse(
        annotation_types=annotation_type_counts,
        source_kinds={},
        result_types=result_type_counts,
        has_face=has_face_counts,
        has_authority_link={"true": 0, "false": 0},
    )


def _distance_to_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    score = 1.0 - distance
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def aggregate_entity_scores(
    hits: Sequence[AnnotationSearchResult],
    aggregation: SearchEntityAggregationMode,
) -> dict[uuid.UUID, float]:
    grouped_hits = group_annotation_results_by_entity(hits)
    aggregated_scores: dict[uuid.UUID, float] = {}
    for entity_id, entity_hits in grouped_hits.items():
        scores = [_distance_to_score(hit.distance) for hit in entity_hits]
        if not scores:
            continue
        if aggregation is SearchEntityAggregationMode.average_annotation:
            aggregated_scores[entity_id] = sum(scores) / len(scores)
            continue
        aggregated_scores[entity_id] = max(scores)
    return aggregated_scores


async def _annotation_modality_hits(
    *,
    session: WeaviateAsyncClient,
    modality: SearchModalitySettings,
    query_vectors: list[list[float]],
    limit: int,
) -> dict[AnnotationHitKey, AggregatedAnnotationHit]:
    search_batches = await search_by_vectors(
        client=session,
        vectors=query_vectors,
        annotation_type=modality.annotation_type,
        target_named_vector=modality.vector_name,
        filters=_modality_query_filters(modality),
        limit=limit,
    )
    if not search_batches:
        return {}
    hits = flatten_annotation_search_batches(search_batches)
    return aggregate_annotation_hits(hits)


def aggregate_annotation_hits(
    hits: Sequence[AnnotationSearchResult],
) -> dict[AnnotationHitKey, AggregatedAnnotationHit]:
    grouped_hits = group_annotation_results_by_annotation(hits)
    aggregated_hits: dict[AnnotationHitKey, AggregatedAnnotationHit] = {}
    for key, annotation_hits in grouped_hits.items():
        best_hit = max(
            annotation_hits,
            key=lambda hit: (_distance_to_score(hit.distance), hit.weaviate_id.hex),
        )
        aggregated_hits[key] = AggregatedAnnotationHit(
            hit=best_hit,
            score=_distance_to_score(best_hit.distance),
        )
    return aggregated_hits


def _normalise_scores[TKey](scores: dict[TKey, float]) -> dict[TKey, float]:
    if not scores:
        return {}
    minimum = min(scores.values())
    maximum = max(scores.values())
    if maximum == minimum:
        return dict(scores)
    scale = maximum - minimum
    return {key: (value - minimum) / scale for key, value in scores.items()}


def _group_modalities_by_collection(
    modalities: Sequence[SearchModalitySettings],
) -> dict[str, list[SearchModalitySettings]]:
    grouped: dict[str, list[SearchModalitySettings]] = defaultdict(list)
    for modality in modalities:
        grouped[ANNOTATION_COLLECTION_BY_TYPE[modality.annotation_type]].append(modality)
    return dict(grouped)


def _modality_query_filters(
    modality: SearchModalitySettings,
) -> FilterReturn | None:
    if (
        modality.min_confidence is None
        or modality.annotation_type not in _CONFIDENCE_FILTER_ANNOTATION_TYPES
    ):
        return None
    return Filter.by_property("confidence").greater_or_equal(modality.min_confidence)


async def _resolve_allowed_entity_ids(
    *,
    client: WeaviateAsyncClient,
    requested_entity_types: Sequence[str],
    candidate_entity_ids: set[uuid.UUID],
) -> set[uuid.UUID] | None:
    if not requested_entity_types:
        return None
    if not candidate_entity_ids:
        return set()

    type_filters = [
        Filter.by_property("entity_type").equal(entity_type)
        for entity_type in requested_entity_types
    ]
    entity_collection = client.collections.get(ENTITY_COLLECTION)
    response = await entity_collection.query.fetch_objects(
        filters=Filter.all_of(
            [
                Filter.by_property("entity_id").contains_any(
                    [str(entity_id) for entity_id in candidate_entity_ids]
                ),
                type_filters[0] if len(type_filters) == 1 else Filter.any_of(type_filters),
            ]
        ),
        limit=len(candidate_entity_ids),
    )
    resolved: set[uuid.UUID] = set()
    for obj in query_objects(response):
        entity_id_value = obj.properties.get("entity_id")
        if entity_id_value is None:
            continue
        resolved.add(uuid.UUID(str(entity_id_value)))
    return resolved
