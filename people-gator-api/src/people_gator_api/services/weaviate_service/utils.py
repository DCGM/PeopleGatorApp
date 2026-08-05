"""Shared Weaviate CRUD helpers and response mappers."""

from __future__ import annotations

from collections import Counter
from collections.abc import (
    Mapping,
    Sequence,
)
import json
import uuid
from typing import cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import (
    WeaviateField,
    WeaviateProperties,
)
from weaviate.collections.classes.internal import (
    CrossReferences,
    ReferenceInputs
)

type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

from people_gator_api.schemas.enums import (
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
from people_gator_api.schemas.principals import PrincipalResponse
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    NlcrAuthoritySourceMetadata,
    PageSourceMetadata,
    SourceResponse,
    WikidataSourceMetadata,
    WikimediaImageSourceMetadata,
)
from people_gator_api.services.weaviate_service.db_schema import (
    DOCUMENT_MENTION_COLLECTION,
    FACE_COLLECTION,
    PAGE_MENTION_COLLECTION,
)

async def upsert(
    client: WeaviateAsyncClient,
    collection_name: str,
    object_uuid: uuid.UUID,
    *,
    properties: WeaviateProperties,
    references: ReferenceInputs | None = None,
    vector: dict[str, list[float]] | None = None,
) -> None:
    collection = client.collections.get(collection_name)
    exists = await collection.data.exists(object_uuid)
    if not exists:
        await collection.data.insert(
            uuid=object_uuid,
            properties=properties,
            references=references,
            vector=vector,
        )
        return
    await collection.data.replace(
        uuid=object_uuid,
        properties=properties,
        references=references,
        vector=vector,
    )

def reference_id_filter(link_on: str, reference_id: uuid.UUID) -> FilterReturn:
    return Filter.by_ref(link_on=link_on).by_id().equal(reference_id)

def empty_reference_queries(link_ons: Sequence[str]) -> list[QueryReference]:
    return [
        QueryReference(link_on=link_on, return_properties=[])
        for link_on in link_ons
    ]

async def list_faces_for_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[FaceResponse]:
    faces = client.collections.get(FACE_COLLECTION)
    response = await faces.query.fetch_objects(
        filters=reference_id_filter(link_on="entity", reference_id=entity_id),
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    results = sorted(
        [face_response(item.properties, item.references, item.uuid) for item in response.objects],
        key=lambda item: item.detection_id,
    )
    return results

async def list_document_mentions_for_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[DocumentMentionResponse]:
    document_mentions = client.collections.get(DOCUMENT_MENTION_COLLECTION)
    response = await document_mentions.query.fetch_objects(
        filters=reference_id_filter(link_on="entity", reference_id=entity_id),
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    results = sorted(
        [document_mention_response(item.properties, item.references, item.uuid) for item in response.objects],
        key=lambda item: item.document_mention_id,
    )
    return results

async def list_page_mentions_for_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> list[PageMentionResponse]:
    page_mentions = client.collections.get(PAGE_MENTION_COLLECTION)
    response = await page_mentions.query.fetch_objects(
        filters=reference_id_filter(link_on="document_mention", reference_id=document_mention_id),
        return_references=empty_reference_queries(["principal", "document_mention", "source"]),
    )
    results = sorted(
        [page_mention_response(item.properties, item.references, item.uuid) for item in response.objects],
        key=lambda item: item.page_mention_id,
    )
    return results

async def delete_document_mention_tree(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> None:
    page_mentions = client.collections.get(PAGE_MENTION_COLLECTION)
    await page_mentions.data.delete_many(
        where=reference_id_filter(
            link_on="document_mention",
            reference_id=document_mention_id,
        ),
    )
    return None

def combine_filters(filters: list[FilterReturn]) -> FilterReturn | None:
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return Filter.all_of(filters)


def single_named_vector_payload(
    vector_name: str,
    embedding: list[float] | None,
) -> dict[str, list[float]] | None:
    if embedding is None:
        return None
    return {vector_name: embedding}

def most_common_normalized(values: Sequence[str | None]) -> str | None:
    normalized = [
        " ".join(value.split()).strip().lower()
        for value in values
        if value is not None
    ]
    filtered = [value for value in normalized if value]
    if not filtered:
        return None
    counts = Counter(filtered)
    return counts.most_common(1)[0][0]


def principal_response(
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


def source_response(
    properties: WeaviateProperties,
    references: CrossReferences,
    uuid: uuid.UUID,
) -> SourceResponse:
    source_type = SourceKind(require_str(properties, "source_type"))
    metadata = optional_json_dict(properties, "metadata")
    metadata_model_by_source_type: dict[SourceKind, type] = {
        SourceKind.page: PageSourceMetadata,
        SourceKind.document: DocumentSourceMetadata,
        SourceKind.wikidata: WikidataSourceMetadata,
        SourceKind.wikimedia: WikimediaImageSourceMetadata,
        SourceKind.nlcr: NlcrAuthoritySourceMetadata,
        SourceKind.obalkyknih: DocumentSourceMetadata,
    }
    resolved_metadata = (
        metadata_model_by_source_type[source_type](**metadata)
        if metadata is not None
        else None
    )
    return SourceResponse(
        source_id=uuid,
        source_type=source_type,
        uri=require_str(properties, "uri"),
        metadata=resolved_metadata,
    )


def entity_response(
    properties: WeaviateProperties,
    references: CrossReferences,
    uuid: uuid.UUID,
) -> EntityResponse:
    return EntityResponse(
        entity_id=uuid,
        principal_id=require_reference_uuid(references, "principal"),
        entity_type=optional_str(properties, "entity_type"),
        name=optional_str(properties, "name"),
        description=optional_str(properties, "description"),
        short_description=optional_str(properties, "short_description"),
        aliases=[require_str(alias, "alias") for alias in sequence_of_mappings(properties, "aliases")],
        wikidata_id=optional_str(properties, "wikidata_id"),
        nlcr_authority_id=optional_str(properties, "nlcr_authority_id"),
    )


def page_mention_response(
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
        aliases=[require_str(alias, "alias") for alias in sequence_of_mappings(properties, "aliases")],
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


def document_mention_response(
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
        aliases=[require_str(alias, "alias") for alias in sequence_of_mappings(properties, "aliases")],
    )


def face_response(
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
        return json_dict_from_mapping(raw_value)
    if isinstance(raw_value, str):
        decoded = json.loads(raw_value)
        if isinstance(decoded, Mapping):
            return json_dict_from_mapping(cast(Mapping[str, WeaviateField], decoded))
        raise TypeError(f"Property {key!r} is not a JSON object.")
    raise TypeError(f"Property {key!r} is not an object.")


def json_dict_from_mapping(value_map: Mapping[str, WeaviateField]) -> dict[str, JsonValue]:
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
