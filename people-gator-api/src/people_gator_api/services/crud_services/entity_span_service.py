"""Resolve entity-name occurrences to word-aligned OCR layout spans."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol, cast

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.types import WeaviateField, WeaviateProperties

from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.pero import EntitySpanModel, PageLayoutModel
from people_gator_api.services.crud_services.page_layout_service import get_page_layout
from people_gator_api.services.weaviate_service.db_schema import ENTITY_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    optional_alias_text_array,
    optional_entity_type,
    optional_str,
    reference_id_filter,
)
from people_gator_api.utils.opentelemetry import trace


_ENTITY_PAGE_SIZE = 100
_MIN_SIMILARITY = 0.8
_WORD_PATTERN = re.compile(r"[^\W_]+(?:[’'\-][^\W_]+)*", re.UNICODE)


class _EntityObject(Protocol):
    uuid: uuid.UUID
    properties: WeaviateProperties


@dataclass(frozen=True, slots=True)
class _EntityText:
    entity_id: uuid.UUID
    entity_type: EntityType | None
    mentions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Word:
    region_id: str
    line_id: str
    start_character: int
    end_character: int
    normalized: str


@dataclass(frozen=True, slots=True)
class _Match:
    start_word: int
    end_word: int
    score: float


@trace()
async def get_entity_spans(
    client: WeaviateAsyncClient,
    page_source_id: uuid.UUID,
) -> list[EntitySpanModel]:
    """Return all fuzzy, word-aligned entity spans for one page layout."""
    layout = await get_page_layout(
        client,
        source_id=page_source_id,
        page_path=None,
    )
    entities = await _fetch_mentioned_entities(client, page_source_id)
    return _match_entity_spans(layout, entities)


async def _fetch_mentioned_entities(
    client: WeaviateAsyncClient,
    page_source_id: uuid.UUID,
) -> list[_EntityText]:
    """Fetch every entity directly linked to the requested page source."""
    collection = client.collections.get(ENTITY_COLLECTION)
    entities: list[_EntityText] = []
    after_id: uuid.UUID | None = None
    while True:
        response = await collection.query.fetch_objects(
            filters=reference_id_filter(
                link_on="mentioned_in",
                reference_id=page_source_id,
            ),
            limit=_ENTITY_PAGE_SIZE,
            after=after_id,
            return_properties=["entity_type", "name", "aliases"],
        )
        objects = cast(list[_EntityObject], list(response.objects))
        if not objects:
            break
        entities.extend(_entity_text(item.uuid, item.properties) for item in objects)
        if len(objects) < _ENTITY_PAGE_SIZE:
            break
        next_after_id = objects[-1].uuid
        if next_after_id == after_id:
            raise RuntimeError("Weaviate entity pagination did not advance")
        after_id = next_after_id
    return entities


def _entity_text(
    entity_id: uuid.UUID,
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> _EntityText:
    name = optional_str(properties, "name")
    aliases = optional_alias_text_array(properties, "aliases")
    mentions = tuple(
        value
        for value in dict.fromkeys([name, *aliases])
        if value is not None and value.strip()
    )
    return _EntityText(
        entity_id=entity_id,
        entity_type=optional_entity_type(properties, "entity_type"),
        mentions=mentions,
    )


def _match_entity_spans(
    layout: PageLayoutModel,
    entities: Sequence[_EntityText],
) -> list[EntitySpanModel]:
    words = _layout_words(layout)
    spans: list[tuple[int, EntitySpanModel]] = []
    for entity in entities:
        matches: list[_Match] = []
        normalized_mentions: set[tuple[str, ...]] = set()
        for mention in entity.mentions:
            mention_words = _normalized_words(mention)
            if not mention_words or mention_words in normalized_mentions:
                continue
            normalized_mentions.add(mention_words)
            matches.extend(_mention_matches(words, mention_words))

        for match in _best_non_overlapping(matches):
            first_word = words[match.start_word]
            last_word = words[match.end_word - 1]
            spans.append(
                (
                    match.start_word,
                    EntitySpanModel(
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        start_line_id=first_word.line_id,
                        end_line_id=last_word.line_id,
                        start_character=first_word.start_character,
                        end_character=last_word.end_character,
                    ),
                )
            )
    spans.sort(
        key=lambda item: (
            item[0],
            item[1].start_character,
            item[1].end_character,
            item[1].entity_id,
        )
    )
    return [span for _position, span in spans]


def _layout_words(layout: PageLayoutModel) -> list[_Word]:
    words: list[_Word] = []
    region_positions = {region.id: index for index, region in enumerate(layout.regions)}
    ordered_regions = sorted(
        layout.regions,
        key=lambda region: (
            layout.reading_order.get(region.id, len(layout.regions)),
            region_positions[region.id],
        ),
    )
    for region in ordered_regions:
        line_positions = {line.id: index for index, line in enumerate(region.lines)}
        ordered_lines = sorted(
            region.lines,
            key=lambda line: (
                line.index is None,
                line.index if line.index is not None else line_positions[line.id],
                line_positions[line.id],
            ),
        )
        for line in ordered_lines:
            for word_match in _WORD_PATTERN.finditer(line.transcription):
                words.append(
                    _Word(
                        region_id=region.id,
                        line_id=line.id,
                        start_character=word_match.start(),
                        end_character=word_match.end(),
                        normalized=_normalize(word_match.group()),
                    )
                )
    return words


def _normalized_words(value: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for match in _WORD_PATTERN.finditer(value)
        if (normalized := _normalize(match.group()))
    )


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _mention_matches(
    words: Sequence[_Word],
    mention_words: tuple[str, ...],
) -> list[_Match]:
    target = " ".join(mention_words)
    expected_word_count = len(mention_words)
    window_sizes = range(
        max(1, expected_word_count - 1),
        expected_word_count + 2,
    )
    matches: list[_Match] = []
    for window_size in window_sizes:
        for start_word in range(0, len(words) - window_size + 1):
            end_word = start_word + window_size
            window = words[start_word:end_word]
            if window[0].region_id != window[-1].region_id:
                continue
            candidate = " ".join(word.normalized for word in window)
            length_ratio = min(len(target), len(candidate)) / max(
                len(target), len(candidate)
            )
            if length_ratio < 0.75:
                continue
            score = SequenceMatcher(
                None,
                target,
                candidate,
                autojunk=False,
            ).ratio()
            if score >= _MIN_SIMILARITY:
                matches.append(_Match(start_word, end_word, score))
    return matches


def _best_non_overlapping(matches: Sequence[_Match]) -> list[_Match]:
    """Keep the strongest candidate for each overlapping entity occurrence."""
    accepted: list[_Match] = []
    for match in sorted(
        matches,
        key=lambda item: (
            -item.score,
            -(item.end_word - item.start_word),
            item.start_word,
        ),
    ):
        if any(
            match.start_word < existing.end_word
            and existing.start_word < match.end_word
            for existing in accepted
        ):
            continue
        accepted.append(match)
    return sorted(accepted, key=lambda item: item.start_word)
