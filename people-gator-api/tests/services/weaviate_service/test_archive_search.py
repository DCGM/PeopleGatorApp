"""Unit tests for the pure-Weaviate archive search helpers."""

from __future__ import annotations

import uuid

import pytest

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.services.weaviate_service.archive_search import (
    ArchiveCandidate,
    _as_uuid,
    _deduplicate,
    _entity_source_ranking,
    _source_candidate_from_properties,
)
from people_gator_api.services.weaviate_service.db_schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
    TEXT_MENTION_COLLECTION,
)


def test_as_uuid_parses_valid_uuid() -> None:
    value = uuid.uuid4()
    assert _as_uuid(str(value)) == value


def test_as_uuid_rejects_free_text() -> None:
    assert _as_uuid("Karel Hynek Mácha") is None


def test_deduplicate_preserves_first_occurrence_order() -> None:
    first = uuid.uuid4()
    second = uuid.uuid4()
    assert _deduplicate([first, second, first]) == [first, second]


@pytest.mark.asyncio
async def test_entity_source_ranking_combines_face_and_text_mention_paths() -> None:
    first_entity = uuid.UUID(int=1)
    second_entity = uuid.UUID(int=2)
    first_source = uuid.UUID(int=3)
    second_source = uuid.UUID(int=4)

    def reference(object_id: uuid.UUID) -> object:
        return type(
            "Reference",
            (),
            {"objects": [type("Linked", (), {"uuid": object_id})()]},
        )()

    def appearance(entity_id: uuid.UUID, source_id: uuid.UUID) -> object:
        return type(
            "Appearance",
            (),
            {
                "uuid": uuid.uuid4(),
                "references": {
                    "entity": reference(entity_id),
                    "source": reference(source_id),
                },
            },
        )()

    requested_collections: list[str] = []

    class _Query:
        def __init__(self, collection_name: str) -> None:
            self.collection_name = collection_name

        async def bm25(self, **kwargs: object) -> object:
            assert self.collection_name == ENTITY_COLLECTION
            assert kwargs["query"] == "Ada"
            assert kwargs["query_properties"] == ["name", "aliases"]
            return type(
                "Response",
                (),
                {
                    "objects": [
                        type("Entity", (), {"uuid": first_entity})(),
                        type("Entity", (), {"uuid": second_entity})(),
                    ]
                },
            )()

        async def fetch_objects(self, **_kwargs: object) -> object:
            objects = {
                FACE_COLLECTION: [appearance(first_entity, second_source)],
                TEXT_MENTION_COLLECTION: [
                    appearance(first_entity, first_source),
                    appearance(second_entity, first_source),
                ],
            }[self.collection_name]
            return type("Response", (), {"objects": objects})()

    class _Collections:
        def get(self, collection_name: str) -> object:
            requested_collections.append(collection_name)
            return type("Collection", (), {"query": _Query(collection_name)})()

    collections = _Collections()
    client = type("Client", (), {"collections": collections})()

    ranking = await _entity_source_ranking(
        client,  # pyright: ignore[reportArgumentType]
        "Ada",
        None,
    )

    assert ranking == [first_source, second_source]
    assert requested_collections == [
        ENTITY_COLLECTION,
        FACE_COLLECTION,
        TEXT_MENTION_COLLECTION,
    ]


def test_source_candidate_from_page_properties() -> None:
    source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    page_id = uuid.uuid4()
    candidate = _source_candidate_from_properties(
        source_id,
        {
            "source_type": SourceKind.page.value,
            "library": "nkcr",
            "document": str(document_id),
            "page": str(page_id),
        },
    )
    assert candidate is not None
    assert candidate.kind is SourceKind.page
    assert candidate.document_id == document_id
    assert candidate.page_id == page_id


def test_source_candidate_from_document_properties_has_no_page() -> None:
    source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    candidate = _source_candidate_from_properties(
        source_id,
        {
            "source_type": SourceKind.document.value,
            "library": "nkcr",
            "document": str(document_id),
            "page": None,
        },
    )
    assert candidate is not None
    assert candidate.kind is SourceKind.document
    assert candidate.document_id == document_id
    assert candidate.page_id is None


def test_source_candidate_rejects_image_sources() -> None:
    candidate = _source_candidate_from_properties(
        uuid.uuid4(),
        {
            "source_type": SourceKind.image.value,
            "library": None,
            "document": None,
            "page": None,
        },
    )
    assert candidate is None


def test_source_candidate_rejects_non_mapping_properties() -> None:
    assert _source_candidate_from_properties(uuid.uuid4(), "not-a-mapping") is None


def test_candidate_with_matching_score_keeps_identity() -> None:
    source_id = uuid.uuid4()
    document_id = uuid.uuid4()
    candidate = ArchiveCandidate(source_id, SourceKind.page, document_id, None, 0.0)
    scored = candidate.with_matching_score(0.42)
    assert scored.source_id == source_id
    assert scored.document_id == document_id
    assert scored.matching_score == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_search_archive_filters_kind_before_applying_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from people_gator_api.services.weaviate_service import archive_search

    document_source_id = uuid.uuid4()
    page_source_id = uuid.uuid4()
    document = ArchiveCandidate(
        document_source_id,
        SourceKind.document,
        uuid.uuid4(),
        None,
        0.5,
    )
    page = ArchiveCandidate(
        page_source_id,
        SourceKind.page,
        uuid.uuid4(),
        uuid.uuid4(),
        0.4,
    )

    async def rank_sources(
        _client: object,
        _query: str,
        _source_id: uuid.UUID | None,
    ) -> list[uuid.UUID]:
        return [document_source_id, page_source_id]

    async def resolve_sources(
        _client: object,
        _ranked: object,
    ) -> list[ArchiveCandidate]:
        return [document, page]

    monkeypatch.setattr(archive_search, "_entity_source_ranking", rank_sources)
    monkeypatch.setattr(archive_search, "_resolve_source_candidates", resolve_sources)

    results = await archive_search.search_archive(
        object(),  # pyright: ignore[reportArgumentType]
        "Ada",
        source_id=None,
        source_kind=SourceKind.page,
        limit=1,
    )

    assert results == [page]
