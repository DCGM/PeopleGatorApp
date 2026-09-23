"""Resolve stored text mentions to word-aligned OCR layout spans."""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Protocol, cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import QueryReference
from weaviate.collections.classes.internal import CrossReferences
from weaviate.collections.classes.types import WeaviateProperties

from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.pero import PageLayoutModel, TextMentionSpanModel
from people_gator_api.services.crud_services.page_layout_service import get_page_layout
from people_gator_api.weaviate_schema import TEXT_MENTION_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    optional_entity_type,
    reference_id_filter,
    require_reference_uuid,
    require_str,
)
from people_gator_api.utils.opentelemetry import trace


_TEXT_MENTION_PAGE_SIZE = 100
_MIN_SIMILARITY = 0.8
_WORD_PATTERN = re.compile(r"[^\W_]+(?:[’'\-][^\W_]+)*", re.UNICODE)


class _TextMentionObject(Protocol):
    uuid: uuid.UUID
    properties: WeaviateProperties
    references: CrossReferences


@dataclass(frozen=True, slots=True)
class _TextMentionText:
    mention_id: uuid.UUID
    entity_id: uuid.UUID
    entity_type: EntityType | None
    name: str


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
async def get_text_mention_spans(
    client: WeaviateAsyncClient,
    page_source_id: uuid.UUID,
) -> list[TextMentionSpanModel]:
    """Return fuzzy, word-aligned spans for a page's stored text mentions."""
    layout = await get_page_layout(
        client,
        source_id=page_source_id,
        page_path=None,
    )
    mentions = await _fetch_text_mentions(client, page_source_id)
    return _match_text_mention_spans(layout, mentions)


async def _fetch_text_mentions(
    client: WeaviateAsyncClient,
    page_source_id: uuid.UUID,
) -> list[_TextMentionText]:
    """Fetch every text mention linked to the requested page source."""
    collection = client.collections.get(TEXT_MENTION_COLLECTION)
    mentions: list[_TextMentionText] = []
    after_id: uuid.UUID | None = None
    while True:
        response = await collection.query.fetch_objects(
            filters=reference_id_filter(
                link_on="source",
                reference_id=page_source_id,
            ),
            limit=_TEXT_MENTION_PAGE_SIZE,
            after=after_id,
            return_properties=["name"],
            return_references=QueryReference(
                link_on="entity",
                return_properties=["entity_type"],
            ),
        )
        objects = cast(list[_TextMentionObject], list(response.objects))
        if not objects:
            break
        mentions.extend(_text_mention_text(item) for item in objects)
        if len(objects) < _TEXT_MENTION_PAGE_SIZE:
            break
        next_after_id = objects[-1].uuid
        if next_after_id == after_id:
            raise RuntimeError("Weaviate text mention pagination did not advance")
        after_id = next_after_id
    return mentions


def _text_mention_text(item: _TextMentionObject) -> _TextMentionText:
    entity_id = require_reference_uuid(item.references, "entity")
    linked_entities = item.references["entity"].objects
    return _TextMentionText(
        mention_id=item.uuid,
        entity_id=entity_id,
        entity_type=optional_entity_type(
            linked_entities[0].properties,
            "entity_type",
        ),
        name=require_str(item.properties, "name"),
    )


def _match_text_mention_spans(
    layout: PageLayoutModel,
    mentions: Sequence[_TextMentionText],
) -> list[TextMentionSpanModel]:
    words = _layout_words(layout)
    spans: list[tuple[int, TextMentionSpanModel]] = []
    for mention in mentions:
        mention_words = _normalized_words(mention.name)
        if not mention_words:
            continue
        matches = _mention_matches(words, mention_words)

        for match in _best_non_overlapping(matches):
            first_word = words[match.start_word]
            last_word = words[match.end_word - 1]
            spans.append(
                (
                    match.start_word,
                    TextMentionSpanModel(
                        mention_id=mention.mention_id,
                        entity_id=mention.entity_id,
                        entity_type=mention.entity_type,
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
            item[1].mention_id,
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
