"""Service for vector-backed search endpoints.

Contains search execution and facet computation only.
"""

import asyncio
import uuid
from collections.abc import Iterable
from typing import Any, TypeGuard

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
from people_gator_api.services.vector_service.client import get_weaviate_client
from people_gator_api.services.vector_service.schema import (
    ANNOTATION_COLLECTION_BY_TYPE,
    ENTITY_COLLECTION,
    FACE_VECTOR,
    NAME_VECTOR,
)
from people_gator_api.services.vector_service.search import VectorSearchService
from people_gator_api.services.crud_services.profile_service import get_profile

_DEFAULT_MODALITY_WEIGHT = 1.0
async def search(
    session: WeaviateAsyncClient,
    request: SearchRequest,
) -> SearchResponse:
    profile_modalities = await _resolve_profile_modalities(session, request.profile_id)
    modality_vectors = await _resolve_query_vectors(request.query)

    vector_search = VectorSearchService(get_weaviate_client())
    entity_results = await _search_entities(
        vector_search=vector_search,
        request=request,
        modality_vectors=modality_vectors,
        profile_modalities=profile_modalities,
    )
    annotation_results = await _search_annotations(
        vector_search=vector_search,
        request=request,
        modality_vectors=modality_vectors,
        profile_modalities=profile_modalities,
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
        profile_id=request.profile_id,
    )


async def search_facets(
    session: WeaviateAsyncClient,
    query: SearchQuery,
    filters: SearchFilters,
) -> SearchFacetsResponse:
    probe_request = SearchRequest(
        query=query,
        filters=filters,
        result_types=["entity", "annotation"],
        limit=200,
    )
    probe_response = await search(session, probe_request)
    return _compute_facets(probe_response.results)


async def _resolve_profile_modalities(
    session: WeaviateAsyncClient,
    profile_id: uuid.UUID | None,
) -> dict[AnnotationType, float]:
    if profile_id is None:
        return {}

    profile = await get_profile(session, profile_id)
    if profile is None:
        return {}

    return {
        modality.annotation_type: modality.weight
        for modality in profile.modalities
    }


async def _resolve_query_vectors(
    query: SearchQuery,
) -> dict[AnnotationType, list[list[float]]]:
    client = get_weaviate_client()
    vectors: dict[AnnotationType, list[list[float]]] = {
        annotation_type: [] for annotation_type in AnnotationType
    }

    if query.annotation_ids:
        annotation_ids = list(dict.fromkeys(query.annotation_ids))
        collection_items = list(ANNOTATION_COLLECTION_BY_TYPE.items())
        jobs = [
            _fetch_vectors_by_annotation_ids(
                client=client,
                annotation_type=annotation_type,
                collection_name=collection_name,
                annotation_ids=annotation_ids,
            )
            for annotation_type, collection_name in collection_items
        ]
        job_results = await asyncio.gather(*jobs)
        for index, result in enumerate(job_results):
            annotation_type, _ = collection_items[index]
            vectors[annotation_type].extend(result)

    if query.reference_entity_id is not None:
        entity_collection = client.collections.get(ENTITY_COLLECTION)
        try:
            entity_obj = await entity_collection.query.fetch_object_by_id(
                uuid=entity_weaviate_uuid(query.reference_entity_id),
                include_vector=True,
            )
        except Exception:
            entity_obj = None

        if entity_obj is not None and entity_obj.vector:
            raw_face = entity_obj.vector.get(FACE_VECTOR)
            raw_name = entity_obj.vector.get(NAME_VECTOR)
            if _is_float_vector(raw_face):
                vectors[AnnotationType.face].append(raw_face)
            if _is_float_vector(raw_name):
                vectors[AnnotationType.person_name].append(raw_name)

    return {
        annotation_type: value
        for annotation_type, value in vectors.items()
        if value
    }


async def _fetch_vectors_by_annotation_ids(
    *,
    client: WeaviateAsyncClient,
    annotation_type: AnnotationType,
    collection_name: str,
    annotation_ids: list[uuid.UUID],
) -> list[list[float]]:
    _ = annotation_type
    if not annotation_ids:
        return []

    collection: Any = client.collections.get(collection_name)
    row_uuids = [vector_object_uuid(collection_name, annotation_id) for annotation_id in annotation_ids]
    try:
        response: Any = await collection.query.fetch_objects(
            filters=Filter.by_id().contains_any([str(row_uuid) for row_uuid in row_uuids]),
            include_vector=True,
            limit=len(row_uuids),
        )
    except Exception:
        return []

    vectors: list[list[float]] = []
    for obj in response.objects:
        vector = _extract_primary_vector(obj.vector)
        if vector is not None:
            vectors.append(vector)
    return vectors


async def _search_entities(
    *,
    vector_search: VectorSearchService,
    request: SearchRequest,
    modality_vectors: dict[AnnotationType, list[list[float]]],
    profile_modalities: dict[AnnotationType, float],
) -> list[SearchEntityResult]:
    if "entity" not in request.result_types:
        return []

    face_vector = _average_vectors(modality_vectors.get(AnnotationType.face, []))
    name_vector = _average_vectors(modality_vectors.get(AnnotationType.person_name, []))
    description_vector = _average_vectors(modality_vectors.get(AnnotationType.description, []))

    face_weight = profile_modalities.get(AnnotationType.face, _DEFAULT_MODALITY_WEIGHT)
    name_weight = profile_modalities.get(AnnotationType.person_name, _DEFAULT_MODALITY_WEIGHT)
    description_weight = profile_modalities.get(AnnotationType.description, _DEFAULT_MODALITY_WEIGHT)

    if face_vector is None and name_vector is None:
        if description_vector is None:
            return []
        raw_results = await vector_search.search_entities_by_name_description(
            name_vector=name_vector,
            description_vector=description_vector,
            name_weight=name_weight,
            description_weight=description_weight,
            limit=request.limit,
        )
    else:
        raw_results = await vector_search.search_entities_weighted(
            face_vector=face_vector,
            name_vector=name_vector,
            face_weight=face_weight,
            name_weight=name_weight,
            limit=request.limit,
        )

    results: list[SearchEntityResult] = []
    for item in raw_results:
        score = _distance_to_score(item.combined_distance)
        contributions: dict[AnnotationType, SearchSignalContribution] = {}
        if item.face_distance is not None:
            face_score = _distance_to_score(item.face_distance)
            contributions[AnnotationType.face] = SearchSignalContribution(
                score=face_score,
                normalised_score=face_score,
                weight=face_weight,
            )
        if item.name_distance is not None:
            name_score = _distance_to_score(item.name_distance)
            contributions[AnnotationType.person_name] = SearchSignalContribution(
                score=name_score,
                normalised_score=name_score,
                weight=name_weight,
            )
        if item.description_distance is not None:
            description_score = _distance_to_score(item.description_distance)
            contributions[AnnotationType.description] = SearchSignalContribution(
                score=description_score,
                normalised_score=description_score,
                weight=description_weight,
            )

        results.append(
            SearchEntityResult(
                entity_id=item.entity_id,
                score=score,
                signal_contributions=contributions,
            )
        )
    return results


async def _search_annotations(
    *,
    vector_search: VectorSearchService,
    request: SearchRequest,
    modality_vectors: dict[AnnotationType, list[list[float]]],
    profile_modalities: dict[AnnotationType, float],
) -> list[SearchAnnotationResult]:
    wants_annotation_results = (
        "annotation" in request.result_types
        or any(result_type != "entity" for result_type in request.result_types)
    )
    if not wants_annotation_results:
        return []

    annotation_filters = set(request.filters.annotation_types)
    requested_annotation_types = {
        result_type
        for result_type in request.result_types
        if result_type != "entity"
    }

    accumulator: dict[
        tuple[AnnotationType, uuid.UUID],
        SearchAnnotationResult,
    ] = {}

    for annotation_type, vectors in modality_vectors.items():
        if annotation_filters and annotation_type not in annotation_filters:
            continue
        if requested_annotation_types and annotation_type.value not in requested_annotation_types:
            continue

        weight = profile_modalities.get(annotation_type, _DEFAULT_MODALITY_WEIGHT)

        for vector in vectors:
            raw_hits = await vector_search.search_annotations_by_vector(
                vector=vector,
                annotation_type=annotation_type,
                limit=request.limit,
            )
            for hit in raw_hits:
                score = _distance_to_score(hit.distance)
                contribution = SearchSignalContribution(
                    score=score,
                    normalised_score=score,
                    weight=weight,
                )
                key = (annotation_type, hit.annotation_id)
                existing = accumulator.get(key)
                if existing is None:
                    accumulator[key] = SearchAnnotationResult(
                        result_type=annotation_type,
                        annotation_id=hit.annotation_id,
                        source_id=hit.source_id,
                        score=score,
                        signal_contributions={annotation_type: contribution},
                    )
                    continue

                if score > existing.score:
                    existing.score = score
                existing.signal_contributions[annotation_type] = contribution

    return sorted(
        accumulator.values(),
        key=lambda item: item.score,
        reverse=True,
    )[:request.limit]


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


def _extract_primary_vector(
    raw_vector: list[float] | dict[str, object] | None,
) -> list[float] | None:
    if raw_vector is None:
        return None
    if _is_float_vector(raw_vector):
        return raw_vector

    if not isinstance(raw_vector, dict):
        return None

    default_vector = raw_vector.get("default")
    if _is_float_vector(default_vector):
        return [item for item in default_vector]

    for value in raw_vector.values():
        if _is_float_vector(value):
            return [item for item in value]
    return None


def _is_float_vector(value: object) -> TypeGuard[list[float]]:
    if not isinstance(value, list) or not value:
        return False
    return isinstance(value[0], float)


def vector_object_uuid(collection_name: str, row_id: uuid.UUID) -> uuid.UUID:
    _ = collection_name
    return row_id


def entity_weaviate_uuid(entity_id: uuid.UUID) -> uuid.UUID:
    return entity_id
