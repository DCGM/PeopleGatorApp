"""Resolve stored text mentions to word-aligned OCR layout spans."""

from __future__ import annotations

from datetime import datetime
import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from people_gator_api.persistence.contracts import Database
from people_gator_api.schemas.entities import EntityListFilter, EntityListRequest
from people_gator_api.schemas.enums import EntityType, EntityLinkState
from people_gator_api.schemas.missing import MISSING, MissingType
from people_gator_api.schemas.mentions import (
    TextMentionListFilter,
    TextMentionListRequest,
    TextMentionResponse,
)
from people_gator_api.schemas.pero import PageLayoutModel, TextMentionSpanModel
from people_gator_api.media.page_layout import get_page_layout
from people_gator_api.utils.opentelemetry import trace


_TEXT_MENTION_PAGE_SIZE = 100
_MIN_SIMILARITY = 0.8
_WORD_PATTERN = re.compile(r"[^\W_]+(?:[’'\-][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True, slots=True)
class _TextMentionText:
    mention_id: uuid.UUID
    entity_id: uuid.UUID
    entity_type: EntityType | None
    name: str
    entity_link_state: EntityLinkState | None = None
    entity_link_verified_by_user_id: uuid.UUID | None = None
    entity_link_verified_at: datetime | None = None


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
    database: Database,
    page_source_id: uuid.UUID,
    *,
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    entity_link_state: list[EntityLinkState] | MissingType = MISSING,
    filter_: TextMentionListFilter | None = None,
) -> list[TextMentionSpanModel]:
    """Return fuzzy, word-aligned spans for a page's stored text mentions."""
    layout = await get_page_layout(
        library,
        document_id,
        page_id,
    )
    mentions = await _fetch_text_mentions(database, page_source_id, entity_link_state, filter_)
    return _match_text_mention_spans(layout, mentions)


async def _fetch_text_mentions(
    database: Database,
    page_source_id: uuid.UUID,
    entity_link_state: list[EntityLinkState] | MissingType = MISSING,
    filter_: TextMentionListFilter | None = None,
) -> list[_TextMentionText]:
    """Fetch every text mention linked to the requested page source."""
    mentions: list[_TextMentionText] = []
    cursor: str | None = None
    while True:
        response = await database.text_mentions.list(
            TextMentionListRequest(
                filter_=(filter_.model_copy(update={"source_id": [page_source_id]}) if filter_ is not None else TextMentionListFilter(source_id=[page_source_id], entity_link_state=entity_link_state)),
                limit=_TEXT_MENTION_PAGE_SIZE,
                cursor=cursor,
            )
        )
        assigned: list[tuple[TextMentionResponse, uuid.UUID]] = []
        for item in response.items:
            if item.entity_id is not None:
                assigned.append((item, item.entity_id))
        entity_ids = list(dict.fromkeys(entity_id for _item, entity_id in assigned))
        entity_types: dict[uuid.UUID, EntityType] = {}
        if entity_ids:
            entities = await database.entities.list(
                EntityListRequest(
                    filter_=EntityListFilter(entity_id=entity_ids),
                    limit=len(entity_ids),
                )
            )
            entity_types = {
                entity.entity_id: entity.entity_type for entity in entities.items
            }
        mentions.extend(
            _TextMentionText(
                mention_id=item.mention_id,
                entity_id=entity_id,
                entity_type=entity_types.get(entity_id),
                name=item.name,
                entity_link_state=item.entity_link_state,
                entity_link_verified_by_user_id=item.entity_link_verified_by_user_id,
                entity_link_verified_at=item.entity_link_verified_at,
            )
            for item, entity_id in assigned
        )
        if response.cursor is None:
            break
        if response.cursor == cursor:
            raise RuntimeError("Text mention pagination did not advance")
        cursor = response.cursor
    return mentions


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
                        entity_link_state=mention.entity_link_state,
                        entity_link_verified_by_user_id=mention.entity_link_verified_by_user_id,
                        entity_link_verified_at=mention.entity_link_verified_at,
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
