"""Allowlisted keyset ordering for PostgreSQL lists and bounded searches.

A sort is a sequence of :class:`SortKey` expressions ending in the canonical
UUID ascending. Unknown (NULL) values follow every known value in both
directions. Text keys compare ``lower(unaccent(text))`` and then the exact text,
both with the byte-wise ``C`` collation, so PostgreSQL and the Python sorter used
for bounded search candidates agree on Unicode code-point order.

List cursors carry every key value of the last returned row plus a fingerprint
of the complete request, which includes its filters, field and direction. A
continuation is therefore valid only for the same effective order. Keyset
continuation does not depend on the cursor row still existing; concurrent edits
to sortable values can move a row across the boundary, so no snapshot is promised.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast as type_cast

from sqlalchemy import ColumnElement, and_, case, false, func, or_, select

from people_gator_api.schemas.sorting import SortDirection

KeyKind = Literal["text", "uuid", "datetime", "number"]

# Explicit, documented assignment-state order; unassigned is unknown and last.
LINK_STATE_RANK = {"verified": 0, "manual": 1, "automatic": 2}


@dataclass(frozen=True)
class SortKey:
    expression: ColumnElement[Any]
    kind: KeyKind
    descending: bool = False


@dataclass(frozen=True)
class SortSpec:
    """The effective order of one request: its label and complete key list."""

    label: str
    keys: tuple[SortKey, ...]


def normalized_text(value: ColumnElement[Any]) -> ColumnElement[Any]:
    return func.lower(func.demo_unaccent(value))


def text_keys(
    normalized: ColumnElement[Any], exact: ColumnElement[Any], descending: bool
) -> list[SortKey]:
    """Case/accent-insensitive order, then exact recorded text."""
    return [
        SortKey(normalized.collate("C"), "text", descending),
        SortKey(exact.collate("C"), "text", descending),
    ]


def link_state_rank(state: ColumnElement[Any]) -> ColumnElement[Any]:
    return case(
        *((state == name, rank) for name, rank in LINK_STATE_RANK.items()),
        else_=None,
    )


def build_spec(
    field: str | None,
    direction: SortDirection,
    identity: ColumnElement[Any],
    builders: dict[str, Callable[[bool], list[SortKey]]],
    identity_field: str,
) -> SortSpec:
    """Resolve an allowlisted field to keys and append the identity tie-breaker.

    Sorting by the identity itself may be descending; it is its own tie-breaker.
    """
    descending = direction == SortDirection.DESC
    keys: list[SortKey] = []
    identity_descending = False
    if field == identity_field:
        identity_descending = descending
    elif field is not None:
        builder = builders.get(field)
        if builder is None:
            raise ValueError(f"sorting by '{field}' is not supported for this resource")
        keys = builder(descending)
    return SortSpec(
        f"{field or 'default'}:{direction.value}",
        (*keys, SortKey(identity, "uuid", identity_descending)),
    )


def order_by(spec: SortSpec) -> list[Any]:
    return [
        (key.expression.desc() if key.descending else key.expression.asc()).nulls_last()
        for key in spec.keys
    ]


def after_predicate(spec: SortSpec, values: Sequence[object]) -> ColumnElement[bool]:
    """Rows strictly after ``values`` in ``spec`` order, with NULLs last."""
    clauses: list[ColumnElement[bool]] = []
    equal_prefix: list[ColumnElement[bool]] = []
    for key, value in zip(spec.keys, values, strict=True):
        expression = key.expression
        if value is None:
            # Nothing known follows an unknown value; only later NULL ties do.
            strictly_after: ColumnElement[bool] = false()
            equal = expression.is_(None)
        else:
            beyond = expression < value if key.descending else expression > value
            strictly_after = or_(expression.is_(None), beyond)
            equal = expression == value
        clauses.append(and_(*equal_prefix, strictly_after))
        equal_prefix.append(equal)
    return or_(*clauses)


def key_values(spec: SortSpec, row: Sequence[object]) -> list[object]:
    return list(row[: len(spec.keys)])


def _encode_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return float(type_cast(Any, value))


def _decode_value(kind: KeyKind, value: object) -> object:
    if value is None:
        return None
    if kind == "uuid" and isinstance(value, str):
        return uuid.UUID(value)
    if kind == "datetime" and isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    if kind == "text" and isinstance(value, str):
        return value
    if kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    raise ValueError


def encode_keyset(spec: SortSpec, values: Sequence[object], fingerprint: str) -> str:
    payload = json.dumps(
        {"v": 2, "q": fingerprint, "s": spec.label, "k": [_encode_value(v) for v in values]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_keyset(
    cursor: str | None, spec: SortSpec, fingerprint: str
) -> list[object] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded: object = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(decoded, dict):
            raise ValueError
        payload = type_cast(dict[str, object], decoded)
        raw = payload.get("k")
        if (
            payload.get("v") != 2
            or payload.get("q") != fingerprint
            or payload.get("s") != spec.label
            or not isinstance(raw, list)
            or len(type_cast(list[object], raw)) != len(spec.keys)
        ):
            raise ValueError
        values = [
            _decode_value(key.kind, value)
            for key, value in zip(spec.keys, type_cast(list[object], raw), strict=True)
        ]
        if values[-1] is None:
            raise ValueError
        return values
    except (TypeError, ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("cursor is malformed or belongs to a different query") from exc


def keyset_page[T](
    rows: Sequence[tuple[T, Sequence[object]]],
    limit: int,
    spec: SortSpec,
    fingerprint: str,
) -> tuple[list[T], str | None]:
    """Trim a ``limit + 1`` fetch and encode the continuation of the last row."""
    if limit == 0:
        return [], None
    page = list(rows[:limit])
    cursor = (
        encode_keyset(spec, page[-1][1], fingerprint)
        if len(rows) > limit and page
        else None
    )
    return [item for item, _ in page], cursor


def python_sort_key(spec: SortSpec, values: Sequence[object]) -> tuple[object, ...]:
    """Mirror :func:`order_by` for bounded candidates sorted in memory."""
    parts: list[object] = []
    for key, value in zip(spec.keys, values, strict=True):
        if value is None:
            parts.append((1, 0))
            continue
        comparable: object = value.int if isinstance(value, uuid.UUID) else value
        parts.append((0, _Reversed(comparable) if key.descending else comparable))
    return tuple(parts)


class _Reversed:
    __slots__ = ("value",)

    def __init__(self, value: object) -> None:
        self.value = value

    def __lt__(self, other: "_Reversed") -> bool:
        return type_cast(Any, other.value) < type_cast(Any, self.value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Reversed) and self.value == other.value


__all__ = [
    "LINK_STATE_RANK",
    "SortKey",
    "SortSpec",
    "Builders",
    "after_predicate",
    "build_spec",
    "decode_keyset",
    "encode_keyset",
    "key_values",
    "keyset_page",
    "link_state_rank",
    "normalized_text",
    "order_by",
    "python_sort_key",
    "sort_columns",
    "sort_ranked",
    "text_keys",
]


Builders = dict[str, Callable[[bool], list[SortKey]]]


def sort_columns(spec: SortSpec) -> list[ColumnElement[Any]]:
    return [key.expression.label(f"sort_key_{index}") for index, key in enumerate(spec.keys)]


def sort_ranked(
    ranked: list[tuple[uuid.UUID, float, float | None, float | None]],
    spec: SortSpec | None,
    direction: SortDirection,
    values: dict[uuid.UUID, Sequence[object]],
) -> list[tuple[uuid.UUID, float, float | None, float | None]]:
    """Order a complete bounded candidate set before it is paginated.

    ``spec`` None means relevance: final score, then identity ascending.
    """
    if spec is None:
        if direction == SortDirection.DESC:
            return ranked
        return sorted(ranked, key=lambda item: (item[1], item[0].int))
    return sorted(ranked, key=lambda item: python_sort_key(spec, values[item[0]]))


def source_context_keys(source_id: ColumnElement[Any], descending: bool) -> list[SortKey]:
    """Library, archive document and page of an annotation's source; images are unknown."""
    from .models import Document, Page  # models import nothing from this module

    pages = Page.__table__.alias("context_pages")
    documents = Document.__table__.alias("context_documents")

    def lookup(column_name: str) -> ColumnElement[Any]:
        return func.coalesce(
            select_scalar(pages, column_name, source_id),
            select_scalar(documents, column_name, source_id),
        )

    library = lookup("library")
    return [
        *text_keys(normalized_text(library), library, descending),
        SortKey(lookup("document_id"), "uuid", descending),
        SortKey(select_scalar(pages, "page_id", source_id), "uuid", descending),
    ]


def select_scalar(table: Any, column_name: str, source_id: ColumnElement[Any]) -> ColumnElement[Any]:
    return select(table.c[column_name]).where(table.c.id == source_id).scalar_subquery()


def annotation_builders(model: Any) -> Builders:
    """Sort keys shared by faces and text mentions."""
    return {
        "last_touched_at": lambda desc: [SortKey(model.last_touched_at, "datetime", desc)],
        "link_state": lambda desc: [SortKey(link_state_rank(model.entity_link_state), "number", desc)],
        "source": lambda desc: source_context_keys(model.source_id, desc),
    }
