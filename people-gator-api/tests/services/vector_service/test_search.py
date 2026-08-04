from __future__ import annotations

import uuid

import pytest

from people_gator_api.schemas.enums import AnnotationType
from people_gator_api.services.weaviate_service.schemas import EntitySearchResult
from people_gator_api.services.weaviate_service import search as vector_search


def _annotation_result(
    *,
    annotation_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    distance: float | None = None,
) -> EntitySearchResult:
    resolved_annotation_id = annotation_id or uuid.uuid4()
    return EntitySearchResult(
        weaviate_id=uuid.uuid4(),
        annotation_type=AnnotationType.face,
        annotation_id=resolved_annotation_id,
        source_id=uuid.uuid4(),
        model_agent_id=None,
        confidence=None,
        entity_id=entity_id,
        distance=distance,
        certainty=None,
    )


@pytest.mark.asyncio
async def test_search_by_vectors_keeps_independent_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_hit = _annotation_result(distance=0.1)
    second_hit = _annotation_result(distance=0.2)

    async def fake_search_by_vector(**kwargs: object) -> list[EntitySearchResult]:
        vector = kwargs["vector"]
        assert isinstance(vector, list)
        return [first_hit] if vector[0] == 1.0 else [second_hit]

    monkeypatch.setattr(vector_search, "search_by_vector", fake_search_by_vector)

    batches = await vector_search.search_by_vectors(
        client=None,  # type: ignore[arg-type]
        vectors=[[1.0, 0.0], [2.0, 0.0]],
        annotation_type=AnnotationType.face,
        target_named_vector="face",
    )

    assert [batch.query_vector_index for batch in batches] == [0, 1]
    assert batches[0].results == [first_hit]
    assert batches[1].results == [second_hit]


def test_grouping_helpers_preserve_entity_and_annotation_buckets() -> None:
    entity_id = uuid.uuid4()
    shared_annotation_id = uuid.uuid4()
    first_hit = _annotation_result(
        annotation_id=shared_annotation_id,
        entity_id=entity_id,
        distance=0.1,
    )
    second_hit = _annotation_result(
        annotation_id=shared_annotation_id,
        entity_id=entity_id,
        distance=0.2,
    )
    unrelated_hit = _annotation_result(distance=0.3)

    flattened = vector_search.flatten_annotation_search_batches(
        [
            vector_search.AnnotationSearchBatch(query_vector_index=0, results=[first_hit]),
            vector_search.AnnotationSearchBatch(
                query_vector_index=1,
                results=[second_hit, unrelated_hit],
            ),
        ]
    )

    assert flattened == [first_hit, second_hit, unrelated_hit]
    assert vector_search.group_annotation_results_by_entity(flattened) == {
        entity_id: [first_hit, second_hit]
    }
    assert vector_search.group_annotation_results_by_annotation(flattened) == {
        (AnnotationType.face, shared_annotation_id): [first_hit, second_hit],
        (AnnotationType.face, unrelated_hit.annotation_id): [unrelated_hit],
    }
