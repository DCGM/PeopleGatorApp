from __future__ import annotations

import uuid

from fastapi import FastAPI

from people_gator_api.routes.v1.page_layouts import router
from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.pero import (
    PageLayoutModel,
    RegionLayoutModel,
    TextLineModel,
)
from people_gator_api.services.crud_services.entity_span_service import (
    _EntityText,
    _match_entity_spans,
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


def test_fuzzy_entity_spans_are_word_aligned_and_can_cross_lines() -> None:
    ada_id = uuid.uuid4()
    alice_id = uuid.uuid4()
    layout = _layout(
        _line("line-1", "Prefix Ada", 0),
        _line("line-2", "Lovelace, and Alicf.", 1),
    )
    entities = [
        _EntityText(ada_id, EntityType.person, ("Ada Lovelace",)),
        _EntityText(alice_id, EntityType.person, ("Alice",)),
    ]

    spans = _match_entity_spans(layout, entities)

    assert [span.entity_id for span in spans] == [ada_id, alice_id]
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


def test_entity_aliases_match_every_occurrence_without_duplicate_spans() -> None:
    entity_id = uuid.uuid4()
    layout = _layout(_line("line-1", "Ada met Ada.", 0))
    entity = _EntityText(
        entity_id,
        EntityType.person,
        ("Ada Lovelace", "Ada"),
    )

    spans = _match_entity_spans(layout, [entity])

    assert [(span.start_character, span.end_character) for span in spans] == [
        (0, 3),
        (8, 11),
    ]


def test_entity_spans_do_not_cross_layout_regions() -> None:
    entity_id = uuid.uuid4()
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

    spans = _match_entity_spans(
        layout,
        [_EntityText(entity_id, EntityType.person, ("Ada Lovelace",))],
    )

    assert spans == []


def test_entity_span_routes_parallel_page_layout_routes() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]

    assert "get" in paths["/pages/{page_source_id}/entity-spans"]
    assert "get" in paths["/pages/object/entity-spans"]
