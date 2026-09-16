"""Unit tests for the pure-Weaviate archive search helpers."""

from __future__ import annotations

import uuid

import pytest

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.services.weaviate_service.archive_search import (
    ArchiveCandidate,
    _as_uuid,
    _deduplicate,
    _fuse_rankings,
    _group_count,
    _group_name_to_uuid,
    _linked_mention_filters,
    _source_candidate_from_properties,
    _source_scope_filters,
)


def test_as_uuid_parses_valid_uuid() -> None:
    value = uuid.uuid4()
    assert _as_uuid(str(value)) == value


def test_as_uuid_rejects_free_text() -> None:
    assert _as_uuid("Karel Hynek Mácha") is None


def test_group_name_to_uuid_extracts_trailing_uuid() -> None:
    source_id = uuid.uuid4()
    group_name = f"weaviate://localhost/Source/{source_id}"
    assert _group_name_to_uuid(group_name) == source_id


def test_group_name_to_uuid_rejects_plain_text() -> None:
    assert _group_name_to_uuid("not-a-uuid") is None


def test_group_count_scales_with_query_length() -> None:
    assert _group_count("a") == 5
    assert _group_count("x" * 12) == 12
    assert _group_count("x" * 500) == 20


def test_fuse_rankings_prefers_hits_present_in_multiple_arms() -> None:
    first = uuid.uuid4()
    second = uuid.uuid4()
    third = uuid.uuid4()
    fused = _fuse_rankings(
        [
            [first, second],
            [second, third],
        ],
    )
    assert fused[0][0] == second
    scores = dict(fused)
    assert scores[second] > scores[first]
    assert scores[second] > scores[third]


def test_fuse_rankings_breaks_ties_deterministically() -> None:
    first = uuid.UUID(int=1)
    second = uuid.UUID(int=2)
    fused = _fuse_rankings([[first], [second]])
    assert [source_id for source_id, _score in fused] == [first, second]


def test_deduplicate_preserves_first_occurrence_order() -> None:
    first = uuid.uuid4()
    second = uuid.uuid4()
    assert _deduplicate([first, second, first]) == [first, second]


def test_source_scope_filters_none_without_source() -> None:
    assert _source_scope_filters(None) is None


def test_linked_mention_filters_single_entity_has_no_wrapper() -> None:
    entity_id = uuid.uuid4()
    filters = _linked_mention_filters([entity_id], None)
    assert filters is not None


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
