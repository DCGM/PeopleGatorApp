from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from people_gator_api.routes.v1.media import router
from people_gator_api.schemas.common import GenericListResponse
from people_gator_api.schemas.entities import (
    EntityListFilter,
    EntityListRequest,
    EntityResponse,
)
from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.mentions import (
    TextMentionListFilter,
    TextMentionListResponse,
    TextMentionListRequest,
    TextMentionResponse,
)
from people_gator_api.schemas.pero import (
    PageLayoutModel,
    RegionLayoutModel,
    TextLineModel,
)
from people_gator_api.services.crud_services.text_mention_span_service import (
    _TextMentionText,  # pyright: ignore[reportPrivateUsage]
    _fetch_text_mentions,  # pyright: ignore[reportPrivateUsage]
    _match_text_mention_spans,  # pyright: ignore[reportPrivateUsage]
)


def _line(line_id: str, transcription: str, index: int) -> TextLineModel:
    return TextLineModel(
        id=line_id,
        baseline=[],
        polygon=[],
        heights=[],
        transcription=transcription,
        index=index,
    )


def _layout(*lines: TextLineModel) -> PageLayoutModel:
    return PageLayoutModel(
        id="page-1",
        page_size=(1000, 2000),
        regions=[
            RegionLayoutModel(
                id="region-1",
                polygon=[],
                lines=list(lines),
            )
        ],
        reading_order={"region-1": 0},
    )


def test_fuzzy_text_mention_spans_are_word_aligned_and_can_cross_lines() -> None:
    ada_mention_id = uuid.uuid4()
    alice_mention_id = uuid.uuid4()
    ada_entity_id = uuid.uuid4()
    alice_entity_id = uuid.uuid4()
    layout = _layout(
        _line("line-1", "Prefix Ada", 0),
        _line("line-2", "Lovelace, and Alicf.", 1),
    )
    mentions = [
        _TextMentionText(
            ada_mention_id,
            ada_entity_id,
            EntityType.person,
            "Ada Lovelace",
        ),
        _TextMentionText(
            alice_mention_id,
            alice_entity_id,
            EntityType.person,
            "Alice",
        ),
    ]

    spans = _match_text_mention_spans(layout, mentions)

    assert [span.mention_id for span in spans] == [
        ada_mention_id,
        alice_mention_id,
    ]
    assert [span.entity_id for span in spans] == [ada_entity_id, alice_entity_id]
    assert spans[0].entity_type is EntityType.person
    assert spans[0].start_line_id == "line-1"
    assert spans[0].end_line_id == "line-2"
    assert spans[0].start_character == 7
    assert spans[0].end_character == 8
    assert layout.regions[0].lines[0].transcription[7:] == "Ada"
    assert layout.regions[0].lines[1].transcription[:8] == "Lovelace"

    assert spans[1].start_line_id == "line-2"
    assert spans[1].end_line_id == "line-2"
    assert spans[1].start_character == 14
    assert spans[1].end_character == 19
    assert layout.regions[0].lines[1].transcription[14:19] == "Alicf"


def test_text_mention_name_matches_every_ocr_appearance() -> None:
    mention_id = uuid.uuid4()
    layout = _layout(_line("line-1", "Ada met Ada.", 0))
    mention = _TextMentionText(
        mention_id,
        uuid.uuid4(),
        EntityType.person,
        "Ada",
    )

    spans = _match_text_mention_spans(layout, [mention])

    assert [span.mention_id for span in spans] == [mention_id, mention_id]
    assert [(span.start_character, span.end_character) for span in spans] == [
        (0, 3),
        (8, 11),
    ]


def test_text_mention_spans_do_not_cross_layout_regions() -> None:
    layout = PageLayoutModel(
        id="page-1",
        page_size=(1000, 2000),
        regions=[
            RegionLayoutModel(
                id="region-1",
                polygon=[],
                lines=[_line("line-1", "Ada", 0)],
            ),
            RegionLayoutModel(
                id="region-2",
                polygon=[],
                lines=[_line("line-2", "Lovelace", 0)],
            ),
        ],
        reading_order={"region-1": 0, "region-2": 1},
    )

    spans = _match_text_mention_spans(
        layout,
        [
            _TextMentionText(
                uuid.uuid4(),
                uuid.uuid4(),
                EntityType.person,
                "Ada Lovelace",
            )
        ],
    )

    assert spans == []


@pytest.mark.asyncio
async def test_fetch_text_mentions_uses_persistence_contracts() -> None:
    page_source_id = uuid.uuid4()
    mention_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    unassigned_mention_id = uuid.uuid4()
    mention_queries: list[TextMentionListRequest] = []
    entity_queries: list[EntityListRequest] = []

    class _TextMentions:
        async def list(self, query: TextMentionListRequest) -> TextMentionListResponse:
            mention_queries.append(query)
            return TextMentionListResponse(
                items=[
                    TextMentionResponse(
                        mention_id=mention_id,
                        name="Ada Lovelace",
                        context=None,
                        entity_id=entity_id,
                        source_id=page_source_id,
                    ),
                    TextMentionResponse(
                        mention_id=unassigned_mention_id,
                        name="Unassigned",
                        context=None,
                        entity_id=None,
                        source_id=page_source_id,
                    ),
                ],
                limit=100,
            )

    class _Entities:
        async def list(
            self, query: EntityListRequest
        ) -> GenericListResponse[EntityResponse]:
            entity_queries.append(query)
            return GenericListResponse[EntityResponse](
                items=[
                    EntityResponse(
                        entity_id=entity_id,
                        entity_type=EntityType.person,
                        name="Ada Lovelace",
                        user_id=uuid.uuid4(),
                    )
                ],
                limit=1,
            )

    mentions = await _fetch_text_mentions(
        SimpleNamespace(  # pyright: ignore[reportArgumentType]
            text_mentions=_TextMentions(),
            entities=_Entities(),
        ),
        page_source_id,
    )

    assert mentions == [
        _TextMentionText(
            mention_id,
            entity_id,
            EntityType.person,
            "Ada Lovelace",
        )
    ]
    assert len(mention_queries) == 1
    assert len(entity_queries) == 1
    mention_filter = mention_queries[0].filter_
    entity_filter = entity_queries[0].filter_
    assert isinstance(mention_filter, TextMentionListFilter)
    assert isinstance(entity_filter, EntityListFilter)
    assert mention_filter.source_id == [page_source_id]
    assert entity_filter.entity_id == [entity_id]


def test_text_mention_span_route_requires_page_source_id() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]

    assert "get" in paths["/pages/{page_source_id}/text-mentions-spans"]
    assert "/pages/lookup/text-mentions-spans" not in paths
    assert "/pages/{page_source_id}/entity-spans" not in paths
