"""Typed access to Pydantic's experimental ``MISSING`` sentinel.

Pydantic requires the exact sentinel instance in model annotations at runtime.
Static type checkers, however, cannot use that value as a union member.  This
module exposes a marker class while type checking and the original sentinel at
runtime, preserving Pydantic's omission and JSON-schema behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeIs


if TYPE_CHECKING:
    class MissingType:
        """Static representation of Pydantic's missing value."""

    MISSING = MissingType()
else:
    from pydantic.experimental.missing_sentinel import MISSING

    MissingType = MISSING


def is_missing(value: object) -> TypeIs[MissingType]:
    """Return whether *value* is Pydantic's missing sentinel."""
    return value is MISSING


def missing_to_none[T](value: T | MissingType) -> T | None:
    """Convert a possibly missing value into a conventional optional value."""
    if is_missing(value):
        return None
    return value


__all__ = ["MISSING", "MissingType", "is_missing", "missing_to_none"]
