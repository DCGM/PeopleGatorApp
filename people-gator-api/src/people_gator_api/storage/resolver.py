"""Discriminated union of resolver configuration types for SOURCE_SCHEMA.

Each class maps to a ``ResolverType`` enum value and defines the expected
JSONB structure in ``SourceSchema.resolver_config``.

All template fields are validated to contain only ``{placeholder}`` tokens
from a whitelist — no arbitrary Python format strings, no nested braces, no
percent-format — to prevent SSRF and path-traversal attacks at the application
boundary.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from people_gator_api.db.models.enums import ResolverType

# ---------------------------------------------------------------------------
# Template validation helpers
# ---------------------------------------------------------------------------

_ALLOWED_PLACEHOLDERS: dict[str, frozenset[str]] = {
    "db_source_table_row": frozenset({"principal_id"}),
    "s3_image": frozenset({"principal_id", "file_id"}),
    "http_image": frozenset({"file_name"}),
    "fsspec_pagexml": frozenset({"page_id", "library", "document_id"}),
    "fsspec_image": frozenset({"library", "document_id", "page_id"}),
    "s3_table": frozenset({"text_type"}),
}

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
# Guard against nested braces or format spec directives (e.g. {!r}, {:04d}).
_UNSAFE_TEMPLATE_RE = re.compile(r"\{[^}]*[{!:]")


def _validate_template(value: str, resolver_key: str) -> str:
    if _UNSAFE_TEMPLATE_RE.search(value):
        raise ValueError(
            f"Template contains unsafe format spec: {value!r}. Only simple {{placeholder}} tokens are permitted."
        )
    found = frozenset(_PLACEHOLDER_RE.findall(value))
    allowed = _ALLOWED_PLACEHOLDERS.get(resolver_key, frozenset())
    unknown = found - allowed
    if unknown:
        raise ValueError(
            f"Template {value!r} contains unknown placeholders {unknown}. Allowed for {resolver_key!r}: {allowed}."
        )
    return value


# ---------------------------------------------------------------------------
# Resolver config models
# ---------------------------------------------------------------------------


class DbSourceTableRowConfig(BaseModel):
    """Row-level resolver for a DB table identified by principal_id."""

    resolver_type: Literal[ResolverType.db_source_table_row] = ResolverType.db_source_table_row
    source_template: str

    @field_validator("source_template")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_template(v, "db_source_table_row")


class S3ImageResolverConfig(BaseModel):
    """S3-hosted image resolver using bucket and key templates."""

    resolver_type: Literal[ResolverType.s3_image] = ResolverType.s3_image
    bucket_template: str
    key_template: str

    @field_validator("bucket_template", "key_template")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_template(v, "s3_image")


class HttpImageResolverConfig(BaseModel):
    """HTTP-hosted image resolver using base URL and path templates."""

    resolver_type: Literal[ResolverType.http_image] = ResolverType.http_image
    base_url_template: str
    path_template: str

    @field_validator("base_url_template", "path_template")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_template(v, "http_image")


class FsspecPageXmlResolverConfig(BaseModel):
    """Fsspec-addressable PAGE-XML document resolver."""

    resolver_type: Literal[ResolverType.fsspec_pagexml] = ResolverType.fsspec_pagexml
    path_template: str

    @field_validator("path_template")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_template(v, "fsspec_pagexml")


class FsspecImageResolverConfig(BaseModel):
    """Fsspec-addressable image resolver."""

    resolver_type: Literal[ResolverType.fsspec_image] = ResolverType.fsspec_image
    path_template: str

    @field_validator("path_template")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_template(v, "fsspec_image")


class S3TableResolverConfig(BaseModel):
    """S3-hosted tabular data resolver (e.g. Parquet/CSV authority tables)."""

    resolver_type: Literal[ResolverType.s3_table] = ResolverType.s3_table
    bucket_template: str
    key_template: str

    @field_validator("bucket_template", "key_template")
    @classmethod
    def _validate(cls, v: str) -> str:
        return _validate_template(v, "s3_table")


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

ResolverConfig = Annotated[
    DbSourceTableRowConfig
    | S3ImageResolverConfig
    | HttpImageResolverConfig
    | FsspecPageXmlResolverConfig
    | FsspecImageResolverConfig
    | S3TableResolverConfig,
    Field(discriminator="resolver_type"),
]
