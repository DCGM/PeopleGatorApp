"""Tests for Weaviate search helpers and the entity/face search service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.enums import (
    EntityType,
    FaceEmbeddingModel,
    ScoreAggregation,
)
from people_gator_api.schemas.search import (
    FaceSearchQuery,
    FaceSearchResult,
    SearchEntitiesQuery,
    SearchEntitiesResult,
)
from people_gator_api.services.crud_services import search_service
from people_gator_api.services.weaviate_service import search as weaviate_search
from people_gator_api.services.weaviate_service.db_schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
    FACE_VECTOR_BY_MODEL,
)


def _entity_result(
    entity_id: uuid.UUID,
    score: float,
    *,
    name: str | None = None,
) -> SearchEntitiesResult:
    return SearchEntitiesResult(
        entity_id=entity_id,
        entity_type=EntityType.person,
        name=name or str(entity_id),
        description="",
        short_description="",
        aliases=[],
        matching_score=score,
    )


# ---------------------------------------------------------------------------
# Weaviate helpers: BM25 name search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_name_search_uses_bm25_over_name_and_aliases() -> None:
    entity_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class _Query:
        async def bm25(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                objects=[
                    SimpleNamespace(
                        uuid=entity_id,
                        properties={
                            "entity_type": "person",
                            "name": "Ada Lovelace",
                            "description": "Mathematician",
                            "short_description": "English mathematician",
                            "aliases": ["Augusta Ada King"],
                        },
                        metadata=SimpleNamespace(score=7.5),
                    )
                ]
            )

    class _Collections:
        def get(self, collection_name: str) -> SimpleNamespace:
            assert collection_name == ENTITY_COLLECTION
            return SimpleNamespace(query=_Query())

    results = await weaviate_search.search_entities_by_names_or_aliases(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        ["Ada", "Lovelace"],
        limit=5,
    )

    assert captured["query"] == "Ada, Lovelace"
    assert captured["query_properties"] == ["name", "aliases"]
    assert captured["filters"] is None
    assert captured["limit"] == 5
    assert len(results) == 1
    assert results[0].entity_id == entity_id
    assert results[0].name == "Ada Lovelace"
    assert results[0].aliases == ["Augusta Ada King"]
    assert results[0].matching_score == 7.5


@pytest.mark.asyncio
async def test_name_search_skips_weaviate_for_empty_or_invalid_queries() -> None:
    client = SimpleNamespace()  # pyright: ignore[reportArgumentType]

    assert await weaviate_search.search_entities_by_names_or_aliases(client, []) == []  # pyright: ignore[reportArgumentType]
    assert await weaviate_search.search_entities_by_names_or_aliases(  # pyright: ignore[reportArgumentType]
        client, ["   "]
    ) == []
    assert await weaviate_search.search_entities_by_names_or_aliases(  # pyright: ignore[reportArgumentType]
        client, ["Ada"], limit=0
    ) == []


@pytest.mark.asyncio
async def test_name_search_applies_entity_type_filter() -> None:
    captured: dict[str, object] = {}

    class _Query:
        async def bm25(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(objects=[])

    class _Collections:
        def get(self, collection_name: str) -> SimpleNamespace:
            assert collection_name == ENTITY_COLLECTION
            return SimpleNamespace(query=_Query())

    await weaviate_search.search_entities_by_names_or_aliases(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        ["Ada"],
        entity_types=[EntityType.person, EntityType.place],
    )

    entity_type_filter = captured["filters"]
    children = vars(entity_type_filter)["filters"]
    assert len(children) == 2
    assert all("entity_type" in repr(child) for child in children)


# ---------------------------------------------------------------------------
# Weaviate helpers: score aggregation
# ---------------------------------------------------------------------------


def test_aggregate_scores_supports_min_max_and_average() -> None:
    scores = [0.2, 0.5, 0.9]

    assert weaviate_search._aggregate_scores(  # pyright: ignore[reportPrivateUsage]
        scores, ScoreAggregation.min
    ) == pytest.approx(0.2)
    assert weaviate_search._aggregate_scores(  # pyright: ignore[reportPrivateUsage]
        scores, ScoreAggregation.max
    ) == pytest.approx(0.9)
    assert weaviate_search._aggregate_scores(  # pyright: ignore[reportPrivateUsage]
        scores, ScoreAggregation.average
    ) == pytest.approx(0.5333333333333333)


def test_aggregate_scores_of_empty_list_raises() -> None:
    # min([]), max([]) and fmean([]) all raise; document the contract.
    with pytest.raises(ValueError):
        weaviate_search._aggregate_scores(  # pyright: ignore[reportPrivateUsage]
            [], ScoreAggregation.max
        )


# ---------------------------------------------------------------------------
# Weaviate helpers: grouped face -> entity search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_face_grouped_search_aggregates_scores_per_entity() -> None:
    entity_id = uuid.uuid4()
    captured: dict[str, object] = {}

    def _face(distance: float) -> SimpleNamespace:
        return SimpleNamespace(
            metadata=SimpleNamespace(distance=distance),
            references={
                "entity": SimpleNamespace(
                    objects=[
                        SimpleNamespace(
                            properties={
                                "entity_type": "person",
                                "name": "Ada Lovelace",
                                "description": "Mathematician",
                                "short_description": "",
                                "aliases": [],
                            }
                        )
                    ]
                )
            },
        )

    class _Query:
        async def near_vector(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                groups={
                    f"weaviate://localhost/entity/{entity_id}": SimpleNamespace(
                        objects=[_face(0.1), _face(0.3), _face(0.5)],
                    )
                }
            )

    class _Collections:
        def get(self, collection_name: str) -> SimpleNamespace:
            assert collection_name == FACE_COLLECTION
            return SimpleNamespace(query=_Query())

    results = await weaviate_search.search_entities_by_faces_vectors(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        [[0.1, 0.2]],
        vector_name=FACE_VECTOR_BY_MODEL[
            FaceEmbeddingModel.gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3
        ],
        aggregation=ScoreAggregation.max,
    )

    assert captured["group_by"] is not None
    assert captured["target_vector"] is not None
    assert len(results) == 1
    assert results[0].entity_id == entity_id
    assert results[0].name == "Ada Lovelace"
    # max aggregation over similarities 0.9 / 0.7 / 0.5
    assert results[0].matching_score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_face_grouped_search_drops_unparseable_group_names() -> None:
    class _Query:
        async def near_vector(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(groups={"not-a-uuid": SimpleNamespace(objects=[])})

    class _Collections:
        def get(self, collection_name: str) -> SimpleNamespace:
            assert collection_name == FACE_COLLECTION
            return SimpleNamespace(query=_Query())

    results = await weaviate_search.search_entities_by_faces_vectors(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        [[0.1]],
        vector_name="face_vector",
    )

    assert results == []


@pytest.mark.asyncio
async def test_face_grouped_search_skips_weaviate_for_invalid_inputs() -> None:
    client = SimpleNamespace()  # pyright: ignore[reportArgumentType]

    assert await weaviate_search.search_entities_by_faces_vectors(  # pyright: ignore[reportArgumentType]
        client, [], vector_name="face_vector"
    ) == []
    assert await weaviate_search.search_entities_by_faces_vectors(  # pyright: ignore[reportArgumentType]
        client, [[0.1]], vector_name="face_vector", number_of_groups=0
    ) == []
    assert await weaviate_search.search_entities_by_faces_vectors(  # pyright: ignore[reportArgumentType]
        client, [[0.1]], vector_name="face_vector", objects_per_group=0
    ) == []


# ---------------------------------------------------------------------------
# Weaviate helpers: face similarity search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_face_search_converts_distance_to_similarity() -> None:
    face_id = uuid.uuid4()
    source_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class _Query:
        async def near_vector(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                objects=[
                    SimpleNamespace(
                        uuid=face_id,
                        metadata=SimpleNamespace(distance=0.25),
                        references={
                            "entity": SimpleNamespace(
                                objects=[SimpleNamespace(uuid=entity_id)]
                            ),
                            "source": SimpleNamespace(
                                objects=[SimpleNamespace(uuid=source_id)]
                            ),
                        },
                        properties={
                            "bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4}
                        },
                    )
                ]
            )

    class _Collections:
        def get(self, collection_name: str) -> SimpleNamespace:
            assert collection_name == FACE_COLLECTION
            return SimpleNamespace(query=_Query())

    results = await weaviate_search.search_faces_by_vectors(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        [[0.5, 0.5]],
        vector_name="face_vector",
        limit=3,
    )

    assert captured["limit"] == 3
    assert len(results) == 1
    assert results[0].face_id == face_id
    assert results[0].source_id == source_id
    assert results[0].entity_id == entity_id
    assert results[0].matching_score == pytest.approx(0.75)
    assert results[0].bounding_box is not None
    assert results[0].bounding_box.x == 1
    assert results[0].bounding_box.height == 4


@pytest.mark.asyncio
async def test_face_search_skips_weaviate_for_empty_vectors_or_zero_limit() -> None:
    client = SimpleNamespace()  # pyright: ignore[reportArgumentType]

    assert await weaviate_search.search_faces_by_vectors(  # pyright: ignore[reportArgumentType]
        client, [], vector_name="face_vector"
    ) == []
    assert await weaviate_search.search_faces_by_vectors(  # pyright: ignore[reportArgumentType]
        client, [[0.1]], vector_name="face_vector", limit=0
    ) == []


@pytest.mark.asyncio
async def test_fetch_face_vectors_returns_named_vectors_in_order() -> None:
    first = uuid.uuid4()
    second = uuid.uuid4()
    vector = [0.1, 0.2, 0.3]

    class _Query:
        async def fetch_objects_by_ids(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["ids"] == [str(first), str(second)]
            assert kwargs["include_vector"] == ["face_vector"]
            return SimpleNamespace(
                objects=[
                    SimpleNamespace(vector={"face_vector": vector}),
                    SimpleNamespace(vector={"face_vector": None}),
                ]
            )

    class _Collections:
        def get(self, collection_name: str) -> SimpleNamespace:
            assert collection_name == FACE_COLLECTION
            return SimpleNamespace(query=_Query())

    vectors = await weaviate_search.fetch_face_vectors(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        [first, second],
        vector_name="face_vector",
    )

    assert vectors == [vector]


@pytest.mark.asyncio
async def test_fetch_face_vectors_empty_ids_skips_weaviate() -> None:
    assert await weaviate_search.fetch_face_vectors(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        [],
        vector_name="face_vector",
    ) == []


# ---------------------------------------------------------------------------
# Search service: entity search (text + face fusion)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entity_search_returns_empty_for_missing_query_signals() -> None:
    response = await search_service.search_entities(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        SearchEntitiesQuery(),
    )

    assert response.items == []
    assert response.total_count == 0
    assert response.limit == 20
    assert response.after_id is None


@pytest.mark.asyncio
async def test_entity_search_text_only_uses_bm25(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entity_id = uuid.uuid4()
    captured: dict[str, object] = {}

    async def fake_bm25_search(
        _client: object, query: list[str], *, limit: int
    ) -> list[SearchEntitiesResult]:
        captured["query"] = query
        captured["limit"] = limit
        return [_entity_result(entity_id, 3.0)]

    monkeypatch.setattr(
        search_service, "search_entities_by_names_or_aliases", fake_bm25_search
    )

    response = await search_service.search_entities(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        SearchEntitiesQuery(q=["Ada"], limit=7),
    )

    assert captured["limit"] == 7
    assert len(response.items) == 1
    assert response.items[0].entity_id == entity_id
    assert response.total_count == 1
    assert response.after_id == entity_id
    assert response.limit == 7


@pytest.mark.asyncio
async def test_entity_search_face_only_fetches_vectors_and_excludes_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    face_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    captured: dict[str, object] = {}

    async def fake_fetch_face_vectors(
        _client: object,
        requested_face_ids: list[uuid.UUID],
        *,
        vector_name: str,
    ) -> list[list[float]]:
        assert requested_face_ids == [face_id]
        assert vector_name in FACE_VECTOR_BY_MODEL.values()
        return [[0.1, 0.2]]

    async def fake_grouped_search(
        _client: object,
        *,
        query_vectors: list[list[float]],
        vector_name: str,
        excluded_face_ids: Sequence[uuid.UUID],
        number_of_groups: int,
    ) -> list[SearchEntitiesResult]:
        captured["vector_name"] = vector_name
        captured["excluded_face_ids"] = excluded_face_ids
        captured["number_of_groups"] = number_of_groups
        return [_entity_result(entity_id, 0.9)]

    monkeypatch.setattr(search_service, "fetch_face_vectors", fake_fetch_face_vectors)
    monkeypatch.setattr(
        search_service,
        "search_entities_by_faces_vectors",
        fake_grouped_search,
    )

    response = await search_service.search_entities(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        SearchEntitiesQuery(q_face_id=[face_id], limit=4),
    )

    assert captured["excluded_face_ids"] == [face_id]
    assert captured["number_of_groups"] == 4
    assert len(response.items) == 1
    assert response.items[0].entity_id == entity_id


@pytest.mark.asyncio
async def test_entity_search_missing_reference_vectors_falls_back_to_text_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_face_vectors(
        _client: object, _face_ids: list[uuid.UUID], *, vector_name: str
    ) -> list[list[float]]:
        del vector_name
        return []

    grouped_calls: list[dict[str, object]] = []

    async def fake_grouped_search(
        _client: object,
        *,
        query_vectors: list[list[float]],
        **_kwargs: object,
    ) -> list[SearchEntitiesResult]:
        # Mirror the real guard: empty vectors short-circuit without Weaviate.
        grouped_calls.append({"query_vectors": query_vectors})
        return []

    async def fake_bm25_search(
        _client: object, query: list[str], *, limit: int
    ) -> list[SearchEntitiesResult]:
        captured["query"] = query
        captured["limit"] = limit
        return [_entity_result(uuid.uuid4(), 1.0)]

    monkeypatch.setattr(search_service, "fetch_face_vectors", fake_fetch_face_vectors)
    monkeypatch.setattr(
        search_service,
        "search_entities_by_faces_vectors",
        fake_grouped_search,
    )
    monkeypatch.setattr(
        search_service, "search_entities_by_names_or_aliases", fake_bm25_search
    )

    response = await search_service.search_entities(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        SearchEntitiesQuery(q=["Ada"], q_face_id=[uuid.uuid4()]),
    )

    assert len(response.items) == 1
    assert "query" in captured  # BM25 branch ran
    assert grouped_calls[0]["query_vectors"] == []  # face branch short-circuited


# ---------------------------------------------------------------------------
# Search service: reciprocal rank fusion
# ---------------------------------------------------------------------------


def test_fuse_entity_results_ranks_shared_entities_first() -> None:
    first_id = uuid.uuid4()
    shared_id = uuid.uuid4()

    fused = search_service._fuse_entity_results(  # pyright: ignore[reportPrivateUsage]
        [
            [_entity_result(first_id, 1000.0), _entity_result(shared_id, 1.0)],
            [_entity_result(shared_id, 0.2)],
        ]
    )

    assert [item.entity_id for item in fused] == [shared_id, first_id]
    assert all(item.matching_score < 1 for item in fused)


def test_fuse_entity_results_returns_single_list_unchanged() -> None:
    first_id = uuid.uuid4()
    ranked = [_entity_result(first_id, 5.0)]

    fused = search_service._fuse_entity_results(  # pyright: ignore[reportPrivateUsage]
        [[], ranked]
    )

    assert [item.entity_id for item in fused] == [first_id]
    assert fused[0].matching_score == 5.0


def test_fuse_entity_results_handles_all_empty_lists() -> None:
    assert search_service._fuse_entity_results([[], []]) == []  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Search service: face similarity search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_face_search_returns_empty_when_reference_vectors_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_face_vectors(
        _client: object, _face_ids: list[uuid.UUID], *, vector_name: str
    ) -> list[list[float]]:
        del vector_name
        return []

    monkeypatch.setattr(search_service, "fetch_face_vectors", fake_fetch_face_vectors)

    response = await search_service.search_faces(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        FaceSearchQuery(face_ids=[uuid.uuid4()]),
    )

    assert response.items == []
    assert response.total_count == 0
    assert response.after_id is None


@pytest.mark.asyncio
async def test_face_search_excludes_reference_faces_and_paginates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_id = uuid.uuid4()
    matched_id = uuid.uuid4()
    captured: dict[str, object] = {}

    async def fake_fetch_face_vectors(
        _client: object,
        requested_face_ids: list[uuid.UUID],
        *,
        vector_name: str,
    ) -> list[list[float]]:
        assert requested_face_ids == [reference_id]
        assert vector_name in FACE_VECTOR_BY_MODEL.values()
        return [[0.9, 0.1]]

    async def fake_face_search(
        _client: object,
        _query_vectors: list[list[float]],
        *,
        vector_name: str,
        excluded_face_ids: Sequence[uuid.UUID],
        limit: int,
    ) -> list[FaceSearchResult]:
        captured["vector_name"] = vector_name
        captured["excluded_face_ids"] = excluded_face_ids
        captured["limit"] = limit
        return [
            FaceSearchResult(
                face_id=matched_id,
                matching_score=0.8,
            )
        ]

    monkeypatch.setattr(search_service, "fetch_face_vectors", fake_fetch_face_vectors)
    monkeypatch.setattr(search_service, "search_faces_by_vectors", fake_face_search)

    response = await search_service.search_faces(
        SimpleNamespace(),  # pyright: ignore[reportArgumentType]
        FaceSearchQuery(face_ids=[reference_id], limit=9),
    )

    assert captured["excluded_face_ids"] == [reference_id]
    assert captured["limit"] == 9
    assert len(response.items) == 1
    assert response.items[0].face_id == matched_id
    assert response.total_count == 1
    assert response.after_id == matched_id
    assert response.limit == 9
