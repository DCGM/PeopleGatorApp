"""Service for vector-backed search endpoints."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeGuard

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from people_gator_api.schemas.enums import AnnotationType
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
from people_gator_api.services.weaviate_utils import query_objects
from people_gator_api.services.vector_service.schemas import AnnotationSearchResult
from people_gator_api.services.vector_service.search import search_by_vector

_DIRECT_ENTITY_ANNOTATION_TYPES = frozenset(
    {
        AnnotationType.entity_name,
        AnnotationType.description,
        AnnotationType.face,
        AnnotationType.document_mention,
        AnnotationType.span,
    }
)


@dataclass(slots=True, frozen=True)
class ModalityScoreSet:
    raw_scores: dict[uuid.UUID, float]
    normalized_scores: dict[uuid.UUID, float]


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
            _fetch_query_vectors_for_annotation_ids(
                client=session,
                collection_name=collection_name,
                modalities=collection_modalities,
                annotation_ids=annotation_ids,
            )
            for collection_name, collection_modalities in modalities_by_collection.items()
        ]
        for job_result in await asyncio.gather(*annotation_jobs):
            for annotation_type, resolved_vectors in job_result.items():
                vectors[annotation_type].extend(resolved_vectors)

    if query.reference_entity_id is not None:
        entity_jobs = [
            _fetch_query_vectors_for_entity(
                client=session,
                collection_name=collection_name,
                modalities=collection_modalities,
                entity_id=query.reference_entity_id,
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


async def _fetch_query_vectors_for_annotation_ids(
    *,
    client: WeaviateAsyncClient,
    collection_name: str,
    modalities: Sequence[SearchModalitySettings],
    annotation_ids: Sequence[uuid.UUID],
) -> dict[AnnotationType, list[list[float]]]:
    if not annotation_ids:
        return {}

    collection = client.collections.get(collection_name)
    response = await collection.query.fetch_objects(
        filters=Filter.by_id().contains_any([str(annotation_id) for annotation_id in annotation_ids]),
        include_vector=True,
        limit=len(annotation_ids),
    )
    vectors: dict[AnnotationType, list[list[float]]] = defaultdict(list)
    for obj in query_objects(response):
        for modality in modalities:
            vector = _extract_named_vector(obj.vector, modality.vector_name)
            if vector is not None:
                vectors[modality.annotation_type].append(vector)
    return dict(vectors)


async def _fetch_query_vectors_for_entity(
    *,
    client: WeaviateAsyncClient,
    collection_name: str,
    modalities: Sequence[SearchModalitySettings],
    entity_id: uuid.UUID,
) -> dict[AnnotationType, list[list[float]]]:
    collection = client.collections.get(collection_name)
    response = await collection.query.fetch_objects(
        filters=Filter.by_property("entity_id").equal(str(entity_id)),
        include_vector=True,
        limit=500,
    )
    vectors: dict[AnnotationType, list[list[float]]] = defaultdict(list)
    for obj in query_objects(response):
        for modality in modalities:
            vector = _extract_named_vector(obj.vector, modality.vector_name)
            if vector is not None:
                vectors[modality.annotation_type].append(vector)
    return dict(vectors)


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
    for modality in used_modalities:
        raw_scores = await _entity_modality_scores(
            session=session,
            modality=modality,
            query_vectors=modality_vectors[modality.annotation_type],
            limit=candidate_limit,
        )
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
    query_vector = _average_vectors(query_vectors)
    if query_vector is None:
        return {}

    annotation_results = await search_by_vector(
        client=session,
        vector=query_vector,
        annotation_type=modality.annotation_type,
        target_named_vector=modality.vector_name,
        limit=limit,
        min_confidence=modality.min_confidence,
    )
    grouped_scores: dict[uuid.UUID, list[float]] = defaultdict(list)
    for result in annotation_results:
        if result.entity_id is None:
            continue
        grouped_scores[result.entity_id].append(_distance_to_score(result.distance))

    if modality.aggregation is SearchEntityAggregationMode.average_annotation:
        return {
            entity_id: sum(scores) / len(scores)
            for entity_id, scores in grouped_scores.items()
            if scores
        }
    return {
        entity_id: max(scores)
        for entity_id, scores in grouped_scores.items()
        if scores
    }


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
    accumulator: dict[tuple[AnnotationType, uuid.UUID], SearchAnnotationResult] = {}
    for modality in selected_modalities:
        query_vector = _average_vectors(modality_vectors[modality.annotation_type])
        if query_vector is None:
            continue
        raw_hits = await search_by_vector(
            client=session,
            vector=query_vector,
            annotation_type=modality.annotation_type,
            target_named_vector=modality.vector_name,
            limit=candidate_limit,
            min_confidence=modality.min_confidence,
        )
        raw_scores = {
            _annotation_hit_key(hit): _distance_to_score(hit.distance)
            for hit in raw_hits
        }
        normalized_scores = _normalise_scores(raw_scores)
        for hit in raw_hits:
            key = _annotation_hit_key(hit)
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
                    result_type=hit.annotation_type,
                    annotation_id=hit.annotation_id,
                    source_id=hit.source_id,
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


def _average_vectors(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dimension = len(vectors[0])
    n_vectors = len(vectors)
    return [sum(vector[idx] for vector in vectors) / n_vectors for idx in range(dimension)]


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


def _extract_named_vector(
    raw_vector: list[float] | Mapping[str, object] | None,
    vector_name: str,
) -> list[float] | None:
    if raw_vector is None:
        return None
    if _is_float_vector(raw_vector):
        return list(raw_vector)
    if not isinstance(raw_vector, Mapping):
        return None

    named_vector = raw_vector.get(vector_name)
    if _is_float_vector(named_vector):
        return list(named_vector)
    return None


def _is_float_vector(value: object) -> TypeGuard[list[float]]:
    if not isinstance(value, list) or not value:
        return False
    return isinstance(value[0], float)


def _annotation_hit_key(hit: AnnotationSearchResult) -> tuple[AnnotationType, uuid.UUID]:
    return hit.annotation_type, hit.annotation_id
