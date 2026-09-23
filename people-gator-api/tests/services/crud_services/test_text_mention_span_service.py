from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from people_gator_api.routes.v1.media import router
from people_gator_api.schemas.enums import EntityType
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
from people_gator_api.weaviate_schema import (
    TEXT_MENTION_COLLECTION,
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
async def test_fetch_text_mentions_uses_source_link_and_linked_entity_type() -> None:
    page_source_id = uuid.uuid4()
    mention_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class _Query:
        async def fetch_objects(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                objects=[
                    SimpleNamespace(
                        uuid=mention_id,
                        properties={"name": "Ada Lovelace"},
                        references={
                            "entity": SimpleNamespace(
                                objects=[
                                    SimpleNamespace(
                                        uuid=entity_id,
                                        properties={"entity_type": "person"},
                                    )
                                ]
                            )
                        },
                    )
                ]
            )

    class _Collections:
        def get(self, name: str) -> SimpleNamespace:
            assert name == TEXT_MENTION_COLLECTION
            return SimpleNamespace(query=_Query())

    mentions = await _fetch_text_mentions(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
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
    assert captured["return_properties"] == ["name"]
    assert captured["return_references"] is not None


def test_text_mention_span_route_requires_page_source_id() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]

    assert "get" in paths["/pages/{page_source_id}/text-mentions-spans"]
    assert "/pages/lookup/text-mentions-spans" not in paths
    assert "/pages/{page_source_id}/entity-spans" not in paths
