"""Shared Weaviate CRUD helpers and response mappers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import uuid
from typing import Protocol, cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import WeaviateField
from weaviate.collections.classes.types import WeaviateProperties

from people_gator_api.schemas.enums import PrincipalType
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.entities import BoundingBox
from people_gator_api.schemas.entities import DescriptionResponse
from people_gator_api.schemas.entities import DocumentMentionResponse
from people_gator_api.schemas.entities import EntityNameResponse
from people_gator_api.schemas.entities import EntityResponse
from people_gator_api.schemas.entities import FaceKeypoint
from people_gator_api.schemas.entities import FaceResponse
from people_gator_api.schemas.entities import PageMentionResponse
from people_gator_api.schemas.entities import Polygon
from people_gator_api.schemas.entities import PolygonPoint
from people_gator_api.schemas.entities import SpanResponse
from people_gator_api.schemas.principals import PrincipalResponse
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    NlcrAuthoritySourceMetadata,
    PageSourceMetadata,
    SourceResponse,
    WikidataSourceMetadata,
    WikimediaImageSourceMetadata,
)
from people_gator_api.services.vector_service.schema import DESCRIPTION_COLLECTION
from people_gator_api.services.vector_service.schema import DOCUMENT_MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import ENTITY_COLLECTION
from people_gator_api.services.vector_service.schema import ENTITY_NAME_COLLECTION
from people_gator_api.services.vector_service.schema import FACE_COLLECTION
from people_gator_api.services.vector_service.schema import PAGE_MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import PRINCIPAL_COLLECTION
from people_gator_api.services.vector_service.schema import SOURCE_COLLECTION
from people_gator_api.services.vector_service.schema import SPAN_COLLECTION

type MutableProperties = dict[str, WeaviateField]
type ReferenceMap = dict[str, uuid.UUID]
type VectorPayload = list[float] | dict[str, list[float]]
type JsonValue = (
    str
    | int
    | float
    | bool
    | None
    | dict[str, "JsonValue"]
    | list["JsonValue"]
)


class WeaviateObjectLike(Protocol):
    uuid: uuid.UUID
    properties: Mapping[str, WeaviateField]
    vector: list[float] | Mapping[str, object] | None
    metadata: object | None


@dataclass(slots=True, frozen=True)
class StoredPrincipal:
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    is_active: bool


@dataclass(slots=True, frozen=True)
class StoredUser(StoredPrincipal):
    external_subject: str
    external_issuer: str
    email: str | None


@dataclass(slots=True, frozen=True)
class StoredObject:
    object_uuid: uuid.UUID
    properties: Mapping[str, WeaviateField]


async def fetch_by_id(
    client: WeaviateAsyncClient,
    collection_name: str,
    id_property: str,
    object_id: uuid.UUID,
) -> StoredObject | None:
    return await fetch_single(
        client,
        collection_name,
        Filter.by_property(id_property).equal(str(object_id)),
    )


async def fetch_single(
    client: WeaviateAsyncClient,
    collection_name: str,
    filters: FilterReturn,
) -> StoredObject | None:
    response = await client.collections.get(collection_name).query.fetch_objects(
        filters=filters,
        limit=1,
    )
    objects = query_objects(response)
    if not objects:
        return None
    item = objects[0]
    return StoredObject(object_uuid=item.uuid, properties=item.properties)


async def upsert(
    client: WeaviateAsyncClient,
    collection_name: str,
    object_uuid: uuid.UUID,
    *,
    properties: MutableProperties,
    references: ReferenceMap | None = None,
    vector: VectorPayload | None = None,
) -> None:
    collection = client.collections.get(collection_name)
    id_property = collection_id_property(collection_name)
    current = await fetch_by_id(client, collection_name, id_property, object_uuid)
    if current is None:
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


async def require_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> DocumentMentionResponse:
    obj = await fetch_by_id(
        client,
        DOCUMENT_MENTION_COLLECTION,
        "document_mention_id",
        document_mention_id,
    )
    if obj is None:
        raise ValueError(f"Document mention {document_mention_id} does not exist.")
    return document_mention_response(obj.properties)


async def require_page_mention(
    client: WeaviateAsyncClient,
    page_mention_id: uuid.UUID,
) -> PageMentionResponse:
    obj = await fetch_by_id(
        client,
        PAGE_MENTION_COLLECTION,
        "page_mention_id",
        page_mention_id,
    )
    if obj is None:
        raise ValueError(f"Page mention {page_mention_id} does not exist.")
    return page_mention_response(obj.properties)


async def list_page_mentions_for_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> list[PageMentionResponse]:
    response = await client.collections.get(PAGE_MENTION_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("document_mention_id").equal(str(document_mention_id)),
        limit=1000,
    )
    objects = query_objects(response)
    return sorted(
        [page_mention_response(item.properties) for item in objects],
        key=lambda item: item.page_mention_id,
    )


async def list_spans_for_page_mention(
    client: WeaviateAsyncClient,
    page_mention_id: uuid.UUID,
) -> list[SpanResponse]:
    response = await client.collections.get(SPAN_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("page_mention_id").equal(str(page_mention_id)),
        limit=1000,
    )
    objects = query_objects(response)
    return sorted(
        [span_response(item.properties) for item in objects],
        key=lambda item: item.span_id,
    )


async def delete_document_mention_tree(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> None:
    page_mentions = await list_page_mentions_for_document_mention(client, document_mention_id)
    for page_mention in page_mentions:
        spans = await list_spans_for_page_mention(client, page_mention.page_mention_id)
        for span in spans:
            await client.collections.get(SPAN_COLLECTION).data.delete_by_id(span.span_id)
        await client.collections.get(PAGE_MENTION_COLLECTION).data.delete_by_id(
            page_mention.page_mention_id
        )

    await client.collections.get(DOCUMENT_MENTION_COLLECTION).data.delete_by_id(
        document_mention_id
    )


async def refresh_entity_aggregates(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> None:
    entity_obj = await fetch_by_id(client, ENTITY_COLLECTION, "entity_id", entity_id)
    if entity_obj is None:
        return
    entity = entity_response(entity_obj.properties)

    entity_names = await _list_entity_names(client, entity_id)
    descriptions = await _list_descriptions(client, entity_id)
    document_mentions = await _list_document_mentions(client, entity_id)

    aggregated_names = [item.name for item in entity_names] + [
        item.name for item in document_mentions
    ]
    aggregated_descriptions = [item.text for item in descriptions] + [
        item.information for item in document_mentions
    ]

    await upsert(
        client,
        ENTITY_COLLECTION,
        entity_id,
        properties={
            "entity_id": entity.entity_id,
            "principal_id": entity.principal_id,
            "entity_type": entity.entity_type,
            "name": most_common_normalized(aggregated_names),
            "description": most_common_normalized(aggregated_descriptions),
            "wikidata_id": entity.wikidata_id,
            "nlcr_authority_id": entity.nlcr_authority_id,
        },
        references={"principal": entity.principal_id},
    )


def combine_filters(filters: list[FilterReturn]) -> FilterReturn | None:
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return Filter.all_of(filters)


def collection_id_property(collection_name: str) -> str:
    collection_to_id_property = {
        PRINCIPAL_COLLECTION: "principal_id",
        SOURCE_COLLECTION: "source_id",
        ENTITY_COLLECTION: "entity_id",
        PAGE_MENTION_COLLECTION: "page_mention_id",
        DOCUMENT_MENTION_COLLECTION: "document_mention_id",
        SPAN_COLLECTION: "span_id",
        FACE_COLLECTION: "detection_id",
        DESCRIPTION_COLLECTION: "description_id",
        ENTITY_NAME_COLLECTION: "entity_name_id",
    }
    return collection_to_id_property[collection_name]


def query_objects(response: object) -> list[WeaviateObjectLike]:
    # Weaviate response stubs don't preserve the concrete object container shape here.
    return cast(list[WeaviateObjectLike], getattr(response, "objects"))


def single_named_vector_payload(
    vector_name: str,
    embedding: list[float] | None,
) -> dict[str, list[float]] | None:
    if embedding is None:
        return None
    return {vector_name: embedding}


def dual_named_vector_payload(
    *,
    name_embedding: list[float] | None = None,
    fulltext_embedding: list[float] | None = None,
    name_vector_name: str,
    fulltext_vector_name: str,
) -> dict[str, list[float]] | None:
    payload: dict[str, list[float]] = {}
    if name_embedding is not None:
        payload[name_vector_name] = name_embedding
    if fulltext_embedding is not None:
        payload[fulltext_vector_name] = fulltext_embedding
    return payload or None


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
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> PrincipalResponse:
    return PrincipalResponse(
        principal_id=require_uuid(properties, "principal_id"),
        principal_type=PrincipalType(require_str(properties, "principal_type")),
        display_name=require_str(properties, "display_name"),
        is_active=require_bool(properties, "is_active"),
    )


def source_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> SourceResponse:
    source_type = SourceKind(require_str(properties, "source_type"))
    metadata = optional_json_dict(properties, "metadata")
    metadata_model_by_source_type: dict[SourceKind, type] = {
        SourceKind.page: PageSourceMetadata,
        SourceKind.document: DocumentSourceMetadata,
        SourceKind.wikidata: WikidataSourceMetadata,
        SourceKind.wikimedia: WikimediaImageSourceMetadata,
        SourceKind.nlcr: NlcrAuthoritySourceMetadata,
    }
    resolved_metadata = (
        metadata_model_by_source_type[source_type](**metadata)
        if metadata is not None
        else None
    )
    return SourceResponse(
        source_id=require_uuid(properties, "source_id"),
        source_type=source_type,
        uri=require_str(properties, "uri"),
        metadata=resolved_metadata,
    )


def entity_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> EntityResponse:
    return EntityResponse(
        entity_id=require_uuid(properties, "entity_id"),
        principal_id=require_uuid(properties, "principal_id"),
        entity_type=optional_str(properties, "entity_type"),
        name=optional_str(properties, "name"),
        description=optional_str(properties, "description"),
        wikidata_id=optional_str(properties, "wikidata_id"),
        nlcr_authority_id=optional_str(properties, "nlcr_authority_id"),
    )


def page_mention_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> PageMentionResponse:
    return PageMentionResponse(
        page_mention_id=require_uuid(properties, "page_mention_id"),
        name=require_str(properties, "name"),
        information=require_str(properties, "information"),
        confidence=require_float(properties, "confidence"),
        document_mention_id=require_uuid(properties, "document_mention_id"),
        source_id=require_uuid(properties, "source_id"),
        model_agent_id=require_uuid(properties, "model_agent_id"),
    )


def span_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> SpanResponse:
    polygons = sequence_of_mappings(properties, "polygons")
    return SpanResponse(
        span_id=require_uuid(properties, "span_id"),
        text=require_str(properties, "text"),
        page_mention_id=require_uuid(properties, "page_mention_id"),
        source_id=require_uuid(properties, "source_id"),
        entity_id=require_uuid(properties, "entity_id"),
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
            for polygon in polygons
        ],
    )


def document_mention_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> DocumentMentionResponse:
    return DocumentMentionResponse(
        document_mention_id=require_uuid(properties, "document_mention_id"),
        name=require_str(properties, "name"),
        information=require_str(properties, "information"),
        model_agent_id=require_uuid(properties, "model_agent_id"),
        source_id=require_uuid(properties, "source_id"),
        entity_id=require_uuid(properties, "entity_id"),
    )


def face_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> FaceResponse:
    bounding_box = mapping_value(properties, "bounding_box")
    keypoints = sequence_of_mappings(properties, "keypoints")
    return FaceResponse(
        detection_id=require_uuid(properties, "detection_id"),
        source_id=require_uuid(properties, "source_id"),
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
        model_agent_id=require_uuid(properties, "model_agent_id"),
        entity_id=require_uuid(properties, "entity_id"),
        confidence=require_float(properties, "confidence"),
    )


def description_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> DescriptionResponse:
    return DescriptionResponse(
        description_id=require_uuid(properties, "description_id"),
        text=require_str(properties, "text"),
        language=require_str(properties, "language"),
        source_id=require_uuid(properties, "source_id"),
        entity_id=require_uuid(properties, "entity_id"),
    )


def entity_name_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> EntityNameResponse:
    return EntityNameResponse(
        entity_name_id=require_uuid(properties, "entity_name_id"),
        name=require_str(properties, "name"),
        source_id=require_uuid(properties, "source_id"),
        entity_id=require_uuid(properties, "entity_id"),
    )


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


async def _list_document_mentions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[DocumentMentionResponse]:
    response = await client.collections.get(DOCUMENT_MENTION_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("entity_id").equal(str(entity_id)),
        limit=1000,
    )
    objects = query_objects(response)
    return sorted(
        [document_mention_response(item.properties) for item in objects],
        key=lambda item: item.document_mention_id,
    )


async def _list_descriptions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[DescriptionResponse]:
    response = await client.collections.get(DESCRIPTION_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("entity_id").equal(str(entity_id)),
        limit=1000,
    )
    objects = query_objects(response)
    return sorted(
        [description_response(item.properties) for item in objects],
        key=lambda item: item.description_id,
    )


async def _list_entity_names(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[EntityNameResponse]:
    response = await client.collections.get(ENTITY_NAME_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("entity_id").equal(str(entity_id)),
        limit=1000,
    )
    objects = query_objects(response)
    return sorted(
        [entity_name_response(item.properties) for item in objects],
        key=lambda item: item.entity_name_id,
    )
