"""CRUD service for simplified annotation entities."""

import uuid

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from people_gator_api.schemas.entities import DescriptionCreateRequest
from people_gator_api.schemas.entities import DescriptionResponse
from people_gator_api.schemas.entities import DocumentMentionCreateRequest
from people_gator_api.schemas.entities import DocumentMentionResponse
from people_gator_api.schemas.entities import FaceCreateRequest
from people_gator_api.schemas.entities import FaceResponse
from people_gator_api.schemas.entities import InformationCreateRequest
from people_gator_api.schemas.entities import InformationResponse
from people_gator_api.schemas.entities import MentionCreateRequest
from people_gator_api.schemas.entities import MentionResponse
from people_gator_api.schemas.entities import NameCreateRequest
from people_gator_api.schemas.entities import NameResponse
from people_gator_api.services.vector_service.schema import DESCRIPTION_COLLECTION
from people_gator_api.services.vector_service.schema import DOCUMENT_MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import DOCUMENT_MENTION_INFORMATION_VECTOR
from people_gator_api.services.vector_service.schema import DOCUMENT_MENTION_NAME_VECTOR
from people_gator_api.services.vector_service.schema import FACE_COLLECTION
from people_gator_api.services.vector_service.schema import INFORMATION_COLLECTION
from people_gator_api.services.vector_service.schema import MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import NAME_COLLECTION
from people_gator_api.services.weaviate_utils import combine_filters
from people_gator_api.services.weaviate_utils import description_response
from people_gator_api.services.weaviate_utils import document_mention_response
from people_gator_api.services.weaviate_utils import face_response
from people_gator_api.services.weaviate_utils import fetch_by_id
from people_gator_api.services.weaviate_utils import information_response
from people_gator_api.services.weaviate_utils import mention_response
from people_gator_api.services.weaviate_utils import name_response
from people_gator_api.services.weaviate_utils import refresh_entity_aggregates
from people_gator_api.services.weaviate_utils import require_document_mention
from people_gator_api.services.weaviate_utils import upsert
from people_gator_api.utils.uuid_utils import new_uuid6


async def create_mention(
    client: WeaviateAsyncClient,
    payload: MentionCreateRequest,
) -> MentionResponse:
    await require_document_mention(client, payload.document_mention_id)
    mention_id = new_uuid6()
    polygons = (
        [
            {
                "points": [{"x": point.x, "y": point.y} for point in polygon.points]
            }
            for polygon in payload.polygons
        ]
        if payload.polygons is not None
        else None
    )
    await upsert(
        client,
        MENTION_COLLECTION,
        mention_id,
        properties={
            "mention_id": mention_id,
            "text": payload.text,
            "offset_start": payload.offset_start,
            "offset_end": payload.offset_end,
            "polygons": polygons,
            "confidence": payload.confidence,
            "document_mention_id": payload.document_mention_id,
            "source_id": payload.source_id,
            "model_agent_id": payload.model_agent_id,
            "embedding": payload.embedding,
            "model_identifier": payload.model_identifier,
        },
        references={
            "document_mention": payload.document_mention_id,
            "source": payload.source_id,
            "model_agent": payload.model_agent_id,
        },
        vector=payload.embedding,
    )
    document_mention = await get_document_mention(client, payload.document_mention_id)
    assert document_mention is not None
    await refresh_entity_aggregates(client, document_mention.entity_id)
    return MentionResponse(
        mention_id=mention_id,
        text=payload.text,
        document_mention_id=payload.document_mention_id,
        source_id=payload.source_id,
        offset_start=payload.offset_start,
        offset_end=payload.offset_end,
        polygons=payload.polygons,
        model_agent_id=payload.model_agent_id,
        confidence=payload.confidence,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )


async def get_mention(
    client: WeaviateAsyncClient,
    mention_id: uuid.UUID,
) -> MentionResponse | None:
    obj = await fetch_by_id(client, MENTION_COLLECTION, "mention_id", mention_id)
    if obj is None:
        return None
    return mention_response(obj.properties)


async def list_mentions(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[MentionResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[object] = []
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    response = await client.collections.get(MENTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    items = sorted(
        [mention_response(item.properties) for item in response.objects],
        key=lambda item: item.mention_id,
    )
    if after_id is not None:
        items = [item for item in items if item.mention_id > after_id]
    return items[:limit]


async def create_information(
    client: WeaviateAsyncClient,
    payload: InformationCreateRequest,
) -> InformationResponse:
    document_mention = await require_document_mention(client, payload.document_mention_id)
    information_id = new_uuid6()
    await upsert(
        client,
        INFORMATION_COLLECTION,
        information_id,
        properties={
            "information_id": information_id,
            "text": payload.text,
            "document_mention_id": payload.document_mention_id,
            "source_id": payload.source_id,
            "model_agent_id": payload.model_agent_id,
            "embedding": payload.embedding,
            "model_identifier": payload.model_identifier,
        },
        references={
            "document_mention": payload.document_mention_id,
            "source": payload.source_id,
            "model_agent": payload.model_agent_id,
        },
        vector=payload.embedding,
    )
    await refresh_entity_aggregates(client, document_mention.entity_id)
    return InformationResponse(
        information_id=information_id,
        text=payload.text,
        document_mention_id=payload.document_mention_id,
        source_id=payload.source_id,
        model_agent_id=payload.model_agent_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )


async def get_information(
    client: WeaviateAsyncClient,
    information_id: uuid.UUID,
) -> InformationResponse | None:
    obj = await fetch_by_id(client, INFORMATION_COLLECTION, "information_id", information_id)
    if obj is None:
        return None
    return information_response(obj.properties)


async def list_information(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[InformationResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[object] = []
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    response = await client.collections.get(INFORMATION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    items = sorted(
        [information_response(item.properties) for item in response.objects],
        key=lambda item: item.information_id,
    )
    if after_id is not None:
        items = [item for item in items if item.information_id > after_id]
    return items[:limit]


async def create_document_mention(
    client: WeaviateAsyncClient,
    payload: DocumentMentionCreateRequest,
) -> DocumentMentionResponse:
    document_mention_id = new_uuid6()
    await upsert(
        client,
        DOCUMENT_MENTION_COLLECTION,
        document_mention_id,
        properties={
            "document_mention_id": document_mention_id,
            "name": payload.name,
            "information": payload.information,
            "model_agent_id": payload.model_agent_id,
            "source_id": payload.source_id,
            "entity_id": payload.entity_id,
            "embedding": payload.embedding,
            "model_identifier": payload.model_identifier,
        },
        references={
            "entity": payload.entity_id,
            "source": payload.source_id,
            "model_agent": payload.model_agent_id,
        },
        vector={
            DOCUMENT_MENTION_NAME_VECTOR: payload.embedding or [],
            DOCUMENT_MENTION_INFORMATION_VECTOR: payload.embedding or [],
        }
        if payload.embedding is not None
        else {},
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return DocumentMentionResponse(
        document_mention_id=document_mention_id,
        name=payload.name,
        information=payload.information,
        model_agent_id=payload.model_agent_id,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )


async def get_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> DocumentMentionResponse | None:
    obj = await fetch_by_id(
        client,
        DOCUMENT_MENTION_COLLECTION,
        "document_mention_id",
        document_mention_id,
    )
    if obj is None:
        return None
    return document_mention_response(obj.properties)


async def list_document_mentions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DocumentMentionResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[object] = []
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    response = await client.collections.get(DOCUMENT_MENTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    items = sorted(
        [document_mention_response(item.properties) for item in response.objects],
        key=lambda item: item.document_mention_id,
    )
    if after_id is not None:
        items = [item for item in items if item.document_mention_id > after_id]
    return items[:limit]


async def create_face(
    client: WeaviateAsyncClient,
    payload: FaceCreateRequest,
) -> FaceResponse:
    detection_id = new_uuid6()
    await upsert(
        client,
        FACE_COLLECTION,
        detection_id,
        properties={
            "detection_id": detection_id,
            "bounding_box": {
                "x": payload.bounding_box.x,
                "y": payload.bounding_box.y,
                "width": payload.bounding_box.width,
                "height": payload.bounding_box.height,
            },
            "keypoints": [
                {"type": item.type, "x": item.x, "y": item.y}
                for item in payload.keypoints
            ],
            "confidence": payload.confidence,
            "source_id": payload.source_id,
            "model_agent_id": payload.model_agent_id,
            "entity_id": payload.entity_id,
            "embedding": payload.embedding,
            "model_identifier": payload.model_identifier,
        },
        references={
            "entity": payload.entity_id,
            "source": payload.source_id,
            "model_agent": payload.model_agent_id,
        },
        vector=payload.embedding,
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return FaceResponse(
        detection_id=detection_id,
        source_id=payload.source_id,
        bounding_box=payload.bounding_box,
        keypoints=payload.keypoints,
        model_agent_id=payload.model_agent_id,
        entity_id=payload.entity_id,
        confidence=payload.confidence,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )


async def get_face(
    client: WeaviateAsyncClient,
    detection_id: uuid.UUID,
) -> FaceResponse | None:
    obj = await fetch_by_id(client, FACE_COLLECTION, "detection_id", detection_id)
    if obj is None:
        return None
    return face_response(obj.properties)


async def list_faces(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[FaceResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[object] = []
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    response = await client.collections.get(FACE_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    items = sorted(
        [face_response(item.properties) for item in response.objects],
        key=lambda item: item.detection_id,
    )
    if after_id is not None:
        items = [item for item in items if item.detection_id > after_id]
    return items[:limit]


async def create_description(
    client: WeaviateAsyncClient,
    payload: DescriptionCreateRequest,
) -> DescriptionResponse:
    description_id = new_uuid6()
    await upsert(
        client,
        DESCRIPTION_COLLECTION,
        description_id,
        properties={
            "description_id": description_id,
            "text": payload.text,
            "language": payload.language,
            "source_id": payload.source_id,
            "entity_id": payload.entity_id,
            "embedding": payload.embedding,
            "model_identifier": payload.model_identifier,
        },
        references={"entity": payload.entity_id, "source": payload.source_id},
        vector=payload.embedding,
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return DescriptionResponse(
        description_id=description_id,
        text=payload.text,
        language=payload.language,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )


async def get_description(
    client: WeaviateAsyncClient,
    description_id: uuid.UUID,
) -> DescriptionResponse | None:
    obj = await fetch_by_id(client, DESCRIPTION_COLLECTION, "description_id", description_id)
    if obj is None:
        return None
    return description_response(obj.properties)


async def list_descriptions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DescriptionResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[object] = []
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    response = await client.collections.get(DESCRIPTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    items = sorted(
        [description_response(item.properties) for item in response.objects],
        key=lambda item: item.description_id,
    )
    if after_id is not None:
        items = [item for item in items if item.description_id > after_id]
    return items[:limit]


async def create_name(
    client: WeaviateAsyncClient,
    payload: NameCreateRequest,
) -> NameResponse:
    name_id = new_uuid6()
    await upsert(
        client,
        NAME_COLLECTION,
        name_id,
        properties={
            "name_id": name_id,
            "name": payload.name,
            "source_id": payload.source_id,
            "entity_id": payload.entity_id,
            "embedding": payload.embedding,
            "model_identifier": payload.model_identifier,
        },
        references={"entity": payload.entity_id, "source": payload.source_id},
        vector=payload.embedding,
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return NameResponse(
        name_id=name_id,
        name=payload.name,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
        embedding=payload.embedding,
        model_identifier=payload.model_identifier,
    )


async def get_name(
    client: WeaviateAsyncClient,
    name_id: uuid.UUID,
) -> NameResponse | None:
    obj = await fetch_by_id(client, NAME_COLLECTION, "name_id", name_id)
    if obj is None:
        return None
    return name_response(obj.properties)


async def list_names(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[NameResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[object] = []
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    response = await client.collections.get(NAME_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    items = sorted(
        [name_response(item.properties) for item in response.objects],
        key=lambda item: item.name_id,
    )
    if after_id is not None:
        items = [item for item in items if item.name_id > after_id]
    return items[:limit]
