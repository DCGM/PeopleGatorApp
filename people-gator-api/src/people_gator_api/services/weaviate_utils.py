"""Shared Weaviate CRUD helpers and response mappers."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import uuid
from typing import Any, cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.types import WeaviateField
from weaviate.collections.classes.types import WeaviateProperties

from people_gator_api.models.enums import AnnotationType
from people_gator_api.models.enums import PrincipalType
from people_gator_api.models.enums import SourceKind
from people_gator_api.schemas.entities import BoundingBox
from people_gator_api.schemas.entities import DescriptionResponse
from people_gator_api.schemas.entities import DocumentMentionResponse
from people_gator_api.schemas.entities import EntityResponse
from people_gator_api.schemas.entities import FaceKeypoint
from people_gator_api.schemas.entities import FaceResponse
from people_gator_api.schemas.entities import InformationResponse
from people_gator_api.schemas.entities import MentionPolygon
from people_gator_api.schemas.entities import MentionPolygonPoint
from people_gator_api.schemas.entities import MentionResponse
from people_gator_api.schemas.entities import NameResponse
from people_gator_api.schemas.principals import PrincipalResponse
from people_gator_api.schemas.sources import SourceResponse
from people_gator_api.services.vector_service.schema import DESCRIPTION_COLLECTION
from people_gator_api.services.vector_service.schema import DESCRIPTION_VECTOR
from people_gator_api.services.vector_service.schema import DOCUMENT_MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import ENTITY_COLLECTION
from people_gator_api.services.vector_service.schema import FACE_COLLECTION
from people_gator_api.services.vector_service.schema import FACE_VECTOR
from people_gator_api.services.vector_service.schema import INFORMATION_COLLECTION
from people_gator_api.services.vector_service.schema import MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import NAME_COLLECTION
from people_gator_api.services.vector_service.schema import NAME_VECTOR
from people_gator_api.services.vector_service.schema import PRINCIPAL_COLLECTION
from people_gator_api.services.vector_service.schema import SEARCH_PROFILE_COLLECTION
from people_gator_api.services.vector_service.schema import SEARCH_PROFILE_MODALITY_COLLECTION
from people_gator_api.services.vector_service.schema import SOURCE_COLLECTION

_PROFILE_MODALITY_NS = uuid.UUID("50c5b391-e4cc-4f2d-8c24-459deca56f85")

type MutableProperties = dict[str, Any]  # Third-party Weaviate nested property typing is too imprecise here.
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
    properties: WeaviateProperties


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
    filters: Any,  # Third-party Weaviate filter expression type is not exported precisely.
) -> StoredObject | None:
    response = await client.collections.get(collection_name).query.fetch_objects(
        filters=filters,
        limit=1,
    )
    if not response.objects:
        return None
    item = response.objects[0]
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


async def list_mentions_for_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> list[MentionResponse]:
    response = await client.collections.get(MENTION_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("document_mention_id").equal(str(document_mention_id)),
        limit=1000,
    )
    return sorted(
        [mention_response(item.properties) for item in response.objects],
        key=lambda item: item.mention_id,
    )


async def list_information_for_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> list[InformationResponse]:
    response = await client.collections.get(INFORMATION_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("document_mention_id").equal(str(document_mention_id)),
        limit=1000,
    )
    return sorted(
        [information_response(item.properties) for item in response.objects],
        key=lambda item: item.information_id,
    )


async def delete_document_mention_tree(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> None:
    mentions = await list_mentions_for_document_mention(client, document_mention_id)
    for mention in mentions:
        await client.collections.get(MENTION_COLLECTION).data.delete_by_id(mention.mention_id)

    information_records = await list_information_for_document_mention(client, document_mention_id)
    for information in information_records:
        await client.collections.get(INFORMATION_COLLECTION).data.delete_by_id(
            information.information_id
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

    names = await _list_names(client, entity_id)
    descriptions = await _list_descriptions(client, entity_id)
    faces = await _list_faces(client, entity_id)
    document_mentions = await _list_document_mentions(client, entity_id)

    mention_count = 0
    information_count = 0
    for document_mention in document_mentions:
        mention_count += len(
            await list_mentions_for_document_mention(client, document_mention.document_mention_id)
        )
        information_count += len(
            await list_information_for_document_mention(
                client,
                document_mention.document_mention_id,
            )
        )

    await upsert(
        client,
        ENTITY_COLLECTION,
        entity_id,
        properties={
            "entity_id": entity.entity_id,
            "principal_id": entity.principal_id,
            "name": most_common_normalized([item.name for item in names]),
            "description": most_common_normalized([item.text for item in descriptions]),
            "face_count": len(faces),
            "mention_count": mention_count,
            "information_count": information_count,
            "document_mention_count": len(document_mentions),
            "description_count": len(descriptions),
            "name_count": len(names),
        },
        references={"principal": entity.principal_id},
        vector=named_vector_payload(
            face_vector=mean_embedding([item.embedding for item in faces]),
            name_vector=mean_embedding([item.embedding for item in names]),
            description_vector=mean_embedding([item.embedding for item in descriptions]),
        ),
    )


def combine_filters(filters: list[Any]) -> Any | None:
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
        MENTION_COLLECTION: "mention_id",
        INFORMATION_COLLECTION: "information_id",
        DOCUMENT_MENTION_COLLECTION: "document_mention_id",
        FACE_COLLECTION: "detection_id",
        DESCRIPTION_COLLECTION: "description_id",
        NAME_COLLECTION: "name_id",
        SEARCH_PROFILE_COLLECTION: "profile_id",
        SEARCH_PROFILE_MODALITY_COLLECTION: "modality_id",
    }
    return collection_to_id_property[collection_name]


def profile_modality_uuid(
    profile_id: uuid.UUID,
    annotation_type: AnnotationType,
) -> uuid.UUID:
    return uuid.uuid5(_PROFILE_MODALITY_NS, f"{profile_id}:{annotation_type.value}")


def named_vector_payload(
    *,
    face_vector: list[float] | None = None,
    name_vector: list[float] | None = None,
    description_vector: list[float] | None = None,
) -> dict[str, list[float]]:
    payload: dict[str, list[float]] = {}
    if face_vector is not None:
        payload[FACE_VECTOR] = face_vector
    if name_vector is not None:
        payload[NAME_VECTOR] = name_vector
    if description_vector is not None:
        payload[DESCRIPTION_VECTOR] = description_vector
    return payload


def mean_embedding(vectors: Sequence[list[float] | None]) -> list[float] | None:
    present = [vector for vector in vectors if vector is not None]
    if not present:
        return None
    dimension = len(present[0])
    return [
        sum(vector[index] for vector in present) / len(present)
        for index in range(dimension)
    ]


def most_common_normalized(values: Sequence[str]) -> str | None:
    normalized = [" ".join(value.split()).strip().lower() for value in values]
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
    return SourceResponse(
        source_id=require_uuid(properties, "source_id"),
        source_type=SourceKind(require_str(properties, "source_type")),
        uri=require_str(properties, "uri"),
        metadata=optional_json_dict(properties, "metadata"),
    )


def entity_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> EntityResponse:
    return EntityResponse(
        entity_id=require_uuid(properties, "entity_id"),
        principal_id=require_uuid(properties, "principal_id"),
        name=optional_str(properties, "name"),
        description=optional_str(properties, "description"),
    )


def mention_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> MentionResponse:
    polygons = optional_sequence_of_mappings(properties, "polygons")
    resolved_polygons = (
        [
            MentionPolygon(
                points=[
                    MentionPolygonPoint(
                        x=require_number(point, "x"),
                        y=require_number(point, "y"),
                    )
                    for point in sequence_of_mappings(polygon, "points")
                ]
            )
            for polygon in polygons
        ]
        if polygons is not None
        else None
    )
    return MentionResponse(
        mention_id=require_uuid(properties, "mention_id"),
        text=require_str(properties, "text"),
        document_mention_id=require_uuid(properties, "document_mention_id"),
        source_id=require_uuid(properties, "source_id"),
        offset_start=require_int(properties, "offset_start"),
        offset_end=require_int(properties, "offset_end"),
        polygons=resolved_polygons,
        model_agent_id=require_uuid(properties, "model_agent_id"),
        confidence=require_float(properties, "confidence"),
        embedding=optional_float_sequence(properties, "embedding"),
        model_identifier=optional_str(properties, "model_identifier"),
    )


def information_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> InformationResponse:
    return InformationResponse(
        information_id=require_uuid(properties, "information_id"),
        text=require_str(properties, "text"),
        document_mention_id=require_uuid(properties, "document_mention_id"),
        source_id=require_uuid(properties, "source_id"),
        model_agent_id=require_uuid(properties, "model_agent_id"),
        embedding=optional_float_sequence(properties, "embedding"),
        model_identifier=optional_str(properties, "model_identifier"),
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
        embedding=optional_float_sequence(properties, "embedding"),
        model_identifier=optional_str(properties, "model_identifier"),
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
        embedding=optional_float_sequence(properties, "embedding"),
        model_identifier=optional_str(properties, "model_identifier"),
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
        embedding=optional_float_sequence(properties, "embedding"),
        model_identifier=optional_str(properties, "model_identifier"),
    )


def name_response(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
) -> NameResponse:
    return NameResponse(
        name_id=require_uuid(properties, "name_id"),
        name=require_str(properties, "name"),
        source_id=require_uuid(properties, "source_id"),
        entity_id=require_uuid(properties, "entity_id"),
        embedding=optional_float_sequence(properties, "embedding"),
        model_identifier=optional_str(properties, "model_identifier"),
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


def optional_uuid(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> uuid.UUID | None:
    raw_value = properties.get(key)
    if raw_value is None:
        return None
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


def optional_float(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> float | None:
    raw_value = properties.get(key)
    if raw_value is None:
        return None
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


def optional_float_sequence(
    properties: WeaviateProperties | Mapping[str, WeaviateField],
    key: str,
) -> list[float] | None:
    raw_value = properties.get(key)
    if raw_value is None:
        return None
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise TypeError(f"Property {key!r} is not a number sequence.")
    floats: list[float] = []
    for item in raw_value:
        if isinstance(item, int) and not isinstance(item, bool):
            floats.append(float(item))
            continue
        if isinstance(item, float):
            floats.append(item)
            continue
        raise TypeError(f"Property {key!r} contains a non-numeric item.")
    return floats


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
) -> list[Mapping[str, WeaviateField]] | None:
    raw_value = properties.get(key)
    if raw_value is None:
        return None
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
    return sorted(
        [document_mention_response(item.properties) for item in response.objects],
        key=lambda item: item.document_mention_id,
    )


async def _list_faces(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[FaceResponse]:
    response = await client.collections.get(FACE_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("entity_id").equal(str(entity_id)),
        limit=1000,
    )
    return sorted(
        [face_response(item.properties) for item in response.objects],
        key=lambda item: item.detection_id,
    )


async def _list_descriptions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[DescriptionResponse]:
    response = await client.collections.get(DESCRIPTION_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("entity_id").equal(str(entity_id)),
        limit=1000,
    )
    return sorted(
        [description_response(item.properties) for item in response.objects],
        key=lambda item: item.description_id,
    )


async def _list_names(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> list[NameResponse]:
    response = await client.collections.get(NAME_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("entity_id").equal(str(entity_id)),
        limit=1000,
    )
    return sorted(
        [name_response(item.properties) for item in response.objects],
        key=lambda item: item.name_id,
    )
