"""Readable BM25 search helpers for Entity records."""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)
from typing import cast
from uuid import UUID

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import MetadataQuery
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import WeaviateField

from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.search import EntitySearchResult
from people_gator_api.services.weaviate_service.db_schema import ENTITY_COLLECTION
from people_gator_api.services.weaviate_service.utils import optional_str

_DEFAULT_LIMIT = 20


async def search_entities_by_name_or_aliases(
    client: WeaviateAsyncClient,
    query_name: list[str],
    *,
    filters: FilterReturn | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[EntitySearchResult]:
    """Search Entity documents with BM25 across name and aliases."""
    cleaned_name = ", ".join(query_name).strip()
    if not cleaned_name:
        return []

    response = await client.collections.get(ENTITY_COLLECTION).query.bm25(
        query=cleaned_name,
        query_properties=["name", "aliases"],
        filters=filters,
        limit=limit,
        return_metadata=MetadataQuery(score=True),
    )
    return [_entity_object_to_result(obj) for obj in response.objects]


def _entity_object_to_result(
    entity_object: object,
) -> EntitySearchResult:
    object_uuid = getattr(entity_object, "uuid")
    raw_properties = getattr(entity_object, "properties")
    metadata = getattr(entity_object, "metadata", None)

    properties = _as_weaviate_properties(raw_properties)

    return EntitySearchResult(
        entity_id=_field_to_uuid(object_uuid),
        entity_type=_optional_entity_type(properties),
        name=optional_str(properties, "name") or "",
        description=optional_str(properties, "description") or "",
        short_description=optional_str(properties, "short_description") or "",
        aliases=_optional_alias_text_array(properties),
        matching_score=_metadata_score(metadata),
    )


def _as_weaviate_properties(raw_properties: object) -> dict[str, WeaviateField]:
    if not isinstance(raw_properties, Mapping):
        raise TypeError("Expected mapping-like properties from Weaviate object.")

    # We validated Mapping at runtime; values come from Weaviate property payloads.
    mapping = cast(Mapping[object, WeaviateField], raw_properties)
    properties: dict[str, WeaviateField] = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise TypeError("Weaviate property names must be strings.")
        properties[key] = value
    return properties


def _optional_entity_type(
    properties: Mapping[str, WeaviateField],
) -> EntityType | None:
    raw_value = optional_str(properties, "entity_type")
    if raw_value is None:
        return None
    return EntityType(raw_value)


def _optional_alias_text_array(properties: Mapping[str, WeaviateField]) -> list[str]:
    raw_value = properties.get("aliases")
    if raw_value is None:
        return []
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise TypeError("Property 'aliases' is not a text array.")

    aliases: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            raise TypeError("Property 'aliases' contains a non-string alias item.")
        aliases.append(item)
    return aliases


def _field_to_uuid(value: WeaviateField | None) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise TypeError("Expected UUID-compatible field value.")


def _metadata_score(metadata: object | None) -> float:
    if metadata is None:
        return 0.0
    score_value = getattr(metadata, "score", None)
    if isinstance(score_value, (int, float)):
        return float(score_value)
    return 0.0
