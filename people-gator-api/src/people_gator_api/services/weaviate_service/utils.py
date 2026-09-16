"""Shared Weaviate CRUD helpers and response mappers."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import (
    Mapping,
    Sequence,
)
import json
import logging
import uuid
from typing import Protocol, cast

from pydantic import AnyUrl
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import (
    WeaviateField,
    WeaviateProperties,
)
from weaviate.collections.classes.internal import CrossReferences

from people_gator_api.schemas.enums import (
    EntityType,
    PrincipalType,
    SourceKind,
)
from people_gator_api.schemas.entities import (
    BoundingBox,
    DocumentMentionResponse,
    EntityResponse,
    FaceKeypoint,
    FaceResponse,
    PageMentionResponse,
    Polygon,
    PolygonPoint,
)
from people_gator_api.schemas.principals import (
    ModelAgentResponse,
    PrincipalResponse,
    UserResponse,
)
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    PageSourceMetadata,
    SourceResponse,
)
from people_gator_api.utils.opentelemetry import trace

type JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


logger = logging.getLogger(__name__)


class _CollectionQueryObject(Protocol):
    properties: WeaviateProperties
    references: CrossReferences
    uuid: uuid.UUID


async def fetch_collection_object(
    client: WeaviateAsyncClient,
    collection_name: str,
    object_id: uuid.UUID,
    *,
    reference_names: Sequence[str] = (),
) -> _CollectionQueryObject | None:
    """Fetch one object with a consistent missing-object and reference contract."""
    response = await client.collections.get(collection_name).query.fetch_object_by_id(
        object_id,
        return_references=empty_reference_queries(reference_names),
    )
    return cast(_CollectionQueryObject | None, response)


def reference_id_filter(link_on: str, reference_id: uuid.UUID) -> FilterReturn:
    return Filter.by_ref(link_on=link_on).by_id().equal(reference_id)


def empty_reference_queries(link_ons: Sequence[str]) -> list[QueryReference]:
    return [
        QueryReference(link_on=link_on, return_properties=[]) for link_on in link_ons
    ]


def combine_filters(filters: list[FilterReturn]) -> FilterReturn | None:
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return Filter.all_of(filters)


@trace()
async def fetch_collection_page_with_total_count(
    client: WeaviateAsyncClient,
    collection_name: str,
    *,
    filters: FilterReturn | None,
    limit: int,
    return_references: Sequence[QueryReference],
    after_id: uuid.UUID | None,
) -> tuple[list[_CollectionQueryObject], int]:
    collection = client.collections.get(collection_name)
    if limit < 0:
        raise ValueError("limit must be greater than or equal to 0")

    aggregate_coroutine = collection.aggregate.over_all(
        total_count=True,
        filters=filters,
    )
    if limit > 0:
        fetch_coroutine = collection.query.fetch_objects(
            filters=filters,
            limit=limit,
            return_references=list(return_references),
            after=after_id,
        )
        fetch_response, aggregate_response = await asyncio.gather(
            fetch_coroutine,
            aggregate_coroutine,
        )
        fetch_objects = list(fetch_response.objects)
    else:
        aggregate_response = await aggregate_coroutine
        fetch_objects: list[_CollectionQueryObject] = []
    total_count_value = aggregate_response.total_count
    total_count = (
        total_count_value if isinstance(total_count_value, int) else len(fetch_objects)
    )
    return fetch_objects, total_count


def single_named_vector_payload(
    vector_name: str,
    embedding: list[float] | None,
) -> dict[str, list[float]] | None:
    if embedding is None:
        return None
    return {vector_name: embedding}


def most_common_normalized(values: Sequence[str | None]) -> str | None:
    normalized = [
        " ".join(value.split()).strip().lower() for value in values if value is not None
    ]
    filtered = [value for value in normalized if value]
    if not filtered:
        return None
    counts = Counter(filtered)
    return counts.most_common(1)[0][0]


# -------------------------------------------------------
# Weaviate property accessors and response mappers
# -------------------------------------------------------


def parse_principal(
    properties: WeaviateProperties,
    references: CrossReferences,
    uuid: uuid.UUID,
) -> PrincipalResponse:
    return PrincipalResponse(
        principal_id=uuid,
        principal_type=PrincipalType(require_str(properties, "principal_type")),
        display_name=require_str(properties, "display_name"),
        is_active=require_bool(properties, "is_active"),
    )


def parse_user(
    properties: WeaviateProperties,
    references: CrossReferences,
    uuid: uuid.UUID,
) -> UserResponse:
    return UserResponse(
        principal_id=uuid,
        principal_type=PrincipalType(require_str(properties, "principal_type")),
        display_name=require_str(properties, "display_name"),
        is_active=require_bool(properties, "is_active"),
        external_subject=require_str(properties, "external_subject"),
        external_issuer=require_str(properties, "external_issuer"),
        email=optional_str(properties, "email"),
    )


def parse_model_agent(
    properties: WeaviateProperties,
    references: CrossReferences,
    uuid: uuid.UUID,
) -> ModelAgentResponse:
    return ModelAgentResponse(
        principal_id=uuid,
        principal_type=PrincipalType(require_str(properties, "principal_type")),
        display_name=require_str(properties, "display_name"),
        is_active=require_bool(properties, "is_active"),
        model_slug=require_str(properties, "model_slug"),
        model_version=require_str(properties, "model_version"),
    )


def parse_source(
    properties: WeaviateProperties,
    references: CrossReferences,
    uuid: uuid.UUID,
) -> SourceResponse:
    source_type = SourceKind(require_str(properties, "source_type"))
    uri = require_str(properties, "uri")
    library = optional_str(properties, "library")
    document = properties.get("document")
    page = properties.get("page")
    resolved_metadata = None
    if source_type == SourceKind.page:
        if library is None or document is None or page is None:
            raise KeyError("Page source is missing its flat archive identity fields.")
        resolved_metadata = PageSourceMetadata(
            library=library,
            document=_as_uuid(document, "document"),
            page=_as_uuid(page, "page"),
            kramerius_url=AnyUrl(uri),
        )
    elif source_type == SourceKind.document:
        if library is None or document is None:
            raise KeyError("Document source is missing its flat archive identity fields.")
        resolved_metadata = DocumentSourceMetadata(
            library=library,
            document=_as_uuid(document, "document"),
            kramerius_url=AnyUrl(uri),
        )
    logger.debug(
        "Mapping source response",
        extra={
            "source_id": str(uuid),
            "source_type": source_type.value,
            "has_metadata": resolved_metadata is not None,
        },
    )
    return SourceResponse(
        source_id=uuid,
        source_type=source_type,
        uri=uri,
        metadata=resolved_metadata,
    )


def _as_uuid(value_: WeaviateField, property_name: str) -> uuid.UUID:
    if isinstance(value_, uuid.UUID):
        return value_
    if isinstance(value_, str):
        return uuid.UUID(value_)
    raise TypeError(f"Property {property_name!r} is not a UUID.")


def parse_entity(
    properties: WeaviateProperties,
    references: CrossReferences,
    uuid: uuid.UUID,
) -> EntityResponse:
    return EntityResponse(
        entity_id=uuid,
        principal_id=require_reference_uuid(references, "principal"),
        entity_type=optional_entity_type(properties, "entity_type"),
        name=optional_str(properties, "name"),
        description=optional_str(properties, "description"),
        short_description=optional_str(properties, "short_description"),
        aliases=require_alias_text_array(properties, "aliases"),
        wikidata_id=optional_str(properties, "wikidata_id"),
        nlcr_authority_id=optional_str(properties, "nlcr_authority_id"),
    )


def parse_page_mention(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    references: CrossReferences,
    uuid: uuid.UUID,
) -> PageMentionResponse:
    return PageMentionResponse(
        page_mention_id=uuid,
        document_mention_id=require_reference_uuid(references, "document_mention"),
        source_id=require_reference_uuid(references, "source"),
        principal_id=require_reference_uuid(references, "principal"),
        name=require_str(properties, "name"),
        aliases=require_alias_text_array(properties, "aliases"),
        information=require_str(properties, "information"),
        polygons=[
            Polygon(
                points=[
                    PolygonPoint(
                        x=require_number(point, "x"),
                        y=require_number(point, "y"),
                    )
                    for point in sequence_of_mappings(polygon, "points")
                ]
            )
            for polygon in sequence_of_mappings(properties, "polygons")
        ],
    )


def parse_document_mention(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    references: CrossReferences,
    uuid: uuid.UUID,
) -> DocumentMentionResponse:
    return DocumentMentionResponse(
        document_mention_id=uuid,
        principal_id=require_reference_uuid(references, "principal"),
        source_id=require_reference_uuid(references, "source"),
        entity_id=require_reference_uuid(references, "entity"),
        name=require_str(properties, "name"),
        information=require_str(properties, "information"),
        aliases=require_alias_text_array(properties, "aliases"),
    )


def parse_face(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    references: CrossReferences,
    uuid: uuid.UUID,
) -> FaceResponse:
    bounding_box = mapping_value(properties, "bounding_box")
    keypoints = sequence_of_mappings(properties, "keypoints")
    return FaceResponse(
        detection_id=uuid,
        principal_id=require_reference_uuid(references, "principal"),
        entity_id=require_reference_uuid(references, "entity"),
        source_id=require_reference_uuid(references, "source"),
        bounding_box=BoundingBox(
            x=require_int(bounding_box, "x"),
            y=require_int(bounding_box, "y"),
            width=require_int(bounding_box, "width"),
            height=require_int(bounding_box, "height"),
        ),
        keypoints=[
            FaceKeypoint(
                type=require_str(item, "type"),
                x=require_number(item, "x"),
                y=require_number(item, "y"),
            )
            for item in keypoints
        ],
        confidence=require_float(properties, "confidence"),
    )


# -------------------------------------------------------
# Weaviate property accessors and response mappers
# -------------------------------------------------------


def require_reference_uuid(
    references: CrossReferences,
    key: str,
) -> uuid.UUID:
    if key not in references:
        raise KeyError(f"Missing reference {key!r}.")
    linked_objects = references[key].objects
    if not linked_objects:
        raise KeyError(f"Reference {key!r} has no linked objects.")
    return linked_objects[0].uuid


def value(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> WeaviateField:
    if key not in properties:
        raise KeyError(f"Missing property {key!r}.")
    return properties[key]


def require_uuid(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> uuid.UUID:
    raw_value = value(properties, key)
    if isinstance(raw_value, uuid.UUID):
        return raw_value
    if isinstance(raw_value, str):
        return uuid.UUID(raw_value)
    raise TypeError(f"Property {key!r} is not a UUID.")


def require_str(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> str:
    raw_value = value(properties, key)
    if isinstance(raw_value, str):
        return raw_value
    raise TypeError(f"Property {key!r} is not a string.")


def optional_str(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> str | None:
    raw_value = properties.get(key)
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        return raw_value
    raise TypeError(f"Property {key!r} is not a string.")


def require_bool(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> bool:
    raw_value = value(properties, key)
    if isinstance(raw_value, bool):
        return raw_value
    raise TypeError(f"Property {key!r} is not a bool.")


def require_int(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> int:
    raw_value = value(properties, key)
    if isinstance(raw_value, int) and not isinstance(raw_value, bool):
        return raw_value
    raise TypeError(f"Property {key!r} is not an int.")


def require_float(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> float:
    raw_value = value(properties, key)
    if isinstance(raw_value, int) and not isinstance(raw_value, bool):
        return float(raw_value)
    if isinstance(raw_value, float):
        return raw_value
    raise TypeError(f"Property {key!r} is not a float.")


def require_number(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> float:
    return require_float(properties, key)


def mapping_value(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> Mapping[str, WeaviateField]:
    raw_value = value(properties, key)
    if isinstance(raw_value, Mapping):
        return raw_value
    raise TypeError(f"Property {key!r} is not an object.")


def sequence_of_mappings(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> list[Mapping[str, WeaviateField]]:
    raw_value = value(properties, key)
    return as_mapping_sequence(raw_value, key)


def optional_sequence_of_mappings(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> list[Mapping[str, WeaviateField]]:
    raw_value = properties.get(key)
    if raw_value is None:
        return []
    return as_mapping_sequence(raw_value, key)


def require_alias_text_array(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> list[str]:
    raw_value = value(properties, key)
    return as_alias_text_array(raw_value, key)


def optional_alias_text_array(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> list[str]:
    raw_value = properties.get(key)
    if raw_value is None:
        return []
    return as_alias_text_array(raw_value, key)


def optional_entity_type(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    field_name: str,
) -> EntityType | None:
    raw_value = optional_str(properties, field_name)
    if raw_value is None:
        return None
    return EntityType(raw_value)


def as_alias_text_array(raw_value: WeaviateField, key: str) -> list[str]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise TypeError(f"Property {key!r} is not a text array.")

    aliases: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            raise TypeError(f"Property {key!r} contains a non-string alias item.")
        aliases.append(item)
    return aliases


def as_mapping_sequence(
    raw_value: WeaviateField,
    key: str,
) -> list[Mapping[str, WeaviateField]]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise TypeError(f"Property {key!r} is not an object sequence.")
    mappings: list[Mapping[str, WeaviateField]] = []
    for item in raw_value:
        if not isinstance(item, Mapping):
            raise TypeError(f"Property {key!r} contains a non-object item.")
        mappings.append(item)
    return mappings


def optional_json_dict(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> dict[str, JsonValue] | None:
    raw_value = properties.get(key)
    if raw_value is None:
        return None
    if isinstance(raw_value, Mapping):
        logger.debug("Property already a JSON mapping", extra={"property": key})
        return json_dict_from_mapping(raw_value)
    if isinstance(raw_value, str):
        logger.debug("Decoding JSON string property", extra={"property": key})
        decoded = json.loads(raw_value)
        if isinstance(decoded, Mapping):
            return json_dict_from_mapping(cast(Mapping[str, WeaviateField], decoded))
        raise TypeError(f"Property {key!r} is not a JSON object.")
    raise TypeError(f"Property {key!r} is not an object.")


def json_dict_from_mapping(
    value_map: Mapping[str, WeaviateField],
) -> dict[str, JsonValue]:
    return {key: json_value(item) for key, item in value_map.items()}


def json_value(raw_value: WeaviateField) -> JsonValue:
    if raw_value is None or isinstance(raw_value, (str, int, float, bool)):
        return raw_value
    if isinstance(raw_value, uuid.UUID):
        return str(raw_value)
    if isinstance(raw_value, Mapping):
        return json_dict_from_mapping(raw_value)
    if isinstance(raw_value, Sequence) and not isinstance(raw_value, (str, bytes)):
        return [json_value(item) for item in raw_value]
    raise TypeError("Unsupported JSON-compatible value.")
