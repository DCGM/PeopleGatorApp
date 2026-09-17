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
    _source_scope_filter,
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


def test_source_scope_filter_none_without_source() -> None:
    assert _source_scope_filter(None) is None


def test_source_scope_filter_targets_direct_mentioned_in_reference() -> None:
    assert _source_scope_filter(uuid.uuid4()) is not None


@pytest.mark.asyncio
async def test_entity_source_ranking_follows_direct_links() -> None:
    first_source = uuid.uuid4()
    second_source = uuid.uuid4()
    references = {
        "mentioned_in": type(
            "Reference",
            (),
            {
                "objects": [
                    type("Linked", (), {"uuid": first_source})(),
                    type("Linked", (), {"uuid": second_source})(),
                ]
            },
        )()
    }

    class _Query:
        async def bm25(self, **kwargs: object) -> object:
            assert kwargs["query"] == "Ada"
            assert kwargs["query_properties"] == ["name", "aliases"]
            return type(
                "Response",
                (),
                {
                    "objects": [
                        type("Entity", (), {"references": references})(),
                        type("Entity", (), {"references": references})(),
                    ]
                },
            )()

    collection = type("Collection", (), {"query": _Query()})()
    collections = type(
        "Collections",
        (),
        {"get": lambda self, _name: collection},
    )()
    client = type("Client", (), {"collections": collections})()

    ranking = await _entity_source_ranking(
        client,  # pyright: ignore[reportArgumentType]
        "Ada",
        None,
    )

    assert ranking == [first_source, second_source]


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
